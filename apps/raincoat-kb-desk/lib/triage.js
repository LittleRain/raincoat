// Inbox → raw → summary → concept 的整理流水。Hermes 退役后由这里接管。
// 原则：模型只出「提案」，落盘由本地代码按 vault 规范机械执行；不整页重写既有页面。
import { mkdir, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises'
import { execFile } from 'node:child_process'
import { basename, join, relative, sep } from 'node:path'
import { buildFrontmatter, parseFrontmatter, readDoc, relPath, resolveInVault, slugify } from './vault.js'
import { callModel, parseJsonLoose } from './ai.js'

const SPACE_NAMES = { work: '工作', builder: 'Builder', acg: '二次元行业', family: '家庭' }

async function exists(path) {
  try {
    await stat(path)
    return true
  } catch {
    return false
  }
}

async function listFiles(dir, filter = () => true) {
  const out = []
  let entries
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return out
  }
  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue
    const full = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...(await listFiles(full, filter)))
    else if (entry.isFile() && entry.name.endsWith('.md') && filter(full)) out.push(full)
  }
  return out
}

function stripMd(rel) {
  return rel.replace(/\.md$/, '')
}

/** 找同 space 下已有的摘要：先比 slug，再比标题（同一篇重投时模型可能换个 slug）。 */
async function findExistingSummary(root, space, slug, title) {
  const dir = join(root, '01 wiki', space, 'summaries')
  let names = []
  try {
    names = await readdir(dir)
  } catch {
    return null
  }
  const hit = names.find((name) => name.endsWith(`-${slug}.md`))
  const pick = (name) => {
    const match = /^S-(\d+)-/.exec(name)
    return { id: match ? Number(match[1]) : 0, path: `01 wiki/${space}/summaries/${name}` }
  }
  if (hit) return pick(hit)
  const norm = (value) => String(value || '').toLowerCase().replace(/[\s\p{P}\p{S}]/gu, '')
  const target = norm(title)
  if (!target) return null
  for (const name of names) {
    if (!name.endsWith('.md')) continue
    const text = await readFile(join(dir, name), 'utf8').catch(() => '')
    const { data } = parseFrontmatter(text)
    if (norm(data?.title).includes(target) || target.includes(norm(data?.title))) return pick(name)
  }
  return null
}

/** 全库最大 summary 编号，例如 S-2067 → 2067。 */
async function maxSummaryId(root) {
  let max = 0
  for (const space of Object.keys(SPACE_NAMES)) {
    const files = await listFiles(join(root, '01 wiki', space, 'summaries'))
    for (const file of files) {
      const hit = /^S-(\d+)/.exec(basename(file))
      if (hit) max = Math.max(max, Number(hit[1]))
    }
  }
  return max
}

/** 给模型看的知识库现状：空间、既有概念页、最近摘要标题。 */
export async function vaultContext(root) {
  const spaces = []
  for (const space of Object.keys(SPACE_NAMES)) {
    const conceptFiles = await listFiles(join(root, '01 wiki', space, 'concepts'))
    const concepts = await Promise.all(conceptFiles.map(async (file) => ({
      path: relPath(root, file),
      title: parseFrontmatter(await readFile(file, 'utf8')).data?.title || basename(file, '.md'),
    })))
    const summaries = (await listFiles(join(root, '01 wiki', space, 'summaries')))
      .map((file) => basename(file, '.md'))
      .sort()
      .slice(-12)
    spaces.push({ space, label: SPACE_NAMES[space], concepts, recentSummaries: summaries })
  }
  return spaces
}

