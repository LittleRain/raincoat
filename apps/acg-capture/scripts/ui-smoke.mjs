// 面板离线冒烟：不启动宿主，验证「运行记录」的可读文案与整棵组件树能渲染。
// 跑法：node apps/acg-capture/scripts/ui-smoke.mjs
// 说明：用真实 ~/.dsh/acg-capture/runs/*/run.json 当夹具，把 useState 的初值换成夹具
//      （React 元素会被逐个展开调用），所以只测格式化与渲染，不测交互与网络。
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const CLIENT = fileURLToPath(new URL('../client.js', import.meta.url))
const RUNS = path.join(os.homedir(), '.dsh', 'acg-capture', 'runs')

const src = fs.readFileSync(CLIENT, 'utf8')

const fakeReact = {
  // children 同时放进 props：组件用 h(X, props, child) 传子节点时，React 是从
  // props.children 取的，桩不这么做就会让「带子节点的组件」在冒烟里渲染成空壳。
  createElement: (type, props, ...children) => {
    const kids = children.flat(9).filter((c) => c !== null && c !== undefined && c !== false)
    return {
      type: typeof type === 'function' ? type.name || 'Fn' : type,
      fn: typeof type === 'function' ? type : null,
      props: { ...(props || {}), children: kids },
      children: kids,
    }
  },
  useState: (init) => [typeof init === 'function' ? init() : init, () => {}],
  useEffect: () => {},
  useCallback: (fn) => fn,
  useRef: (init) => ({ current: init === undefined ? null : init }),
}
const requireStub = (name) => (name === 'react' ? fakeReact : {})

/** 夹具：真实 run.json，list 接口里有的字段（itemCount/feeds）在这里补齐。 */
function fixtures() {
  if (!fs.existsSync(RUNS)) return []
  return fs
    .readdirSync(RUNS)
    .filter((name) => name.startsWith('r-'))
    .sort()
    .reverse()
    .map((name) => {
      const dir = path.join(RUNS, name)
      const run = JSON.parse(fs.readFileSync(path.join(dir, 'run.json'), 'utf8'))
      run.itemCount = Array.isArray(run.items) ? run.items.length : 0
      if (!run.feeds) {
        const file = path.join(dir, 'feeds.json')
        if (fs.existsSync(file)) {
          const feeds = JSON.parse(fs.readFileSync(file, 'utf8'))
          run.feeds = {
            items: (feeds.items || []).length,
            channels: (feeds.captured || []).length,
            errors: (feeds.errors || []).length,
          }
        }
      }
      return run
    })
}

const ALL = fixtures()
// 最新一轮补一份 scope（引擎 2026-11-17 之后才写），同时留几轮没 scope 的老数据测退化
const newest = ALL.find((run) => run.kind === 'discover' && (run.items || []).length)
if (newest) newest.feeds = { ...(newest.feeds || {}), ds: { queries: 6, hits: 8, errors: 0 } }
if (newest && !newest.scope) {
  newest.scope = {
    mode: 'new_pans',
    window: { since: newest.params?.since, until: newest.params?.until },
    brands: ['一番赏（大陆）', 'KAYOU赏', '好物赏'],
    channels: { weibo: 12, wechat: 3, xhs: 1 },
    pages: newest.params?.pages || 2,
    groups: [{ name: 'g1', brands: ['KAYOU赏'] }],
  }
}

/** 载入插件，并把面板的 useState 初值换成夹具（tab / 选中的运行用 localStorage 夹具控制）。 */
function storeFor(tab, fixture) {
  // tab 用「场景 + 子页」拼：discover / backfill / guide 属官方赏，bag / bag-leads / bag-guide 属福袋，
  // vg / summary / vg-guide 属虚拟商品
  const scene = tab === 'vg' || tab === 'summary' || tab === 'vg-guide' ? 'vg' : tab.startsWith('bag') ? 'bag' : 'kuji'
  const kind = scene === 'vg' ? 'vg-discover' : scene === 'bag' ? 'bag-discover' : tab
  const state = { scene }
  if (scene === 'kuji') state['kuji:tab'] = tab
  if (scene === 'vg') state['vg:tab'] = tab === 'summary' ? 'summary' : tab === 'vg-guide' ? 'guide' : 'tasks'
  if (scene === 'bag') state['bag:tab'] = tab === 'bag-leads' ? 'leads' : tab === 'bag-guide' ? 'guide' : 'tasks'
  const first = (fixture.filter((run) => run.kind === kind)[0] || {}).id
  if (first) state[`run:${scene === 'kuji' ? kind : scene}`] = first
  return state
}

