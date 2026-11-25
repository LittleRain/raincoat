/**
 * DSH workspace 对账插件（host 侧）。
 *
 * 背景：DSH 的 workspace 注册表（~/.dsh/storages/workspace.json）是「内存权威 + 整文件回写」。
 * 同一个 DSH home 上跑着两个 host（launchd 的 `dsh web` 与桌面端自带 host）时，
 * 两个进程各持一份内存快照、互相整份覆盖：最后写入的赢，另一端的分组、顺序、归档集
 * 就会和磁盘对不上——这就是「web 看到的对话和桌面端不一样」的根因。
 *
 * 本插件把注册表收敛成「会话目录的纯函数」：
 *   - 分组：按会话 header 的 canonical cwd 分组（与 DSH 自带 bootstrap 同一套语义）
 *   - 顺序：组内按 createdAt 降序、id 升序（与 DSH 的 compareHeaders 一致）
 *   - 归档：跨 host 的真源放在本插件自己的状态文件里，两端各自同步进内存注册表
 * 两个 host 算的是同一个纯函数，任一端写出的内容都相同，于是互相覆盖不再产生差异；
 * 崩溃重启后重新对账即可自愈，不需要人工修数据。
 *
 * 约束：apply() 绝不能抛异常——插件加载失败会让 host 起不来（本插件要解决的正是这类崩溃）。
 */
import fs from 'node:fs/promises'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { groupByCwd, diffMembership, planOrder, signature, canonicalOrder } from './grouping.js'
import { readState, writeState, writeStatus, readDefaultWorkspaceId, readCachedSummary } from './state.js'

const TICK_MS = 60_000
const FIRST_TICK_MS = 1_000

