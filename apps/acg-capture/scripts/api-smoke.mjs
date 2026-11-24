// 后端路由冒烟：不启动宿主，验证「福袋裁决」这条最容易被 id 编码绊倒的路由能进到引擎。
// 跑法：node apps/acg-capture/scripts/api-smoke.mjs
// 背景：福袋 item id 带中文（bag-20261117-原神-…），路由若只放行 ASCII，前端点「采纳并写表」
//      会拿到 404「未知路由」。本脚本断言：中文 id 的裁决请求到达引擎（返回「运行不存在」）。
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'acg-api-smoke-'))
process.env.ACG_DATA_DIR = tmp

const { registerHttp } = await import('../lib/http.js')

let handler = null
const ctx = {
  webServer: { register: (options) => { handler = options.handler; return () => {} } },
  connection: {},
}
registerHttp(ctx)

const server = http.createServer((req, res) => handler(req, res))
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const port = server.address().port
const base = `http://127.0.0.1:${port}/acg-capture/api`

const failures = []
function check(name, condition, detail) {
  if (condition) {
    console.log(`✓ ${name}`)
  } else {
    console.log(`✗ ${name}${detail ? ` —— ${detail}` : ''}`)
    failures.push(name)
  }
}

async function post(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  return { status: response.status, body: await response.text() }
}

const leads = await fetch(`${base}/bag/leads`)
check('GET /bag/leads 返回 200', leads.status === 200, String(leads.status))

const item = encodeURIComponent('bag-20261117-原神-2026年-双11心')
const decide = await post(`${base}/bag/runs/r-20261117-160000-bag-discover/items/${item}/decide`, {
  decision: 'reject',
  write: false,
})
check(
  '中文 item id 的裁决路由进入引擎（不是 404 未知路由）',
  decide.status === 400 && decide.body.includes('运行不存在'),
  `${decide.status} ${decide.body.slice(0, 120)}`,
)

const plain = await post(`${base}/bag/runs/r-20261117-160000-bag-discover/items/bag-plain-id/decide`, {
  decision: 'reject',
  write: false,
})
check('ASCII item id 也不受影响', plain.status === 400 && plain.body.includes('运行不存在'), String(plain.status))

// 并发裁决：面板上同时点多个「采纳」，三条都要落到 run.json。
// 2026-11-18 的现场是只有一条成功：每个点击 spawn 一个引擎进程，并发读改写把彼此的状态顶回去。
const runId = 'r-20261118-120000-bag-discover'
const runDir = path.join(tmp, 'runs', runId)
fs.mkdirSync(runDir, { recursive: true })
const items = [0, 1, 2].map((index) => ({
  id: `bag-conc-${index}`,
  ip: `测试IP${index}`,
  officialName: `测试福袋${index}`,
  carrier: '福袋',
  status: 'pending_review',
  reasons: ['quote_unverified'],
  tiers: [],
}))
fs.writeFileSync(
  path.join(runDir, 'run.json'),
  JSON.stringify(
    {
      id: runId,
      kind: 'bag-discover',
      status: 'partial',
      dryRun: false,
      counts: { dispatched: 3, done: 0, accepted: 0, rejected: 0, pending: 3, unavailable: 0, written: 0 },
      items,
    },
    null,
    1,
  ),
)
fs.writeFileSync(path.join(runDir, 'events.jsonl'), '')

const parallel = await Promise.all(
  items.map((entry) =>
    post(`${base}/bag/runs/${runId}/items/${entry.id}/decide`, {
      decision: 'accept',
      write: false,
      note: '并发验收',
    }),
  ),
)
const okCount = parallel.filter((item) => item.status === 200).length
const state = JSON.parse(fs.readFileSync(path.join(runDir, 'run.json'), 'utf8'))
const accepted = state.items.filter((entry) => entry.status === 'accepted').length
check('并发 3 个采纳都返回 200', okCount === 3, parallel.map((item) => `${item.status} ${item.body.slice(0, 80)}`).join(' | '))
check('并发采纳的 3 条都落进 run.json', accepted === 3, `accepted=${accepted}`)
check(
  '并发后统计不串（pending=0 / accepted=3）',
  state.counts.pending === 0 && state.counts.accepted === 3,
  JSON.stringify(state.counts),
)

server.close()
fs.rmSync(tmp, { recursive: true, force: true })

if (failures.length) {
  console.log(`\n${failures.length} 项失败`)
  process.exit(1)
}
console.log('\n全部通过')
