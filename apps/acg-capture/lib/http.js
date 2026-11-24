import { execFile } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { BAG_ENGINE, DATA_DIR, ENGINE, ROOT, VG_ENGINE, listRuns, readBagChannels, readBagLeads, readBagLedgerCache, readChannels, readEvents, readRun, readVgLedgerCache, readVgSources, updateChannel } from './store.js'
import { startRun, stopRun, stderrOf, runningIds } from './runner.js'

const PREFIX = '/acg-capture/api'

/**
 * 裁决（采纳 / 判废）串行化。
 *
 * 面板上同时点多个「采纳」时，每个点击都会 spawn 一个引擎进程去读改写同一个 run.json 并写企微表。
 * 引擎侧已经用文件锁兜底（acg/common.py 的 run_lock），这里再按 runId 排个队，
 * 让同一条 run 的裁决先进先出：既不会并发轰炸企微接口，也不会出现「后点的先写」。
 */
const decideQueues = new Map()

function enqueueDecide(key, task) {
  const previous = decideQueues.get(key) || Promise.resolve()
  const current = previous.then(task, task)
  const tail = current.then(
    () => {},
    () => {},
  )
  decideQueues.set(key, tail)
  tail.then(() => {
    if (decideQueues.get(key) === tail) decideQueues.delete(key)
  })
  return current
}

function json(res, status, body) {
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(payload),
  })
  res.end(payload)
}

function readJson(req) {
  return new Promise((resolve) => {
    let raw = ''
    req.on('data', (chunk) => {
      raw += chunk
      if (raw.length > 200_000) req.destroy()
    })
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : {})
      } catch {
        resolve({})
      }
    })
    req.on('error', () => resolve({}))
  })
}

function bustBagSnapshot() {
  try {
    fs.unlinkSync(BAG_SNAPSHOT_FILE)
  } catch {
    /* 没有缓存就不用删 */
  }
}

function bustVgSnapshot() {
  try {
    fs.unlinkSync(VG_SNAPSHOT_FILE)
  } catch {
    /* 没有缓存就不用删 */
  }
}

function readJsonFile(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return null
  }
}

const SNAPSHOT_FILE = path.join(DATA_DIR, 'cache', 'snapshot.json')
const BAG_SNAPSHOT_FILE = path.join(DATA_DIR, 'cache', 'bag-snapshot.json')
const VG_SNAPSHOT_FILE = path.join(DATA_DIR, 'cache', 'vg-snapshot.json')
const BAG_SNAPSHOT_TTL = 5 * 60 * 1000
const SNAPSHOT_TTL = 10 * 60 * 1000
let snapshotRefreshing = false

function readSnapshotFile() {
  try {
    const raw = JSON.parse(fs.readFileSync(SNAPSHOT_FILE, 'utf8'))
    return raw
  } catch {
    return null
  }
}

function writeSnapshotFile(value) {
  fs.mkdirSync(path.dirname(SNAPSHOT_FILE), { recursive: true })
  const tmp = `${SNAPSHOT_FILE}.tmp`
  fs.writeFileSync(tmp, JSON.stringify({ ...value, cachedAt: Date.now() }))
  fs.renameSync(tmp, SNAPSHOT_FILE)
}

function runEngine(args, timeout = 120_000) {
  return new Promise((resolve) => {
    const env = { ...process.env, PATH: [path.join(os.homedir(), '.local', 'bin'), process.env.PATH || ''].join(':') }
    execFile('python3', [ENGINE, ...args], { cwd: ROOT, env, timeout, maxBuffer: 4 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error) {
        // 引擎的失败原因在 stdout 的 JSON 里（exit 1），stderr 通常只有人读日志
        let message = (stderr || '').trim()
        try {
          const parsed = JSON.parse(stdout)
          if (parsed?.error) message = parsed.error
        } catch {
          /* stdout 不是 JSON，退回原始信息 */
        }
        if (!message) message = error.message || '引擎执行失败'
        resolve({ ok: false, error: message.slice(0, 400) })
        return
      }
      try {
        resolve({ ok: true, result: JSON.parse(stdout) })
      } catch {
        resolve({ ok: false, error: stdout.slice(0, 300) })
      }
    })
  })
}

