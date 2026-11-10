// 失败任务排查：先把本机能看到的证据收齐（远端错误 / 阶段记录 / vault 与 git / 源站探测 / Inbox），
// 再让模型基于这些证据给「最可能原因 + 怎么修 + 怎么重试」。没有模型时证据本身也有用。
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { callModel } from './ai.js'
import { listJobs, ready as triageReady } from './triage-queue.js'
import { gitOverview, listInbox } from './vault.js'

const PROBE_TIMEOUT_MS = 6500
const PROBE_MAX_BYTES = 220_000
const USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'

// ───────────────────────── 错误归类 ─────────────────────────

/**
 * 把远端 error 文本归到已知失败类型。归类只用于给证据和提示定调，
 * 最终结论仍以阶段记录和本机状态为准。
 */
export function classifyError(message) {
  const text = String(message || '')
  if (!text.trim()) return { code: 'unknown', label: '远端没有留下错误文本', scope: 'unknown' }
  if (/uncommitted changes/i.test(text)) return { code: 'vault-dirty', label: '本机 vault 有未提交改动，worker 拒绝写入', scope: 'local' }
  if (/lease expired/i.test(text)) return { code: 'lease-expired', label: 'worker 租约过期（抓取阶段没按时续约）', scope: 'worker' }
  if (/vault sync failed|pull --rebase failed|SSL_ERROR|unable to access|Could not resolve|Connection timed out/i.test(text)) {
    return { code: 'git-sync', label: 'vault 同步（git 拉取/推送）失败', scope: 'local' }
  }
  if (/\b(401|403)\b|unauthorized|forbidden|invalid token|token expired/i.test(text)) return { code: 'auth', label: '凭据被拒或过期', scope: 'worker' }
  if (/ENOTFOUND|getaddrinfo|DNS/i.test(text)) return { code: 'dns', label: '域名解析失败', scope: 'worker' }
  if (/ETIMEDOUT|timed? ?out|aborted|ECONNRESET|ECONNREFUSED/i.test(text)) return { code: 'network', label: '网络连接失败或超时', scope: 'worker' }
  if (/captcha|验证码|环境异常|安全验证|访问过于频繁|登录后|请先登录|login required|sign in/i.test(text)) {
    return { code: 'login-wall', label: '源站要求登录或人机验证', scope: 'source' }
  }
  if (/\b404\b|not found/i.test(text)) return { code: 'source-404', label: '源站返回 404', scope: 'source' }
  if (/\b(4\d\d|5\d\d)\b/.test(text)) return { code: 'http-status', label: '源站返回异常状态码', scope: 'source' }
  if (/duplicate/i.test(text)) return { code: 'duplicate', label: '重复提交', scope: 'queue' }
  return { code: 'unknown', label: '未归入已知类型，需要看阶段记录', scope: 'unknown' }
}

/** 错误类型 → 给模型的判读参考，避免它对着常见错误瞎猜。 */
const CLUE_MAP = {
  'vault-dirty': 'worker 写盘前会检查 vault 是否干净；失败说明失败当时有未提交改动。修法是先在 vault 里 commit 或 stash，再重试。',
  'lease-expired': '租约过期说明 worker 领取后没能按时上报进度：抓取慢（大文件/JS 渲染）、worker 掉线、或源站卡住都会这样；重试前先确认 mac-mini 上的 worker 进程与网络。',
  'git-sync': 'git 拉取/推送失败通常是网络或代理问题；远端提示本地 commit 已保留，不要 reset，重新 push 即可。',
  auth: '凭据问题要换 credentials.env 里的 token，重试不会自己好。',
  'login-wall': '登录墙/验证码页面 worker 抓不到正文；需要在能登录的环境里取正文，或换来源。',
  'source-404': '链接失效或需要登录；先人工打开确认，再决定是否删任务。',
  network: '网络错误要区分本机与 mac-mini 的网络：本机能打开不代表 worker 能打开。',
  duplicate: '重复任务通常已经在队列或 Inbox 里，先去重再判断。',
}

// ───────────────────────── 源站探测 ─────────────────────────

export function isPrivateHost(hostname) {
  const host = String(hostname || '').toLowerCase().replace(/^\[|\]$/g, '')
  if (!host) return true
  if (host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') || host.endsWith('.internal')) return true
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    const [a, b] = host.split('.').map(Number)
    if (a === 0 || a === 10 || a === 127) return true
    if (a === 169 && b === 254) return true
    if (a === 172 && b >= 16 && b <= 31) return true
    if (a === 192 && b === 168) return true
    if (a === 100 && b >= 64 && b <= 127) return true
  }
  if (host === '::1' || host.startsWith('fc') || host.startsWith('fd') || host.startsWith('fe80')) return true
  return false
}

