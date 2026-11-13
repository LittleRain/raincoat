// 本地 vault 读写：frontmatter、目录扫描、体检规则、摄入落盘。
// 只碰 markdown；所有相对路径都要先过 resolveInVault，避免越界读写。
import { execFile } from 'node:child_process'
import { mkdir, readdir, readFile, stat, writeFile } from 'node:fs/promises'
import { basename, dirname, extname, join, relative, resolve, sep } from 'node:path'

const INBOX_DIR = '00 Inbox'
const SKIP_DIRS = new Set(['99 archive', '附件', '.git', '.obsidian', '.trash', 'node_modules'])

export function resolveInVault(root, relPath) {
  if (typeof relPath !== 'string' || !relPath.trim()) throw Object.assign(new Error('缺少文件路径'), { status: 400 })
  const cleaned = relPath.replace(/^[/\\]+/, '')
  const full = resolve(root, cleaned)
  const rootWithSep = root.endsWith(sep) ? root : root + sep
  if (full !== root && !full.startsWith(rootWithSep)) throw Object.assign(new Error('路径越界'), { status: 400 })
  return full
}

export function relPath(root, full) {
  return relative(root, full).split(sep).join('/')
}

/** YAML 子集解析：key: value、key: [a, b]、引号包裹。frontmatter 都是扁平的，不做嵌套。 */
export function parseFrontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text)
  if (!match) return { data: null, body: text, raw: null }
  const data = {}
  for (const line of match[1].split('\n')) {
    const hit = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line.trim())
    if (!hit) continue
    const key = hit[1]
    let value = hit[2].trim()
    if (value.startsWith('[') && value.endsWith(']')) {
      data[key] = value
        .slice(1, -1)
        .split(',')
        .map((part) => part.trim().replace(/^['"]|['"]$/g, ''))
        .filter(Boolean)
      continue
    }
    data[key] = value.replace(/^['"]|['"]$/g, '')
  }
  return { data, body: text.slice(match[0].length), raw: match[1] }
}

export function buildFrontmatter(data) {
  const lines = ['---']
  for (const [key, value] of Object.entries(data)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) lines.push(`${key}: [${value.join(', ')}]`)
    else lines.push(`${key}: ${value}`)
  }
  lines.push('---', '')
  return lines.join('\n')
}

async function walk(root, dir = root, depth = 0, out = []) {
  if (depth > 6) return out
  let entries = []
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return out
  }
  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue
      await walk(root, full, depth + 1, out)
    } else if (extname(entry.name).toLowerCase() === '.md') {
      out.push(full)
    }
  }
  return out
}

