import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import os from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

// 「暂停」只停整理，不停同步：切到暂停后一轮 tick 仍然会跑 git 同步/推送，
// 报告里写明暂停，而不是整轮直接 return（旧行为会让 pull/push 一起冻住）。

const tempDir = await mkdtemp(join(os.tmpdir(), 'kb-watcher-'))
const vault = join(tempDir, 'vault')
await mkdir(vault, { recursive: true })
const git = (...args) => execFileSync('git', args, { cwd: vault, stdio: 'pipe' })
git('init', '-q')
git('config', 'user.email', 'test@local')
git('config', 'user.name', 'test')
await writeFile(join(vault, 'README.md'), 'hello\n', 'utf8')
git('add', 'README.md')
git('commit', '-q', '-m', 'init')

process.env.DSH_HOME = tempDir
const dataDir = join(tempDir, 'raincoat-kb-desk')
await mkdir(dataDir, { recursive: true })
await writeFile(
  join(dataDir, 'settings.json'),
  JSON.stringify({ vault, autoIngest: false, autoApply: true, autoPush: true, watchSeconds: 60, credentialsFile: join(tempDir, 'credentials.env') }),
  'utf8',
)
await writeFile(join(tempDir, 'credentials.env'), 'WORKER_TOKEN=test\nINGEST_TOKEN=test\n', 'utf8')

const { runWatcherNow, watcherState } = await import('../lib/watcher.js')

test('a paused watcher still runs the sync step and says why nothing was ingested', async () => {
  await runWatcherNow({})
  const report = watcherState().lastReport
  assert.ok(report, 'tick should record a report')
  assert.equal(report.skipped, undefined, 'paused must not short-circuit the whole tick')
  assert.ok(
    (report.notes || []).some((note) => /自动处理已暂停/.test(note)),
    `expected a paused note, got ${JSON.stringify(report.notes)}`,
  )
  assert.equal(report.enqueued, 0)
  assert.equal(watcherState().lastRunAt > 0, true, 'lastRunAt should be recorded')
})
