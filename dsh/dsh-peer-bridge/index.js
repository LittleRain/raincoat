/**
 * 「双端会话」宿主侧。
 *
 * 桌面端（自带 host）与 `dsh web`（launchd）是两个独立进程、共享同一个
 * `$DSH_HOME`。会话写锁只能被一个进程持有，而核心没有 release 原语，所以
 * 本插件默认只做单向可见：
 *
 *   1. 对端发现：两端各写一份带 pid 的心跳记录，合并成「谁在线、各自持有谁」。
 *   2. 只读打开：把带进程 token 的地址交给浏览器，另一端打开同一会话即可阅读。
 *   3. 增量提示：只读端比较 updatedAt，发现对端写了新内容就提示刷新。
 *   4. 让出写锁（`/release`）：用户明确点「切到本端」时才动手，见 releaseLocal。
 *
 * 投递、分叉、自动迁移一律不做：同一时刻只有一个端在写，另一端只读。
 *
 * 边界：不修改核心包、不把登录 token 交给对端。让出写锁只在用户点击时发生，
 * 且代价是「原端那条会话冻结」——原端 agent 还在，但写不进去了，会如实提示。
 */
import { writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { labelForProfile, HEARTBEAT_MS, peersDir, readPeers, removePeer, writePeer } from './lib/peers.js'
import { HEADER, ensureSecret, providedSecret, secretMatches } from './lib/secret.js'
import { startReconciler } from './lib/reconciler.js'
import { readCachedTitle } from './lib/state.js'

export const inject = ['connection', 'webServer']

const ROUTE = '/dsh-bridge/api'
const PROBE_TIMEOUT_MS = 1_200
const PROBE_CACHE_MS = 2_000

/** 插件入口绝不抛异常：加载失败会让整个 host 起不来。 */
/** 本进程里被 resume 过的会话句柄：agent.id -> AgentHandle。释放写锁的首选。 */
const agentHandles = new Map()
/**
 * 本进程 sessionPersistence 发出的写句柄：session.id -> SessionHandle。
 *
 * 核心没有 release 原语：写句柄只在 agent-loop 的 teardown 闭包里，
 * controller 又把 AgentHandle 丢了（`resumeObserved()` 只取 `.agent`）。
 * 所以除了截 resume 的返回值，还截 open/create 的返回值——拿到句柄就能
 * `close()`，flock 随 fd 关闭释放。只记账，不在这里关。
 */
const writeHandles = new Map()
/** 已让出写锁、但本端 agent 还活着的会话：再写会失败，界面按「冻结」提示。 */
const frozenSessions = new Map()
let resumeTapInstalled = false
let persistenceTapInstalled = false
/** 记账命中次数：>0 说明这个进程里 tap 真的生效，不是「装上了但没人走」。 */
let persistenceTapHits = 0
/** 自检结果：`ok: true` 才算 tap 真的在生效；null 表示这次没条件验证。 */
let persistenceSelfCheck = null
let selfCheckScheduled = false
/** 探锁期间不要让自检用的写句柄被记账，否则刚放掉又抓回来。 */
let probing = 0

/**
 * 把 agents.resume 包一层，顺手留下返回的 AgentHandle。
 * 只转发、不改语义；包不上（服务只读、方法改名）就返回 false，功能降级。
 */
function installResumeTap(ctx) {
  const agents = service(ctx, 'agents')
  if (!agents || typeof agents.resume !== 'function') return false
  if (agents.resume.__peerBridge === true) {
    resumeTapInstalled = true
    return true
  }
  const original = agents.resume
  const wrapped = async function peerBridgeResume(...args) {
    const handle = await original.apply(this ?? agents, args)
    try {
      const id = handle?.agent?.id
      if (typeof id === 'string' && id !== '') {
        agentHandles.set(id, handle)
        if (agentHandles.size > 200) {
          const oldest = agentHandles.keys().next()
          if (!oldest.done) agentHandles.delete(oldest.value)
        }
      }
    } catch {
      /* 记账失败不影响 resume 本身 */
    }
    return handle
  }
  wrapped.__peerBridge = true
  try {
    agents.resume = wrapped
  } catch {
    try {
      Object.defineProperty(agents, 'resume', { value: wrapped, configurable: true, writable: true })
    } catch {
      return false
    }
  }
  // 服务代理每次 get 都可能返回绑定后的新函数，不能靠 === 判断是否装上；
  // 赋值没抛异常就算接管成功，真伪由运行时是否记到句柄来验证（见 /_probe）。
  resumeTapInstalled = true
  return true
}

/**
 * tap 装上了不等于 tap 生效：服务代理可能在每次 get 时返回新的绑定函数，
 * 赋值既不抛错也不管事。装完 3 秒后拿第一条已存会话开一个只读句柄试一下，
 * 看 hits 有没有涨——只读、立刻关，不改任何状态，但能立刻暴露失效。
 */
function scheduleTapSelfCheck(ctx) {
  if (selfCheckScheduled) return
  selfCheckScheduled = true
  const timer = setTimeout(async () => {
    try {
      const persistence = service(ctx, 'sessionPersistence')
      if (!persistence || typeof persistence.open !== 'function' || typeof persistence.list !== 'function') {
        persistenceSelfCheck = { at: Date.now(), ok: false, reason: 'no-list' }
        return
      }
      const snapshots = await persistence.list()
      const id = (snapshots ?? [])
        .map((item) => item?.header?.id ?? item?.id)
        .find((value) => typeof value === 'string' && value !== '')
      if (!id) {
        persistenceSelfCheck = { at: Date.now(), ok: null, reason: 'no-sessions-to-probe' }
        return
      }
      const before = persistenceTapHits
      const handle = await persistence.open(id, 'read')
      const after = persistenceTapHits
      try {
        await handle?.close?.()
      } catch {
        /* 只读句柄，关不掉无所谓 */
      }
      persistenceSelfCheck = { at: Date.now(), ok: after > before, reason: after > before ? undefined : 'tap-not-called' }
    } catch (error) {
      persistenceSelfCheck = { at: Date.now(), ok: false, reason: `probe-failed:${errorText(error)}` }
    }
  }, 3_000)
  timer?.unref?.()
}

/**
 * 把 sessionPersistence.open / create 包一层，记下返回的写句柄。
 *
 * 判据只看句柄自己（`id` / `access` / `close`），不解析调用参数：将来
 * `open` 多一个参数、或 `create` 换签名，这里都不用跟着改。
 * 只转发、不改语义；包不上就返回 false，功能退化成「只能靠 resume 句柄」。
 */
function installPersistenceTap(ctx) {
  const persistence = service(ctx, 'sessionPersistence')
  if (!persistence) return false
  const installed = ['open', 'create'].map((name) => wrapPersistenceMethod(persistence, name))
  persistenceTapInstalled = installed.some(Boolean)
  if (persistenceTapInstalled) scheduleTapSelfCheck(ctx)
  return persistenceTapInstalled
}

function wrapPersistenceMethod(persistence, name) {
  const original = persistence?.[name]
  if (typeof original !== 'function') return false
  if (original.__peerBridge === true) return true
  const wrapped = async function peerBridgePersistence(...args) {
    const handle = await original.apply(this ?? persistence, args)
    try {
      persistenceTapHits += 1
      const id = typeof handle?.id === 'string' ? handle.id : ''
      // 句柄自带 access；老版本没有时才按调用形状猜（create 恒为写，open 看第二个参数）。
      const askedWrite = name === 'create' || args[1] === 'write'
      const access = typeof handle?.access === 'string' ? handle.access : askedWrite ? 'write' : 'read'
      // 自检探锁拿到的句柄立刻就会关掉，不该留台账，也不该把冻结标记擦掉。
      if (probing === 0 && id !== '' && access === 'write' && typeof handle.close === 'function') {
        writeHandles.set(id, handle)
        frozenSessions.delete(id)
        if (writeHandles.size > 200) {
          const oldest = writeHandles.keys().next()
          if (!oldest.done) writeHandles.delete(oldest.value)
        }
      }
    } catch {
      /* 记账失败不影响开句柄本身 */
    }
    return handle
  }
  wrapped.__peerBridge = true
  try {
    persistence[name] = wrapped
  } catch {
    try {
      Object.defineProperty(persistence, name, { value: wrapped, configurable: true, writable: true })
    } catch {
      return false
    }
  }
  return true
}

export function apply(ctx) {
  try {
    start(ctx)
  } catch (error) {
    console.error('[peer-bridge] 初始化失败，双端面板将不可用：', error?.message ?? error)
  }
  try {
    // 尽早接管：服务可能在 apply 时还没就绪，等它出现立刻装，赶在会话恢复之前。
    if (typeof ctx.inject === 'function') {
      ctx.inject(['agents'], (scope) => {
        installResumeTap(scope ?? ctx)
      })
      ctx.inject(['sessionPersistence'], (scope) => {
        installPersistenceTap(scope ?? ctx)
      })
    }
    installResumeTap(ctx)
    installPersistenceTap(ctx)
  } catch (error) {
    console.error('[peer-bridge] 接管 agents.resume / sessionPersistence 失败，本次启动可能无法让出会话：', error?.message ?? error)
  }
  try {
    // workspace 注册表对账：两端分组/顺序/归档集恒等，是双端看到同一份列表的前提。
    startReconciler(ctx)
  } catch (error) {
    console.error('[peer-bridge] workspace 对账初始化失败，两端列表可能漂移：', error?.message ?? error)
  }
}

/** 可选服务一律用 ctx.get：没有它时降级，而不是让宿主起不来。 */
function service(ctx, name) {
  try {
    return typeof ctx?.get === 'function' ? ctx.get(name) : undefined
  } catch {
    return undefined
  }
}

function start(ctx) {
  const home = process.env.DSH_HOME ?? undefined
  const dirs = {
    peers: peersDir(home),
  }
  /**
   * 启动时 env 可能还没注入 profile，所以每次用的时候现读。
   * 顺序：DSH_PROFILE → DSH_PROFILE_DIR 目录名 → 进程形态兜底
   * （Electron 主进程 = 桌面端，CLI 起的就是 web 端）。
   */
  const profileNow = () => {
    const direct = process.env.DSH_PROFILE
    if (typeof direct === 'string' && direct !== '') return direct
    const dir = process.env.DSH_PROFILE_DIR
    if (typeof dir === 'string') {
      const name = dir.split('/').filter(Boolean).pop()
      if (name) return name
    }
    // 两种宿主都跑在 Electron 的 node 里（ELECTRON_RUN_AS_NODE），
    // 所以先看子命令，再看是不是 Electron 主进程。
    if (process.argv.some((arg) => arg === 'web')) return 'web'
    if (process.versions?.electron) return 'desktop'
    return ''
  }
  const startedAt = Date.now()
  const origin =
    typeof ctx.webServer.getOrigin === 'function'
      ? ctx.webServer.getOrigin()
      : typeof ctx.webServer.port === 'number'
        ? `http://127.0.0.1:${ctx.webServer.port}`
        : 'http://127.0.0.1'
  // 带进程 token 的地址只能在宿主里算，而且必须每次心跳重算：插件启动早期
  // connection 服务可能还没挂上 authenticatedUrl，早算一次就会把裸 origin 固定一辈子，
  // 对端「在对端打开」时于是撞 401。
  const authenticatedUrl = () => {
    const base = `${origin}/`
    const readers = [
      () => ctx.connection?.authenticatedUrl?.(base),
      // 宿主可能把 authenticatedUrl 挂在 connection.authentication 上；没 inject 的服务
      // 直接读属性会抛错，所以一律走 ctx.get 再取方法。
      () => ctx.get?.('connection.authentication')?.authenticatedUrl?.(base),
    ]
    for (const read of readers) {
      try {
        const value = read()
        if (typeof value === 'string' && value.includes('token=')) return value
      } catch {
        /* 这一层拿不到就试下一层 */
      }
    }
    return base
  }
  // 重启后用户需要一个能直接打开的地址；只有 web 端写，免得桌面端把 3080 那条盖掉。
  {
    const first = authenticatedUrl()
    if (first.includes('token=') && profileNow() === 'web') {
      const homeDir = process.env.DSH_HOME || join(homedir(), '.dsh')
      writeFile(join(homeDir, 'last-web-url.txt'), `${first}\n`, { mode: 0o600 }).catch(() => {})
    }
  }

  const secretReady = ensureSecret(home).catch((error) => {
    console.error('[peer-bridge] 生成共享令牌失败，宿主之间只能看到对方在线、看不到持有情况：', error?.message ?? error)
    return undefined
  })

  const beat = () => {
    const url = authenticatedUrl()
    writePeer({ dir: dirs.peers, pid: process.pid, origin, url, profile: profileNow(), startedAt }).catch(() => {
      /* 心跳失败只影响可见性，不影响会话 */
    })
  }
  beat()
  const timer = setInterval(beat, HEARTBEAT_MS)
  timer.unref?.()

  const probeCache = new Map()

  const disposeRoute = ctx.webServer.register({
    kind: 'prefix',
    path: ROUTE,
    // DSH 0.2.2 起 carrier 在路由之前统一鉴权，默认策略是「必须带浏览器 cookie」。
    // 宿主之间的请求只有回环 + 共享令牌，永远拿不到 cookie，于是两边互相判成离线
    // （对端 alive=false、heldIds 空），「谁持有这条会话」整条链路就断了。
    // 这里按请求来源分流：只有回环 + 带 x-dsh-bridge 头 + 只打 peer 专用端点时才放行到
    // 插件自己的令牌校验（authorizePeer），其余请求继续走 carrier 的 cookie 鉴权。
    auth: (request) => (isPeerRequest(request) ? 'anonymous' : 'required'),
    handler: (req, res) => {
      // 返回 promise 只是为了让测试能 await；路由忽略返回值也不受影响。
      return handle(ctx, req, res, { dirs, origin, startedAt, secretReady, probeCache, profileNow }).catch((error) => {
        try {
          fail(res, 500, 'internal', String(error?.message ?? error))
        } catch {
          /* 响应可能已经结束 */
        }
      })
    },
  })

  ctx.effect(
    () => () => {
      clearInterval(timer)
      disposeRoute()
      removePeer({ dir: dirs.peers, pid: process.pid }).catch(() => {})
    },
    'peer-bridge: peer heartbeat',
  )
}

async function handle(ctx, req, res, env) {
  const url = new URL(req.url ?? '/', 'http://127.0.0.1')
  const path = url.pathname
  const method = (req.method ?? 'GET').toUpperCase()

  if (path === `${ROUTE}/held`) {
    if (method !== 'GET') return fail(res, 405, 'method', '只接受 GET')
    if (!(await authorizePeer(req, env))) return fail(res, 401, 'unauthorized', '需要宿主之间的共享令牌')
    return json(res, 200, await heldPayload(ctx, env))
  }

  if (path === `${ROUTE}/overview`) {
    if (method !== 'GET') return fail(res, 405, 'method', '只接受 GET')
    const rejection = browserRejection(ctx, req)
    if (rejection !== undefined) return fail(res, rejection, 'unauthorized', '需要 DSH 浏览器会话')
    return json(res, 200, await overviewPayload(ctx, env))
  }

  if (path === `${ROUTE}/release`) {
    if (method !== 'POST') return fail(res, 405, 'method', '只接受 POST')
    const peerAuthorized = await authorizePeer(req, env)
    if (!peerAuthorized) {
      const rejection = browserRejection(ctx, req)
      if (rejection !== undefined) return fail(res, rejection, 'unauthorized', '需要 DSH 浏览器会话')
    }
    let body
    try {
      body = await readJsonBody(req)
    } catch (error) {
      return fail(res, 400, 'bad-body', String(error?.message ?? error))
    }
    const sessionId = typeof body?.sessionId === 'string' ? body.sessionId : ''
    if (sessionId === '') return fail(res, 400, 'bad-request', '缺少 sessionId')
    const toPid = Number(body?.toPid)
    if (!peerAuthorized && Number.isInteger(toPid)) {
      // 本机浏览器发起：请对端放出这条会话，再由本端接手。
      const peers = await probePeers(env)
      const peer = peers.find((item) => item.pid === toPid && item.alive)
      if (!peer) return fail(res, 409, 'no-peer', '另一端不在线')
      const secret = await env.secretReady
      try {
        const response = await fetch(`${peer.origin}${ROUTE}/release`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-dsh-bridge': secret ?? '' },
          body: JSON.stringify({ sessionId }),
          signal: AbortSignal.timeout(3_000),
        })
        const payload = await response.json().catch(() => ({}))
        return json(res, 200, payload)
      } catch (error) {
        return fail(res, 502, 'peer-unreachable', String(error?.message ?? error))
      }
    }
    return json(res, 200, await releaseLocal(ctx, sessionId))
  }

  if (path === `${ROUTE}/_probe` && process.env.DSH_PEER_BRIDGE_PROBE === '1') {
    if (method !== 'POST') return fail(res, 405, 'method', '只接受 POST')
    if (!(await authorizePeer(req, env))) return fail(res, 401, 'unauthorized', '需要共享令牌')
    let body
    try {
      body = await readJsonBody(req)
    } catch (error) {
      return fail(res, 400, 'bad-body', String(error?.message ?? error))
    }
    const sessionId = typeof body?.sessionId === 'string' ? body.sessionId : ''
    const controller = service(ctx, 'sessionController')
    const agents = service(ctx, 'agents')
    const out = {
      tap: resumeTapInstalled,
      hasResume: typeof agents?.resume === 'function',
      before: Boolean(agents?.get?.(sessionId)),
      resolved: false,
      captured: agentHandles.has(sessionId),
      writeCaptured: writeHandles.has(sessionId),
      persistenceTap: persistenceTapInstalled,
      persistenceTapHits,
      persistenceSelfCheck,
      frozen: frozenSessions.has(sessionId),
      release: null,
    }
    if (sessionId !== '' && controller && typeof controller.resolveAgent === 'function') {
      try {
        const found = await controller.resolveAgent(sessionId)
        out.resolved = !(found && found.error)
        out.resolvedError = found?.error ? String(found.error.message ?? found.error) : undefined
      } catch (error) {
        out.resolved = false
        out.resolvedError = String(error?.message ?? error)
      }
      out.captured = agentHandles.has(sessionId)
      out.afterResolve = Boolean(agents?.get?.(sessionId))
      if (body?.forget === true) {
        agentHandles.delete(sessionId)
        out.forgot = true
      }
      out.diagnose = diagnose(ctx, sessionId)
      out.release = await releaseLocal(ctx, sessionId)
      out.afterRelease = Boolean(agents?.get?.(sessionId))
    }
    return json(res, 200, out)
  }

  if (path === `${ROUTE}/diagnose`) {
    if (method !== 'POST') return fail(res, 405, 'method', '只接受 POST')
    if (!(await authorizePeer(req, env))) return fail(res, 401, 'unauthorized', '需要共享令牌')
    let body
    try {
      body = await readJsonBody(req)
    } catch (error) {
      return fail(res, 400, 'bad-body', String(error?.message ?? error))
    }
    return json(res, 200, { ok: true, ...diagnose(ctx, typeof body?.sessionId === 'string' ? body.sessionId : '') })
  }

  if (path === `${ROUTE}/sessions`) {
    if (method !== 'GET') return fail(res, 405, 'method', '只接受 GET')
    const rejection = browserRejection(ctx, req)
    if (rejection !== undefined) return fail(res, rejection, 'unauthorized', '需要 DSH 浏览器会话')
    return json(res, 200, { ok: true, sessions: await listSessions(ctx) })
  }

  return fail(res, 404, 'not-found', '没有这个接口')
}