function runVg(args, timeout = 180_000) {
  return new Promise((resolve) => {
    const env = { ...process.env, PATH: [path.join(os.homedir(), '.local', 'bin'), process.env.PATH || ''].join(':') }
    execFile('python3', [VG_ENGINE, ...args], { cwd: ROOT, env, timeout, maxBuffer: 8 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error && !stdout) {
        resolve({ ok: false, error: (stderr || error.message || '引擎执行失败').slice(0, 400) })
        return
      }
      try {
        resolve(JSON.parse(stdout))
      } catch {
        resolve({ ok: false, error: (stderr || stdout || 'vg 引擎返回非 JSON').slice(0, 300) })
      }
    })
  })
}

function runBag(args, timeout = 180_000) {
  return new Promise((resolve) => {
    const env = { ...process.env, PATH: [path.join(os.homedir(), '.local', 'bin'), process.env.PATH || ''].join(':') }
    execFile('python3', [BAG_ENGINE, ...args], { cwd: ROOT, env, timeout, maxBuffer: 8 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error && !stdout) {
        resolve({ ok: false, error: (stderr || error.message || '引擎执行失败').slice(0, 400) })
        return
      }
      try {
        resolve(JSON.parse(stdout))
      } catch {
        resolve({ ok: false, error: (stderr || stdout || 'bag 引擎返回非 JSON').slice(0, 300) })
      }
    })
  })
}

function runSnapshot() {
  return new Promise((resolve) => {
    const env = { ...process.env, PATH: [path.join(os.homedir(), '.local', 'bin'), process.env.PATH || ''].join(':') }
    execFile(
      'python3',
      [ENGINE, '--snapshot'],
      { cwd: ROOT, env, timeout: 60_000, maxBuffer: 4 * 1024 * 1024 },
      (error, stdout, stderr) => {
        if (error) {
          resolve({ error: (stderr || error.message || '').slice(0, 300) })
          return
        }
        try {
          resolve(JSON.parse(stdout))
        } catch {
          resolve({ error: 'snapshot 解析失败' })
        }
      },
    )
  })
}