function loadPanel(tab, fixture = ALL, prevStore) {
  let mod = null
  // 真 localStorage 会被组件写回；这里用可变对象模拟，才能验「切走再回来」的读回路径
  const store = { data: prevStore || storeFor(tab, fixture) }
  globalThis.window = {
    __ModuleLoader__: { load: (m) => { mod = m } },
    localStorage: {
      getItem: (key) => (key === 'acg-ui-state' ? JSON.stringify(store.data) : null),
      setItem: (key, value) => {
        if (key === 'acg-ui-state') store.data = JSON.parse(value)
      },
      removeItem: () => {},
    },
  }
  globalThis.__FIXTURE__ = fixture
  globalThis.__TAB__ = tab
  const patched = src
    // 福袋 / 虚拟商品的任务页不接 kind 属性，按各自引擎的 kind 注入夹具（先做带函数名的锚点替换）
    .replace(
      `function BagTasks() {
      const [runs, setRuns] = useState([])
      const [run, setRun] = useState(null)`,
      `function BagTasks() {
      const [runs, setRuns] = useState(__FIXTURE__.filter((r) => r.kind === 'bag-discover'))
      const [run, setRun] = useState(__FIXTURE__.filter((r) => r.kind === 'bag-discover')[0] || null)`,
    )
    .replace(
      `function VGTasks() {
      const [runs, setRuns] = useState([])
      const [run, setRun] = useState(null)`,
      `function VGTasks() {
      const [runs, setRuns] = useState(__FIXTURE__.filter((r) => r.kind === 'vg-discover'))
      const [run, setRun] = useState(__FIXTURE__.filter((r) => r.kind === 'vg-discover')[0] || null)`,
    )
    .replace('const [runs, setRuns] = useState([])', 'const [runs, setRuns] = useState(__FIXTURE__.filter((r) => r.kind === kind))')
    .replace('const [run, setRun] = useState(null)',
      'const [run, setRun] = useState(__FIXTURE__.filter((r) => r.kind === kind)[0] || null)')
  new Function('window', 'require', patched)(globalThis.window, requireStub)

  let panel = null
  mod.factory(requireStub).apply({
    slots: {
      inject: (name, fn) => fn(),
      register: (meta, component) => {
        if (meta.name === 'main') panel = component
        return () => {}
      },
    },
  })
  return { panel, test: mod.factory(requireStub).__test, store }
}

function walk(node, depth = 0, out = []) {
  if (typeof node === 'string' || typeof node === 'number') {
    out.push(String(node))
    return out
  }
  if (!node || typeof node !== 'object') return out
  if (node.fn) {
    const rendered = node.fn(node.props || {})
    out.push(`${'  '.repeat(depth)}<${node.type}>`)
    for (const child of Array.isArray(rendered) ? rendered : [rendered]) walk(child, depth + 1, out)
    return out
  }
  if (node.type) out.push(`${'  '.repeat(depth)}${node.type}`)
  for (const child of node.children || []) walk(child, depth + 1, out)
  return out
}

function report(tab, checks, fixture) {
  const { panel } = loadPanel(tab, fixture)
  const text = walk(panel()).join(' | ')
  console.log(`\n[${tab}]`)
  let failed = 0
  for (const key of checks) {
    const ok = text.includes(key)
    if (!ok) failed += 1
    console.log(`${ok ? '✓' : '✗'} ${key}`)
  }
  return failed
}

const { test } = loadPanel('discover')
const discover = ALL.find((run) => run.kind === 'discover')
const backfill = ALL.find((run) => run.kind === 'backfill')

console.log('样例（列表里那一行会长这样）：')
for (const run of [discover, backfill].filter(Boolean)) {
  console.log(`· ${test.statusLabel(run.status)} | ${test.runHeadline(run)}`)
  console.log(`  ${test.scopeBrief(run)}`)
}

