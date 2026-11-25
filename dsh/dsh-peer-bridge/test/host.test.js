/**
 * 宿主半侧的冒烟测试：用假 ctx + 假对端宿主跑一遍真实路由。
 *
 * 覆盖三件容易出错的事：overview 能不能把「本端持有 / 对端持有」拼对；
 * overview 能不能把两端合并成一份视图；宿主之间的共享令牌是不是真的在拦未授权请求。
 */
import assert from 'node:assert/strict'
import EventEmitter from 'node:events'
import fs from 'node:fs/promises'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { apply } from '../index.js'
import { peersDir, writePeer } from '../lib/peers.js'
import { ensureSecret } from '../lib/secret.js'

function fakeRes() {
  const out = { status: 0, headers: null, body: '' }
  return {
    out,
    writeHead(status, headers) {
      out.status = status
      out.headers = headers
      return this
    },
    end(body) {
      out.body = body ?? ''
      return this
    },
  }
}

function fakeReq({ method, url, body, headers = {}, address = '127.0.0.1' }) {
  const req = new EventEmitter()
  req.method = method
  req.url = url
  req.headers = headers
  req.socket = { remoteAddress: address }
  req.destroy = () => {}
  if (body !== undefined) {
    const payload = Buffer.from(JSON.stringify(body))
    process.nextTick(() => {
      req.emit('data', payload)
      req.emit('end')
    })
  }
  return req
}

function makeCtx({ rows, held, requestRejection = () => undefined }) {
  const state = { handler: undefined, disposers: [] }
  const services = {
    sessionController: {
      list: async () => ({ items: rows }),
      fork: async () => ({ sessionId: 'session-child' }),
    },
    agents: { list: () => held.map((id) => ({ id })) },
    sessionPersistence: {
      open: async () => ({ inheritedEventCount: 42, close: async () => {} }),
    },
    connection: {
      authenticatedUrl: (base) => `${base}?token=self`,
      requestRejection: (request) => requestRejection(request),
    },
  }
  const ctx = {
    webServer: {
      getOrigin: () => 'http://127.0.0.1:64399',
      register: (route) => {
        state.route = route
        state.handler = route.handler
        return () => {}
      },
    },
    connection: services.connection,
    get: (name) => services[name],
    effect: (fn) => state.disposers.push(fn()),
  }
  return { ctx, state }
}

async function call(state, options) {
  const res = fakeRes()
  await state.handler(fakeReq(options), res)
  return { status: res.out.status, headers: res.out.headers, body: res.out.body ? JSON.parse(res.out.body) : null }
}

async function cleanup(home) {
  // 心跳写在 dispose 之后仍有概率落盘，rm 会撞上 ENOTEMPTY，重试几次即可。
  for (let i = 0; i < 5; i += 1) {
    try {
      await fs.rm(home, { recursive: true, force: true, maxRetries: 0 })
      return
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 40))
    }
  }
}

test('overview 拼出本端持有 + 对端持有', async () => {
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'peer-bridge-host-'))
  const previous = process.env.DSH_HOME
  process.env.DSH_HOME = home

  const peerServer = http.createServer((req, res) => {
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ ok: true, pid: 999, label: 'Web 端', held: [{ sessionId: 'session-b', running: false }] }))
  })
  await new Promise((resolve) => peerServer.listen(0, '127.0.0.1', resolve))
  const port = peerServer.address().port
  await writePeer({
    dir: peersDir(home),
    pid: 999,
    origin: `http://127.0.0.1:${port}`,
    url: `http://127.0.0.1:${port}/?token=peer`,
    profile: 'web',
  })

  const { ctx, state } = makeCtx({
    rows: [
      { sessionId: 'session-a', updatedAt: Date.now(), running: false, projections: { values: { meta: { title: '在跑的活' } } } },
      { sessionId: 'session-b', updatedAt: Date.now(), running: false },
    ],
    held: ['session-a'],
  })

  try {
    apply(ctx)
    const overview = await call(state, { method: 'GET', url: '/dsh-bridge/api/overview' })

    assert.equal(overview.status, 200)
    assert.equal(overview.body.ok, true)
    assert.deepEqual(overview.body.heldIds, ['session-a'])
    assert.equal(overview.body.sessions[0].title, '在跑的活')
    assert.equal(overview.body.self.profile, process.env.DSH_PROFILE ?? '')
    assert.equal(overview.body.peers.length, 1)
    assert.equal(overview.body.peers[0].alive, true)
    assert.deepEqual(overview.body.peers[0].heldIds, ['session-b'])
    assert.equal(overview.body.capabilities.release, true)

    // 分叉/代发一律不做：这里没有可提交的写操作。
  } finally {
    for (const dispose of state.disposers) await dispose?.()
    peerServer.close()
    if (previous === undefined) delete process.env.DSH_HOME
    else process.env.DSH_HOME = previous
    await cleanup(home)
  }
})