/** 合并：本端会话列表 + 本端持有的热会话 + 对端自述。 */
async function overviewPayload(ctx, env) {
  const [sessions, peers] = await Promise.all([listSessions(ctx), probePeers(env)])
  const heldIds = sessions.filter((row) => row.held).map((row) => row.sessionId)

  return {
    ok: true,
    self: { pid: process.pid, profile: env.profileNow(), label: labelForProfile(env.profileNow()), origin: env.origin, startedAt: env.startedAt },
    heldIds,
    sessions,
    peers: peers.map((peer) => ({
      pid: peer.pid,
      profile: peer.profile,
      label: peer.label,
      origin: peer.origin,
      // 带进程 token 的启动 URL：只回给同源的已登录页面（与「在另一端打开」同一取舍），
      // 宿主之间互调只用共享令牌，不用这个。
      url: peer.url,
      alive: peer.alive,
      heldIds: peer.heldIds ?? [],
      runningIds: peer.runningIds ?? [],
      error: peer.error,
    })),
    capabilities: { release: true, fork: false, proxyOwnership: false, readOnlyMirror: true, freezeOnRelease: true },
    // 让出写锁靠的是接管 sessionPersistence：装上了但没生效（服务代理换了、DSH 升级）
    // 只有自检能看出来，界面据此提前说清楚，别等用户点了才失败。
    writeTap: {
      installed: persistenceTapInstalled,
      hits: persistenceTapHits,
      selfCheck: persistenceSelfCheck,
    },
  }
}