let failed = 0
// 三个任务页的骨架必须一样：抓取配置（带配置项）→ 当前状态 → 运行记录 → 详情。
// 2026-11-18 之前只有游戏虚拟商品有这两块，这份断言就是防回退的。
const UNIFIED = ['抓取配置', '当前状态', '写回表格', '运行记录', '开始抓取']
failed += report('discover', [
  ...UNIFIED,
  '抓取窗口',
  '只用已确认渠道',
  '已收录盘',
  '缺单抽价',
  '查看中',
  '抓新品 11-16 → 11-17',
  '候选 5',
  '采纳 2',
  '用时 5 分 38 秒',
  '个品牌',
  '微博 12',
  '原文 52 条',
  '每号 2 页',
  '抓取逻辑',
  'DS 搜索 6 次',
  '已写入表',
  'r-20261117-132937-discover',
])
failed += report('backfill', [
  ...UNIFIED.map((key) => (key === '开始抓取' ? '开始补齐' : key)),
  '本轮派发',
  '缺子品结构',
  '补齐信息',
  '抓取逻辑',
  '补缺口：3 个盘',
  'dry-run 未写表',
  '数量 3',
])
failed += report('bag', [...UNIFIED, '线索范围', 'workbuddy + DeepSeek', '已入库福袋', '可用渠道'])
// 三个 tab 都要有「流程说明」，且都是同一套排版（七步 / 分工 / 疑问 / 词表 / 自己跑）
const GUIDE_SHELL = ['一轮任务的七步', '常见疑问', '词表', '想自己跑一遍']
failed += report('guide', [...GUIDE_SHELL, '这套东西是怎么跑的', '四道门全过才算数', '为什么写入是 0', 'LAST / 最终赏', '--kind discover'])
failed += report('bag-guide', [...GUIDE_SHELL, '官方福袋是怎么跑的', '两个子页的分工', '等价载体', 'lead-genshin', '--kind discover'])
failed += report('vg-guide', [...GUIDE_SHELL, '游戏虚拟商品是怎么跑的', '三路取证', '首充双倍', '--discover-only'])
failed += report('vg', [...UNIFIED, '抓取模式', '游戏窗口', '取证通道', '发现 + 首抓', '已入库游戏'])
failed += report('summary', ['游戏汇总', '已收录游戏', '渠道库'])

// 游戏虚拟商品的格式化：用一条合成运行记录验「人可读」，不依赖真实 run
const vgRun = {
  id: 'r-20261117-100000-vg-discover',
  kind: 'vg-discover',
  trigger: 'schedule',
  dryRun: false,
  status: 'done',
  stage: 'done',
  startedAt: '2026-11-17T10:00:00+08:00',
  endedAt: '2026-11-17T10:03:00+08:00',
  params: { windowDays: 60, since: '2026-09-19', until: '2026-11-17', discoverOnly: false },
  counts: { accepted: 3, pending: 1, written: 3, duplicate: 2 },
  scope: { window: { since: '2026-09-19', until: '2026-11-17' }, lanes: ['workbuddy', 'deepseek'], knownGames: 5 },
  feeds: { store: 5, workbuddy: 4, deepseek: 3 },
  discovery: {
    raw: 9,
    kept: 2,
    dropped: 7,
    games: [{ game: '某新游', publisher: '某发行商', priority: 'P0', heat: ['发行商名单', '商店内购页'], appStore: '', status: '已上线' }],
    droppedGames: [{ game: '某新游', reason: 'threshold_missed' }],
  },
  itemCount: 5,
  items: [],
}
console.log('\n[vg 文案]')
for (const line of test.vgScopeLines(vgRun)) console.log(`· ${line}`)
console.log(`· ${test.vgRunHeadline(vgRun)} | ${test.vgRunMeta(vgRun)}`)
console.log(`· 统计 ${test.vgRunStats(vgRun).map(([k, v]) => `${k} ${v}`).join(' / ')}`)
const vgExpect = [
  ['表里已有 5 个游戏', test.vgScopeLines(vgRun).join('')],
  ['候选 9 → 过热度门槛 2 → 丢弃 7', test.vgScopeLines(vgRun).join('')],
  ['发现新游戏 + 首抓入库', test.vgRunHeadline(vgRun)],
  ['最近 60 天新游戏', test.vgWindowLabel(vgRun.params.windowDays)],
  ['某新游（热度不够）', test.vgDropText(vgRun.discovery.droppedGames)],
  ['面额与价格不成比例', test.vgReason(['ratio_conflict'])],
]
for (const [label, text] of vgExpect) {
  const ok = String(text).includes(label)
  if (!ok) failed += 1
  console.log(`${ok ? '✓' : '✗'} ${label}`)
}

