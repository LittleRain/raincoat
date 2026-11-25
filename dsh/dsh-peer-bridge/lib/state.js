/**
 * 跨 host 的规范状态文件：归档集的唯一真源。
 *
 * 两个 host 共用同一个 DSH home 时，DSH 的 workspace 注册表是「内存权威 + 整文件回写」，
 * 两个进程各自持有一份快照、互相覆盖，最后写入的那份赢。这个插件把「谁是权威」换成
 * 一个本插件自己的状态文件：归档集写在 ~/.dsh/workspace-reconciler/state.json，
 * 两端各自读同一份、并在检测到对方变更时同步进自己的内存注册表。
 *
 * 写入用 tmp + fsync + rename，和 DSH 自己的存储层一样是原子的：崩溃不会写坏文件。
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

export const STATE_DIR = path.join(process.env.DSH_HOME || path.join(os.homedir(), '.dsh'), 'workspace-reconciler')
export const STATE_FILE = path.join(STATE_DIR, 'state.json')

/** 原子写：tmp → fsync → rename。 */
export function writeJsonAtomic(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 })
  const tmp = `${file}.${process.pid}.${Date.now().toString(36)}.tmp`
  const handle = fs.openSync(tmp, 'w', 0o600)
  try {
    fs.writeFileSync(handle, `${JSON.stringify(value, null, 2)}\n`, 'utf8')
    fs.fsyncSync(handle)
  } finally {
    fs.closeSync(handle)
  }
  fs.renameSync(tmp, file)
}

export function readState(file = STATE_FILE) {
  try {
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'))
    if (!parsed || !Array.isArray(parsed.archivedSessionIds)) return null
    return parsed
  } catch {
    return null
  }
}

export function writeState(state, file = STATE_FILE) {
  writeJsonAtomic(file, {
    archivedSessionIds: [...new Set(state.archivedSessionIds ?? [])].sort(),
    updatedAt: Date.now(),
    updatedBy: `${process.pid}`,
  })
}

/** 每个 host 一份状态报告：用于肉眼核对两端分组是否一致。 */
export function writeStatus(report, file = path.join(STATE_DIR, `status-${process.pid}.json`)) {
  writeJsonAtomic(file, { ...report, pid: process.pid, at: Date.now() })
}

export function readDefaultWorkspaceId(storageFile = path.join(process.env.DSH_HOME || path.join(os.homedir(), '.dsh'), 'storages', 'workspace.json')) {
  try {
    const parsed = JSON.parse(fs.readFileSync(storageFile, 'utf8'))
    const id = parsed?.global?.defaultWorkspaceId
    return typeof id === 'string' ? id : null
  } catch {
    return null
  }
}

/**
 * 读共享投影缓存里某会话的标题。
 * 投影缓存由拥有该会话的 host 写入；另一个 host 读不到持久化投影时，
 * 可以从这里看到「这条对话本来叫什么」，用于报告而不是代写。
 */
export function readCachedTitle(sessionId, cacheDir = path.join(process.env.DSH_HOME || path.join(os.homedir(), '.dsh'), 'storages', 'session_projcache', 'sessions')) {
  const summary = readCachedSummary(sessionId, cacheDir)
  return summary?.title ?? null
}

/**
 * 读共享投影缓存里某会话的摘要：标题 + 轮次数。
 *
 * 轮次数用来区分「真实对话」和「只建了壳、没说过一句话」的会话：
 * 两个 host 读的是同一个缓存文件，所以这个判据在两端完全一致，
 * 不会像「本端拿不到投影」那样造成新的分歧。
 */
export function readCachedSummary(sessionId, cacheDir = path.join(process.env.DSH_HOME || path.join(os.homedir(), '.dsh'), 'storages', 'session_projcache', 'sessions')) {
  if (typeof sessionId !== 'string' || sessionId.length === 0) return null
  try {
    const file = path.join(cacheDir, `${sessionId}.json`)
    const stat = fs.statSync(file)
    const parsed = JSON.parse(fs.readFileSync(file, 'utf8'))
    const rows = parsed?.record?.rows ?? {}
    const title = rows?.title?.val
    const turns = rows?.sessionStats?.val?.turns
    return {
      mtimeMs: stat.mtimeMs,
      title: typeof title === 'string' && title.length > 0 ? title : null,
      turns: typeof turns === 'number' ? turns : null,
    }
  } catch {
    return null
  }
}