function probeChannel(channel) {
  const url = channel?.url || ''
  if (!url.startsWith('http')) {
    return Promise.resolve({ ok: false, error: 'manual_channel', samples: [] })
  }
  return fetch(url, {
    signal: AbortSignal.timeout(15_000),
    headers: { 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130 Safari/537.36' },
  })
    .then(async (response) => {
      const text = await response.text()
      const titleMatch = text.match(/<title[^>]*>([\s\S]*?)<\/title>/i)
      const samples = []
      const re = /<(h1|h2|h3|a)[^>]*>([\s\S]*?)<\/\1>/gi
      let match
      while ((match = re.exec(text)) && samples.length < 5) {
        const value = match[2].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
        if (value.length >= 2 && value.length <= 80) samples.push(value)
      }
      return {
        ok: response.ok,
        status: response.status,
        title: titleMatch ? titleMatch[1].replace(/\s+/g, ' ').trim().slice(0, 120) : '',
        samples,
      }
    })
    .catch((error) => ({ ok: false, error: error.name === 'TimeoutError' ? 'timeout' : String(error.message || error), samples: [] }))
}

/**
 * 同源/会话校验。旧宿主（DSH < 0.2.2）由插件自己补一层，靠 `connection.requestRejection`；
 * 该 API 在 DSH 0.2.2 起被 `connection.admit()` 取代，而 admit 内部读取
 * `connection.authentication` 需要插件先注入该服务，否则抛错。
 * 新的 carrier 已默认对所有 webServer 路由鉴权，所以这里只在旧 API 存在时补校验。
 */
function legacyRejection(ctx, headers) {
  const connection = typeof ctx?.get === 'function' ? ctx.get('connection') : ctx?.connection
  if (typeof connection?.requestRejection === 'function') {
    try {
      return connection.requestRejection({ headers })
    } catch {
      return 503
    }
  }
  return undefined
}

export function registerHttp(ctx) {
  return ctx.webServer.register({
    kind: 'prefix',
    path: PREFIX,
    handler: async (req, res) => {
      try {
        const rejection = legacyRejection(ctx, req.headers)
        if (rejection === 401 || rejection === 403) {
          return json(res, rejection, { error: rejection === 401 ? '需要登录' : '来源不可信' })
        }
        if (rejection !== undefined) {
          return json(res, 503, { error: '来源校验暂不可用' })
        }
        const url = new URL(req.url || '/', 'http://127.0.0.1')
        const route = url.pathname.slice(PREFIX.length) || '/'
        const method = (req.method || 'GET').toUpperCase()
        // 线索/渠道/运行写操作后，快照缓存必须失效，否则前端还会看到旧统计
        if (route.startsWith('/bag/') && method !== 'GET') bustBagSnapshot()
        if (route.startsWith('/vg/') && method !== 'GET') bustVgSnapshot()

        if (method === 'GET' && route === '/health') {
          return json(res, 200, { ok: true, plugin: 'acg-capture', running: runningIds() })
        }

        if (method === 'GET' && route === '/snapshot') {
          const force = url.searchParams.get('force') === '1'
          const cached = readSnapshotFile()
          const fresh = cached && Date.now() - (cached.cachedAt || 0) < SNAPSHOT_TTL
          if (!force && fresh) return json(res, 200, { ...cached, cached: true })
          if (!force && cached) {
            // 先回旧值，后台刷新；避免每次打开子页都等两次拉表
            if (!snapshotRefreshing) {
              snapshotRefreshing = true
              runSnapshot().then(writeSnapshotFile).finally(() => {
                snapshotRefreshing = false
              })
            }
            return json(res, 200, { ...cached, cached: true, stale: true })
          }
          const value = await runSnapshot()
          if (!value.error) writeSnapshotFile(value)
          return json(res, 200, value)
        }

        if (method === 'GET' && route === '/runs') {
          const kind = url.searchParams.get('kind') || ''
          return json(res, 200, { runs: listRuns({ kind: kind || undefined, limit: 20 }), running: runningIds() })
        }

        const runMatch = route.match(/^\/runs\/(r-[0-9]{8}-[0-9]{6}-(?:backfill|discover))$/)
        if (method === 'GET' && runMatch) {
          const run = readRun(runMatch[1])
          if (!run) return json(res, 404, { error: 'run 不存在' })
          return json(res, 200, { run, running: runningIds().includes(run.id), stderr: stderrOf(run.id) })
        }

        const eventMatch = route.match(/^\/runs\/(r-[0-9]{8}-[0-9]{6}-(?:backfill|discover))\/events$/)
        if (method === 'GET' && eventMatch) {
          const after = Number(url.searchParams.get('after') || 0)
          return json(res, 200, { events: readEvents(eventMatch[1], after) })
        }

        const decideMatch = route.match(
          /^\/runs\/(r-[0-9]{8}-[0-9]{6}-(?:backfill|discover))\/items\/([A-Za-z0-9_-]+)\/decide$/,
        )
        if (method === 'POST' && decideMatch) {
          const body = await readJson(req)
          const decision = body.decision === 'reject' ? 'reject' : 'accept'
          const args = ['--decide', decideMatch[1], '--item', decideMatch[2], '--decision', decision]
          if (!body.dryRun) args.push('--write')
          if (body.note) args.push('--note', String(body.note).slice(0, 500))
          if (body.source) args.push('--source', String(body.source).slice(0, 500))
          const outcome = await enqueueDecide(`acg:${decideMatch[1]}`, () => runEngine(args))
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        const stopMatch = route.match(/^\/runs\/(r-[0-9]{8}-[0-9]{6}-(?:backfill|discover))\/stop$/)
        if (method === 'POST' && stopMatch) {
          return json(res, 200, { stopped: stopRun(stopMatch[1]) })
        }

        if (method === 'POST' && route === '/runs') {
          const body = await readJson(req)
          const kind = body.kind === 'discover' ? 'discover' : 'backfill'
          const started = startRun({
            kind,
            write: Boolean(body.write),
            batch: Math.min(999, Math.max(1, Number(body.batch) || 999)),
            since: typeof body.since === 'string' ? body.since : '',
            trigger: 'manual',
          })
          // 引擎建 run.json 有几百毫秒延迟；先等它落地再回 runId，
          // 否则前端第一轮轮询会 404，被当成启动失败（2026-11-16 实测）。
          const runFile = path.join(DATA_DIR, 'runs', started.runId, 'run.json')
          for (let i = 0; i < 30 && !fs.existsSync(runFile); i += 1) {
            await new Promise((resolve) => setTimeout(resolve, 100))
          }
          if (!fs.existsSync(runFile)) {
            // 引擎没建出 run.json：多半是锁被占（上一轮还在跑）或启动即失败，
            // 把子进程 stderr 带回去，前端才有可读的原因。
            const detail = (stderrOf(started.runId) || '').trim()
            return json(res, 409, {
              error: detail || '引擎启动失败，没有生成 run.json',
              runId: started.runId,
            })
          }
          return json(res, 200, { ...started, ready: true })
        }

        if (method === 'GET' && route === '/channels') {
          const data = readChannels()
          return json(res, 200, { brands: data.brands, file: 'workflows/kuji-tracking/references/channels.json' })
        }

        const channelMatch = route.match(/^\/channels\/([a-z0-9-]+)$/)
        if (method === 'PUT' && channelMatch) {
          const body = await readJson(req)
          const allowed = ['status', 'channel', 'type', 'url', 'note', 'canAnswer']
          const patch = {}
          for (const key of allowed) {
            if (key in body) patch[key] = body[key]
          }
          if (patch.status) patch.confirmedAt = patch.status === 'confirmed' ? new Date().toISOString() : null
          const row = updateChannel(channelMatch[1], patch)
          if (!row) return json(res, 404, { error: '渠道不存在' })
          return json(res, 200, { channel: row })
        }

        const probeMatch = route.match(/^\/channels\/([a-z0-9-]+)\/probe$/)
        if (method === 'POST' && probeMatch) {
          const row = readChannels().brands.find((item) => item.id === probeMatch[1])
          if (!row) return json(res, 404, { error: '渠道不存在' })
          const evidence = await probeChannel(row)
          updateChannel(probeMatch[1], { lastProbe: { ...evidence, at: new Date().toISOString() } })
          return json(res, 200, { evidence })
        }

        // ---- 官方福袋 ----------------------------------------------------
        if (method === 'GET' && route === '/bag/snapshot') {
          const force = url.searchParams.get('force') === '1'
          const cached = readJsonFile(BAG_SNAPSHOT_FILE)
          const fresh = cached && Date.now() - (cached.cachedAt || 0) < BAG_SNAPSHOT_TTL
          if (!force && fresh) return json(res, 200, { ...cached, cached: true })
          const value = await runBag(['--snapshot'], 90_000)
          if (value && !value.error) {
            fs.mkdirSync(path.dirname(BAG_SNAPSHOT_FILE), { recursive: true })
            const tmp = `${BAG_SNAPSHOT_FILE}.tmp`
            fs.writeFileSync(tmp, JSON.stringify({ ...value, cachedAt: Date.now() }))
            fs.renameSync(tmp, BAG_SNAPSHOT_FILE)
          }
          return json(res, 200, value)
        }

        if (method === 'GET' && route === '/bag/leads') {
          const data = readBagLeads()
          return json(res, 200, { leads: data.leads || [], channels: readBagChannels().channels || [] })
        }

        if (method === 'POST' && route === '/bag/leads') {
          const body = await readJson(req)
          const outcome = await runBag(['--leads-upsert-json', JSON.stringify(body)], 60_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        const bagLeadMatch = route.match(/^\/bag\/leads\/(lead-[a-z0-9-]+)$/)
        if (method === 'DELETE' && bagLeadMatch) {
          const outcome = await runBag(['--leads-delete', bagLeadMatch[1]], 60_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        const bagLeadStatus = route.match(/^\/bag\/leads\/(lead-[a-z0-9-]+)\/status$/)
        if (method === 'PUT' && bagLeadStatus) {
          const body = await readJson(req)
          const status = body.status === 'paused' ? 'paused' : 'active'
          const outcome = await runBag(['--leads-status', bagLeadStatus[1], '--status', status], 60_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        if (method === 'GET' && route === '/bag/channels') {
          return json(res, 200, { channels: readBagChannels().channels || [], file: 'workflows/kuji-tracking/references/bag-channels.json' })
        }

        if (method === 'POST' && route === '/bag/channels') {
          const body = await readJson(req)
          const outcome = await runBag(['--channels-upsert-json', JSON.stringify(body)], 60_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        const bagChannelMatch = route.match(/^\/bag\/channels\/([a-z0-9-]+)$/)
        if (method === 'DELETE' && bagChannelMatch) {
          const outcome = await runBag(['--channels-delete', bagChannelMatch[1]], 60_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        const bagProbeMatch = route.match(/^\/bag\/channels\/([a-z0-9-]+)\/probe$/)
        if (method === 'POST' && bagProbeMatch) {
          const outcome = await runBag(['--channels-probe', bagProbeMatch[1]], 120_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        if (method === 'GET' && route === '/bag/ledger') {
          const cached = readBagLedgerCache()
          return json(res, 200, { bags: cached.bags || [], at: cached.at || '' })
        }

        if (method === 'GET' && route === '/bag/runs') {
          return json(res, 200, { runs: listRuns({ kind: 'bag-discover', limit: 20 }), running: runningIds() })
        }

        if (method === 'POST' && route === '/bag/runs') {
          const body = await readJson(req)
          const active = listRuns({ kind: 'bag-discover', limit: 20 })
          const busy = active.find((run) => run.status === 'running' && runningIds().includes(run.id))
          if (busy) {
            return json(res, 409, { error: `已有官方福袋抓取在跑：${busy.id}`, runId: busy.id })
          }
          const started = startRun({
            kind: 'bag-discover',
            write: Boolean(body.write),
            leads: typeof body.leads === 'string' ? body.leads : '',
            lanes: typeof body.lanes === 'string' ? body.lanes : 'workbuddy,deepseek',
            modes: typeof body.modes === 'string' ? body.modes : '',
          })
          return json(res, 200, { ...started, ready: true })
        }

        const bagRunMatch = route.match(/^\/bag\/runs\/(r-[0-9]{8}-[0-9]{6}-bag-discover)$/)
        if (method === 'GET' && bagRunMatch) {
          const run = readRun(bagRunMatch[1])
          if (!run) return json(res, 404, { error: 'run 不存在' })
          return json(res, 200, { run, running: runningIds().includes(run.id), stderr: stderrOf(run.id) })
        }

        const bagStopMatch = route.match(/^\/bag\/runs\/(r-[0-9]{8}-[0-9]{6}-bag-discover)\/stop$/)
        if (method === 'POST' && bagStopMatch) {
          return json(res, 200, { stopped: stopRun(bagStopMatch[1]) })
        }

        // 官方福袋的 item id 带中文（bag-20261117-原神-…），而且从 URL 里来的是
        // percent-encoded：这里必须放宽到 [^/]+ 再解码，否则 404「未知路由」。
        const bagDecideMatch = route.match(
          /^\/bag\/runs\/(r-[0-9]{8}-[0-9]{6}-bag-discover)\/items\/([^/]+)\/decide$/,
        )
        if (method === 'POST' && bagDecideMatch) {
          const body = await readJson(req)
          const decision = body.decision === 'reject' ? 'reject' : 'accept'
          const itemId = decodeURIComponent(bagDecideMatch[2])
          const args = ['--decide', bagDecideMatch[1], '--item', itemId, '--decision', decision]
          if (body.write) args.push('--write')
          if (body.note) args.push('--note', String(body.note).slice(0, 500))
          if (body.source) args.push('--source', String(body.source).slice(0, 500))
          const outcome = await enqueueDecide(`bag:${bagDecideMatch[1]}`, () => runBag(args, 90_000))
          return json(res, outcome.ok ? 200 : 400, outcome)
        }


        // ---- 游戏虚拟商品 ------------------------------------------------
        if (method === 'GET' && (route === '/vg/snapshot' || route === '/vg/summary')) {
          const force = url.searchParams.get('force') === '1'
          const cached = readJsonFile(VG_SNAPSHOT_FILE)
          const fresh = cached && Date.now() - (cached.cachedAt || 0) < BAG_SNAPSHOT_TTL
          if (!force && fresh) return json(res, 200, { ...cached, cached: true })
          const value = await runVg(['--snapshot'], 120_000)
          if (value && !value.ok === false && !value.error) {
            fs.mkdirSync(path.dirname(VG_SNAPSHOT_FILE), { recursive: true })
            const tmp = `${VG_SNAPSHOT_FILE}.tmp`
            fs.writeFileSync(tmp, JSON.stringify({ ...value, cachedAt: Date.now() }))
            fs.renameSync(tmp, VG_SNAPSHOT_FILE)
          }
          return json(res, 200, value)
        }

        if (method === 'GET' && route === '/vg/channels') {
          const sources = readVgSources()
          return json(res, 200, {
            channels: sources.channels || [],
            file: 'workflows/kuji-tracking/references/vg-sources.json',
          })
        }

        if (method === 'POST' && route === '/vg/channels') {
          const body = await readJson(req)
          const outcome = await runVg(['--channels-upsert-json', JSON.stringify(body)], 60_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        const vgChannelMatch = route.match(/^\/vg\/channels\/([a-z0-9-]+)$/)
        if (method === 'DELETE' && vgChannelMatch) {
          const outcome = await runVg(['--channels-delete', vgChannelMatch[1]], 60_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        const vgProbeMatch = route.match(/^\/vg\/channels\/([a-z0-9-]+)\/probe$/)
        if (method === 'POST' && vgProbeMatch) {
          const outcome = await runVg(['--channels-probe', vgProbeMatch[1]], 120_000)
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        if (method === 'GET' && route === '/vg/ledger') {
          let cached = readVgLedgerCache()
          if (!(cached.items || []).length) {
            // 缓存还没建（宿主刚重启 / 首次打开汇总页）：跑一次只读 snapshot 顺手刷新缓存
            await runVg(['--snapshot'], 120_000)
            cached = readVgLedgerCache()
          }
          return json(res, 200, { items: cached.items || [], at: cached.at || '', byGame: cached.byGame || {} })
        }

        if (method === 'GET' && route === '/vg/runs') {
          return json(res, 200, { runs: listRuns({ kind: 'vg-discover', limit: 20 }), running: runningIds() })
        }

        if (method === 'POST' && route === '/vg/runs') {
          const body = await readJson(req)
          const active = listRuns({ kind: 'vg-discover', limit: 20 })
          const busy = active.find((run) => run.status === 'running' && runningIds().includes(run.id))
          if (busy) {
            return json(res, 409, { error: `已有游戏虚拟商品抓取在跑：${busy.id}`, runId: busy.id })
          }
          const started = startRun({
            kind: 'vg-discover',
            write: Boolean(body.write),
            lanes: typeof body.lanes === 'string' ? body.lanes : 'workbuddy,deepseek',
            windowDays: Number(body.windowDays) || 0,
            mode: body.mode === 'discover' ? 'discover' : '',
          })
          return json(res, 200, { ...started, ready: true })
        }

        const vgRunMatch = route.match(/^\/vg\/runs\/(r-[0-9]{8}-[0-9]{6}-vg-discover)$/)
        if (method === 'GET' && vgRunMatch) {
          const run = readRun(vgRunMatch[1])
          if (!run) return json(res, 404, { error: 'run 不存在' })
          return json(res, 200, { run, running: runningIds().includes(run.id), stderr: stderrOf(run.id) })
        }

        const vgStopMatch = route.match(/^\/vg\/runs\/(r-[0-9]{8}-[0-9]{6}-vg-discover)\/stop$/)
        if (method === 'POST' && vgStopMatch) {
          return json(res, 200, { stopped: stopRun(vgStopMatch[1]) })
        }

        const vgDecideMatch = route.match(
          /^\/vg\/runs\/(r-[0-9]{8}-[0-9]{6}-vg-discover)\/items\/([A-Za-z0-9_-]+)\/decide$/,
        )
        if (method === 'POST' && vgDecideMatch) {
          const body = await readJson(req)
          const decision = body.decision === 'reject' ? 'reject' : 'accept'
          const args = ['--decide', vgDecideMatch[1], '--item', vgDecideMatch[2], '--decision', decision]
          if (body.write) args.push('--write')
          if (body.note) args.push('--note', String(body.note).slice(0, 500))
          if (body.source) args.push('--source', String(body.source).slice(0, 500))
          const outcome = await enqueueDecide(`vg:${vgDecideMatch[1]}`, () => runVg(args, 120_000))
          return json(res, outcome.ok ? 200 : 400, outcome)
        }

        return json(res, 404, { error: `未知路由 ${method} ${route}` })
      } catch (error) {
        return json(res, 500, { error: String(error?.message || error).slice(0, 400) })
      }
    },
  })
}