const PAGE_MARKERS = [
  [/环境异常|完成验证|安全验证|访问过于频繁|请完成下方验证|滑动验证|人机验证/, '反爬/人机验证'],
  [/该内容已被发布者删除|此内容因违规无法查看|内容不存在|已被删除|此内容被多人投诉/, '内容已删除或不可见'],
  [/请在微信客户端打开|微信扫一扫|打开微信扫一扫/, '要求微信内打开'],
  [/登录后(?:查看|阅读|继续)|请先登录|sign in to continue|log in to continue|requires? (?:login|signin)/i, '要求登录'],
]

function detectPageMarkers(text) {
  const hits = []
  for (const [pattern, label] of PAGE_MARKERS) {
    if (pattern.test(text) && !hits.includes(label)) hits.push(label)
  }
  return hits
}

async function readLimited(body, limit) {
  if (!body) return ''
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8', { fatal: false })
  let out = ''
  let bytes = 0
  while (bytes < limit) {
    const { done, value } = await reader.read()
    if (done) break
    bytes += value.byteLength
    out += decoder.decode(value, { stream: true })
  }
  try {
    await reader.cancel()
  } catch {
    // 读够就取消，取消失败不影响结论
  }
  return out
}

/**
 * 从本机探测源站。只做一次 GET，读前 220KB 找登录墙/验证码标记。
 * 内网地址直接跳过，避免把排障请求打进本地服务。
 */
export async function probeUrl(url, { timeoutMs = PROBE_TIMEOUT_MS, fetchImpl = fetch } = {}) {
  let target
  try {
    target = new URL(String(url || ''))
  } catch {
    return { ok: false, skipped: 'URL 不合法' }
  }
  if (!/^https?:$/.test(target.protocol)) return { ok: false, skipped: '不是 http(s) 链接' }
  if (isPrivateHost(target.hostname)) return { ok: false, skipped: '内网地址，跳过探测' }
  const started = Date.now()
  try {
    const res = await fetchImpl(target, {
      method: 'GET',
      redirect: 'follow',
      headers: { 'user-agent': USER_AGENT, accept: 'text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.5' },
      signal: AbortSignal.timeout(timeoutMs),
    })
    const type = String(res.headers.get('content-type') || '')
    const textual = /text\/|html|json|xml|javascript/i.test(type)
    const text = textual ? await readLimited(res.body, PROBE_MAX_BYTES) : ''
    if (!textual && res.body) {
      try {
        await res.body.cancel()
      } catch {
        // 非文本不读正文
      }
    }
    const titleMatch = /<title[^>]*>([^<]{1,200})<\/title>/i.exec(text)
    const finalUrl = res.url || target.href
    return {
      ok: true,
      status: res.status,
      contentType: type || null,
      finalUrl: finalUrl !== target.href ? finalUrl : null,
      bytes: Buffer.byteLength(text),
      ms: Date.now() - started,
      title: titleMatch ? titleMatch[1].trim() : null,
      markers: textual ? detectPageMarkers(text) : [],
    }
  } catch (error) {
    const timeout = error?.name === 'TimeoutError' || error?.name === 'AbortError'
    return {
      ok: false,
      error: timeout ? `本机探测超时（${Math.round(timeoutMs / 1000)}s）` : error?.message || String(error),
      ms: Date.now() - started,
    }
  }
}

// ───────────────────────── 证据收集 ─────────────────────────

function fmtMs(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return `${date.toISOString().slice(0, 16).replace('T', ' ')}Z`
}

function fmtGap(ms) {
  if (!ms || ms < 1000) return '—'
  if (ms < 60_000) return `${Math.round(ms / 1000)} 秒`
  return `${Math.floor(ms / 60_000)} 分 ${Math.round((ms % 60_000) / 1000)} 秒`
}

/** 阶段之间的最大间隔，用来看「领了任务但半天没动静」这类租约问题。 */
export function biggestGap(stages = []) {
  let best = null
  for (let i = 1; i < stages.length; i += 1) {
    const prev = stages[i - 1]?.at
    const next = stages[i]?.at
    if (!prev || !next) continue
    const gap = next - prev
    if (gap > 0 && (!best || gap > best.ms)) best = { ms: gap, from: stages[i - 1], to: stages[i] }
  }
  return best
}

