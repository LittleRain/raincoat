import assert from 'node:assert/strict'
import { mkdtemp, writeFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import os from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

// 重试链路：插件把远端 failed 任务逐条放回队列。这里用本地假服务模拟
// 「全部成功」「部分失败」「服务端还没这个接口」三种情况，不碰真实摄入服务。

const tempDir = await mkdtemp(join(os.tmpdir(), 'kb-retry-'))
const credentialsFile = join(tempDir, 'credentials.env')
await writeFile(credentialsFile, 'WORKER_TOKEN=test-worker\nINGEST_TOKEN=test-ingest\n', 'utf8')
process.env.DSH_HOME = tempDir

const state = { failed: [], retryCodes: {} }
const calls = []

const server = createServer(async (req, res) => {
  const url = new URL(req.url || '/', 'http://localhost')
  calls.push(`${req.method} ${url.pathname}${url.search}`)
  const send = (status, body) => {
    res.writeHead(status, { 'content-type': 'application/json' })
    res.end(JSON.stringify(body))
  }
  if (req.method === 'GET' && url.pathname === '/api/jobs') {
    return send(200, { status: 'failed', count: state.failed.length, jobs: state.failed })
  }
  const match = url.pathname.match(/^\/api\/jobs\/([^/]+)\/retry$/)
  if (req.method === 'POST' && match) {
    const id = decodeURIComponent(match[1])
    const code = state.retryCodes[id] ?? 200
    if (code === 200) return send(200, { job: { id, status: 'queued', attempts: 0 } })
    if (code === 404) {
      res.writeHead(404, { 'content-type': 'text/html' })
      return res.end('<pre>Cannot POST /jobs/__probe__/retry</pre>')
    }
    return send(code, { error: 'job is not retryable' })
  }
  return send(404, { error: 'not found' })
})

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const { port } = server.address()

await writeFile(
  join(tempDir, 'raincoat-kb-desk', 'settings.json'),
  JSON.stringify({ vault: tempDir, apiBase: `http://127.0.0.1:${port}/api`, credentialsFile }),
  'utf8',
).catch(async (error) => {
  // dataDir() 还没建过，先建目录再写
  if (error.code !== 'ENOENT') throw error
  const { mkdir } = await import('node:fs/promises')
  await mkdir(join(tempDir, 'raincoat-kb-desk'), { recursive: true })
  await writeFile(
    join(tempDir, 'raincoat-kb-desk', 'settings.json'),
    JSON.stringify({ vault: tempDir, apiBase: `http://127.0.0.1:${port}/api`, credentialsFile }),
    'utf8',
  )
})

const { createIngest } = await import('../lib/ingest.js')
const ingest = createIngest()

test('retries a specific job id and reports the new queue state', async () => {
  state.failed = []
  state.retryCodes = {}
  const result = await ingest.retry(['job-1'])
  assert.equal(result.total, 1)
  assert.deepEqual(result.retried, ['job-1'])
  assert.deepEqual(result.failed, [])
})

test('retries every failed job when no ids are given', async () => {
  state.failed = [{ id: 'a' }, { id: 'b' }]
  state.retryCodes = {}
  const result = await ingest.retry()
  assert.equal(result.total, 2)
  assert.deepEqual(result.retried.sort(), ['a', 'b'])
})

test('keeps going after a single job fails and reports it per item', async () => {
  state.failed = [{ id: 'a' }, { id: 'b' }]
  state.retryCodes = { a: 409 }
  const result = await ingest.retry()
  assert.deepEqual(result.retried, ['b'])
  assert.equal(result.failed.length, 1)
  assert.equal(result.failed[0].id, 'a')
  assert.match(result.failed[0].error, /not retryable/)
})

test('explains an old remote service that has no retry endpoint', async () => {
  state.retryCodes = { old: 404 }
  const result = await ingest.retry(['old'])
  assert.equal(result.retried.length, 0)
  assert.match(result.failed[0].error, /远端服务还没有重试接口/)
})

test('dedupes ids so a double click does not retry twice', async () => {
  state.retryCodes = {}
  calls.length = 0
  const result = await ingest.retry(['x', 'x', ' '])
  assert.equal(result.total, 1)
  assert.equal(calls.filter((line) => line.includes('/jobs/x/retry')).length, 1)
})

test.after(() => {
  server.close()
})
