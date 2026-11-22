#!/usr/bin/env node
/**
 * 摄入闭环看门狗。
 *
 * 它只读状态、只发通知，不碰 vault 的 git，也不改任何队列 —— 因此它可以
 * 独立于插件进程存活：插件死了、被 reload 了、整台机器刚睡醒，它都能回答
 * 「现在正常吗」，并把异常推给人。
 *
 * 用法：
 *   node scripts/watchdog.mjs            # 检查一次
 *   node scripts/watchdog.mjs --print    # 只打印状态，不发通知
 *
 * 退出码：0 正常 / 1 有警告（launchd 不关心，供手工调用判断）
 */
import { execFile } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync, mkdirSync, statfsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const DSH_HOME = process.env.DSH_HOME || join(homedir(), '.dsh')
const STATE_DIR = join(DSH_HOME, 'raincoat-kb-desk')
const ALERT_FILE = join(STATE_DIR, 'alerts.json')
const STATUS_FILE = join(STATE_DIR, 'ingest-status.md')
const PRINT_ONLY = process.argv.includes('--print')
const ALERT_COOLDOWN_MS = 30 * 60 * 1000

const readJson = (file, fallback = null) => {
  try {
    return JSON.parse(readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}

const settings = readJson(join(STATE_DIR, 'settings.json'), {}) || {}
const VAULT = settings.vault || join(homedir(), 'Documents', 'ob_vault')
const API_BASE = settings.apiBase || 'https://rainpark.cn/api'
const CRED_FILE = settings.credentialsFile || join(homedir(), '.config', 'kb-ingest', 'credentials.env')

function readEnvFile(file) {
  const out = {}
  try {
    for (const line of readFileSync(file, 'utf8').split('\n')) {
      const m = /^([A-Z_][A-Z0-9_]*)=(.*)$/.exec(line.trim())
      if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, '')
    }
  } catch {}
  return out
}

const creds = readEnvFile(CRED_FILE)
const TOKEN = process.env.WORKER_TOKEN || creds.WORKER_TOKEN

function run(cmd, args, timeout = 15_000) {
  return new Promise((resolve) => {
    execFile(cmd, args, { timeout, maxBuffer: 4 * 1024 * 1024 }, (error, stdout, stderr) => {
      resolve({ ok: !error, stdout: String(stdout || '').trim(), stderr: String(stderr || error?.message || '').trim() })
    })
  })
}

const git = (args) => run('git', ['-C', VAULT, ...args])

async function api(path) {
  if (!TOKEN) return { ok: false, error: '缺少 WORKER_TOKEN' }
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { 'x-worker-token': TOKEN },
      signal: AbortSignal.timeout(10_000),
    })
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` }
    return { ok: true, data: await res.json() }
  } catch (error) {
    return { ok: false, error: error?.message || String(error) }
  }
}

const fmtAge = (ms) => {
  if (!Number.isFinite(ms) || ms < 0) return '未知'
  const min = Math.round(ms / 60_000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟`
  const hour = Math.round(min / 60)
  if (hour < 24) return `${hour} 小时`
  return `${Math.round(hour / 24)} 天`
}

const checks = []
const add = (id, level, title, detail) => checks.push({ id, level, title, detail })

// 1) 闭环心跳：插件每 watchSeconds 跑一轮，这里按 3 轮为容差
const watcherState = readJson(join(STATE_DIR, 'watcher-state.json'), {}) || {}
const watchSeconds = Number(settings.watchSeconds) || 60
const staleAfter = Math.max(300_000, watchSeconds * 3 * 1000)
const lastRunAge = Date.now() - (Number(watcherState.lastRunAt) || 0)
if (!watcherState.lastRunAt) {
  add('watcher', 'warn', '闭环从未跑过', 'watcher-state.json 里没有 lastRunAt，插件可能没启动自动闭环')
} else if (lastRunAge > staleAfter) {
  add('watcher', 'warn', `闭环心跳停了（${fmtAge(lastRunAge)}）`, `超过 ${Math.round(staleAfter / 60000)} 分钟没有跑过一轮，检查 web 实例是否在运行`)
} else {
  add('watcher', 'ok', '闭环心跳正常', `上一轮 ${fmtAge(lastRunAge)}前`)
}

if (watcherState.lastError) {
  add('error', 'warn', '上一轮报错', String(watcherState.lastError).slice(0, 300))
}

// 2) 队列里卡住的条目
const jobsRaw = readJson(join(STATE_DIR, 'triage-jobs.json'), [])
const jobs = Array.isArray(jobsRaw) ? jobsRaw : Array.isArray(jobsRaw?.jobs) ? jobsRaw.jobs : []
const OPEN = new Set(['queued', 'running', 'proposal'])
const stuck = jobs.filter((job) => OPEN.has(job.status) && Date.now() - (Number(job.updatedAt) || Number(job.createdAt) || 0) > 45 * 60 * 1000)
if (stuck.length) {
  add('stuck', 'warn', `${stuck.length} 个整理任务卡住超过 45 分钟`, stuck.slice(0, 3).map((j) => j.title || j.path).join('、'))
} else {
  const openCount = jobs.filter((job) => OPEN.has(job.status)).length
  add('queue', 'ok', '整理队列通畅', openCount ? `在跑 ${openCount} 个` : '队列空')
}

