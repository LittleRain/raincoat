// 本地摄入反查：远端 history 缺 vault_path 时，插件要能从 vault 的 raw frontmatter
// 认出「这条链接已经落盘成哪篇 raw、对应哪篇摘要」。
import assert from 'node:assert/strict'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import os from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

const { buildLocalIngestIndex, localIngestIndex, urlKeys } = await import('../lib/vault.js')

const root = await mkdtemp(join(os.tmpdir(), 'kb-desk-local-index-'))
await mkdir(join(root, '00 raw/builder/2026/11'), { recursive: true })
await mkdir(join(root, '01 wiki/builder/summaries'), { recursive: true })

await writeFile(join(root, '00 raw/builder/2026/11/fable.md'), [
  '---',
  'title: 实测 Claude Fable 5.2',
  'source_url: https://mp.weixin.qq.com/s/sKoVHL_oNsik9vtUjr0lHg',
  '---',
  '',
  '正文',
].join('\n'), 'utf8')

await writeFile(join(root, '00 raw/builder/2026/11/x-post.md'), [
  '---',
  'title: X 上的帖子',
  'url: "https://x.com/someone/status/123?s=46"',
  '---',
  '',
  '正文',
].join('\n'), 'utf8')

await writeFile(join(root, '01 wiki/builder/summaries/S-2079-fable.md'), [
  '---',
  'title: S-2079 实测 Claude Fable 5.2',
  'source: 00 raw/builder/2026/11/fable.md',
  '---',
  '',
  '摘要',
].join('\n'), 'utf8')

test('urlKeys：原样、去尾斜杠、去 query 都能匹配', () => {
  const keys = urlKeys('https://x.com/someone/status/123?s=46')
  assert.ok(keys.includes('https://x.com/someone/status/123?s=46'))
  assert.ok(keys.includes('https://x.com/someone/status/123'))
})

test('buildLocalIngestIndex：URL → raw + 摘要', async () => {
  const map = await buildLocalIngestIndex(root)
  const hit = map.get('https://mp.weixin.qq.com/s/sKoVHL_oNsik9vtUjr0lHg')
  assert.deepEqual(hit, {
    raw: '00 raw/builder/2026/11/fable.md',
    summary: '01 wiki/builder/summaries/S-2079-fable.md',
  })
})

test('localIngestIndex：尾斜杠、带 query 的链接也能认出来', async () => {
  const lookup = await localIngestIndex(root, { ttl: 0 })
  assert.equal(lookup('https://mp.weixin.qq.com/s/sKoVHL_oNsik9vtUjr0lHg/')?.raw, '00 raw/builder/2026/11/fable.md')
  assert.equal(lookup('https://x.com/someone/status/123')?.raw, '00 raw/builder/2026/11/x-post.md')
  assert.equal(lookup('https://x.com/someone/status/123?s=46')?.raw, '00 raw/builder/2026/11/x-post.md')
  assert.equal(lookup('https://mp.weixin.qq.com/s/never-seen'), null)
  assert.equal(lookup(''), null)
})

// 摘要有两种 source 写法：旧的 source_file 带 ../，正文里也可能只有 [Source: raw/...]。
// raw 里还有 frontmatter 没写收尾 --- 的文件（vault 里真实存在），都要能认出来。
await mkdir(join(root, '00 raw/work/2026/11'), { recursive: true })
await mkdir(join(root, '01 wiki/work/summaries'), { recursive: true })

await writeFile(join(root, '00 raw/work/2026/11/loose.md'), [
  '---',
  'title: 未闭合的 frontmatter',
  'source_url: "https://example.com/loose"',
  'tags:',
  '  - ingest/manual',
  '正文第一行',
].join('\n'), 'utf8')

await writeFile(join(root, '01 wiki/work/summaries/S-1-loose.md'), [
  '---',
  'title: S-1 未闭合的 frontmatter',
  'source_file: "../../../00 raw/work/2026/11/loose.md"',
  '---',
  '',
  '摘要',
].join('\n'), 'utf8')

test('未闭合 frontmatter 的 raw + source_file 写法也能对上', async () => {
  const lookup = await localIngestIndex(root, { ttl: 0 })
  assert.deepEqual(lookup('https://example.com/loose'), {
    raw: '00 raw/work/2026/11/loose.md',
    summary: '01 wiki/work/summaries/S-1-loose.md',
  })
})