const TRIAGE_SYSTEM = [
  '你是个人知识库的整理者。知识库规范：raw 不可变；summary 必须标注来源；概念页只做增量补充，不重写；每个判断都要能指回原文。',
  '输出严格 JSON，不要解释、不要代码块围栏。',
  '字段：decision（raw=值得长期沉淀 / idea=只是个灵感 / drop=不值得留）、space（work|builder|acg|family）、title、slug（英文小写连字符或拼音，≤6 词）、reason（一句话说明为什么这样判）。',
  'summary：{ tldr（2 句以内）、keyPoints（3–5 条，每条一句事实或判断）、judgement（1–2 句你的判断，必须区分事实与推断）、openQuestions（0–3 条，没把握就少写）}。',
  'concepts：数组，逐条给出对既有概念页的增量。action=update 时 path 必须取自给定列表；action=create 时给 title。字段：{ action, path?, title?, section（State|Assessment|Open Threads 之一）, heading（一句话小标题）, text（2–4 句，必须引用原文可核对的事实）, openThreads（0–2 条） }。',
  '不许编造：原文没有的数字、身份、融资额一律不写；不确定的写在 openQuestions 里并注明「未核实」。',
  '如果原文只是转载或信息量很低，decision 用 idea 或 drop，summary 从简。',
].join('\n')

export function triageUserPrompt({ inbox, body, spaces }) {
  const catalog = spaces
    .map((space) => `- ${space.space}（${space.label}）概念页：\n${space.concepts.map((c) => `  · ${c.path} — ${c.title}`).join('\n') || '  · （暂无）'}\n  最近摘要：${space.recentSummaries.join('、') || '（暂无）'}`)
    .join('\n')
  return [
    `标题：${inbox.title || '（无标题）'}`,
    `来源：${inbox.frontmatter?.source_url || inbox.frontmatter?.url || '（未知）'}`,
    `抓取时间：${inbox.frontmatter?.captured_at || '（未知）'}`,
    '',
    '知识库现状：',
    catalog,
    '',
    '待整理内容：',
    String(body).slice(0, 14000),
  ].join('\n')
}

export async function proposeTriage(ctx, root, relInbox) {
  const doc = await readDoc(root, relInbox)
  const spaces = await vaultContext(root)
  const { text } = await callModel(ctx, {
    system: TRIAGE_SYSTEM,
    messages: [{ role: 'user', content: triageUserPrompt({ inbox: { title: doc.title, frontmatter: doc.frontmatter }, body: doc.body, spaces }) }],
    maxTokens: 2600,
  })
  const parsed = parseJsonLoose(text)
  if (!parsed) throw Object.assign(new Error('模型没有返回可解析的整理提案'), { status: 502 })
  if (!SPACE_NAMES[parsed.space]) parsed.space = 'builder'
  if (!['raw', 'idea', 'drop'].includes(parsed.decision)) parsed.decision = 'raw'
  parsed.slug = slugify(parsed.slug || parsed.title || doc.title)
  parsed.concepts = Array.isArray(parsed.concepts) ? parsed.concepts.slice(0, 4) : []
  parsed.summary = parsed.summary || {}
  parsed.summary.keyPoints = Array.isArray(parsed.summary.keyPoints) ? parsed.summary.keyPoints.slice(0, 6) : []
  parsed.summary.openQuestions = Array.isArray(parsed.summary.openQuestions) ? parsed.summary.openQuestions.slice(0, 4) : []
  return { inbox: { path: doc.path, title: doc.title, excerpt: String(doc.body).slice(0, 300) }, proposal: parsed }
}