// 3) worker 心跳（抓取端必须在线，否则一条稿都进不来）
const workers = await api('/workers')
const retired = new Set(Array.isArray(settings.retiredWorkers) ? settings.retiredWorkers : ['mac-mini'])
if (workers.ok) {
  const list = (workers.data?.workers || []).filter((w) => !retired.has(w.name))
  const stale = list.filter((w) => !w.online || Number(w.age_sec) > 480)
  if (!list.length) {
    add('worker', 'warn', '没有任何抓取 worker 在线', '服务端 /workers 为空')
  } else if (stale.length) {
    add('worker', 'warn', '抓取 worker 心跳超时', stale.map((w) => `${w.name}（${w.age_sec}s）`).join('、'))
  } else {
    add('worker', 'ok', '抓取 worker 在线', list.map((w) => `${w.name} ${w.age_sec}s`).join('、'))
  }
} else {
  add('worker', 'warn', '查不到 worker 心跳', workers.error || '')
}

// 4) 服务端最近 24 小时失败的摄取
const failed = await api('/jobs?status=failed')
const alertState = readJson(ALERT_FILE, {}) || {}
const knownFailed = new Set(Array.isArray(alertState.knownFailed) ? alertState.knownFailed : [])
if (failed.ok) {
  const rows = failed.data?.jobs || failed.data || []
  // 只对「第一次见到的失败」报警：历史失败（内容其实已经补进去了）不该天天喊。
  const fresh = rows.filter((job) => !knownFailed.has(job.id))
  if (fresh.length) {
    add('failed', 'warn', `新增 ${fresh.length} 条摄取失败`, fresh.slice(0, 2).map((j) => `${j.url || j.id}：${String(j.error || '').slice(0, 120)}`).join(' ｜ '))
  } else {
    add('failed', 'ok', '没有新的失败摄取', rows.length ? `历史 ${rows.length} 条（已记账，不再重复提醒）` : '')
  }
  // 记账：见过的 id 不再报警
  for (const job of rows) knownFailed.add(job.id)
  alertState.knownFailed = [...knownFailed].slice(-500)
} else {
  add('failed', 'warn', '查不到失败列表', failed.error || '')
}

// 5) git 是否领先/落后
const ahead = await git(['rev-list', '--count', '@{u}..HEAD'])
const behind = await git(['rev-list', '--count', 'HEAD..@{u}'])
const status = await git(['status', '--porcelain'])
const dirtyTracked = status.ok ? status.stdout.split('\n').filter((l) => l && !l.startsWith('??')).length : 0
if (ahead.ok && Number(ahead.stdout) > 0) {
  add('ahead', 'warn', `本地领先 origin ${ahead.stdout} 个提交`, '提交没推出去，远端可能连不上')
} else {
  add('git', 'ok', '本地与 origin 同步', `落后 ${behind.ok ? behind.stdout : '?'}`)
}
if (dirtyTracked > 0) {
  add('dirty', 'ok', `工作区有 ${dirtyTracked} 个已跟踪改动`, '下一轮自动提交会带上')
}

// 6) 磁盘
try {
  const stats = statfsSync(VAULT)
  const freeGb = (stats.bavail * stats.bsize) / 1024 ** 3
  if (freeGb < 10) add('disk', 'warn', `磁盘只剩 ${freeGb.toFixed(1)}GB`, VAULT)
  else add('disk', 'ok', '磁盘充足', `${freeGb.toFixed(0)}GB 可用`)
} catch {}

const warns = checks.filter((c) => c.level === 'warn')
const now = new Date()
const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`

const body = [
  '# 摄入闭环状态',
  '',
  `更新：${stamp}`,
  '',
  `结论：${warns.length ? `⚠️ ${warns.length} 个问题` : '✅ 正常'}`,
  '',
  ...checks.map((c) => `- ${c.level === 'warn' ? '⚠️' : '✅'} **${c.title}**${c.detail ? ` — ${c.detail}` : ''}`),
  '',
  '> 由 `scripts/watchdog.mjs` 生成；有问题会推系统通知，同一问题 30 分钟内不重复。',
  '',
].join('\n')

mkdirSync(STATE_DIR, { recursive: true })
writeFileSync(STATUS_FILE, body, 'utf8')

// vault 里只在异常、或跨天时留一份，避免每 10 分钟制造一次提交
const alerts = readJson(ALERT_FILE, {}) || {}
const today = stamp.slice(0, 10)
if (warns.length || alerts.vaultCopyDay !== today) {
  const target = join(VAULT, '02 outputs', 'health', 'ingest-status.md')
  try {
    mkdirSync(join(VAULT, '02 outputs', 'health'), { recursive: true })
    writeFileSync(target, body, 'utf8')
    alerts.vaultCopyDay = today
  } catch {}
}

// 通知：同样的问题 30 分钟内只喊一次
const notify = async (title, message) => {
  if (PRINT_ONLY) return
  try {
    const esc = (s) => String(s).replace(/["\\]/g, '\\$&')
    await run('osascript', ['-e', `display notification "${esc(message)}" with title "${esc(title)}" sound name "Ping"`])
  } catch {}
  const hook = settings.alertWebhook
  if (hook) {
    try {
      await fetch(hook, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ msgtype: 'text', text: { content: `${title}\n${message}` } }),
        signal: AbortSignal.timeout(8000),
      })
    } catch {}
  }
}

const alerted = []
for (const warn of warns) {
  const last = Number(alerts[warn.id]) || 0
  if (Date.now() - last < ALERT_COOLDOWN_MS) continue
  alerts[warn.id] = Date.now()
  alerted.push(warn)
}
if (alerted.length) {
  await notify(
    `知识库闭环：${alerted.length} 个问题`,
    alerted.map((w) => `${w.title}${w.detail ? `（${w.detail}）` : ''}`).join('；').slice(0, 200),
  )
}
writeFileSync(ALERT_FILE, JSON.stringify({ ...alerts, knownFailed: alertState.knownFailed }, null, 1), 'utf8')

if (PRINT_ONLY) console.log(body)
else console.log(`[watchdog] ${warns.length ? `${warns.length} warn` : 'ok'} · notified ${alerted.length}`)
process.exit(warns.length ? 1 : 0)
