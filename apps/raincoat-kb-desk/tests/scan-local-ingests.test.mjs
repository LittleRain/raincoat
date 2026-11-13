// 本地摄入扫描：没走远端队列、只落在 vault 里的摄入（agent 直接落盘 / 手工整理）
// 也要能被「摄入」页列出来；没有来源链接的手记不混进来。
import assert from 'node:assert/strict'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import os from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

const { scanLocalIngests } = await import('../lib/vault.js')

const root = await mkdtemp(join(os.tmpdir(), 'kb-desk-scan-local-'))
await mkdir(join(root, '00 raw/builder/2026/11'), { recursive: true })
await mkdir(join(root, '01 wiki/builder/summaries'), { recursive: true })

// 播客这种：source_url + 摘要页用 source_file 指回 raw
await writeFile(join(root, '00 raw/builder/2026/11/podcast.md'), [
  '---',
  'title: 对谈千问蒋冠军',
  'platform: xiaoyuzhou',
  'source_url: "https://www.xiaoyuzhoufm.com/episode/abc123"',
  'ingested_at: "2026-11-13T14:15:39+08:00"',
  '---',
  '',
  '正文',
].join('\n'), 'utf8')

await writeFile(join(root, '01 wiki/builder/summaries/S-2089-podcast.md'), [
  '---',
  'title: S-2089 对谈千问蒋冠军',
  'source_file: "../../../00 raw/builder/2026/11/podcast.md"',
  '---',
  '',
  '摘要',
].join('\n'), 'utf8')

// 灵感 / 手记：没有来源链接，不该出现
await writeFile(join(root, '00 raw/builder/2026/11/idea.md'), [
  '---',
  'title: 一个想法',
  '---',
  '',
  '随手记',
].join('\n'), 'utf8')

test('scanLocalIngests：带 url 的 raw 出现，并带上摘要路径', async () => {
  const rows = await scanLocalIngests(root, { days: 3650, limit: 20 })
  assert.equal(rows.length, 1)
  assert.equal(rows[0].raw, '00 raw/builder/2026/11/podcast.md')
  assert.equal(rows[0].summary, '01 wiki/builder/summaries/S-2089-podcast.md')
  assert.equal(rows[0].platform, 'xiaoyuzhou')
  assert.equal(rows[0].space, 'builder')
  assert.equal(rows[0].url, 'https://www.xiaoyuzhoufm.com/episode/abc123')
})

test('scanLocalIngests：days 之外的老摄入被过滤掉', async () => {
  const old = await mkdtemp(join(os.tmpdir(), 'kb-desk-scan-local-old-'))
  await mkdir(join(old, '00 raw/acg'), { recursive: true })
  await writeFile(join(old, '00 raw/acg/stale.md'), [
    '---',
    'title: 很久以前的素材',
    'source_url: "https://example.com/old"',
    'ingested_at: "2025-01-01"',
    '---',
    '',
    '正文',
  ].join('\n'), 'utf8')
  assert.equal((await scanLocalIngests(old, { days: 30, limit: 20 })).length, 0)
  assert.equal((await scanLocalIngests(old, { days: 3650, limit: 20 })).length, 1)
})
