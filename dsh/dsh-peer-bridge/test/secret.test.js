import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { ensureSecret, providedSecret, secretMatches } from '../lib/secret.js'

async function tmpHome() {
  return fs.mkdtemp(path.join(os.tmpdir(), 'handoff-secret-'))
}

test('首次生成、二次复用，权限 0600', async () => {
  const home = await tmpHome()
  const first = await ensureSecret(home)
  const second = await ensureSecret(home)
  assert.equal(typeof first, 'string')
  assert.ok(first.length >= 32)
  assert.equal(first, second)
  const stat = await fs.stat(path.join(home, 'handoff', 'secret'))
  assert.equal(stat.mode & 0o777, 0o600)
})

test('并发创建只留一份', async () => {
  const home = await tmpHome()
  const values = await Promise.all([ensureSecret(home), ensureSecret(home), ensureSecret(home)])
  assert.equal(new Set(values).size, 1)
})

test('比较是严格相等的', () => {
  assert.equal(secretMatches('abc', 'abc'), true)
  assert.equal(secretMatches('abc', 'abd'), false)
  assert.equal(secretMatches('abc', 'abcd'), false)
  assert.equal(secretMatches(undefined, 'abc'), false)
  assert.equal(secretMatches('abc', undefined), false)
})

test('请求头取令牌，数组取第一个', () => {
  assert.equal(providedSecret({ headers: { 'x-dsh-bridge': 'v' } }), 'v')
  assert.equal(providedSecret({ headers: { 'x-dsh-bridge': ['v', 'w'] } }), 'v')
  assert.equal(providedSecret({ headers: {} }), undefined)
  assert.equal(providedSecret(undefined), undefined)
})