// 补齐信息的三种结论（2026-11-17：待确认要有「为什么要你确认」，未公布不该给采纳按钮）
const mixed = {
  id: 'r-20261117-120000-backfill',
  kind: 'backfill',
  trigger: 'manual',
  dryRun: true,
  status: 'done',
  stage: 'done',
  startedAt: '2026-11-17T12:00:00+08:00',
  endedAt: '2026-11-17T12:09:00+08:00',
  params: { batchSize: 3 },
  counts: { accepted: 0, rejected: 0, pending: 1, unavailable: 2, written: 0 },
  batch: [
    { panRecordId: 'p1', pan: '一番赏 Tamagotchi', gaps: ['count'] },
    { panRecordId: 'p2', pan: '一番赏 女神异闻录 30th', gaps: ['count'] },
    { panRecordId: 'p3', pan: '一番赏 GLAY', gaps: ['count'] },
  ],
  itemCount: 3,
  items: [
    {
      id: 'i-p1', pan: '一番赏 Tamagotchi', panRecordId: 'p1', gap: 'count', status: 'pending_review',
      reasons: [], fields: { count: 'pending' }, found: { count: 10 },
      blocked: [{ field: 'count', kind: 'A', source: 'https://lite-gmc.oneone.com.tw/product/43738', error: 'ConnectionResetError' }],
      ask: '各赏数量：候选里已经有值（10 个赏别），但 lite-gmc.oneone.com.tw 打不开（ConnectionResetError），机器核不了原文；你能打开来源核对，就填 URL 点「采纳并写入」；核不了就判废，等下一轮',
      candidate: { prizes: [{ kind: 'A', count: 2 }, { kind: 'B', count: 1 }], total: 70 },
    },
    {
      id: 'i-p2', pan: '一番赏 女神异闻录 30th', panRecordId: 'p2', gap: 'count', status: 'unavailable',
      reasons: ['count_not_published'], fields: { count: 'unavailable' }, found: { count: 0 },
      ask: '各赏数量：来源页没有这个数（一番赏预告页只写「全 N 種」的款式数，不写每款几个）；这轮没有可确认的东西，等官方或代理页更新后下一轮会自动再补',
      candidate: { prizes: [{ kind: 'A', count: null }] },
    },
    {
      id: 'i-p3', pan: '一番赏 GLAY', panRecordId: 'p3', gap: 'count', status: 'unavailable',
      reasons: ['count_not_published'], fields: { count: 'unavailable' },
      ask: '各赏数量：来源页没有这个数；这轮没有可确认的东西，等官方或代理页更新后下一轮会自动再补',
      candidate: {},
    },
  ],
}
failed += report('backfill', [
  '待确认',
  '来源未公布',
  '未公布',
  '各赏数量：候选里已经有值',
  '机器核不了原文',
  '采纳并写入（数量）',
  '不需要你确认',
  '来源页没有这个数',
], [mixed])

// 老运行没有 ask 字段时也要能说人话（退化路径）
const legacyPending = { ...mixed.items[1], ask: '', reasons: ['count_missing'], status: 'pending_review', fields: undefined }
console.log('\n[老运行的退化文案]')
const legacyText = test.askFallback(legacyPending)
console.log(`· ${legacyText}`)
if (!legacyText.includes('机器判断不了')) failed += 1
if (!test.askFallback({ ...mixed.items[1], ask: '' }).includes('来源没有这个数')) failed += 1
console.log(test.writableFields(mixed.items[0]).join(',') === 'count' ? '✓ 有值才给采纳' : '✗ 有值才给采纳')
if (test.writableFields(mixed.items[0]).join(',') !== 'count') failed += 1
if (test.writableFields(mixed.items[2]).length) { failed += 1; console.log('✗ 没值不该给采纳') }

// 切走再回来：上一轮看到哪（tab / 子页 / 选中的运行 / 滚动位置）要能从 localStorage 读回来
console.log('\n[恢复上次页面]')
const first = loadPanel('backfill')
const saved = { 'run:backfill': 'r-20261117-120000-backfill', 'scroll:kuji': 320 }
for (const [key, value] of Object.entries(saved)) first.test.writeUiState(key, value)
const restored = first.test.readUiState()
for (const [key, value] of Object.entries(saved)) {
  const ok = restored[key] === value
  if (!ok) failed += 1
  console.log(`${ok ? '✓' : '✗'} ${key} = ${JSON.stringify(restored[key])}`)
}
// 同一个 localStorage 重新挂载 = 切走再回来
const remount = loadPanel('backfill', [mixed], first.store.data)
const remountText = walk(remount.panel()).join(' | ')
const remountOk = remountText.includes('补齐信息') && remountText.includes('各赏数量：候选里已经有值')
if (!remountOk) failed += 1
console.log(`${remountOk ? '✓' : '✗'} 重新挂载后仍停在「补齐信息」并显示上次选中的运行`)

