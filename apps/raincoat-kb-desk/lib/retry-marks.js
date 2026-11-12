// 历史归档里的失败任务没法在远端重排（队列已经把它清理掉了），只能按原链接重新提交。
// 提交成功后在这里记一笔「哪条失败已经换成哪条新任务」，列表上才能看出来它不用再处理，
// 而不是重新提交完还一直挂在「失败」里。只是本地视图状态，不写 vault、不回传远端。
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { dataDir } from './config.js'

const LIMIT = 300

function storeFile() {
  return join(dataDir(), 'retry-marks.json')
}

export function readMarks() {
  try {
    const parsed = JSON.parse(readFileSync(storeFile(), 'utf8'))
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

/** 记下 fromId → 新任务。写盘失败不影响重试结果，下次再点还会重新提交。 */
export function markResubmitted(fromId, entry) {
  const id = String(fromId || '').trim()
  if (!id) return readMarks()
  const marks = readMarks()
  marks[id] = { at: Date.now(), ...entry }
  const ids = Object.keys(marks)
  if (ids.length > LIMIT) {
    ids.sort((a, b) => (marks[a]?.at || 0) - (marks[b]?.at || 0))
    for (const key of ids.slice(0, ids.length - LIMIT)) delete marks[key]
  }
  try {
    writeFileSync(storeFile(), `${JSON.stringify(marks, null, 2)}\n`, 'utf8')
  } catch {
    // 只影响列表标记，不影响这次重新提交
  }
  return marks
}