test('分叉入口已经下线，POST 不会悄悄做别的事', async () => {
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'peer-bridge-host-'))
  const previous = process.env.DSH_HOME
  process.env.DSH_HOME = home

  const { ctx, state } = makeCtx({
    rows: [{ sessionId: 'session-run', updatedAt: Date.now(), running: true }],
    held: ['session-run'],
  })

  try {
    apply(ctx)
    const gone = await call(state, {
      method: 'POST',
      url: '/dsh-bridge/api/handoff',
      body: { sessionId: 'session-run' },
    })
    assert.equal(gone.status, 404)
    assert.equal(gone.body.code, 'not-found')
  } finally {
    for (const dispose of state.disposers) await dispose?.()
    if (previous === undefined) delete process.env.DSH_HOME
    else process.env.DSH_HOME = previous
    await cleanup(home)
  }
})

test('宿主之间必须带共享令牌，浏览器请求走同源校验', async () => {
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'peer-bridge-host-'))
  const previous = process.env.DSH_HOME
  process.env.DSH_HOME = home

  const { ctx, state } = makeCtx({
    rows: [{ sessionId: 'session-a', updatedAt: Date.now(), running: false }],
    held: ['session-a'],
  })

  try {
    apply(ctx)
    const anonymous = await call(state, { method: 'GET', url: '/dsh-bridge/api/held' })
    assert.equal(anonymous.status, 401)

    const secret = await ensureSecret(home)
    const authorized = await call(state, {
      method: 'GET',
      url: '/dsh-bridge/api/held',
      headers: { 'x-dsh-bridge': secret },
    })
    assert.equal(authorized.status, 200)
    assert.deepEqual(authorized.body.held, [{ sessionId: 'session-a', running: false }])
  } finally {
    for (const dispose of state.disposers) await dispose?.()
    if (previous === undefined) delete process.env.DSH_HOME
    else process.env.DSH_HOME = previous
    await cleanup(home)
  }
})

/**
 * DSH 0.2.2 起 carrier 在路由前统一鉴权，默认要求浏览器 cookie。
 * 宿主之间的请求只有回环 + 共享令牌，必须由这个 auth 策略放行到插件自己的令牌校验，
 * 否则 /held 永远 401，两端互相判成离线（alive=false）——「双端」整条链路就废了。
 */
test('路由 auth 策略：只给 peer 端点放行，浏览器路由仍要求登录', async () => {
  const { ctx, state } = makeCtx({ rows: [], held: [] })
  apply(ctx)

  const policy = state.route.auth
  assert.equal(typeof policy, 'function', '路由必须自带 auth 策略，不能落回默认的 required')

  // webserver 派发时给的是 URL 对象（new URL(req.url, 'http://x')），不是字符串。
  const peerBase = {
    socket: { remoteAddress: '127.0.0.1' },
    headers: { 'x-dsh-bridge': 'shared-secret' },
    url: new URL('/dsh-bridge/api/held?x=1', 'http://x'),
  }

  assert.equal(policy(peerBase), 'anonymous')
  assert.equal(policy({ ...peerBase, url: new URL('/dsh-bridge/api/release', 'http://x') }), 'anonymous')
  // 字符串形态也要认，避免测试和宿主之间出现口径差。
  assert.equal(policy({ ...peerBase, url: '/dsh-bridge/api/held' }), 'anonymous')
  // 会话列表不能因为带了个头就跳过 cookie 鉴权。
  assert.equal(policy({ ...peerBase, url: new URL('/dsh-bridge/api/overview', 'http://x') }), 'required')
  assert.equal(policy({ ...peerBase, url: new URL('/dsh-bridge/api/sessions', 'http://x') }), 'required')
  // 没有令牌头 = 浏览器请求。
  assert.equal(policy({ ...peerBase, headers: {} }), 'required')
  // 非回环一律不放行；也不能靠路径前缀绕过（/held/../overview 之类的变形不认）。
  assert.equal(policy({ ...peerBase, socket: { remoteAddress: '192.168.1.9' } }), 'required')
  assert.equal(policy({ ...peerBase, url: new URL('/dsh-bridge/api/heldx', 'http://x') }), 'required')

  for (const dispose of state.disposers) await dispose?.()
})