function insertIntoSection(body, section, block) {
  // 标题可能带 emoji 或后缀（`## 📂 摘要 (Summaries)`），按「包含关键词」匹配，插入到该节末尾。
  const head = new RegExp(`^##[^\\n]*${section}[^\\n]*$`, 'm').exec(body)
  const piece = block.trim()
  if (!head) {
    // 页面还没有这一节：新节要落在线下区标记/分隔线之前，否则会被当成证据链的一部分。
    // 搜索必须跳过 frontmatter，否则会撞上开头那个 `---`。
    const fence = /^---\n[\s\S]*?\n---\n/.exec(body)
    const offset = fence ? fence[0].length : 0
    const anchor = /(?:^<!--[^\n]*-->[ \t]*$\n+)?^---[ \t]*$|^##\s*Timeline[ \t]*$/m.exec(body.slice(offset))
    if (!anchor) return `${body.trimEnd()}\n\n## ${section}\n\n${piece}\n`
    const at = offset + anchor.index
    const before = body.slice(0, at).replace(/\s+$/, '')
    return `${before}\n\n## ${section}\n\n${piece}\n\n${body.slice(at)}`
  }
  const start = head.index + head[0].length
  const rest = body.slice(start)
  const next = /^##\s+/m.exec(rest)
  const raw = next ? rest.slice(0, next.index) : rest

  // 节尾常有 `---` 分隔线和 `<!-- 线下区 -->` 这类标记，插入点必须落在它们之前，
  // 否则新内容会跑到线下区（证据链区），破坏「线上区只改线上区」的规矩。
  let middle = raw.replace(/\s+$/, '')
  let suffix = ''
  for (;;) {
    const hit = /\n+(?:---|<!--[^\n]*-->)[ \t]*$/.exec(middle)
    if (!hit) break
    suffix = middle.slice(hit.index) + suffix
    middle = middle.slice(0, hit.index)
  }
  middle = middle.replace(/^\n+/, '').replace(/\s+$/, '')

  const pieceIsList = /^[-*]\s/.test(piece)
  const middleIsList = /^[-*]\s/.test(middle.split('\n').pop() || '')
  const tight = pieceIsList && middleIsList && middle !== ''

  return [
    body.slice(0, start),
    middle ? `\n\n${middle}` : '',
    tight ? `\n${piece}` : `\n\n${piece}`,
    suffix,
    next ? `\n\n${rest.slice(next.index)}` : '\n',
  ].join('')
}

