/**
 * 宿主之间的共享能力令牌。
 *
 * 交接协议要在两个宿主之间互问「你持有哪个会话」。直接用浏览器登录 token
 * 去调对端 API 等于把登录凭证借出去；这里用一个只落在本机磁盘上的独立
 * 令牌（0600，同用户可读），并且服务端只接受回环地址来的请求。
 */
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import { ensureDir, secretPath } from './fsx.js'

const HEADER = 'x-dsh-bridge'

/** 首次调用时生成；并发创建用 wx 抢，输了就重读既有文件。 */
export async function ensureSecret(home) {
  const file = secretPath(home)
  const existing = await readSecret(file)
  if (existing !== undefined) return existing

  await ensureDir(path.dirname(file))
  const created = crypto.randomBytes(32).toString('hex')
  try {
    await fs.writeFile(file, `${created}\n`, { mode: 0o600, flag: 'wx' })
    return created
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error
    const raced = await readSecret(file)
    if (raced === undefined) throw new Error('handoff secret 存在但读不出来')
    return raced
  }
}

async function readSecret(file) {
  try {
    const text = (await fs.readFile(file, 'utf8')).trim()
    return text === '' ? undefined : text
  } catch {
    return undefined
  }
}

/** 常数时间比较；长度不同直接失败，避免把长度也当信息。 */
export function secretMatches(provided, expected) {
  if (typeof provided !== 'string' || typeof expected !== 'string') return false
  if (provided.length !== expected.length) return false
  const a = Buffer.from(provided)
  const b = Buffer.from(expected)
  return a.length === b.length && crypto.timingSafeEqual(a, b)
}

/** 从请求头取令牌（node-http 的 header 名是小写）。 */
export function providedSecret(req) {
  const value = req?.headers?.[HEADER]
  return Array.isArray(value) ? value[0] : value
}

export { HEADER }
