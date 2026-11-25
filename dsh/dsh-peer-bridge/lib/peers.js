/**
 * 对端宿主登记表（文件协议）。
 *
 * 每个宿主启动时把自己的回环地址、带 token 的启动 URL、profile 写进
 * `$DSH_HOME/handoff/peers/<pid>.json`，每 10 秒心跳一次；40 秒没刷新就当作
 * 已经退出。这份登记表只用于「知道对端在哪、叫什么」，不用于执行权——
 * 执行权的唯一权威仍然是会话自己的写锁。
 */
import fs from 'node:fs/promises'
import path from 'node:path'
import { ensureDir, peersDir, writeJsonAtomic } from './fsx.js'

/** 心跳间隔；超过 4 个周期没刷新就当作已经退出的宿主。 */
export const HEARTBEAT_MS = 10_000
export const STALE_MS = HEARTBEAT_MS * 4

export { peersDir }

const PROFILE_LABELS = {
  desktop: '桌面端',
  web: 'Web 端',
  headless: '无头端',
}

/** 把 profile 名翻译成人看的标签；未知 profile 原样返回。 */
export function labelForProfile(profile) {
  const key = typeof profile === 'string' ? profile.trim() : ''
  if (key === '') return '未知端'
  return PROFILE_LABELS[key] ?? key
}

function peerFile(dir, pid) {
  return path.join(dir, `${pid}.json`)
}

/**
 * 登记（或刷新）本端宿主。
 * @param {object} input - 目录、pid、origin、带 token 的 url、profile。
 * @returns {Promise<void>} 写完即返回，失败由调用方吞掉。
 */
export async function writePeer({
  dir,
  pid,
  origin,
  url,
  profile = '',
  startedAt = Date.now(),
  now = Date.now(),
}) {
  await ensureDir(dir)
  await writeJsonAtomic(peerFile(dir, pid), {
    pid,
    profile,
    label: labelForProfile(profile),
    origin,
    url,
    startedAt,
    updatedAt: now,
  })
}

/**
 * 读出仍然活着的对端。
 * @returns {Promise<Array<{pid:number,profile:string,label:string,origin:string,url:string,startedAt:number,updatedAt:number}>>}
 */
export async function readPeers({ dir, excludePid, now = Date.now(), staleMs = STALE_MS }) {
  let names
  try {
    names = await fs.readdir(dir)
  } catch {
    return []
  }
  const alive = []
  for (const name of names) {
    if (!name.endsWith('.json')) continue
    let record
    try {
      record = JSON.parse(await fs.readFile(path.join(dir, name), 'utf8'))
    } catch {
      continue
    }
    const pid = Number(record?.pid)
    const updatedAt = Number(record?.updatedAt)
    if (!Number.isInteger(pid) || typeof record?.url !== 'string' || !Number.isFinite(updatedAt)) continue
    if (now - updatedAt > staleMs) continue
    if (pid === excludePid) continue
    const profile = typeof record?.profile === 'string' ? record.profile : ''
    alive.push({
      pid,
      profile,
      label: typeof record?.label === 'string' && record.label !== '' ? record.label : labelForProfile(profile),
      origin: String(record?.origin ?? ''),
      url: record.url,
      startedAt: Number(record?.startedAt) || updatedAt,
      updatedAt,
    })
  }
  alive.sort((a, b) => b.updatedAt - a.updatedAt)
  return alive
}

/** 退出时抹掉自己的登记。 */
export async function removePeer({ dir, pid }) {
  try {
    await fs.rm(peerFile(dir, pid), { force: true })
  } catch {
    /* 退出路径不抛错 */
  }
}