function appendTimeline(body, line) {
  if (/^##\s*Timeline\s*$/m.test(body)) return insertIntoSection(body, 'Timeline', `- ${line}`)
  return `${body.trimEnd()}\n\n## Timeline\n\n- ${line}\n`
}

function ensureBacklink(body, link) {
  // 调用方偶尔会带上 `- ` 前缀，统一去掉再补，避免插成 `- - [[...]]`。
  link = String(link).replace(/^\s*-\s*/, '').trim()
  // 只认「独立成一条」的回链：Timeline 里也会出现同一个链接，不能据此就跳过。
  const escaped = link.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  if (new RegExp(`^[-*]\\s*${escaped}\\s*$`, 'm').test(body)) return body
  if (/^##[^\n]*(相关链接|相关页面|Links)/m.test(body)) return insertIntoSection(body, '相关链接', `- ${link}`)
  return `${body.trimEnd()}\n\n## 相关链接\n\n- ${link}\n`
}

function bumpFrontmatter(text, patch) {
  const { data, body } = parseFrontmatter(text)
  const next = { ...(data || {}), ...patch }
  return `${buildFrontmatter(next)}${body}`
}

async function recountSpace(root, space) {
  const raw = await listFiles(join(root, '00 raw', space))
  const summaries = await listFiles(join(root, '01 wiki', space, 'summaries'))
  const concepts = await listFiles(join(root, '01 wiki', space, 'concepts'))
  return { raw: raw.length, summaries: summaries.length, concepts: concepts.length }
}

async function syncIndexes(root, space, { summaryPath, tldr, date }) {
  const changes = []
  const counts = await recountSpace(root, space)
  const indexFile = join(root, '01 wiki/index.md')
  if (await exists(indexFile)) {
    const text = await readFile(indexFile, 'utf8')
    const parts = text.split(/^### /m)
    const label = SPACE_NAMES[space]
    const updated = parts.map((part, i) => {
      if (i === 0) return part
      const head = part.slice(0, part.indexOf('\n'))
      if (!head.includes(label) && !head.includes(space)) return part
      return part
        .replace(/(原始来源：)\s*\d+(\s*篇)/, `$1${counts.raw}$2`)
        .replace(/(已处理摘要：)\s*\d+/, `$1${counts.summaries}`)
        .replace(/(概念条目：)\s*\d+/, `$1${counts.concepts}`)
        .replace(/(last_updated:\s*)\S+/, `$1${date}`)
    })
    const next = `### ${updated.slice(1).join('### ')}`
    if (next !== text) {
      await writeFile(indexFile, next, 'utf8')
      changes.push({ path: '01 wiki/index.md', note: `统计 ${counts.raw}/${counts.summaries}/${counts.concepts}` })
    }
  }

  const spaceIndex = join(root, '01 wiki', space, '_index.md')
  if (await exists(spaceIndex)) {
    const text = await readFile(spaceIndex, 'utf8')
    const link = stripMd(summaryPath).replace(new RegExp(`^01 wiki/${space}/`), `${space}/`)
    const bullet = `- [[${link}]] — ${String(tldr || '').replace(/\s+/g, ' ').slice(0, 120)}（${date}）`
    let next = text
    if (!next.includes(`[[${link}]]`)) {
      if (/^##[^\n]*摘要/m.test(next)) {
        next = insertIntoSection(next, '摘要', bullet)
      } else {
        next = `${next.trimEnd()}\n\n## 📂 摘要 (Summaries)\n\n${bullet}\n`
      }
      await writeFile(spaceIndex, next, 'utf8')
      changes.push({ path: `01 wiki/${space}/_index.md`, note: '摘要列表追加一条' })
    }
  }
  return changes
}

async function appendLog(root, line) {
  const logFile = join(root, '01 wiki/log.md')
  const prev = (await exists(logFile)) ? await readFile(logFile, 'utf8') : ''
  await writeFile(logFile, `${prev.trimEnd()}\n${line}\n`, 'utf8')
  return { path: '01 wiki/log.md', note: '追加一条' }
}

export async function applyTriage(ctx, root, proposal) {
  const date = new Date().toISOString().slice(0, 10)
  const space = SPACE_NAMES[proposal.space] ? proposal.space : 'builder'
  const changes = []
  const warnings = []

  if (proposal.decision === 'drop') {
    const target = resolveInVault(root, proposal.inboxPath)
    await rm(target, { force: true })
    changes.push({ path: proposal.inboxPath, note: '按提案丢弃，已从 Inbox 移除' })
    return { changes, warnings, summaryPath: null }
  }

  const rawRel = `00 raw/${space}/${date.slice(0, 4)}/${date.slice(5, 7)}/${proposal.slug}.md`
  // 幂等：同一篇被重复整理时复用已有摘要，不再新起一个编号（否则会 S-2075 / S-2077 各存一份）。
  const existing = await findExistingSummary(root, space, proposal.slug, proposal.title)
  const summaryId = existing ? existing.id : (await maxSummaryId(root)) + 1
  const summaryRel = existing ? existing.path : `01 wiki/${space}/summaries/S-${summaryId}-${proposal.slug}.md`
  if (existing) warnings.push(`已经有摘要 ${summaryRel}，这次只做增量更新`)

  if (proposal.decision === 'raw' && (await exists(resolveInVault(root, rawRel)))) {
    warnings.push(`原文 ${rawRel} 已存在，跳过重写`)
  } else if (proposal.decision === 'raw') {
    const source = await readDoc(root, proposal.inboxPath)
    const rawBody = [
      `# ${proposal.title || source.title}`,
      '',
      source.body.trim(),
      '',
      `> 抓取于 ${source.frontmatter?.captured_at || date}，来源 ${source.frontmatter?.source_url || ''}`,
      `> [Source: ${proposal.inboxPath}]`,
      '',
    ].join('\n')
    const rawFull = resolveInVault(root, rawRel)
    await mkdir(join(rawFull, '..'), { recursive: true })
    await writeFile(rawFull, `${buildFrontmatter({
      title: proposal.title || source.title,
      space,
      platform: source.frontmatter?.platform || 'web',
      source_url: source.frontmatter?.source_url || source.frontmatter?.url || '',
      canonical_url: source.frontmatter?.canonical_url || source.frontmatter?.source_url || '',
      ingested_at: new Date().toISOString(),
      captured_at: source.frontmatter?.captured_at || date,
      published_at: source.frontmatter?.published_at || '',
      author: source.frontmatter?.author || '',
      status: 'parsed',
      tags: ['ingest/kb-desk', ...(Array.isArray(source.frontmatter?.tags) ? source.frontmatter.tags : [])].slice(0, 12),
    })}${rawBody}`, 'utf8')
    changes.push({ path: rawRel, note: '原文归档（不可变）' })
  }

  const summaryText = [
    buildFrontmatter({
      title: `S-${summaryId} ${proposal.title || ''}`.trim(),
      type: 'source-summary',
      space,
      created: date,
      last_updated: date,
      source_count: proposal.decision === 'raw' ? 1 : 0,
      status: 'draft',
      tags: Array.isArray(proposal.tags) ? proposal.tags.slice(0, 10) : [],
      source: proposal.decision === 'raw' ? rawRel : proposal.inboxPath,
    }),
    `# S-${summaryId} ${proposal.title || ''}`.trim(),
    '',
    `> 来源：${proposal.decision === 'raw' ? rawRel : '（仅灵感，未归档原文）'}`,
    `> [Source: ${proposal.decision === 'raw' ? rawRel : proposal.inboxPath}]`,
    '',
    '---',
    '',
    '## TL;DR',
    '',
    proposal.summary?.tldr || '（模型未给出摘要，需要人工补）',
    '',
    '## 核心观点',
    '',
    ...(proposal.summary?.keyPoints || []).map((line) => `- ${line}`),
    '',
    '## 我的判断',
    '',
    proposal.summary?.judgement || '（待补）',
    '',
    ...(proposal.summary?.openQuestions?.length
      ? ['## 待验证', '', ...proposal.summary.openQuestions.map((line) => `- ${line}`), '']
      : []),
  ].join('\n')
  const summaryFull = resolveInVault(root, summaryRel)
  if (!existing) {
    await mkdir(join(summaryFull, '..'), { recursive: true })
    await writeFile(summaryFull, summaryText, 'utf8')
    changes.push({ path: summaryRel, note: '摘要' })
  }

  const summaryLink = `[[${stripMd(summaryRel).replace(/^01 wiki\//, '')}]]`
  for (const item of proposal.concepts || []) {
    const heading = String(item.heading || '').trim()
    const text = String(item.text || '').trim()
    if (!text) continue
    const block = [`**${heading || '补充'}**：${text}`, item.openThreads?.length ? '' : null]
      .filter(Boolean)
      .join('\n')
    const threads = (item.openThreads || []).map((line) => `- ${line}`).join('\n')

    if (item.action === 'update' && item.path) {
      let target
      try {
        target = resolveInVault(root, item.path)
      } catch {
        warnings.push(`提案里的概念页路径越界，已跳过：${item.path}`)
        continue
      }
      if (!(await exists(target))) {
        warnings.push(`概念页不存在，已跳过：${item.path}`)
        continue
      }
      let content = await readFile(target, 'utf8')
      const section = ['State', 'Assessment', 'Open Threads', 'Open Thread'].includes(item.section) ? item.section : 'State'
      if (heading && content.includes(`**${heading}**`)) {
        warnings.push(`${item.path} 已有「${heading}」这一条，跳过`)
        continue
      }
      content = insertIntoSection(content, section === 'Open Thread' ? 'Open Threads' : section, block)
      if (threads) content = insertIntoSection(content, 'Open Threads', threads)
      content = appendTimeline(content, `${date} 补入「${heading || proposal.title}」 ${summaryLink}`)
      content = ensureBacklink(content, `- ${summaryLink}`)
      const { data } = parseFrontmatter(content)
      const count = Number(data?.source_count || 0) + 1
      content = bumpFrontmatter(content, { source_count: count, last_updated: date })
      await writeFile(target, content, 'utf8')
      changes.push({ path: relPath(root, target), note: `+1 段（${section}）+ Timeline + 回链，source_count→${count}` })
      continue
    }

    if (item.action === 'create') {
      const title = String(item.title || heading || proposal.title || '').trim()
      if (!title) continue
      const rel = `01 wiki/${space}/concepts/${slugify(title)}.md`
      const full = resolveInVault(root, rel)
      if (await exists(full)) {
        warnings.push(`概念页已存在，跳过新建：${rel}`)
        continue
      }
      const page = [
        buildFrontmatter({
          title,
          type: 'concept-page',
          space,
          created: date,
          last_updated: date,
          source_count: 1,
          status: 'draft',
          tags: [],
        }),
        '<!-- ═══ 线上区：当前真相，有新信息就重写 ═══ -->',
        '',
        `> ${proposal.summary?.tldr || title}`,
        '',
        '## State',
        '',
        block,
        '',
        '## Assessment',
        '',
        '（待补：这一页目前只有一条来源，判断留空。）',
        '',
        '## Open Threads',
        '',
        threads || '- （无）',
        '',
        '## Timeline',
        '',
        `- ${date} 建页 ${summaryLink}`,
        '',
        '## 相关链接',
        '',
        `- ${summaryLink}`,
        '',
      ].join('\n')
      await mkdir(join(full, '..'), { recursive: true })
      await writeFile(full, page, 'utf8')
      changes.push({ path: rel, note: '新建概念页（status: draft）' })
    }
  }

  const indexChanges = await syncIndexes(root, space, { summaryPath: summaryRel, tldr: proposal.summary?.tldr, date })
  changes.push(...indexChanges)

  const conceptNote = (proposal.concepts || []).map((c) => (c.action === 'create' ? `新建 ${c.title}` : `${basename(c.path || '', '.md')} +1`)).join('、')
  const logLine = `## [${date}] ingest:${space} | ${proposal.title || ''} → ${proposal.decision === 'raw' ? rawRel : '（仅灵感）'} + ${basename(summaryRel)}${conceptNote ? `；${conceptNote}` : ''}`
  changes.push(await appendLog(root, logLine))

  const inboxFull = resolveInVault(root, proposal.inboxPath)
  await rm(inboxFull, { force: true })
  changes.push({ path: proposal.inboxPath, note: '已从 Inbox 移除' })

  return { changes, warnings, summaryPath: summaryRel }
}

/** 只推送（本地领先、但工作区干净时用）。 */
export async function gitPush(root) {
  const run = (args) => new Promise((resolvePromise) => {
    execFile('git', ['-C', root, ...args], { timeout: 120_000 }, (error, stdout, stderr) => {
      resolvePromise({ ok: !error, stdout: String(stdout || '').trim(), stderr: String(stderr || error?.message || '').trim() })
    })
  })
  const push = await run(['push'])
  return { ok: push.ok, message: push.ok ? '已推送' : push.stderr.split('\n').slice(-2).join(' ') }
}

export async function gitCommitAndPush(root, message, options = {}) {
  const run = (args, timeout = 60_000) =>
    new Promise((resolve) => {
      execFile('git', args, { cwd: root, timeout }, (error, stdout, stderr) => {
        resolve({ ok: !error, stdout: String(stdout || ''), stderr: String(stderr || error?.message || '') })
      })
    })
  const status = await run(['status', '--porcelain'])
  if (!status.ok) return { ok: false, step: 'status', message: status.stderr }
  if (!status.stdout.trim()) return { ok: true, message: '没有需要提交的改动' }
  const paths = Array.isArray(options.paths) && options.paths.length ? options.paths : null
  const add = await run(paths ? ['add', '-A', '--', ...paths] : ['add', '-A'])
  if (!add.ok) return { ok: false, step: 'add', message: add.stderr }
  if (paths) {
    const staged = await run(['diff', '--cached', '--quiet'])
    if (staged.ok) return { ok: true, message: '没有需要提交的改动（指定路径下无变化）' }
  }
  const commit = await run(['commit', '-m', message || `kb: 整理 Inbox ${new Date().toISOString().slice(0, 10)}`])
  if (!commit.ok) return { ok: false, step: 'commit', message: commit.stderr }
  // worker 在远端持续 push，本地提交之后先 rebase 再推，避免被拒。
  const pull = await run(['pull', '--rebase', '--quiet'], 90_000)
  const pulled = pull.ok ? '' : `（pull 失败：${pull.stderr.split('\n')[0]}）`
  let push = await run(['push'], 120_000)
  if (!push.ok) {
    // 期间又有新提交：rebase 一次再推。
    const retryPull = await run(['pull', '--rebase', '--quiet'], 90_000)
    if (retryPull.ok) push = await run(['push'], 120_000)
  }
  return {
    ok: push.ok,
    step: 'push',
    message: push.ok ? `已提交并推送${pulled}` : `${pulled}${push.stderr}`.trim() || '推送失败',
    commit: commit.stdout,
  }
}
