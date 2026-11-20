import assert from 'node:assert/strict'
import { access, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import os from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

// 同一篇文章被重投（worker 重新推送 / 手工补录）时，Inbox 那份要就地丢弃，
// 并在 log.md 留一条 triage:drop —— 不然会白跑一次模型、再多长一条 job。

const tempDir = await mkdtemp(join(os.tmpdir(), 'kb-dup-'))
const vault = join(tempDir, 'vault')
await mkdir(join(vault, '00 Inbox/2026/11/20'), { recursive: true })
await mkdir(join(vault, '00 raw/builder'), { recursive: true })
await mkdir(join(vault, '01 wiki'), { recursive: true })

const url = 'https://mp.weixin.qq.com/s/DUPLICATE-CASE'
await writeFile(
  join(vault, '00 raw/builder/already-ingested.md'),
  `---\ntitle: 已入库\nspace: builder\nsource_url: ${url}\n---\n\n正文\n`,
  'utf8',
)
await writeFile(
  join(vault, '00 Inbox/2026/11/20/重投的那份.md'),
  `---\ntitle: 重投的那份\nurl: ${url}\n---\n\n正文\n`,
  'utf8',
)

const { dropDuplicateInbox } = await import('../lib/triage.js')

test('重投的 Inbox 文件被丢弃，并在 log.md 留下 drop 痕迹', async () => {
  const doc = { path: '00 Inbox/2026/11/20/重投的那份.md', title: '重投的那份' }
  const result = await dropDuplicateInbox(vault, doc, { raw: '00 raw/builder/already-ingested.md' })

  await assert.rejects(access(join(vault, doc.path)), 'Inbox 副本应当被移走')
  assert.equal(result.rawPath, '00 raw/builder/already-ingested.md')

  const log = await readFile(join(vault, '01 wiki/log.md'), 'utf8')
  assert.match(log, /triage:builder \| 重投的那份 → drop/)
  assert.match(log, /already-ingested\.md/)
  assert.equal(result.changes.length, 2)
})
