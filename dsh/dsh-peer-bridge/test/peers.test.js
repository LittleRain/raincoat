import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { labelForProfile, readPeers, removePeer, writePeer } from '../lib/peers.js'

async function tmpdir() {
  return fs.mkdtemp(path.join(os.tmpdir(), 'handoff-peers-'))
}

test('写进去的对端能被读出来，并带上人读的标签', async () => {
  const dir = await tmpdir()
  await writePeer({ dir, pid: 11, origin: 'http://127.0.0.1:1111', url: 'http://127.0.0.1:1111/?token=x', profile: 'desktop' })
  const peers = await readPeers({ dir, excludePid: 999 })
  assert.equal(peers.length, 1)
  assert.equal(peers[0].pid, 11)
  assert.equal(peers[0].label, '桌面端')
  assert.equal(peers[0].profile, 'desktop')
})

test('排除自己', async () => {
  const dir = await tmpdir()
  await writePeer({ dir, pid: 12, origin: 'http://127.0.0.1:12', url: 'http://127.0.0.1:12/?token=y', profile: 'web' })
  const peers = await readPeers({ dir, excludePid: 12 })
  assert.deepEqual(peers, [])
})

test('心跳过期的对端不算活着', async () => {
  const dir = await tmpdir()
  const now = Date.now()
  await writePeer({ dir, pid: 13, origin: 'http://127.0.0.1:13', url: 'http://127.0.0.1:13/?token=z', profile: 'web', now })
  const fresh = await readPeers({ dir, excludePid: 0, now: now + 1_000 })
  assert.equal(fresh.length, 1)
  const stale = await readPeers({ dir, excludePid: 0, now: now + 60_000 })
  assert.deepEqual(stale, [])
})

test('坏文件不影响其他对端', async () => {
  const dir = await tmpdir()
  await fs.writeFile(path.join(dir, 'bad.json'), '{ not json')
  await writePeer({ dir, pid: 14, origin: 'http://127.0.0.1:14', url: 'http://127.0.0.1:14/?token=w', profile: 'web' })
  const peers = await readPeers({ dir, excludePid: 0 })
  assert.equal(peers.length, 1)
  assert.equal(peers[0].pid, 14)
})

test('移除登记后读不到', async () => {
  const dir = await tmpdir()
  await writePeer({ dir, pid: 15, origin: 'http://127.0.0.1:15', url: 'http://127.0.0.1:15/?token=v', profile: 'web' })
  await removePeer({ dir, pid: 15 })
  assert.deepEqual(await readPeers({ dir, excludePid: 0 }), [])
})

test('未知 profile 原样显示，空 profile 兜底', () => {
  assert.equal(labelForProfile('desktop'), '桌面端')
  assert.equal(labelForProfile('web'), 'Web 端')
  assert.equal(labelForProfile('custom'), 'custom')
  assert.equal(labelForProfile(''), '未知端')
  assert.equal(labelForProfile(undefined), '未知端')
})
