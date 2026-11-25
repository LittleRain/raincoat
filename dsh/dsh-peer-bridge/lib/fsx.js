/**
 * 跨宿主交接用的文件协议底座。
 *
 * 两个 DSH 宿主（桌面端自带的 host 与 launchd 的 `dsh web`）共用同一个
 * `$DSH_HOME`，所以「谁持有哪个会话」「哪个会话交接给了谁」这类信息可以
 * 直接落在磁盘上，不需要网络协议，也不需要改核心。
 *
 * 目录约定（全部 0700，文件 0600）：
 *   handoff/peers/<pid>.json     各宿主的心跳登记
 *   handoff/links/<sessionId>.json  交接记录（父会话 → 子会话）
 *   handoff/secret               宿主之间的共享能力令牌
 */
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

/** $DSH_HOME；没有环境变量时退回 ~/.dsh。 */
export function dshHome() {
  return process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
}

export function handoffDir(home = dshHome()) {
  return path.join(home, 'handoff')
}

export function peersDir(home = dshHome()) {
  return path.join(handoffDir(home), 'peers')
}

export function linksDir(home = dshHome()) {
  return path.join(handoffDir(home), 'links')
}

export function secretPath(home = dshHome()) {
  return path.join(handoffDir(home), 'secret')
}

export async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true, mode: 0o700 })
}

/** 原子写：先写同目录临时文件再 rename，读方永远看不到半截 JSON。 */
export async function writeJsonAtomic(file, value, mode = 0o600) {
  await ensureDir(path.dirname(file))
  const tmp = `${file}.${process.pid}.${Date.now()}.tmp`
  await fs.writeFile(tmp, `${JSON.stringify(value)}\n`, { mode })
  await fs.rename(tmp, file)
}

/** 读不到、解析失败一律返回 undefined：交接信息是可丢的提示，不是真相。 */
export async function readJson(file) {
  try {
    return JSON.parse(await fs.readFile(file, 'utf8'))
  } catch {
    return undefined
  }
}

/** 会话 id 进文件名前做一次编码，避免大小写/路径分隔符带来的意外。 */
export function safeName(id) {
  return encodeURIComponent(String(id)).replaceAll('.', '%2E')
}
