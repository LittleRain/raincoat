/**
 * 规范分组：把会话 header 映射成「路径 → 有序会话 id 列表」。
 *
 * 这里是纯函数，不碰 DSH 运行时，所以可以单测；index.js 只负责把结果写回
 * workspace 注册表。排序规则与 DSH 自带的 bootstrap 一致（createdAt 降序、
 * id 升序），保证两个 host 算出来的顺序一致。
 */

/** DSH bootstrap 的 compareHeaders：createdAt 降序，再按 id 升序。 */
export function compareHeaders(left, right) {
  return right.createdAt - left.createdAt || String(left.id).localeCompare(String(right.id))
}

/** 子 Agent 会话不是对话，UI 本来就不显示；默认不进分组，避免注册表膨胀。 */
export function isSubagentHeader(header) {
  return header?.origin === 'subagent' || (header?.delegationDepth ?? 0) > 0
}

/**
 * 按 canonical cwd 分组。
 *
 * @param {Array<{id:string,cwd:string,createdAt:number,origin?:string,delegationDepth?:number}>} headers
 * @param {{resolvePath?: (cwd:string)=>Promise<string>|string, includeSubagents?: boolean}} options
 * @returns {Map<string, Array<{id:string,createdAt:number}>>}
 */
export async function groupByCwd(headers, options = {}) {
  const { resolvePath, includeSubagents = false } = options
  const groups = new Map()
  for (const header of headers ?? []) {
    if (!header || typeof header.id !== 'string' || typeof header.cwd !== 'string') continue
    if (!includeSubagents && isSubagentHeader(header)) continue
    let path = header.cwd
    if (typeof resolvePath === 'function') {
      try {
        path = await resolvePath(header.cwd)
      } catch {
        path = header.cwd
      }
    }
    const members = groups.get(path) ?? []
    members.push({ id: header.id, createdAt: Number(header.createdAt ?? 0) })
    groups.set(path, members)
  }
  for (const members of groups.values()) members.sort(compareHeaders)
  return groups
}

/**
 * 成员差异：需要补进 / 移出 workspace 的会话。
 *
 * @param {string[]} desired
 * @param {string[]} current
 */
export function diffMembership(desired, current) {
  const wanted = new Set(desired)
  const present = new Set(current)
  return {
    attach: desired.filter((id) => !present.has(id)),
    detach: current.filter((id) => !wanted.has(id)),
  }
}

/**
 * 排序调整计划：把 current 变成 desired 需要的 (sessionId, beforeSessionId) 移动序列。
 * insertSessionBefore(x, y) 把 x 挪到 y 前面，所以「把 desired[i] 挪到当前第 i 位之前」
 * 就能逐位对齐。
 *
 * @param {string[]} desired
 * @param {string[]} current
 * @returns {Array<[string,string]>}
 */
export function planOrder(desired, current) {
  const moves = []
  const arr = current.slice()
  for (let i = 0; i < desired.length; i++) {
    if (arr[i] === desired[i]) continue
    const from = arr.indexOf(desired[i], i)
    if (from < 0) continue
    const before = arr[i]
    if (before === undefined) continue
    moves.push([desired[i], before])
    arr.splice(from, 1)
    arr.splice(i, 0, desired[i])
  }
  return moves
}

/** 集合签名：用于判断归档集是否变化。 */
export function signature(ids) {
  return [...new Set(ids ?? [])].sort().join(',')
}

/**
 * 规范 workspace 顺序：按路径下最新会话的 createdAt 降序、路径升序。
 * 与 DSH 自带 bootstrap 的分组排序一致，两个 host 因此算出同样的顺序。
 *
 * @param {Map<string, Array<{id:string,createdAt:number}>>} groups
 * @returns {string[]} 有序的路径列表
 */
export function canonicalOrder(groups) {
  const rank = (workspacePath) => {
    const members = groups.get(workspacePath) ?? []
    return members.reduce((max, member) => Math.max(max, member.createdAt ?? 0), 0)
  }
  return [...groups.keys()].sort((left, right) => rank(right) - rank(left) || left.localeCompare(right))
}
