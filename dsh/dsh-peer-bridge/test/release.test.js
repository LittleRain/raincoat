/**
 * 让出写锁的四种结局：真放掉（冻结）、放不掉（still-held）、正在跑（busy）、不在手上（not-held）。
 *
 * 这里用一个假 SessionPersistence：`open(id, 'write')` 抢占 flock、`close()` 释放，
 * 语义与 `dsh-session-persistence-jsonl` 的独占租约相同。插件对句柄只做记账 + close，
 * 所以这个假实现足够验证「记账 → 关句柄 → 复核」这条链。
 */
import assert from 'node:assert/strict'
import { Readable } from 'node:stream'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import http from 'node:http'
import { apply } from '../index.js'
import { peersDir, writePeer } from '../lib/peers.js'

function fakeRes() {
  const out = { status: 0, body: '' }
  return {
    out,
    writeHead(status) {
      out.status = status
      return this
    },
    end(body) {
      out.body = body ?? ''
      return this
    },
  }
}

function fakeReq({ method, url, body }) {
  // 用真 Readable：请求体在监听器挂上之后才流出来，和真 socket 一样不会抢跑。
  const req = new Readable({ read() {} })
  req.method = method
  req.url = url
  req.headers = {}
  req.socket = { remoteAddress: '127.0.0.1' }
  req.destroy = () => {
    req.push(null)
  }
  if (body !== undefined) req.push(Buffer.from(JSON.stringify(body)))
  req.push(null)
  return req
}

/** 假宿主：一条独占写锁 + 一个 agent 注册表。 */
function makeWorld({ activity = 'idle' } = {}) {
  const lock = { held: false }
  const closes = []
  const flushes = []
  const agentsMap = new Map()

  const persistence = {
    open: async (id, access) => {
      if (access === 'write') {
        if (lock.held) {
          const error = new Error(`session "${id}" is already owned`)
          error.name = 'SessionAlreadyOwnedError'
          throw error
        }
        lock.held = true
        return {
          id,
          access: 'write',
          close: async () => {
            lock.held = false
            closes.push(id)
          },
        }
      }
      return { id, access: 'read', close: async () => {} }
    },
    create: async (header) => {
      if (lock.held) {
        const error = new Error(`session "${header?.id}" is already owned`)
        error.name = 'SessionAlreadyOwnedError'
        throw error
      }
      lock.held = true
      return {
        id: header?.id,
        access: 'write',
        close: async () => {
          lock.held = false
        },
      }
    },
    flush: async () => {
      flushes.push(Date.now())
    },
  }

  const agents = {
    get: (id) => agentsMap.get(id),
    list: () => [...agentsMap.values()],
    resume: async () => {
      throw new Error('测试里不走真的 resume')
    },
  }

  const services = {
    sessionController: {
      list: async () => ({
        items: [...agentsMap.keys()].map((sessionId) => ({ sessionId, updatedAt: Date.now(), running: false })),
      }),
    },
    agents,
    sessionPersistence: persistence,
    connection: {
      authenticatedUrl: (base) => `${base}?token=self`,
      requestRejection: () => undefined,
    },
  }

  const state = { handler: undefined, disposers: [] }
  const ctx = {
    webServer: {
      getOrigin: () => 'http://127.0.0.1:64399',
      register: (route) => {
        state.handler = route.handler
        return () => {}
      },
    },
    connection: services.connection,
    get: (name) => services[name],
    effect: (fn) => state.disposers.push(fn()),
  }

  const world = {
    ctx,
    state,
    lock,
    closes,
    flushes,
    persistence,
    agentsMap,
    /** 模拟宿主自己恢复会话：拿到写句柄并让 agent 上线。 */
    async hostResumes(sessionId) {
      const handle = await persistence.open(sessionId, 'write')
      agentsMap.set(sessionId, { id: sessionId, activity })
      return handle
    },
  }
  return world
}

async function call(state, options) {
  const res = fakeRes()
  await state.handler(fakeReq(options), res)
  return { status: res.out.status, body: res.out.body ? JSON.parse(res.out.body) : null }
}

async function withWorld(options, run) {
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'peer-bridge-release-'))
  const previous = process.env.DSH_HOME
  process.env.DSH_HOME = home
  const world = makeWorld(options)
  try {
    apply(world.ctx)
    await run(world, home)
  } finally {
    for (const dispose of world.state.disposers) await dispose?.()
    if (previous === undefined) delete process.env.DSH_HOME
    else process.env.DSH_HOME = previous
    for (let i = 0; i < 5; i += 1) {
      try {
        await fs.rm(home, { recursive: true, force: true, maxRetries: 0 })
        break
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 40))
      }
    }
  }
}

