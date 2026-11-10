// 排查模块的单测：错误归类、内网判断、阶段间隔、检查清单，以及一次证据收集的端到端拼装。
// 用临时 DSH_HOME 隔离整理队列的本地状态，测试不读也不写真实 vault。
import assert from 'node:assert/strict'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

process.env.DSH_HOME = mkdtempSync(join(tmpdir(), 'kb-desk-diag-home-'))

const { buildSignals, biggestGap, classifyError, gatherFailure, isPrivateHost, probeUrl } = await import('../lib/diagnose.js')

test('classifyError：把常见失败文本归到具体类型', () => {
  const cases = [
    ['vault has uncommitted changes (87 files); commit or discard them before the worker writes', 'vault-dirty', 'local'],
    ['lease expired 3 times; giving up', 'lease-expired', 'worker'],
    ["vault sync failed; left commit local (d3e872c): pull --rebase failed; local commits preserved: fatal: unable to access 'https://github.com/LittleRain/rain_knowledge.git/'", 'git-sync', 'local'],
    ['request failed: HTTP 401 unauthorized', 'auth', 'worker'],
    ['getaddrinfo ENOTFOUND mp.weixin.qq.com', 'dns', 'worker'],
    ['connect ETIMEDOUT 101.32.104.11:443', 'network', 'worker'],
    ['环境异常，请完成验证后再访问', 'login-wall', 'source'],
    ['GET https://mp.weixin.qq.com/s/x 404 not found', 'source-404', 'source'],
    ['source responded HTTP 502', 'http-status', 'source'],
    ['duplicate source_id in queue', 'duplicate', 'queue'],
    ['something odd happened', 'unknown', 'unknown'],
  ]
  for (const [message, code, scope] of cases) {
    const result = classifyError(message)
    assert.equal(result.code, code, `归类错误：${message} → ${result.code}`)
    assert.equal(result.scope, scope, `作用域错误：${message} → ${result.scope}`)
    assert.ok(result.label.length > 0)
  }
  assert.deepEqual(classifyError('  '), { code: 'unknown', label: '远端没有留下错误文本', scope: 'unknown' })
  assert.deepEqual(classifyError(null).code, 'unknown')
})

test('isPrivateHost：内网直接跳过，公网域名继续探测', () => {
  for (const host of ['localhost', 'vault.local', 'foo.internal', '127.0.0.1', '10.1.2.3', '192.168.1.9', '172.20.0.4', '169.254.1.1', '100.64.3.2', '::1', '[::1]', 'fd12:3456::1', 'fe80::1', '']) {
    assert.equal(isPrivateHost(host), true, `${host} 应判为内网`)
  }
  for (const host of ['mp.weixin.qq.com', 'github.com', '172.32.0.1', '11.0.0.1', '100.128.0.1', '8.8.8.8']) {
    assert.equal(isPrivateHost(host), false, `${host} 不应判为内网`)
  }
})

test('probeUrl：跳过内网、拒绝非 http(s)，并按页面标记判定登录墙', async () => {
  assert.deepEqual(await probeUrl('http://127.0.0.1:3000/x'), { ok: false, skipped: '内网地址，跳过探测' })
  assert.deepEqual(await probeUrl('ftp://example.com/a'), { ok: false, skipped: '不是 http(s) 链接' })
  assert.equal((await probeUrl('not a url')).ok, false)

  const html = '<html><head><title>提示</title></head><body>该内容已被发布者删除</body></html>'
  const fake = async (url, options) => {
    assert.equal(options.method, 'GET')
    assert.equal(options.redirect, 'follow')
    return new Response(html, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } })
  }
  const result = await probeUrl('https://mp.weixin.qq.com/s/abc', { fetchImpl: fake })
  assert.equal(result.ok, true)
  assert.equal(result.status, 200)
  assert.equal(result.title, '提示')
  assert.deepEqual(result.markers, ['内容已删除或不可见'])
  assert.equal(result.finalUrl, null)
})

test('biggestGap：取阶段之间最大间隔，缺时间戳的跳过', () => {
  assert.equal(biggestGap([]), null)
  assert.equal(biggestGap([{ stage: 'a', at: 1000 }]), null)
  const stages = [
    { stage: 'claim', at: 1_000 },
    { stage: 'fetch', at: 4_000 },
    { stage: 'write', at: 200_000 },
    { stage: 'push' },
    { stage: 'done', at: 260_000 },
  ]
  const gap = biggestGap(stages)
  assert.equal(gap.ms, 196_000)
  assert.equal(gap.from.stage, 'fetch')
  assert.equal(gap.to.stage, 'write')
})

test('buildSignals：vault 脏与失败原因对齐时标红，干净时反过来说明可以重试', () => {
  const dirtyJob = { error: 'vault has uncommitted changes (3 files); commit or discard them', attempts: 1 }
  const dirty = buildSignals({
    job: dirtyJob,
    errorClass: classifyError(dirtyJob.error),
    stages: [{ stage: 'write', status: 'failed', at: 5, note: 'worktree not clean' }],
    lastFailed: { stage: 'write', status: 'failed', note: 'worktree not clean' },
    git: { ok: true, dirty: 3, behind: 0, ahead: 0 },
  })
  assert.ok(dirty.some((item) => item.level === 'error' && item.title.includes('3 个未提交改动') && item.title.includes('与失败原因一致')))
  assert.ok(dirty.some((item) => item.level === 'error' && item.title.includes('最后一个失败阶段：write') && item.detail === 'worktree not clean'))

  const clean = buildSignals({
    job: dirtyJob,
    errorClass: classifyError(dirtyJob.error),
    stages: [],
    git: { ok: true, dirty: 0, behind: 2, ahead: 1 },
  })
  assert.ok(clean.some((item) => item.level === 'ok' && item.title === '现在 vault 是干净的'))
  assert.ok(clean.some((item) => item.level === 'warn' && item.title.includes('落后 origin 2')))
  assert.ok(clean.some((item) => item.level === 'warn' && item.title.includes('1 个提交没推送')))
  assert.ok(clean.some((item) => item.level === 'warn' && item.title === '远端没有阶段记录'))
})