export function startReconciler(ctx) {
  const lookup = (name) => {
    try {
      return typeof ctx?.get === 'function' ? ctx.get(name) : ctx?.[name]
    } catch {
      return undefined
    }
  }
  const registry = lookup('workspaceRegistry')
  const persistence = lookup('sessionPersistence')
  if (!registry || !persistence) return
  const startedAt = Date.now()

  let timer = null
  let firstHandle = null
  let running = false
  let lastLocalSig = null
  let lastCanonicalSig = null
  const summaryCache = new Map()

  const log = (message) => {
    try {
      console.log(`[workspace-reconciler] ${message}`)
    } catch {
      /* 日志失败不能影响 host */
    }
  }

  const canonical = async (cwd) => {
    try {
      return await fs.realpath(cwd)
    } catch {
      return cwd
    }
  }

  /**
   * 把每个 workspace 的成员对齐到规范分组，并按规范顺序排列。
   *
   * 分组输入是「全部会话」（含 0 轮次的空壳），所以空壳会被保留在 cwd 所属的 workspace 里，
   * 不再被 detach。原因：GUI 的侧栏分组与工作区高亮完全由 `workspace.sessionIds` 决定
   * （`groupByWorkspace` / `owningGroupKey`），一旦刚打开、还没说话的会话被移出，
   * 它就会掉进「未分组」、所在工作区的选中态随之消失；若工作区因此变空，
   * `pruneWorkspaces` 还会把整行删掉，表现为「工作区和内容一起丢了」。
   */
  async function alignMembership(groups) {
    const byPath = new Map(registry.list().map((entity) => [entity.path, entity]))
    for (const [workspacePath, members] of groups) {
      let entity = byPath.get(workspacePath)
      if (!entity) {
        try {
          entity = await registry.create(workspacePath, path.basename(workspacePath))
          byPath.set(workspacePath, entity)
          log(`新建 workspace ${workspacePath}`)
        } catch (error) {
          log(`创建 workspace 失败 ${workspacePath}：${error?.message ?? error}`)
          continue
        }
      }
      const desired = members.map((member) => member.id)
      const { attach, detach } = diffMembership(desired, entity.sessionIds.slice())
      for (const id of detach) {
        try {
          await entity.detachSession(id)
        } catch (error) {
          log(`移出 ${id} 失败：${error?.message ?? error}`)
        }
      }
      for (const id of attach) {
        try {
          await entity.attachSession(id)
        } catch (error) {
          log(`纳入 ${id} 失败：${error?.message ?? error}`)
        }
      }
      for (const [id, before] of planOrder(desired, entity.sessionIds.slice())) {
        try {
          await entity.insertSessionBefore(id, before)
        } catch (error) {
          log(`排序 ${id} 失败：${error?.message ?? error}`)
        }
      }
    }
  }

  /**
   * 清理历史残留：
   *   - 同一路径登记了多行（两个 host 各自建过）→ 保留成员多的那条，其余删掉
   *   - 路径下已经没有会话、又不是默认 workspace 的空行 → 删掉
   * 删 workspace 只删登记，不删会话与文件。
   */
  async function pruneWorkspaces(groups) {
    const defaultId = readDefaultWorkspaceId()
    const byPath = new Map()
    for (const entity of registry.list()) {
      const list = byPath.get(entity.path) ?? []
      list.push(entity)
      byPath.set(entity.path, list)
    }
    for (const [workspacePath, entities] of byPath) {
      if (entities.length > 1) {
        const keep = entities
          .slice()
          .sort((left, right) => right.sessionIds.length - left.sessionIds.length || left.id.localeCompare(right.id))[0]
        for (const entity of entities) {
          if (entity.id === keep.id) continue
          try {
            await registry.delete(entity.id)
            log(`删除重复 workspace ${workspacePath}（${entity.id}）`)
          } catch (error) {
            log(`删除重复 workspace 失败 ${entity.id}：${error?.message ?? error}`)
          }
        }
        continue
      }
      const entity = entities[0]
      if (!entity) continue
      const members = groups.get(workspacePath)
      const empty = !members || members.length === 0
      if (empty && entity.id !== defaultId && entity.sessionIds.length === 0) {
        try {
          await registry.delete(entity.id)
          log(`删除空 workspace ${workspacePath}`)
        } catch (error) {
          log(`删除空 workspace 失败 ${entity.id}：${error?.message ?? error}`)
        }
      }
    }
  }

  /** 把注册表里的 workspace 顺序调整成规范顺序。 */
  async function alignOrder(groups) {
    const entities = registry.list()
    const byPath = new Map(entities.map((entity) => [entity.path, entity]))
    const desired = canonicalOrder(groups)
      .map((workspacePath) => byPath.get(workspacePath))
      .filter(Boolean)
      .map((entity) => entity.id)
    const current = entities.map((entity) => entity.id)
    for (const [id, before] of planOrder(desired, current)) {
      try {
        await registry.insertBefore(id, before)
      } catch (error) {
        log(`调整 workspace 顺序失败 ${id}：${error?.message ?? error}`)
      }
    }
  }

  /**
   * 从共享投影缓存读每条会话的摘要（标题 + 轮次数），按 mtime 缓存避免反复解析大文件。
   * 这是两个 host 共享的判据：谁在读都一样，所以不会引入新的分歧。
   */
  function collectSummaries(headers) {
    const summaries = []
    for (const header of headers ?? []) {
      if (!header?.id) continue
      const cached = summaryCache.get(header.id)
      const fresh = readCachedSummary(header.id)
      if (!fresh) continue
      if (cached && cached.mtimeMs === fresh.mtimeMs) {
        summaries.push(cached)
        continue
      }
      const summary = { sessionId: header.id, ...fresh }
      summaryCache.set(header.id, summary)
      summaries.push(summary)
    }
    return summaries
  }

  /**
   * 找出「本 host 看不到标题、但共享投影缓存里有标题」的会话。
   * 这类会话通常正被另一个 host 占用（活跃会话），投影快照还没固化到会话日志，
   * 于是另一端侧栏显示成「未命名」。这里只报告、不代写（跨 host 抢写会话日志有风险）。
   */
  async function collectPendingTitles() {
    const controller = typeof ctx.get === 'function' ? ctx.get('sessionController') : ctx.sessionController
    if (!controller || typeof controller.list !== 'function') return []
    const pending = []
    let items = []
    try {
      const result = await controller.list({})
      items = result?.items ?? result?.value?.items ?? []
    } catch {
      return []
    }
    const cached = new Map(collectSummaries(items.map((item) => ({ id: item?.sessionId }))).map((summary) => [summary.sessionId, summary]))
    for (const item of items) {
      const title = item?.projections?.values?.title
      if (title) continue
      const known = cached.get(item?.sessionId)
      if (known?.title) pending.push({ sessionId: item.sessionId, title: known.title })
    }
    return pending
  }

  /** 把规范归档集套用到本 host 的内存注册表。 */
  async function applyArchived(canonicalIds) {
    const local = new Set(registry.archivedSessionIds)
    const wanted = new Set(canonicalIds)
    for (const id of wanted) {
      if (local.has(id)) continue
      try {
        await registry.archiveSession(id)
      } catch (error) {
        log(`归档 ${id} 失败：${error?.message ?? error}`)
      }
    }
    for (const id of local) {
      if (wanted.has(id)) continue
      try {
        await registry.unarchiveSession(id)
      } catch (error) {
        log(`取消归档 ${id} 失败：${error?.message ?? error}`)
      }
    }
  }

  /**
   * 归档集同步：规范文件是跨 host 真源。
   *   - 规范文件比本进程启动新、且本地没有新变化 → 采用规范文件（另一端刚操作过）
   *   - 本地有变化（用户刚在本端归档/取消归档）→ 写回规范文件
   */
  async function syncArchived() {
    const local = [...registry.archivedSessionIds]
    const localSig = signature(local)
    const state = readState()
    if (state === null) {
      writeState({ archivedSessionIds: local })
      lastLocalSig = localSig
      lastCanonicalSig = localSig
      return
    }
    const canonicalIds = state.archivedSessionIds
    const canonicalSig = signature(canonicalIds)
    if (localSig === canonicalSig) {
      lastLocalSig = localSig
      lastCanonicalSig = canonicalSig
      return
    }
    const canonicalIsNewer = state.updatedAt > startedAt && canonicalSig !== lastCanonicalSig
    const localIsNewer = localSig !== lastLocalSig
    if (localIsNewer && !canonicalIsNewer) {
      writeState({ archivedSessionIds: local })
      lastLocalSig = localSig
      lastCanonicalSig = localSig
      log(`归档集本地变更已写回规范文件（${local.length} 条）`)
      return
    }
    await applyArchived(canonicalIds)
    lastLocalSig = canonicalSig
    lastCanonicalSig = canonicalSig
    log(`归档集已对齐规范文件（${canonicalIds.length} 条）`)
  }

  async function tick() {
    if (running) return
    running = true
    try {
      const snapshots = await persistence.list()
      const headers = (snapshots ?? []).map((snapshot) => snapshot?.header).filter(Boolean)
      const summaries = collectSummaries(headers)
      const shells = summaries.filter((summary) => summary.turns === 0).map((summary) => summary.sessionId)
      // 成员与顺序都按「全部会话」计算（含 0 轮次的空壳，子 Agent 会话仍由 groupByCwd 排除）：
      // GUI 的侧栏分组、工作区高亮，以及 workspace 的去留，全都只看 workspace.sessionIds。
      // 空壳一旦被移出，刚打开、还没说话的会话就掉进「未分组」；工作区若因此变空，还会被
      // pruneWorkspaces 整行删掉 —— 表现就是「进入对话没多久，工作区连内容一起不见了」。
      const groups = await groupByCwd(headers, { resolvePath: canonical })
      await alignMembership(groups)
      await pruneWorkspaces(groups)
      await alignOrder(groups)
      await syncArchived()

      const workspaces = registry.list().map((entity) => ({ path: entity.path, count: entity.sessionIds.length }))
      // contentHash 与顺序无关：只比较「每条路径归了多少条会话」；
      // orderHash 另外反映 workspace 分组的显示顺序，方便核对两端顺序是否一致。
      const contentHash = createHash('sha256')
        .update(JSON.stringify(workspaces.slice().sort((left, right) => left.path.localeCompare(right.path))))
        .digest('hex')
        .slice(0, 16)
      const orderHash = createHash('sha256').update(JSON.stringify(workspaces)).digest('hex').slice(0, 16)
      const pendingTitles = await collectPendingTitles()
      writeStatus({
        workspaces,
        order: workspaces.map((workspace) => workspace.path),
        archived: [...registry.archivedSessionIds].sort(),
        contentHash,
        orderHash,
        pendingTitles,
        emptyShells: shells,
        conversations: headers.length - shells.length,
      })
      log(
        `对账完成：${workspaces.length} 个 workspace / ${headers.length - shells.length} 条对话 / 归档 ${registry.archivedSessionIds.length} 条（内容 ${contentHash} / 顺序 ${orderHash}）` +
          (pendingTitles.length ? ` / ${pendingTitles.length} 条对话在本端没有标题（被另一端占用）` : ''),
      )
    } catch (error) {
      log(`对账失败：${error?.message ?? error}`)
    } finally {
      running = false
    }
  }

  ctx.effect(() => {
    firstHandle = setTimeout(() => {
      void tick()
    }, FIRST_TICK_MS)
    timer = setInterval(() => {
      void tick()
    }, TICK_MS)
    return () => {
      if (firstHandle) clearTimeout(firstHandle)
      if (timer) clearInterval(timer)
    }
  })
}