export function slugify(title) {
  return String(title || '未命名')
    .replace(/[\\/:*?"<>|#^[\]]/g, ' ')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 72)
}

const DAY = 86_400_000
export function daysSince(ms) {
  if (!ms || Number.isNaN(ms)) return null
  return Math.floor((Date.now() - ms) / DAY)
}

export function formatDate(ms) {
  const date = new Date(ms || Date.now())
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function excerptOf(body, limit = 220) {
  return body
    .replace(/^#.*$/gm, ' ')
    .replace(/\[\[([^\]|]+)(\|[^\]]+)?\]\]/g, '$1')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_>`]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, limit)
}

export async function readDoc(root, rel) {
  const full = resolveInVault(root, rel)
  const text = await readFile(full, 'utf8')
  const { data, body } = parseFrontmatter(text)
  const info = await stat(full)
  return {
    path: relPath(root, full),
    title: data?.title || basename(full, '.md'),
    frontmatter: data,
    body,
    text,
    updatedAt: info.mtimeMs,
    bytes: info.size,
  }
}

// ── 摄入记录反查：远端队列只记「写没写 Inbox」，本地到底落成哪篇 raw / 摘要，
// 要靠 vault 自己说。索引按 URL 建，只读 frontmatter，30 秒过期。

const LOCAL_INDEX_TTL_MS = 30_000
const localIndexCache = new Map()

/** 一个链接可能以几种形态出现在 frontmatter 里：原样、去尾斜杠、去 hash、去 query。 */
export function urlKeys(value) {
  const text = String(value || '').trim().replace(/^["']|["']$/g, '')
  if (!text) return []
  const keys = new Set([text.replace(/\/+$/, '')])
  try {
    const parsed = new URL(text)
    parsed.hash = ''
    keys.add(parsed.toString().replace(/\/+$/, ''))
    const bare = `${parsed.origin}${parsed.pathname}`.replace(/\/+$/, '')
    keys.add(bare)
  } catch {
    // 不是标准 URL（比如只剩一个 slug）就只按原样匹配
  }
  return [...keys].filter(Boolean)
}

/** frontmatter 缺收尾 `---` 的 raw 也要能认（vault 里确实有这种文件），退化成扫描开头几 KB。 */
function urlFieldsOf(text, data) {
  if (data) return ['source_url', 'canonical_url', 'url'].map((key) => data[key]).filter(Boolean)
  const head = text.slice(0, 4000)
  const values = []
  for (const key of ['source_url', 'canonical_url', 'url']) {
    const hit = new RegExp(`^${key}:\\s*["']?([^"'\\n]+)`, 'm').exec(head)
    if (hit) values.push(hit[1].trim())
  }
  return values
}

/** 摘要里指向原文的字段有好几种写法（source / source_file / [Source: ...]），统一成 `00 raw/...`。 */
function rawRelFromRef(ref) {
  const text = String(ref || '').trim().replace(/^["']|["']$/g, '').replace(/\\/g, '/')
  if (!text) return ''
  const withPrefix = text.indexOf('00 raw/')
  if (withPrefix >= 0) return text.slice(withPrefix)
  const bare = text.indexOf('raw/')
  if (bare >= 0) return `00 ${text.slice(bare)}`
  return ''
}

/** 扫 summaries，建 raw 相对路径 → 摘要相对路径。摘要里指向原文的写法有 source / source_file / [Source: ...] 三种。 */
async function buildSummaryIndex(root) {
  const summaryBySource = new Map()
  for (const full of await walk(root, join(root, '01 wiki'))) {
    if (!/[\\/]summaries[\\/]/.test(full)) continue
    const text = await readFile(full, 'utf8').catch(() => '')
    const { data } = parseFrontmatter(text)
    const refs = ['source', 'source_file'].map((key) => rawRelFromRef(data?.[key])).filter(Boolean)
    if (!refs.length) {
      for (const hit of (text.match(/(?:00 )?raw\/(?:work|builder|acg)\/[^\n\]\)`]+?\.md/g) || []).slice(0, 3)) {
        const rel = rawRelFromRef(hit)
        if (rel) refs.push(rel)
      }
    }
    for (const rel of refs) {
      if (!summaryBySource.has(rel)) summaryBySource.set(rel, relPath(root, full))
    }
  }
  return summaryBySource
}

/** 扫 raw 与 summaries，建 URL → { raw, summary } 的映射。raw 目录不存在就返回空表。 */
export async function buildLocalIngestIndex(root) {
  const summaryBySource = await buildSummaryIndex(root)
  const map = new Map()
  for (const full of await walk(root, join(root, '00 raw'))) {
    const rel = relPath(root, full)
    const text = await readFile(full, 'utf8').catch(() => '')
    const { data } = parseFrontmatter(text)
    const summary = summaryBySource.get(rel) || null
    for (const value of urlFieldsOf(text, data)) {
      for (const key of urlKeys(value)) {
        if (!map.has(key)) map.set(key, { raw: rel, summary })
      }
    }
  }
  return map
}

/**
 * 列出「本地摄入」：vault 里带来源链接的 raw 及其摘要。
 *
 * 摄入页原来的数据源只有远端队列（live jobs + /kb/history.json），所以**没走远端队列的摄入
 * 永远不会出现在列表里**——包括 agent 直接用脚本落盘的（播客转写、批量补录）和手工整理的。
 * 这个函数把 vault 里能对上号的 raw/摘要反扫出来，页面才能把「没登记的任务」也列出来。
 *
 * 只收带 url 的：没有 url 既没法与远端任务去重，也会把灵感 / 手记混进来。
 */
export async function scanLocalIngests(root, { days = 30, limit = 40 } = {}) {
  const summaries = await buildSummaryIndex(root)
  const cutoff = Date.now() - days * 86400000
  const rows = []
  for (const full of await walk(root, join(root, '00 raw'))) {
    const rel = relPath(root, full)
    const text = await readFile(full, 'utf8').catch(() => '')
    if (!text) continue
    const { data } = parseFrontmatter(text)
    const url = ['source_url', 'canonical_url', 'url'].map((key) => data?.[key]).find(Boolean)
    if (!url) continue
    const info = await stat(full).catch(() => null)
    const ingestedAt = Date.parse(data?.ingested_at || data?.captured_at || '') || info?.mtimeMs || null
    if (ingestedAt && ingestedAt < cutoff) continue
    rows.push({
      url: String(url),
      title: data?.title || basename(full, '.md'),
      raw: rel,
      summary: summaries.get(rel) || null,
      platform: data?.platform || null,
      space: /^00 raw\/([^/]+)\//.exec(rel)?.[1] || null,
      ingestedAt,
    })
  }
  rows.sort((a, b) => (b.ingestedAt || 0) - (a.ingestedAt || 0))
  return rows.slice(0, limit)
}

/** 返回 lookup(url) → { raw, summary } | null；同进程内复用 30 秒。 */
export async function localIngestIndex(root, { ttl = LOCAL_INDEX_TTL_MS } = {}) {
  const cached = localIndexCache.get(root)
  if (cached && Date.now() - cached.at < ttl) return cached.lookup
  const map = await buildLocalIngestIndex(root)
  const lookup = (url) => {
    for (const key of urlKeys(url)) {
      const hit = map.get(key)
      if (hit) return hit
    }
    return null
  }
  localIndexCache.set(root, { at: Date.now(), lookup })
  return lookup
}

export async function listInbox(root) {
  const dir = join(root, INBOX_DIR)
  const files = await walk(root, dir)
  const out = []
  for (const full of files) {
    const text = await readFile(full, 'utf8').catch(() => '')
    if (!text) continue
    const { data, body } = parseFrontmatter(text)
    const info = await stat(full).catch(() => null)
    const captured = Date.parse(data?.captured_at || '') || info?.mtimeMs || null
    out.push({
      path: relPath(root, full),
      title: data?.title || basename(full, '.md'),
      url: data?.url || data?.source_url || null,
      source: data?.source || data?.ingest_mode || (data?.source_url ? 'web' : null),
      triage: data?.triage || null,
      capturedAt: captured,
      ageDays: daysSince(captured),
      excerpt: excerptOf(body),
    })
  }
  return out.sort((a, b) => (b.capturedAt || 0) - (a.capturedAt || 0))
}

function spaceOf(rel) {
  const hit = /^01 wiki\/([^/]+)\//.exec(rel)
  return hit ? hit[1] : null
}

function typeOf(rel) {
  const hit = /^01 wiki\/[^/]+\/([^/]+)\//.exec(rel)
  return hit ? hit[1].replace(/s$/, '') : rel.startsWith('00 raw/') ? 'raw' : null
}

export async function recentDocs(root, { days = 30, limit = 40, material = false } = {}) {
  const files = await walk(root)
  const since = Date.now() - days * DAY
  const rows = []
  for (const full of files) {
    const rel = relPath(root, full)
    if (rel.startsWith(INBOX_DIR)) continue
    if (!/^(01 wiki|00 raw)\//.test(rel)) continue
    if (material) {
      // 创作素材只要「沉淀下来的内容」：raw 原文、summary、concept。
      // 索引页、操作日志、周报/日报这些是元信息，拿来选题只会写出对策。
      if (!/^(00 raw\/|01 wiki\/[^/]+\/(concepts|entities|summaries)\/)/.test(rel)) continue
      if (/\/(_?index|log|README)\.md$/i.test(rel) || /\/(weekly|daily|monthly)\//i.test(rel)) continue
    }
    const info = await stat(full).catch(() => null)
    if (!info || info.mtimeMs < since) continue
    rows.push({ rel, full, mtime: info.mtimeMs })
  }
  rows.sort((a, b) => b.mtime - a.mtime)
  const out = []
  for (const row of rows.slice(0, limit)) {
    const text = await readFile(row.full, 'utf8').catch(() => '')
    const { data, body } = parseFrontmatter(text)
    out.push({
      path: row.rel,
      title: data?.title || basename(row.rel, '.md'),
      space: spaceOf(row.rel),
      type: typeOf(row.rel),
      status: data?.status || null,
      updatedAt: row.mtime,
      excerpt: excerptOf(body, 160),
    })
  }
  return out
}

/** 在 vault 里按关键词找相关页，给学习模式当「与我已知的什么冲突」的素材。 */
export async function searchVault(root, query, limit = 5) {
  const terms = [...new Set(
    String(query || '')
      .toLowerCase()
      .split(/[^a-z0-9\u4e00-\u9fa5]+/)
      .filter((word) => word.length >= 2 && !/^(the|and|for|with|this|that|from|一?个|我们|什么|怎么)$/.test(word)),
  )].slice(0, 8)
  if (!terms.length) return []
  const files = (await walk(root)).filter((full) => /^(01 wiki|00 raw)\//.test(relPath(root, full)))
  const scored = []
  for (const full of files) {
    const text = await readFile(full, 'utf8').catch(() => '')
    if (!text) continue
    const lower = text.toLowerCase()
    let score = 0
    for (const term of terms) {
      const hits = lower.split(term).length - 1
      score += hits
    }
    if (!score) continue
    const { data, body } = parseFrontmatter(text)
    scored.push({
      path: relPath(root, full),
      title: data?.title || basename(full, '.md'),
      space: spaceOf(relPath(root, full)),
      excerpt: excerptOf(body, 260),
      score,
    })
  }
  return scored.sort((a, b) => b.score - a.score).slice(0, limit)
}

function gitStatus(root) {
  return new Promise((resolvePromise) => {
    execFile('git', ['-C', root, 'status', '--porcelain'], { timeout: 5000 }, (error, stdout) => {
      if (error) return resolvePromise({ ok: false, dirty: null, error: error.message.split('\n')[0] })
      const lines = String(stdout || '').split('\n').filter(Boolean)
      resolvePromise({ ok: true, dirty: lines.length, files: lines.slice(0, 6).map((line) => line.slice(3)) })
    })
  })
}


function git(root, args, timeout = 20_000) {
  return new Promise((resolvePromise) => {
    execFile('git', ['-C', root, ...args], { timeout }, (error, stdout, stderr) => {
      resolvePromise({ ok: !error, stdout: String(stdout || '').trim(), stderr: String(stderr || error?.message || '').trim() })
    })
  })
}

/** 本地 clone 与 origin 的差距：worker 在远端 push，本地不 pull 就看不到新文件。 */
export async function gitOverview(root, { fetch = false } = {}) {
  if (fetch) await git(root, ['fetch', '--quiet'], 25_000)
  const branch = await git(root, ['rev-parse', '--abbrev-ref', 'HEAD'])
  const behind = await git(root, ['rev-list', '--count', 'HEAD..@{u}'])
  const ahead = await git(root, ['rev-list', '--count', '@{u}..HEAD'])
  const status = await git(root, ['status', '--porcelain'])
  const last = await git(root, ['log', '-1', '--format=%h%x09%s%x09%ct'])
  const [hash = '', subject = '', at = ''] = last.stdout.split('\t')
  return {
    ok: branch.ok,
    branch: branch.stdout || null,
    upstream: branch.ok,
    behind: Number(behind.stdout || 0),
    ahead: Number(ahead.stdout || 0),
    dirty: status.ok ? status.stdout.split('\n').filter(Boolean).length : null,
    lastCommit: hash ? { hash, subject, at: Number(at) * 1000 } : null,
    error: branch.ok ? null : branch.stderr.split('\n')[0],
  }
}

/** 只做 fast-forward；本地有改动或分叉时不强来，把原因交回界面。 */
export async function pullVault(root) {
  const before = await gitOverview(root)
  if (!before.ok) return { ok: false, message: before.error || '不是 git 仓库' }
  if (before.dirty) return { ok: false, message: `本地有 ${before.dirty} 个未提交改动，先处理再拉`, behind: before.behind }
  const pull = await git(root, ['pull', '--ff-only', '--quiet'], 60_000)
  const after = await gitOverview(root)
  return {
    ok: pull.ok,
    message: pull.ok ? (before.behind ? `已拉取 ${before.behind} 个提交` : '已是最新') : pull.stderr.split('\n').slice(-2).join(' '),
    behind: after.behind,
    ahead: after.ahead,
  }
}

/**
 * 体检：把 vault/AGENTS.md 里的硬规则落成可执行的检查。
 * 每条 issue 都带 level/category/file，界面按级别分组，报告按类别分节。
 */
export async function healthCheck(root, settings, ingest) {
  const issues = []
  const add = (level, category, title, detail, file = null, extra = {}) => {
    issues.push({ level, category, title, detail, file, ...extra })
  }
  const files = await walk(root)
  const docs = []
  const linkIndex = new Map()

  for (const full of files) {
    const rel = relPath(root, full)
    const text = await readFile(full, 'utf8').catch(() => '')
    if (!text) continue
    const { data, body } = parseFrontmatter(text)
    docs.push({ rel, data, body, text })
    for (const hit of body.matchAll(/\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]/g)) {
      const key = hit[1].trim()
      linkIndex.set(key, (linkIndex.get(key) || 0) + 1)
    }
  }

  const docByRel = new Map(docs.map((doc) => [doc.rel, doc]))
  const titleIndex = new Map(docs.map((doc) => [doc.data?.title || basename(doc.rel, '.md'), doc.rel]))

  function outboundOf(doc) {
    const targets = new Set()
    for (const hit of doc.body.matchAll(/\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]/g)) {
      const key = hit[1].trim()
      const rel = titleIndex.get(key) || [...titleIndex.entries()].find(([title]) => title === basename(key, '.md'))?.[1]
      if (rel) targets.add(rel)
    }
    return targets.size
  }

  function inboundOf(doc) {
    const name = doc.data?.title || basename(doc.rel, '.md')
    return linkIndex.get(name) || linkIndex.get(basename(doc.rel, '.md')) || 0
  }

  // 1) Inbox 待整理
  const inbox = docs.filter((doc) => doc.rel.startsWith(`${INBOX_DIR}/`))
  for (const doc of inbox) {
    const captured = Date.parse(doc.data?.captured_at || '') || null
    const age = daysSince(captured)
    const level = age === null ? 'yellow' : age >= settings.inboxDangerDays ? 'red' : age >= settings.inboxWarnDays ? 'yellow' : 'blue'
    add(level, 'inbox', doc.data?.title || basename(doc.rel, '.md'), `Inbox 待 triage${age === null ? '' : `，已停留 ${age} 天`}`, doc.rel, { ageDays: age })
  }

  // 2) frontmatter 缺失
  // 00 raw 是不可变正文，缺 frontmatter 修不了，只汇总一句；01 wiki/*/raw/ 是历史导入，跳过。
  const rawMissing = []
  for (const doc of docs) {
    const rel = doc.rel
    if (rel.startsWith('99 archive/')) continue
    if (/^01 wiki\/[^/]+\/raw\//.test(rel)) continue
    if (/(^|\/)(templates?|SCHEMA|README)\.md$/i.test(rel) || /\/(templates?)\//.test(rel)) continue
    if (/\/(_?index|log)\.md$/.test(rel)) continue
    if (!doc.data) {
      if (rel.startsWith('00 raw/')) {
        rawMissing.push(rel)
        continue
      }
      if (rel.startsWith('01 wiki/')) {
        add('red', 'frontmatter', basename(rel, '.md'), '缺少 frontmatter（title/source 等字段无法被索引）', rel)
      }
      continue
    }
    if (rel.startsWith('01 wiki/')) {
      const missing = ['title', 'type', 'space'].filter((key) => !doc.data[key])
      if (missing.length) add('yellow', 'frontmatter', doc.data.title || basename(rel, '.md'), `wiki 页缺少字段：${missing.join('、')}`, rel)
    }
    if (rel.startsWith('00 raw/')) {
      const missing = ['title', 'source'].filter((key) => !doc.data?.[key])
      if (missing.length) rawMissing.push(rel)
    }
  }
  if (rawMissing.length) {
    add('blue', 'frontmatter', `${rawMissing.length} 篇 00 raw 缺 frontmatter`, `raw 是不可变正文，缺字段不影响索引；示例：${rawMissing.slice(0, 3).join('、')}`, rawMissing[0])
  }

  // 3) 连接度：概念页/实体页要 ≥2 条连接；summary 没入链只算待处理，且不逐条刷屏。
  const orphanSummaries = []
  for (const doc of docs) {
    const concept = /^01 wiki\/[^/]+\/(concepts|entities)\//.test(doc.rel)
    const summary = /^01 wiki\/[^/]+\/summaries\//.test(doc.rel)
    if (!concept && !summary) continue
    const outbound = outboundOf(doc)
    const inbound = inboundOf(doc)
    const total = outbound + inbound
    if (total >= 2) continue
    if (summary) {
      orphanSummaries.push(doc)
      continue
    }
    add(total === 0 ? 'red' : 'yellow', 'links', doc.data?.title || basename(doc.rel, '.md'), `入链 ${inbound} / 出链 ${outbound}，概念页要求至少 2 条连接`, doc.rel)
  }
  if (orphanSummaries.length) {
    const bySpace = new Map()
    for (const doc of orphanSummaries) {
      const space = doc.rel.split('/')[2] || 'unknown'
      bySpace.set(space, (bySpace.get(space) || 0) + 1)
    }
    const detail = [...bySpace.entries()].map(([space, count]) => `${space} ${count} 篇`).join('、')
    add('yellow', 'links', `${orphanSummaries.length} 篇 summary 没有任何连接`, `${detail}；摘要应至少被一个概念页引用，或被它引用的概念页反向链接`, orphanSummaries[0]?.rel || null)
  }

  // 4) 待确认与矛盾
  for (const doc of docs) {
    const lines = doc.text.split('\n')
    lines.forEach((line, index) => {
      if (line.includes('⚠️ 待确认')) add('yellow', 'open-questions', doc.data?.title || basename(doc.rel, '.md'), line.replace(/[>*\s]+/g, ' ').trim().slice(0, 160), doc.rel, { line: index + 1 })
      if (/^>\s*CONTRADICTION/i.test(line.trim())) {
        const text = line.replace(/^>\s*/, '').trim()
        const body = text
          .replace(/^CONTRADICTION/i, '')
          .replace(/^[（(]待核[）)]/, '')
          .replace(/^[:：]/, '')
          .trim()
        // 模板占位（[old claim] vs [new claim]）和空记录不是真矛盾
        const meaningful = body.replace(/[^\u4e00-\u9fa5A-Za-z0-9]/g, '').length
        const placeholder = /\[(old|new) claim\]/i.test(text) || meaningful < 8
        if (!placeholder) add('red', 'contradiction', doc.data?.title || basename(doc.rel, '.md'), text.slice(0, 200), doc.rel, { line: index + 1 })
      }
    })
  }

  // 5) Open Threads 过期
  for (const doc of docs) {
    const match = /(^|\n)##\s*Open Threads\s*\n([\s\S]*?)(\n##\s|$)/i.exec(doc.body)
    if (!match) continue
    for (const line of match[2].split('\n')) {
      if (!/^\s*[-*]\s+/.test(line)) continue
      const dateHit = /(20\d{2})-(\d{2})-(\d{2})/.exec(line)
      if (!dateHit) continue
      const age = daysSince(Date.parse(`${dateHit[1]}-${dateHit[2]}-${dateHit[3]}`))
      if (age === null || age < settings.threadWarnDays) continue
      add(age >= settings.threadDangerDays ? 'red' : 'yellow', 'threads', doc.data?.title || basename(doc.rel, '.md'), `${line.replace(/^\s*[-*]\s+/, '').slice(0, 140)}（${age} 天未推进）`, doc.rel, { ageDays: age })
    }
  }

  // 6) wiki 页长期未更新
  for (const doc of docs) {
    if (!/^01 wiki\/[^/]+\//.test(doc.rel)) continue
    const stamp = Date.parse(doc.data?.last_updated || doc.data?.updated || '')
    if (!stamp) continue
    const age = daysSince(stamp)
    if (age !== null && age >= settings.stalePageDays) {
      add('blue', 'stale', doc.data?.title || basename(doc.rel, '.md'), `last_updated 距今 ${age} 天`, doc.rel, { ageDays: age })
    }
  }

  // 7) log.md 断更
  const logDoc = docByRel.get('01 wiki/log.md')
  if (logDoc) {
    const dates = [...logDoc.body.matchAll(/^##\s*\[(20\d{2})-(\d{2})-(\d{2})\]/gm)].map((hit) => Date.parse(`${hit[1]}-${hit[2]}-${hit[3]}`))
    const latest = dates.filter((value) => !Number.isNaN(value)).sort((a, b) => b - a)[0]
    const age = daysSince(latest)
    if (age !== null && age > settings.logStaleDays) {
      add(age > settings.logStaleDays * 2 ? 'yellow' : 'blue', 'log', '操作日志停更', `log.md 最后一条记录在 ${age} 天前`, '01 wiki/log.md', { ageDays: age })
    }
  }

  // 8) vault 未提交改动会直接卡住远端 worker
  const git = await gitStatus(root)
  if (git.ok && git.dirty) {
    add('red', 'pipeline', 'vault 有未提交改动', `${git.dirty} 个文件未提交，远端 worker 会以 "vault has uncommitted changes" 失败；${git.files.join('、')}${git.dirty > git.files.length ? ' 等' : ''}`, null)
  }

  // 8b) 本地落后 origin：worker 在远端提交，不 pull 就看不到新摄入的文件
  const overview = await gitOverview(root)
  if (overview.ok && overview.behind > 0) {
    add(
      overview.behind > 10 ? 'yellow' : 'blue',
      'pipeline',
      `本地落后 origin ${overview.behind} 个提交`,
      'worker 抓完直接 push 到远端，本地 clone 不 pull 就看不到新文件；在摄入页点「拉取」或运行 git pull --ff-only',
      null,
    )
  }

  // 9) 摄入服务：失败任务与积压
  let stats = null
  try {
    stats = await ingest.stats()
    if (stats.failed > 0) {
      const failed = await ingest.jobs('failed', 5)
      add('yellow', 'pipeline', `摄入服务有 ${stats.failed} 个失败任务`, failed.jobs[0]?.error || '打开摄入页查看失败原因', null)
    }
    if (stats.queued > 0 && stats.oldestQueuedAt) {
      const waitMin = Math.round((Date.now() - stats.oldestQueuedAt) / 60000)
      if (waitMin > 30) add('yellow', 'pipeline', '队列有积压', `${stats.queued} 个任务在排队，最早已等待 ${waitMin} 分钟`, null)
    }
  } catch (error) {
    add('blue', 'pipeline', '摄入服务不可达', error?.message || String(error), null)
  }

  const counts = { red: 0, yellow: 0, blue: 0 }
  for (const issue of issues) counts[issue.level] += 1
  return {
    generatedAt: Date.now(),
    root,
    files: docs.length,
    counts,
    total: issues.length,
    stats,
    git: { ok: git.ok, dirty: git.dirty ?? null, behind: overview.ok ? overview.behind : null },
    issues: issues.sort((a, b) => ({ red: 0, yellow: 1, blue: 2 }[a.level] - { red: 0, yellow: 1, blue: 2 }[b.level])),
  }
}

export async function writeHealthReport(root, result) {
  const date = formatDate(result.generatedAt)
  const rel = `02 outputs/health/health-check-${date}.md`
  const full = resolveInVault(root, rel)
  await mkdir(dirname(full), { recursive: true })
  const labels = { red: '🔴 必须处理', yellow: '🟡 待处理', blue: '🔵 建议关注' }
  const categories = { inbox: 'Inbox 待整理', frontmatter: 'frontmatter', links: '连接度', 'open-questions': '待确认', contradiction: '矛盾', threads: 'Open Threads', stale: '长期未更新', log: '操作日志', pipeline: '摄入链路' }
  const lines = [
    buildFrontmatter({ title: `知识库体检 ${date}`, type: 'health', date, generated_by: 'raincoat-kb-desk' }).trim(),
    '',
    `# 知识库体检 ${date}`,
    '',
    `扫描 ${result.files} 个文件：🔴 ${result.counts.red} · 🟡 ${result.counts.yellow} · 🔵 ${result.counts.blue}`,
    '',
  ]
  for (const level of ['red', 'yellow', 'blue']) {
    const rows = result.issues.filter((issue) => issue.level === level)
    if (!rows.length) continue
    lines.push(`## ${labels[level]}`, '')
    const byCategory = new Map()
    for (const row of rows) {
      if (!byCategory.has(row.category)) byCategory.set(row.category, [])
      byCategory.get(row.category).push(row)
    }
    for (const [category, items] of byCategory) {
      lines.push(`### ${categories[category] || category}`, '')
      for (const item of items) {
        lines.push(`- **${item.title}** — ${item.detail}${item.file ? ` \`${item.file}\`${item.line ? `:${item.line}` : ''}` : ''}`)
      }
      lines.push('')
    }
  }
  await writeFile(full, `${lines.join('\n').trim()}\n`, 'utf8')
  return { path: rel, url: null }
}

/** 新建 Inbox 文档：走和远端 worker 一样的落盘规则，交给 triage 流程。 */
export async function writeInboxDoc(root, { title, url, source = 'learning', body, tags = [], author, publishedAt, mode = 'learning' }) {
  const now = Date.now()
  const date = formatDate(now)
  const [year, month, day] = date.split('-')
  const dirRel = `${INBOX_DIR}/${year}/${month}/${day}`
  await mkdir(resolveInVault(root, dirRel), { recursive: true })
  let slug = slugify(title)
  let rel = `${dirRel}/${slug}.md`
  let attempt = 2
  while (true) {
    try {
      await stat(resolveInVault(root, rel))
      rel = `${dirRel}/${slug}-${attempt}.md`
      attempt += 1
    } catch {
      break
    }
  }
  const frontmatter = buildFrontmatter({
    title: title || slug,
    source,
    url: url || '',
    author: author || '',
    captured_at: new Date(now).toISOString(),
    published_at: publishedAt || '',
    ingest_mode: mode,
    triage: 'pending',
    tags,
  })
  const full = resolveInVault(root, rel)
  await writeFile(full, `${frontmatter}${body.trim()}\n`, 'utf8')
  return { path: rel, title: title || slug }
}

export async function writeDraft(root, { title, platform, body }) {
  const date = formatDate(Date.now())
  const rel = `02 outputs/drafts/${date}-${slugify(title)}.md`
  const full = resolveInVault(root, rel)
  await mkdir(dirname(full), { recursive: true })
  await writeFile(full, `${buildFrontmatter({ title, type: 'draft', platform, date, status: 'draft' })}${body.trim()}\n`, 'utf8')
  return { path: rel }
}