test('buildSignals：源站探测四种结论、重试次数、Inbox 与落盘状态', () => {
  const base = { job: { error: 'lease expired 3 times; giving up', attempts: 3, vaultPath: '10 Sources/a.md' }, errorClass: classifyError('lease expired 3 times; giving up') }
  const withProbe = (probe) => buildSignals({ ...base, stages: [{ stage: 'fetch', status: 'running', at: 1 }], probe, inboxHit: { path: '00 Inbox/a.md', title: 'A' }, fileExists: true, triage: { status: 'failed', error: '模型超时' } })

  const okProbe = withProbe({ ok: true, status: 200, bytes: 2048, ms: 120, markers: [] })
  assert.ok(okProbe.some((item) => item.level === 'warn' && item.title.includes('已经重试 3 次')))
  assert.ok(okProbe.some((item) => item.level === 'ok' && item.title.includes('源站现在可访问（HTTP 200，2 KB，120ms）')))
  assert.ok(okProbe.some((item) => item.level === 'warn' && item.title === '这篇已经在 Inbox：00 Inbox/a.md'))
  assert.ok(okProbe.some((item) => item.level === 'ok' && item.title === '落盘文件存在'))
  assert.ok(okProbe.some((item) => item.level === 'error' && item.title === '本地整理（triage）也失败了'))

  const markers = withProbe({ ok: true, status: 200, bytes: 900, ms: 200, markers: ['反爬/人机验证'] })
  assert.ok(markers.some((item) => item.level === 'warn' && item.title.includes('页面像反爬/人机验证')))

  const notFound = withProbe({ ok: true, status: 410, bytes: 300, ms: 80, markers: [] })
  assert.ok(notFound.some((item) => item.level === 'error' && item.title === '源站返回 HTTP 410'))

  const failed = withProbe({ ok: false, error: '本机探测超时（7s）', ms: 6500 })
  assert.ok(failed.some((item) => item.level === 'warn' && item.title.includes('本机探测源站失败：本机探测超时')))

  const skipped = withProbe({ ok: false, skipped: '内网地址，跳过探测' })
  assert.ok(skipped.some((item) => item.level === 'info' && item.title === '没有探测源站：内网地址，跳过探测'))

  const redirected = withProbe({ ok: true, status: 200, bytes: 100, ms: 50, markers: [], finalUrl: 'https://example.com/moved' })
  assert.ok(redirected.some((item) => item.level === 'warn' && item.detail === 'https://example.com/moved'))
})

test('gatherFailure：远端接口正常时拼出 context 与给模型的证据', async () => {
  const root = mkdtempSync(join(tmpdir(), 'kb-desk-diag-vault-'))
  const job = {
    id: 'task-1',
    url: 'https://example.com/post/1',
    title: '一篇讲排障的文章',
    status: 'failed',
    worker: 'mac-mini',
    attempts: 2,
    error: 'lease expired 3 times; giving up',
    createdAt: 1_700_000_000_000,
    finishedAt: 1_700_000_600_000,
    elapsedMs: 600_000,
  }
  const ingest = {
    jobs: async (status, limit) => {
      assert.equal(status, 'failed')
      assert.ok(limit >= 20)
      return { jobs: [job] }
    },
    run: async () => ({
      stages: [
        { stage: 'claim', status: 'ok', at: 1_700_000_000_000 },
        { stage: 'fetch', status: 'failed', at: 1_700_000_500_000, note: '源站 30s 没响应' },
      ],
    }),
  }
  const result = await gatherFailure({ ingest, root, jobId: 'task-1', note: '刚重启了 worker', probe: false })
  assert.equal(result.context.job.id, 'task-1')
  assert.equal(result.context.errorClass.code, 'lease-expired')
  assert.equal(result.context.remoteError, null)
  assert.equal(result.context.fileExists, false)
  assert.ok(result.context.signals.length >= 2)
  assert.ok(result.evidence.includes('【任务】task-1'))
  assert.ok(result.evidence.includes('【用户补充】刚重启了 worker'))
  assert.ok(result.evidence.includes('【机器检查清单】'))
})

test('gatherFailure：远端查不到这次任务时退回前端快照，接口失败记在 evidence 里', async () => {
  const root = mkdtempSync(join(tmpdir(), 'kb-desk-diag-vault2-'))
  const snapshot = { id: 'task-2', url: 'https://example.com/x', status: 'failed', error: 'vault has uncommitted changes (9 files); stop' }
  const ingest = {
    jobs: async () => {
      throw new Error('远端 502')
    },
    run: async () => {
      throw new Error('没有这条 run')
    },
  }
  const result = await gatherFailure({ ingest, root, job: snapshot, probe: false })
  assert.equal(result.context.job.id, 'task-2')
  assert.equal(result.context.remoteError, '远端 502')
  assert.equal(result.context.errorClass.code, 'vault-dirty')
  assert.match(result.evidence, /远端接口异常：远端 502/)

  await assert.rejects(() => gatherFailure({ ingest, root, jobId: 'missing' }), /找不到任务 missing/)
})
