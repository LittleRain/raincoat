import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/** 应用根：apps/acg-capture；引擎与 references 都在同目录的 engines/ 下 */
export const ROOT = fileURLToPath(new URL('..', import.meta.url))
export const ENGINES = path.join(ROOT, 'engines')
export const DATA_DIR = process.env.ACG_DATA_DIR || path.join(os.homedir(), '.dsh', 'acg-capture')
export const RUNS_DIR = path.join(DATA_DIR, 'runs')
export const CHANNELS_FILE = path.join(ENGINES, 'references', 'channels.json')
export const ENGINE = path.join(ENGINES, 'scripts', 'acg_run.py')
export const BAG_ENGINE = path.join(ENGINES, 'scripts', 'bag_run.py')
export const VG_ENGINE = path.join(ENGINES, 'scripts', 'vg_run.py')
export const BAG_REFS = path.join(ENGINES, 'references')

function alive(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

function readJson(file, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return fallback
  }
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const tmp = `${file}.tmp`
  fs.writeFileSync(tmp, JSON.stringify(value, null, 1))
  fs.renameSync(tmp, file)
}

/** 上海时区的 run id，和引擎的命名保持一致，列表才能按名字倒序。 */
export function newRunId(kind) {
  const parts = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
    .format(new Date())
    .replace(/[-:]/g, '')
    .replace(' ', '-')
  return `r-${parts}-${kind}`
}

/** 抓新品的「查了什么」：微博/小红书原文条数与渠道数，老运行也能从 feeds.json 补出来。 */
function feedSummary(dir) {
  const feeds = readJson(path.join(dir, 'feeds.json'))
  if (!feeds) return null
  return {
    items: Array.isArray(feeds.items) ? feeds.items.length : 0,
    channels: Array.isArray(feeds.captured) ? feeds.captured.length : 0,
    errors: Array.isArray(feeds.errors) ? feeds.errors.length : 0,
  }
}

export function listRuns({ kind = '', limit = 20 } = {}) {
  if (!fs.existsSync(RUNS_DIR)) return []
  const dirs = fs
    .readdirSync(RUNS_DIR)
    .filter((name) => name.startsWith('r-'))
    .sort()
    .reverse()
  const runs = []
  for (const name of dirs) {
    const dir = path.join(RUNS_DIR, name)
    const data = readJson(path.join(dir, 'run.json'))
    if (!data) continue
    if (kind && data.kind !== kind) continue
    if (!data.feeds) data.feeds = feedSummary(dir)
    runs.push(summarize(data))
    if (runs.length >= limit) break
  }
  return runs
}

export function summarize(run) {
  return {
    id: run.id,
    kind: run.kind,
    trigger: run.trigger,
    dryRun: run.dryRun,
    status: run.status,
    stage: run.stage,
    startedAt: run.startedAt,
    endedAt: run.endedAt,
    counts: run.counts || {},
    table: run.table || {},
    params: run.params || {},
    feeds: run.feeds || null,
    // 「这一轮到底在抓什么」：品牌/渠道构成、分组、或本批盘子
    scope: run.scope || null,
    // 补齐的「查了什么」= 本批盯的是哪几个盘，取前 8 个够看清区别
    batch: Array.isArray(run.batch)
      ? run.batch.slice(0, 8).map((item) => ({ pan: item.pan || '', gaps: item.gaps || [] }))
      : [],
    itemCount: Array.isArray(run.items) ? run.items.length : 0,
    // 本批实际派了几个盘（params.batchSize 是上限，不再等于批的大小）
    batchCount: Array.isArray(run.batch) ? run.batch.length : 0,
    error: run.error || null,
  }
}

const RUN_ID_RE = /^r-[0-9]{8}-[0-9]{6}-(backfill|discover|bag-discover|vg-discover)$/

export function readRun(id) {
  if (!RUN_ID_RE.test(String(id || ''))) return null
  const dir = path.join(RUNS_DIR, id)
  const data = readJson(path.join(dir, 'run.json'))
  if (data && !data.feeds) data.feeds = feedSummary(dir)
  return data
}

export function readEvents(id, after = 0) {
  if (!RUN_ID_RE.test(String(id || ''))) return []
  const file = path.join(RUNS_DIR, id, 'events.jsonl')
  if (!fs.existsSync(file)) return []
  const lines = fs.readFileSync(file, 'utf8').split('\n')
  const events = []
  for (const line of lines) {
    if (!line.trim()) continue
    try {
      const event = JSON.parse(line)
      if ((event.seq || 0) > after) events.push(event)
    } catch {
      // 半行（运行中正在写）忽略，下一轮再读
    }
  }
  return events.slice(-200)
}

/** 宿主重启后，进程没了但 run.json 还写着 running：标记为中断，避免 UI 假装在跑。 */
export function recoverRuns() {
  if (!fs.existsSync(RUNS_DIR)) return
  for (const name of fs.readdirSync(RUNS_DIR)) {
    if (!name.startsWith('r-')) continue
    const file = path.join(RUNS_DIR, name, 'run.json')
    const data = readJson(file)
    if (!data || data.status !== 'running') continue
    // 引擎进程还活着就不算中断（桌面与 web 两个宿主共用同一份 run 目录）
    if (data.pid && alive(data.pid)) continue
    data.status = 'interrupted'
    data.stage = 'done'
    data.endedAt = new Date().toISOString()
    data.error = '宿主重启，运行中断'
    writeJson(file, data)
  }
}

export function readChannels() {
  const data = readJson(CHANNELS_FILE, { brands: [] })
  return Array.isArray(data?.brands) ? data : { brands: [] }
}

export function updateChannel(id, patch) {
  const data = readChannels()
  const row = data.brands.find((item) => item.id === id)
  if (!row) return null
  Object.assign(row, patch, { updatedAt: new Date().toISOString() })
  writeJson(CHANNELS_FILE, data)
  return row
}


function readRefs(name, fallback) {
  return readJson(path.join(BAG_REFS, name), fallback)
}

export function readBagLeads() {
  return readRefs('bag-leads.json', { leads: [] })
}

export function readBagChannels() {
  return readRefs('bag-channels.json', { channels: [] })
}

export function readBagLedgerCache() {
  return readJson(path.join(DATA_DIR, 'cache', 'bag-ledger.json'), { bags: [] })
}

export function readVgSources() {
  return readRefs('vg-sources.json', { channels: [], discovery: {}, thresholds: {} })
}

export function readVgLedgerCache() {
  return readJson(path.join(DATA_DIR, 'cache', 'vg-ledger.json'), { items: [] })
}