// 抓新品的待确认：没有价格/数量字段，采纳就是建一行新盘，按钮不能因为「没有可写字段」被禁用
const discoverPending = {
  id: 'r-20261117-110000-discover', kind: 'discover', trigger: 'manual', dryRun: true,
  status: 'done', stage: 'done', startedAt: '2026-11-17T11:00:00+08:00', endedAt: '2026-11-17T11:05:00+08:00',
  params: { pages: 2, groups: 3 }, counts: { accepted: 0, rejected: 0, pending: 1, unavailable: 0, written: 0 },
  itemCount: 1,
  items: [{
    id: 'd-1', pan: '一番赏 崩坏：星穹铁道 第四弹', brand: '一番赏', gap: 'new',
    status: 'pending_review', reasons: ['render_incomplete'],
    candidate: { name: '一番赏 崩坏：星穹铁道 第四弹', brand: '一番赏', release: '2026-11-20' },
  }],
}
failed += report('discover', ['采纳并写入（新盘）', '把这条候选建进主表'], [discoverPending])

// 逐条候选按结论筛选：三个 tab 的任务详情共用一套（默认全部，待确认排最前）
console.log('\n[逐条候选状态筛选]')
const renderText = (tab, fixture = ALL, store) => walk(loadPanel(tab, fixture, store).panel()).join(' | ')
const tableRows = (text) => text.split(' | ').filter((part) => part.trim() === 'tr').length

// 各 tab 的结论用词不完全一样（vg 把 duplicate 叫「表内已有」），断言跟着各自的词表走
const TAB_STATUS_WORDS = { discover: {}, bag: {}, vg: { duplicate: '表内已有' } }
for (const [tab, kind] of [['discover', 'discover'], ['bag', 'bag-discover'], ['vg', 'vg-discover']]) {
  const run = ALL.find((item) => item.kind === kind)
  if (!run) continue
  const text = renderText(tab, ALL, storeFor(tab, ALL))
  const groups = test.itemStatusCounts(run.items || [])
  const allLabel = `全部 ${(run.items || []).length}`
  const okAll = text.includes(allLabel)
  if (!okAll) failed += 1
  console.log(`${okAll ? '✓' : '✗'} ${tab}：${allLabel}`)
  for (const group of groups) {
    const label = `${TAB_STATUS_WORDS[tab][group.status] || test.statusLabel(group.status)} ${group.count}`
    const ok = text.includes(label)
    if (!ok) failed += 1
    console.log(`${ok ? '✓' : '✗'} ${tab}：${label}`)
  }
}

// 筛到没有条目的状态：给一句带状态名的话，而不是空表格
const emptyText = renderText('discover', ALL, { ...storeFor('discover', ALL), 'items:filter:discover': 'pending_review' })
const emptyOk = emptyText.includes('「待确认」下没有条目')
if (!emptyOk) failed += 1
console.log(`${emptyOk ? '✓' : '✗'} 筛到空：显示「待确认」下没有条目`)

// 筛到「判废」：只剩表头 + 判废行，已采纳行不再渲染
const discoverRun = ALL.find((item) => item.kind === 'discover')
if (discoverRun) {
  const baseRows = tableRows(renderText('discover', ALL, storeFor('discover', ALL)))
  const rejectedRows = tableRows(renderText('discover', ALL, { ...storeFor('discover', ALL), 'items:filter:discover': 'rejected' }))
  const expected = (discoverRun.items || []).filter((item) => item.status === 'rejected').length
  const okRows = rejectedRows === 1 + expected && rejectedRows < baseRows
  if (!okRows) failed += 1
  console.log(`${okRows ? '✓' : '✗'} 筛到判废：${rejectedRows} 行（表头 1 + 判废 ${expected}），默认 ${baseRows} 行`)
}

console.log(`\n${failed ? `✗ ${failed} 项没命中` : '✓ 全部通过'}`)
process.exit(failed ? 1 : 0)