/** 本端自述：哪些会话此刻在本进程里有活着的 agent（= 持有写锁）。 */
async function heldPayload(ctx, env) {
  const sessions = await listSessions(ctx)
  const held = sessions.filter((row) => row.held).map((row) => ({ sessionId: row.sessionId, running: row.running }))
  return {
    ok: true,
    pid: process.pid,
    profile: env.profileNow(),
    label: labelForProfile(env.profileNow()),
    origin: env.origin,
    held,
    at: Date.now(),
  }
}

/**
 * 本端可见会话。只读，不激活冷会话。
 * title 从 projections 里宽松地取：不同版本投影键名可能不同，取不到就退回短 id。
 */
async function listSessions(ctx) {
  const controller = service(ctx, 'sessionController')
  const agents = service(ctx, 'agents')
  let rows = []
  if (controller && typeof controller.list === 'function') {
    try {
      const value = await controller.list({}, AbortSignal.timeout(5_000))
      if (Array.isArray(value?.items)) rows = value.items
    } catch {
      rows = []
    }
  }

  let held = new Set()
  if (agents && typeof agents.list === 'function') {
    try {
      held = new Set(agents.list().map((agent) => String(agent.id)))
    } catch {
      held = new Set()
    }
  }

  return rows.map((row) => {
    const sessionId = String(row.sessionId)
    return {
      sessionId,
      title: titleOf(row) ?? cachedTitle(sessionId) ?? undefined,
      cwd: typeof row.cwd === 'string' ? row.cwd : undefined,
      updatedAt: Number(row.updatedAt) || 0,
      running: row.running === true,
      // 已让出写锁的会话要报「不持有」，否则对端会以为还被占着、继续禁用输入。
      held: held.has(sessionId) && !frozenSessions.has(sessionId),
      // 已让出写锁但 agent 还在的会话：本端还能看，写不进去了。
      frozen: frozenSessions.has(sessionId),
      blank: row.blank === true,
    }
  })
}

