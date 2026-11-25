// 配置、路径与凭据。所有本地状态都放在 DSH 的用户数据目录，不写进仓库。
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

const DEFAULT_VAULT = join(homedir(), 'Documents', 'ob_vault')
const DEFAULT_API_BASE = 'https://rainpark.cn/api'
const CREDENTIALS_FILE = join(homedir(), '.config', 'kb-ingest', 'credentials.env')

export function dataDir() {
  const base = process.env.DSH_HOME || join(homedir(), '.dsh')
  const dir = join(base, 'raincoat-kb-desk')
  mkdirSync(dir, { recursive: true })
  return dir
}

function settingsFile() {
  return join(dataDir(), 'settings.json')
}

const DEFAULTS = {
  vault: DEFAULT_VAULT,
  apiBase: DEFAULT_API_BASE,
  credentialsFile: CREDENTIALS_FILE,
  // 体检阈值，按 vault/AGENTS.md 的规则来
  inboxWarnDays: 3,
  inboxDangerDays: 7,
  threadWarnDays: 60,
  threadDangerDays: 90,
  stalePageDays: 90,
  logStaleDays: 7,
  // 自动闭环：worker 抓完 → 本地 pull → 整理 → 写入 → 提交推送
  autoIngest: true,
  autoApply: true,
  autoPush: true,
  watchSeconds: 60,
  // 闭环护栏：防止「一个坏条目冻住全部产出」
  // 1) 提案超过这么多分钟还没落盘就判废，释放「提交」这一步
  proposalTtlMinutes: 30,
  // 2) 同一篇整理失败这么多次后停下等人看，不再无限重试烧模型
  maxAttemptsPerDoc: 5,
  // 3) 命中配额/429 后暂停入队这么久，避免每分钟重撞网关
  quotaCooldownMinutes: 10,
}

export function expandHome(value) {
  if (typeof value !== 'string') return value
  if (value === '~') return homedir()
  if (value.startsWith('~/')) return join(homedir(), value.slice(2))
  return value
}

export function readSettings() {
  let saved = {}
  try {
    saved = JSON.parse(readFileSync(settingsFile(), 'utf8'))
  } catch {
    saved = {}
  }
  const merged = { ...DEFAULTS, ...saved }
  merged.vault = expandHome(merged.vault)
  return merged
}

/** 只允许改白名单字段，避免界面把插件写崩。 */
export function writeSettings(patch) {
  const next = { ...readSettings(), ...(patch && typeof patch === 'object' ? patch : {}) }
  const clean = {}
  for (const key of Object.keys(DEFAULTS)) {
    if (next[key] !== undefined) clean[key] = next[key]
  }
  writeFileSync(settingsFile(), `${JSON.stringify(clean, null, 2)}\n`, 'utf8')
  return readSettings()
}

/** 解析 KEY=VALUE 形式的凭据文件；只在进程内使用，不回传前端、不写日志。 */
export function readCredentials(settings = readSettings()) {
  const out = { apiBase: settings.apiBase, ingestToken: null, workerToken: null, source: null }
  const file = expandHome(settings.credentialsFile)
  if (!file || !existsSync(file)) return out
  let raw = ''
  try {
    raw = readFileSync(file, 'utf8')
  } catch {
    return out
  }
  const env = {}
  for (const line of raw.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const index = trimmed.indexOf('=')
    if (index <= 0) continue
    const key = trimmed.slice(0, index).trim()
    let value = trimmed.slice(index + 1).trim()
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1)
    }
    env[key] = value
  }
  out.ingestToken = env.INGEST_TOKEN || env.KB_INGEST_TOKEN || null
  out.workerToken = env.WORKER_TOKEN || env.KB_WORKER_TOKEN || null
  if (!out.apiBase && env.KB_API_BASE) out.apiBase = env.KB_API_BASE
  out.source = file
  return out
}

export function vaultRoot(settings = readSettings()) {
  return resolve(expandHome(settings.vault))
}
