import assert from 'node:assert/strict'
import test from 'node:test'
import { groupByCwd, diffMembership, planOrder, signature, compareHeaders, canonicalOrder } from '../lib/grouping.js'

const header = (id, cwd, createdAt, extra = {}) => ({ id, cwd, createdAt, ...extra })

test('groupByCwd 按路径分组并按 createdAt 降序', async () => {
  const groups = await groupByCwd([
    header('a', '/x', 100),
    header('b', '/y', 300),
    header('c', '/x', 200),
  ])
  assert.deepEqual([...groups.keys()], ['/x', '/y'])
  assert.deepEqual(groups.get('/x').map((m) => m.id), ['c', 'a'])
  assert.deepEqual(groups.get('/y').map((m) => m.id), ['b'])
})

test('groupByCwd 默认排除子 Agent 会话', async () => {
  const groups = await groupByCwd([
    header('top', '/x', 100),
    header('sub', '/x', 200, { origin: 'subagent' }),
    header('sub2', '/x', 300, { delegationDepth: 1 }),
  ])
  assert.deepEqual(groups.get('/x').map((m) => m.id), ['top'])
})

test('groupByCwd 用 resolvePath 归并同一目录的不同写法', async () => {
  const groups = await groupByCwd(
    [header('a', '/link', 100), header('b', '/real', 200)],
    { resolvePath: async (cwd) => (cwd === '/link' ? '/real' : cwd) },
  )
  assert.deepEqual([...groups.keys()], ['/real'])
  assert.equal(groups.get('/real').length, 2)
})

test('compareHeaders 与 DSH 一致：createdAt 降序、id 升序', () => {
  const list = [header('b', '/x', 100), header('a', '/x', 100), header('c', '/x', 200)]
  list.sort(compareHeaders)
  assert.deepEqual(list.map((h) => h.id), ['c', 'a', 'b'])
})

test('diffMembership 给出需要补进与移出的会话', () => {
  const { attach, detach } = diffMembership(['a', 'b', 'c'], ['b', 'x'])
  assert.deepEqual(attach, ['a', 'c'])
  assert.deepEqual(detach, ['x'])
})

test('planOrder 把当前顺序调整成目标顺序', () => {
  const moves = planOrder(['a', 'b', 'c'], ['b', 'c', 'a'])
  // 模拟执行后应得到目标顺序
  const arr = ['b', 'c', 'a']
  for (const [id, before] of moves) {
    const from = arr.indexOf(id)
    arr.splice(from, 1)
    arr.splice(arr.indexOf(before), 0, id)
  }
  assert.deepEqual(arr, ['a', 'b', 'c'])
})

test('planOrder 顺序一致时不产生移动', () => {
  assert.deepEqual(planOrder(['a', 'b'], ['a', 'b']), [])
})

test('signature 对集合排序后比较', () => {
  assert.equal(signature(['b', 'a', 'a']), signature(['a', 'b']))
  assert.notEqual(signature(['a']), signature(['a', 'b']))
})

test('canonicalOrder 按最新会话时间降序、路径升序', async () => {
  const groups = await groupByCwd([
    header('a', '/old', 100),
    header('b', '/new', 900),
    header('c', '/mid', 500),
    header('d', '/tie', 500),
    header('e', '/tie', 500),
  ])
  assert.deepEqual(canonicalOrder(groups), ['/new', '/mid', '/tie', '/old'])
})