/** 标题可能长在几个不同版本的形状上，逐个试；都没有再回落到投影缓存。 */
function titleOf(row) {
  const direct = typeof row?.title === 'string' ? row.title.trim() : ''
  if (direct !== '') return direct
  for (const container of [row?.projections?.values, row?.projections, row?.header?.projections]) {
    if (!container || typeof container !== 'object') continue
    for (const value of Object.values(container)) {
      if (value && typeof value === 'object' && typeof value.title === 'string' && value.title.trim() !== '') {
        return value.title.trim()
      }
    }
  }
  return undefined
}

/**
 * 本端拿不到投影时（会话被另一个 host 占着），标题只在共享投影缓存里。
 * 缓存 60 秒，避免每轮为几百条会话反复读盘。
 */
const titleCache = new Map()
function cachedTitle(sessionId) {
  const hit = titleCache.get(sessionId)
  if (hit && Date.now() - hit.at < 60_000) return hit.title
  let title = null
  try {
    title = readCachedTitle(sessionId)
  } catch {
    title = null
  }
  titleCache.set(sessionId, { at: Date.now(), title })
  return title
}

/** 问每个对端「你持有哪个会话」；连不上就是离线，不阻塞面板。 */
async function probePeers(env) {
  const peers = await readPeers({ dir: env.dirs.peers, excludePid: process.pid })
  return Promise.all(
    peers.map(async (peer) => {
      const cached = env.probeCache.get(peer.pid)
      if (cached && Date.now() - cached.at < PROBE_CACHE_MS) return { ...peer, ...cached.value }
      let value
      try {
        const secret = await env.secretReady
        const response = await fetch(`${peer.origin}${ROUTE}/held`, {
          headers: { accept: 'application/json', 'x-dsh-bridge': secret ?? '' },
          signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const body = await response.json()
        const held = Array.isArray(body?.held) ? body.held : []
        value = {
          alive: true,
          heldIds: held.map((item) => String(item?.sessionId)),
          runningIds: held.filter((item) => item?.running === true).map((item) => String(item.sessionId)),
        }
      } catch (error) {
        value = { alive: false, heldIds: [], runningIds: [], error: String(error?.message ?? error) }
      }
      env.probeCache.set(peer.pid, { at: Date.now(), value })
      return { ...peer, ...value }
    }),
  )
}

/** 浏览器请求复用 DSH 自己的同源会话校验；拿不到校验器时按拒绝处理。 */
function browserRejection(ctx, req) {
  const connection = service(ctx, 'connection')
  // DSH 0.2.2 起 webServer 路由由 carrier 统一鉴权，旧 API 只在旧宿主上补一层。
  if (typeof connection?.requestRejection !== 'function') return undefined
  try {
    return connection.requestRejection({ headers: req.headers })
  } catch {
    return 503
  }
}

/** 宿主之间：必须来自回环地址，且共享令牌一致。 */
async function authorizePeer(req, env) {
  if (!isLoopback(req)) return false
  const secret = await env.secretReady
  if (typeof secret !== 'string' || secret === '') return false
  return secretMatches(providedSecret(req), secret)
}

function isLoopback(req) {
  const address = req?.socket?.remoteAddress ?? ''
  return address === '127.0.0.1' || address === '::1' || address === '::ffff:127.0.0.1'
}

/**
 * 只有「回环 + 带共享令牌头 + 只打 peer 专用端点」的请求才交给插件自己的令牌校验。
 *
 * 这个判定放在路由的 auth 策略里，所以必须窄：一旦把 /overview 也放成 anonymous，
 * 局域网里随便一个请求带个假头就能读到全部会话列表。
 */
function isPeerRequest(request) {
  if (!isLoopback(request)) return false
  const header = request?.headers?.[HEADER]
  const value = Array.isArray(header) ? header[0] : header
  if (typeof value !== 'string' || value === '') return false
  return PEER_ONLY_PATHS.has(requestPathname(request))
}

/**
 * webserver 交给 auth 策略的 `url` 是 `new URL(req.url, 'http://x')` 的 **URL 对象**，
 * 不是字符串；测试里图省事传过字符串，于是曾经在这里漏判过一次。两种都认。
 */
function requestPathname(request) {
  const target = request?.url
  if (target !== null && typeof target === 'object' && typeof target.pathname === 'string') return target.pathname
  const text = String(target ?? '')
  try {
    return new URL(text, 'http://x').pathname
  } catch {
    return text.split('?')[0]
  }
}

const PEER_ONLY_PATHS = new Set([`${ROUTE}/held`, `${ROUTE}/release`])

/** 会话是否正在跑回合：`activity` 是公开状态，读不到再看 phase。 */
function agentRunning(agent) {
  try {
    if (typeof agent?.activity === 'string') return agent.activity !== 'idle'
    const kind = agent?.phase?.kind
    if (typeof kind === 'string') return kind !== 'idle' && kind !== 'maintenance'
  } catch {
    /* 读不到就按空闲处理，后面每一步自己会失败 */
  }
  return false
}

function errorText(error) {
  return String(error?.message ?? error)
}

/** 这个错是不是「别人还占着写锁」。 */
function isOwnedError(error) {
  if (String(error?.name ?? '') === 'SessionAlreadyOwnedError') return true
  const text = `${String(error?.code ?? '')} ${String(error?.message ?? '')}`
  return /already[\s-]?owned|write ownership|locks? (?:it|the session)/i.test(text)
}

/**
 * 用「开一次写句柄再立刻关掉」验证锁是不是真空了。
 * @returns true 空出来了 / false 仍被占 / undefined 判断不了（没有 persistence）
 */
async function lockFree(ctx, sessionId) {
  const persistence = service(ctx, 'sessionPersistence')
  if (!persistence || typeof persistence.open !== 'function') return undefined
  probing += 1
  try {
    const probe = await persistence.open(sessionId, 'write')
    try {
      await probe?.close?.()
    } catch {
      /* 能开出来就说明没被别人占着；关不掉不影响判断 */
    }
    return true
  } catch (error) {
    return isOwnedError(error) ? false : undefined
  } finally {
    probing -= 1
  }
}

/**
 * 让出本宿主里某条会话的写锁。
 *
 * 核心没有 release 原语：写句柄只在 agent-loop 的 teardown 闭包里，controller
 * 又把 AgentHandle 丢了。所以按可靠性排三条路：
 *
 *   1. resume 时截下的 `AgentHandle.dispose()`：走核心 teardown，注册表一起清；
 *   2. 截下的写句柄 `close()`：flock 随 fd 关闭释放。代价是原 agent 还活着、写不进去，
 *      记成「已冻结」并如实告诉用户；
 *   3. scope/ctx 兜底：对写句柄无效，留着给别的版本撞运气。
 *
 * 每一步都用「重新抢一次写锁」复核，不假装成功。
 */
async function releaseLocal(ctx, sessionId) {
  const agents = service(ctx, 'agents')
  if (!agents || typeof agents.get !== 'function') {
    return { ok: false, code: 'unsupported', message: '这个宿主没有 agents 服务', hint: '这里不是 DSH 会话宿主，无法让出会话。' }
  }
  const agent = agents.get(sessionId)
  if (!agent) {
    frozenSessions.delete(sessionId)
    return { ok: true, released: false, reason: 'not-held', message: '这条会话不在本端手里，不需要让出' }
  }
  if (frozenSessions.has(sessionId)) {
    // 冻结过的会话，agent 还在但写句柄已经关了：核心会继续复用这个死句柄，
    // 再「让出」一次只会把死状态传下去，不如直接让用户重启。
    return {
      ok: false,
      code: 'frozen',
      message: '本端这条会话已经冻结',
      hint: '之前让出写锁时关掉了它的写句柄，这个版本接不回来。重启本端应用后再点「切到本端」。',
    }
  }
  if (agentRunning(agent)) {
    return {
      ok: false,
      code: 'busy',
      message: '这条会话正在跑回合',
      hint: '等这一轮跑完再点「切到本端」。现在切断会丢掉正在生成的内容。',
    }
  }

  const tried = []
  const path = []

  // 1) 首选：resume 时截下来的 AgentHandle，dispose 它会走核心 teardown。
  const resumeHandle = agentHandles.get(sessionId)
  if (resumeHandle && typeof resumeHandle.dispose === 'function') {
    try {
      await resumeHandle.dispose()
      agentHandles.delete(sessionId)
      path.push('handle')
    } catch (error) {
      tried.push(['handle', errorText(error)])
    }
  }

  // 2) 核心这版没有 release 原语：关掉写句柄就等于放掉 flock。
  //    dispose 那条路走通了也再确认一次锁：万一核心换了 teardown 顺序，这里还能兜住。
  if (path.length === 0 || (await lockFree(ctx, sessionId)) !== true) {
    const write = writeHandles.get(sessionId)
    if (!write || typeof write.close !== 'function') {
      if (path.length === 0) {
        tried.push([
          'write-handle',
          persistenceTapInstalled ? '本进程没记到这条会话的写句柄' : '没接上 sessionPersistence，无法记账',
        ])
      }
    } else {
      // 先把已经路由进句柄的事件落盘，再关：少丢一截比关得快重要。
      try {
        await service(ctx, 'sessionPersistence')?.flush?.()
      } catch (error) {
        tried.push(['flush', errorText(error)])
      }
      try {
        // close 幂等：重复关闭（比如 teardown 稍后也来关一次）不算失败。
        await write.close()
        writeHandles.delete(sessionId)
        path.push('write-handle')
      } catch (error) {
        tried.push(['write-handle', errorText(error)])
      }
    }
  }

  // 3) 兜底：agent 自己的作用域。生命周期边界归 ownerCtx，收掉它同样会关闭句柄。
  if (path.length === 0 && agents.get(sessionId)) {
    const scope = agent.scope
    const candidates = [
      ['scope.stop', () => scope?.stop?.()],
      ['scope.dispose', () => scope?.dispose?.()],
      ['scope.asyncDispose', () => scope?.[Symbol.asyncDispose]?.()],
      ['ctx.dispose', () => agent.ctx?.dispose?.()],
    ]
    for (const [name, run] of candidates) {
      try {
        const result = run()
        if (result && typeof result.then === 'function') await result
        path.push(name)
        await new Promise((resolve) => setTimeout(resolve, 60))
        if (!agents.get(sessionId)) break
      } catch (error) {
        tried.push([name, errorText(error)])
      }
    }
  }

  // 4) 复核：能重新抢到写锁才算真放掉。
  const free = await lockFree(ctx, sessionId)
  // 真关过句柄、锁却还被占着：只可能是另一端在我们放掉的瞬间接走了。这不是失败。
  const releasedSomething = path.includes('handle') || path.includes('write-handle')
  if (free === false && releasedSomething) {
    return {
      ok: true,
      released: true,
      verified: false,
      path,
      message: '已让出写锁，另一端已经接手',
    }
  }
  if (free === false || (free === undefined && !releasedSomething)) {
    return {
      ok: false,
      code: 'still-held',
      message: '本端放不掉这条会话的写锁',
      hint: persistenceTapInstalled
        ? '这条会话是在插件开始记账之前打开的（通常是宿主启动时自动恢复的那条），手上没有可关的句柄。退出本端应用（Cmd+Q）再重新打开，锁会随进程退出释放。'
        : '这个宿主没接上 sessionPersistence（DSH 版本不匹配），只能退出本端应用（Cmd+Q）释放写锁。',
      tried,
      path,
    }
  }

  const stillThere = Boolean(agents.get(sessionId))
  if (stillThere) {
    // 锁放掉了，但 agent 还活着：它下一次写会撞 SessionHandleClosedError。
    // 这个状态必须让用户看见，否则会以为「切过去了、那边还能接着聊」。
    frozenSessions.set(sessionId, Date.now())
    return {
      ok: true,
      released: true,
      frozen: true,
      verified: free === true,
      path,
      message: '已让出写锁。本端这条会话还能看，但已经写不进去（已冻结）；要恢复请重启本端。',
    }
  }
  return { ok: true, released: true, verified: free === true, path, message: '已让出写锁' }
}

/** 只读诊断：告诉调用方这台宿主上，某条会话有哪些可以拆的入口。 */
function diagnose(ctx, sessionId) {
  const safe = (fn, fallback) => {
    try {
      return fn()
    } catch (error) {
      return `${fallback}:${String(error?.message ?? error)}`
    }
  }
  const agents = service(ctx, 'agents')
  const agent = safe(() => agents?.get?.(sessionId), 'agent')
  const scope = agent ? safe(() => agent.scope, 'scope') : undefined
  return {
    hasAgent: Boolean(agent),
    captured: agentHandles.has(sessionId),
    handles: agentHandles.size,
    writeCaptured: writeHandles.has(sessionId),
    writeHandles: writeHandles.size,
    persistenceTap: persistenceTapInstalled,
    persistenceTapHits,
    persistenceSelfCheck,
    frozen: frozenSessions.has(sessionId),
    agentKeys: agent ? Object.keys(agent).slice(0, 40) : [],
    scopeType: typeof scope,
    scopeKeys: scope && typeof scope === 'object' ? Object.keys(scope).slice(0, 20) : [],
    hasStop: scope ? typeof scope.stop : 'undefined',
    hasDispose: scope ? typeof scope.dispose : 'undefined',
    hasAsyncDispose: scope ? typeof scope[Symbol.asyncDispose] : 'undefined',
    ctxDispose: agent ? safe(() => typeof agent.ctx?.dispose, 'ctx') : 'undefined',
  }
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0
    const chunks = []
    req.on('data', (chunk) => {
      size += chunk.length
      if (size > 8 * 1024) {
        reject(new Error('请求体过大'))
        req.destroy()
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => {
      if (chunks.length === 0) return resolve({})
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))
      } catch (error) {
        reject(error)
      }
    })
    req.on('error', reject)
  })
}

function fail(res, status, code, message) {
  json(res, status, { ok: false, code, message })
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
