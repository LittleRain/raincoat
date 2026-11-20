import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import os from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

// 护栏回归：一条卡住的提案不能把「提交」冻死。
// 覆盖四件事：原文没了的提案立刻判废、存在的提案不动、失败次数与配额冷却可算、
// 队列文件被另一个宿主改过之后能整体接管。

const tempDir = await mkdtemp(join(os.tmpdir(), 'kb-guards-'))
const vault = join(tempDir, 'vault')
await mkdir(join(vault, '00 Inbox/2026/11/20'), { recursive: true })
await writeFile(join(vault, '00 Inbox/2026/11/20/exists.md'), '# x\n', 'utf8')

process.env.DSH_HOME = tempDir
const dataDir = join(tempDir, 'raincoat-kb-desk')
await mkdir(dataDir, { recursive: true })

const now = Date.now()
const seed = [
  { id: 'a', path: '00 Inbox/2026/11/20/gone.md', title: 'gone', status: 'proposal', createdAt: now - 3_600_000, finishedAt: now - 3_600_000, proposal: { decision: 'raw', space: 'builder' } },
  { id: 'b', path: '00 Inbox/2026/11/20/exists.md', title: 'exists', status: 'proposal', createdAt: now, finishedAt: now, proposal: { decision: 'raw', space: 'builder' } },
  { id: 'c', path: '00 Inbox/2026/11/20/retry.md', title: 'retry', status: 'failed', createdAt: now - 60_000, error: '429: {"code":"insufficient_quota"}' },
  { id: 'd', path: '00 Inbox/2026/11/20/retry.md', title: 'retry', status: 'failed', createdAt: now - 30_000, error: 'boom' },
]
await writeFile(join(dataDir, 'triage-jobs.json'), JSON.stringify(seed, null, 1), 'utf8')

const queue = await import('../lib/triage-queue.js')

test('原文消失的提案立刻判废，原文还在的不动', async () => {
  await queue.ready()
  const expired = await queue.expireStaleProposals(null, vault, { proposalTtlMinutes: 30 }, { afterApply: false })
  assert.equal(expired.length, 1)
  assert.match(expired[0].path, /gone\.md$/)
  const jobs = queue.listJobs()
  assert.equal(jobs.find((job) => job.id === 'a').status, 'failed')
  assert.equal(jobs.find((job) => job.id === 'b').status, 'proposal')
})

test('同一篇的失败次数、以及配额冷却都能算出来', () => {
  assert.equal(queue.attemptsFor('00 Inbox/2026/11/20/retry.md'), 2)
  const left = queue.quotaCooldownLeft({ quotaCooldownMinutes: 10 })
  assert.ok(left > 0 && left <= 10 * 60_000, `expected cooldown, got ${left}`)
})

test('已经判废的提案不会被重复判废', async () => {
  const expired = await queue.expireStaleProposals(null, vault, { proposalTtlMinutes: 30 }, { afterApply: false })
  assert.equal(expired.length, 0)
})

test('队列文件被另一个宿主改过之后整体接管', async () => {
  const file = join(dataDir, 'triage-jobs.json')
  const raw = JSON.parse(await readFile(file, 'utf8'))
  raw.push({ id: 'e', path: '00 Inbox/2026/11/20/new.md', title: 'new', status: 'proposal', createdAt: Date.now(), finishedAt: Date.now(), proposal: {} })
  await writeFile(file, JSON.stringify(raw, null, 1), 'utf8')
  await new Promise((resolve) => setTimeout(resolve, 25))
  assert.equal(await queue.syncFromDisk(), true)
  assert.ok(queue.listJobs().some((job) => job.id === 'e'))
})