/**
 * 把一次失败任务的证据收成一个对象：context 给界面渲染，evidence 给模型读。
 * 远端接口不可用时，用前端传上来的 job 快照继续，不让排查整体失败。
 */
export async function gatherFailure({ ingest, root, job, jobId, note = '', probe = true } = {}) {
  const id = String(jobId || job?.id || '')
  let remote = null
  let remoteError = null
  if (ingest?.jobs) {
    try {
      const payload = await ingest.jobs('failed', 50)
      remote = (payload?.jobs || []).find((item) => item.id === id) || null
    } catch (error) {
      remoteError = error?.message || String(error)
    }
  }
  const target = remote || (job && typeof job === 'object' ? job : null)
  if (!target) throw Object.assign(new Error(`找不到任务 ${id} 的失败记录`), { status: 404 })

  let stages = []
  if (ingest?.run) {
    try {
      const run = await ingest.run(id)
      stages = Array.isArray(run?.stages) ? run.stages : []
    } catch {
      stages = []
    }
  }

  let local = []
  try {
    await triageReady()
    local = listJobs()
  } catch {
    local = []
  }

  const [git, inbox] = await Promise.all([
    gitOverview(root).catch(() => null),
    listInbox(root).catch(() => []),
  ])

  const vaultPath = target.vaultPath || target.vault_path || null
  const fileExists = vaultPath ? existsSync(join(root, vaultPath)) : false
  const inboxHit = target.url
    ? inbox.find((doc) => doc.url === target.url) || inbox.find((doc) => doc.url && doc.url.startsWith(target.url)) || null
    : null
  const triage = vaultPath ? local.find((item) => item.path === vaultPath) || null : null
  const errorClass = classifyError(target.error)
  const probeResult = probe && target.url ? await probeUrl(target.url) : null
  const gap = biggestGap(stages)
  const lastFailed = [...stages].reverse().find((stage) => stage.status === 'failed') || null

  const signals = buildSignals({ job: target, errorClass, stages, lastFailed, gap, git, probe: probeResult, inboxHit, triage, fileExists })

  const context = {
    job: {
      id: target.id,
      url: target.url || null,
      title: target.title || null,
      status: target.status || 'failed',
      worker: target.worker || null,
      attempts: Number(target.attempts || 0),
      error: target.error || null,
      vaultPath,
      createdAt: target.createdAt ?? null,
      claimedAt: target.claimedAt ?? null,
      finishedAt: target.finishedAt ?? null,
      elapsedMs: target.elapsedMs ?? null,
    },
    errorClass,
    stages,
    gap,
    git,
    probe: probeResult,
    inboxHit: inboxHit ? { path: inboxHit.path, title: inboxHit.title } : null,
    triage: triage ? { id: triage.id, status: triage.status, error: triage.error || null, path: triage.path } : null,
    fileExists,
    signals,
    remoteError,
  }

  const evidence = buildEvidence(context, note)
  return { context, evidence, job: target, stages }
}