test('截到写句柄时：关句柄放掉锁，agent 留着并标成冻结', async () => {
  await withWorld({}, async (world) => {
    await world.hostResumes('session-frozen')
    assert.equal(world.lock.held, true)

    const released = await call(world.state, {
      method: 'POST',
      url: '/dsh-bridge/api/release',
      body: { sessionId: 'session-frozen' },
    })
    assert.equal(released.status, 200)
    assert.equal(released.body.ok, true)
    assert.equal(released.body.released, true)
    assert.equal(released.body.frozen, true)
    assert.equal(released.body.verified, true)
    assert.match(released.body.message, /冻结/)
    assert.equal(world.lock.held, false)
    // 关闭次数至少一次：复核用的临时写句柄也会 close，所以不比对具体次数。
    assert.equal(world.closes.includes('session-frozen'), true)

    // 冻结要透给对端：本端不再自称持有，状态换成「已让出」。
    const overview = await call(world.state, { method: 'GET', url: '/dsh-bridge/api/overview' })
    const row = overview.body.sessions.find((item) => item.sessionId === 'session-frozen')
    assert.equal(row.held, false)
    assert.equal(row.frozen, true)

    // 再点一次不该假装成功：写句柄已经关了，核心会继续复用这个死句柄。
    const again = await call(world.state, {
      method: 'POST',
      url: '/dsh-bridge/api/release',
      body: { sessionId: 'session-frozen' },
    })
    assert.equal(again.body.ok, false)
    assert.equal(again.body.code, 'frozen')
    assert.match(again.body.hint, /重启本端应用/)
  })
})

test('没截到写句柄时：如实报 still-held，并给退出应用的指引', async () => {
  await withWorld({}, async (world) => {
    world.agentsMap.set('session-early', { id: 'session-early', activity: 'idle' })
    world.lock.held = true

    const result = await call(world.state, {
      method: 'POST',
      url: '/dsh-bridge/api/release',
      body: { sessionId: 'session-early' },
    })
    assert.equal(result.body.ok, false)
    assert.equal(result.body.code, 'still-held')
    assert.match(result.body.hint, /退出本端应用/)
    assert.equal(world.lock.held, true)
    assert.equal(world.closes.length, 0)
  })
})

test('正在跑回合时拒绝让出，提示等这一轮跑完', async () => {
  await withWorld({ activity: 'running' }, async (world) => {
    await world.hostResumes('session-busy')
    const result = await call(world.state, {
      method: 'POST',
      url: '/dsh-bridge/api/release',
      body: { sessionId: 'session-busy' },
    })
    assert.equal(result.body.ok, false)
    assert.equal(result.body.code, 'busy')
    assert.match(result.body.hint, /跑完/)
    assert.equal(world.lock.held, true)
  })
})

test('不在本端手里时直接说清楚，不报错', async () => {
  await withWorld({}, async (world) => {
    const result = await call(world.state, {
      method: 'POST',
      url: '/dsh-bridge/api/release',
      body: { sessionId: 'session-elsewhere' },
    })
    assert.equal(result.body.ok, true)
    assert.equal(result.body.released, false)
    assert.equal(result.body.reason, 'not-held')
  })
})

test('让出前先 flush，别把已经路由进句柄的事件丢掉', async () => {
  await withWorld({}, async (world) => {
    await world.hostResumes('session-flush')
    await call(world.state, {
      method: 'POST',
      url: '/dsh-bridge/api/release',
      body: { sessionId: 'session-flush' },
    })
    assert.equal(world.flushes.length > 0, true)
  })
})

test('本机浏览器点「切到本端」：转给对端执行，原样带回它的回执', async () => {
  await withWorld({}, async (world, home) => {
    const seen = []
    const peerServer = http.createServer((req, res) => {
      let raw = ''
      req.on('data', (chunk) => {
        raw += chunk
      })
      req.on('end', () => {
        res.writeHead(200, { 'content-type': 'application/json' })
        if (req.url.endsWith('/held')) return res.end(JSON.stringify({ ok: true, pid: 4242, held: [] }))
        seen.push(JSON.parse(raw || '{}'))
        return res.end(
          JSON.stringify({
            ok: false,
            code: 'still-held',
            message: '本端放不掉这条会话的写锁',
            hint: '退出本端应用（Cmd+Q）再重新打开',
          }),
        )
      })
    })
    await new Promise((resolve) => peerServer.listen(0, '127.0.0.1', resolve))
    const port = peerServer.address().port
    await writePeer({
      dir: peersDir(home),
      pid: 4242,
      origin: `http://127.0.0.1:${port}`,
      url: `http://127.0.0.1:${port}/?token=peer`,
      profile: 'desktop',
    })

    try {
      const result = await call(world.state, {
        method: 'POST',
        url: '/dsh-bridge/api/release',
        body: { sessionId: 'session-on-peer', toPid: 4242 },
      })
      assert.equal(result.status, 200)
      assert.equal(result.body.code, 'still-held')
      assert.match(result.body.hint, /退出本端应用/)
      assert.equal(seen.length, 1)
      assert.equal(seen[0].sessionId, 'session-on-peer')
    } finally {
      peerServer.close()
    }
  })
})