/** 纯函数：证据 + 判定规则 → 界面上的检查清单。 */
export function buildSignals({ job, errorClass, stages = [], lastFailed = null, gap = null, git = null, probe = null, inboxHit = null, triage = null, fileExists = false }) {
  const signals = []
  const error = String(job?.error || '').trim()

  if (error) {
    signals.push({ level: 'error', title: `远端错误：${error.split('\n')[0].slice(0, 180)}`, detail: `归类：${errorClass?.label || '未归类'}（${errorClass?.scope || 'unknown'}）` })
  } else {
    signals.push({ level: 'warn', title: '远端没有留错误文本', detail: '只能靠阶段记录和本机状态推断；去 mac-mini 看 worker 日志更直接' })
  }

  if (Number(job?.attempts || 0) >= 2) {
    signals.push({ level: 'warn', title: `已经重试 ${job.attempts} 次`, detail: '反复失败说明是持续性原因，先排除再重试，不要靠再点一次碰运气' })
  }

  if (lastFailed) {
    signals.push({ level: 'error', title: `最后一个失败阶段：${lastFailed.stage}`, detail: lastFailed.note || '阶段记录没有写细节' })
  } else if (Array.isArray(stages) && stages.length) {
    signals.push({ level: 'warn', title: '阶段记录里没有 failed 标记', detail: '失败可能发生在阶段之外（例如 worker 收尾时），按错误文本判断' })
  } else {
    signals.push({ level: 'warn', title: '远端没有阶段记录', detail: '可能是任务没进到 worker 就被判失败，或运行记录被清理' })
  }

  if (gap && gap.ms >= 90_000) {
    signals.push({ level: 'warn', title: `阶段之间最长隔了 ${fmtGap(gap.ms)}`, detail: `「${gap.from?.stage}」→「${gap.to?.stage}」；这种空档通常是租约/心跳掉了，或抓取被源站卡住` })
  }

  if (git?.ok) {
    if (Number(git.dirty) > 0) {
      const aligned = errorClass?.code === 'vault-dirty' ? '，与失败原因一致' : ''
      signals.push({ level: 'error', title: `本地 vault 有 ${git.dirty} 个未提交改动${aligned}`, detail: 'worker 写盘前会检查工作区是否干净；先在 vault 里 commit 或 stash，再重试' })
    } else if (errorClass?.code === 'vault-dirty') {
      signals.push({ level: 'ok', title: '现在 vault 是干净的', detail: '失败当时的未提交改动已经不在了；可以直接重试确认' })
    }
    if (Number(git.behind) > 0) {
      signals.push({ level: 'warn', title: `本地落后 origin ${git.behind} 个提交`, detail: 'worker 可能已经写入并推送，只是本地没拉下来；先拉取再判断是否真失败' })
    }
    if (Number(git.ahead) > 0) {
      signals.push({ level: 'warn', title: `本地有 ${git.ahead} 个提交没推送`, detail: 'worker 收尾时会先 pull --rebase；本地提交与远端冲突时同步会失败' })
    }
  } else if (git) {
    signals.push({ level: 'warn', title: '读不到 vault 的 git 状态', detail: git.error || 'vault 可能不是 git 仓库' })
  }

  if (probe) {
    if (probe.skipped) {
      signals.push({ level: 'info', title: `没有探测源站：${probe.skipped}`, detail: '跳过探测，只看远端与本机证据' })
    } else if (!probe.ok) {
      signals.push({ level: 'warn', title: `本机探测源站失败：${probe.error}`, detail: '本机能连不代表 mac-mini 能连，反之亦然；要对比同一网络环境再下结论' })
    } else if (probe.markers?.length) {
      signals.push({ level: 'warn', title: `源站返回 ${probe.status}，但页面像${probe.markers.join('、')}`, detail: '用浏览器打开确认；这类页面 worker 也抓不到正文，重试通常无效' })
    } else if (probe.status >= 400) {
      signals.push({ level: 'error', title: `源站返回 HTTP ${probe.status}`, detail: '链接可能已失效或被限制；先人工打开确认' })
    } else {
      signals.push({ level: 'ok', title: `源站现在可访问（HTTP ${probe.status}，${Math.round((probe.bytes || 0) / 1024)} KB，${probe.ms}ms）`, detail: '链接本身没问题，失败更可能在 worker 侧或本机 git/写盘' })
    }
    if (probe.finalUrl) {
      signals.push({ level: 'warn', title: '源站把请求重定向到了另一个地址', detail: probe.finalUrl })
    }
  }

  if (inboxHit) {
    signals.push({ level: 'warn', title: `这篇已经在 Inbox：${inboxHit.path}`, detail: '可能已经落盘；先看 Inbox 内容是否完整，再决定要不要重试' })
  }
  if (fileExists) {
    signals.push({ level: 'ok', title: '落盘文件存在', detail: job.vaultPath || job.vault_path })
  }
  if (triage && triage.status === 'failed') {
    signals.push({ level: 'error', title: '本地整理（triage）也失败了', detail: String(triage.error || '去 Inbox 卡片上点开看提案状态').slice(0, 300) })
  }

  return signals
}

function buildEvidence(context, note) {
  const { job, errorClass, stages, gap, git, probe, inboxHit, triage, signals, remoteError } = context
  const lines = [
    `【任务】${job.id}`,
    `标题：${job.title || '（无）'}`,
    `链接：${job.url || '（无）'}`,
    `状态：${job.status} · worker ${job.worker || '未知'} · 第 ${job.attempts || 0} 次尝试`,
    `创建 ${fmtMs(job.createdAt)} · 领取 ${fmtMs(job.claimedAt)} · 结束 ${fmtMs(job.finishedAt)} · 耗时 ${job.elapsedMs ? fmtGap(job.elapsedMs) : '—'}`,
    `错误原文：${job.error || '（空）'}`,
    `机器归类：${errorClass.code} / ${errorClass.label}（${errorClass.scope}）`,
    CLUE_MAP[errorClass.code] ? `判读参考：${CLUE_MAP[errorClass.code]}` : '',
    '',
    '【阶段记录】',
    stages.length
      ? stages.map((stage) => `- ${stage.stage} [${stage.status}] ${fmtMs(stage.at)}${stage.durationSec ? ` ${fmtGap(stage.durationSec * 1000)}` : ''}${stage.actor ? ` · ${stage.actor}` : ''}${stage.note ? ` · ${stage.note}` : ''}`).join('\n')
      : '- （没有记录）',
    gap && gap.ms >= 90_000 ? `- 最大阶段间隔 ${fmtGap(gap.ms)}（${gap.from?.stage} → ${gap.to?.stage}）` : '',
    '',
    '【本机 vault / git】',
    git?.ok
      ? `- 分支 ${git.branch || '?'}，未提交 ${git.dirty ?? '?'} 个，落后 origin ${git.behind ?? '?'}，未推送 ${git.ahead ?? '?'}\n- 最后一个提交：${git.lastCommit ? `${git.lastCommit.hash} ${git.lastCommit.subject}（${fmtMs(git.lastCommit.at)}）` : '—'}`
      : `- 读不到：${git?.error || 'vault 不是 git 仓库'}`,
    '',
    '【源站探测（本机）】',
    probe ? (probe.skipped ? `- 跳过：${probe.skipped}` : probe.ok
      ? `- HTTP ${probe.status}，${probe.bytes} bytes，${probe.ms}ms${probe.contentType ? `，${probe.contentType}` : ''}${probe.title ? `，标题「${probe.title}」` : ''}${probe.markers?.length ? `，页面标记：${probe.markers.join('、')}` : ''}${probe.finalUrl ? `，重定向到 ${probe.finalUrl}` : ''}`
      : `- 失败：${probe.error}（${probe.ms}ms）`) : '- 未探测',
    '',
    '【相关状态】',
    `- Inbox 命中：${inboxHit ? `${inboxHit.path}（${inboxHit.title}）` : '无'}`,
    `- 落盘文件：${context.fileExists ? '存在' : '不存在'}`,
    `- 本地整理任务：${triage ? `${triage.status}${triage.error ? ` · ${triage.error}` : ''}` : '无'}`,
    remoteError ? `- 远端接口异常：${remoteError}` : '',
    '',
    '【机器检查清单】',
    signals.map((signal) => `- [${signal.level}] ${signal.title}${signal.detail ? ` —— ${signal.detail}` : ''}`).join('\n'),
    note ? `\n【用户补充】${note}` : '',
  ]
  return lines.filter((line) => line !== '').join('\n')
}

// ───────────────────────── 模型排查 ─────────────────────────

export const DIAGNOSE_SYSTEM = `你是知识库摄入链路的排障助手。用户是能自己上手修的技术用户，他要的是「为什么失败 + 现在改什么」，不是安慰。

规则：
1. 只依据【证据】判断。证据不够就写「证据不足」，并说明差哪一项，不要编造日志或远端状态。
2. 先给分类（vault 脏 / worker 租约 / git 同步 / 抓取或登录墙 / 凭据 / 源站 4xx / 其他）和最可能原因，再给置信度（高/中/低），并说明是「远端 worker、本机 vault/git、源站」哪一侧的问题。
3. 【证据】写 2-4 条，每条对应证据里的一条具体事实，不要复述任务基本信息。
4. 【怎么修】给 1-3 步可执行动作：命令写成可复制的一行；会改数据的地方说明改什么。禁止建议 git reset --hard、删除 vault 文件、清空队列这类不可逆操作。
5. 【重试与验证】写清重试前必须先满足的条件，以及重试后看哪个信号确认成功。
6. 中文，全篇 350 字以内。不写「可能是网络问题，请检查网络」这种没有信息量的句子。

输出格式（Markdown，标题固定）：
## 结论
分类：xxx ｜ 置信度：高/中/低
一句话说清最可能原因，并指出问题在哪一侧。
## 证据
- ...
## 怎么修
1. ...
## 重试与验证
- ...`

export function diagnoseUserPrompt({ evidence }) {
  return `【证据】\n${evidence}\n\n请按固定格式给出排查结论。`
}

/**
 * 流式产出排查结论。调用方负责把 onText 增量写给前端。
 */
export async function diagnoseFailure(ctx, { evidence, signal, onText }) {
  const result = await callModel(ctx, {
    system: DIAGNOSE_SYSTEM,
    messages: [{ role: 'user', content: diagnoseUserPrompt({ evidence }) }],
    maxTokens: 1200,
    signal,
    onText,
  })
  return { text: result.text, model: result.model }
}
