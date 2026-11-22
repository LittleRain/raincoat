// 自动闭环：不再有 Hermes，worker 抓完之后的 pull → 整理 → 写入 → 提交推送由这里接管。
// 每轮都是幂等的：没新文件就什么都不做，队列里有活就不重复入队。
//
// 0.9.6 的护栏（都是为了「一个坏条目不能冻住全部产出」）：
// - 卡住的提案：原文没了立刻判废，反复落盘失败超过 TTL 也判废；
// - 「提交」不再等「全局队列空闲」，只要没有正在跑的整理就推；
// - 同一篇失败有次数预算，配额/429 有冷却，不用 60 秒一次的节奏重撞网关；
// - 上一轮报告落盘，重启或换实例之后仍能回答「上一轮为什么没动」。
import { readFileSync } from 'node:fs'
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { dataDir, readSettings } from './config.js'
import { dropDuplicateInbox, gitCommitAndPush, gitPush } from './triage.js'
import {
  apply,
  attemptsFor,
  enqueue,
  expireStaleProposals,
  hasRunning,
  listJobs,
  quotaCooldownLeft,
  ready as triageReady,
  syncFromDisk,
} from './triage-queue.js'
import { gitOverview, listInbox, localIngestIndex, pullVault } from './vault.js'

// 只提交插件自己会写的路径，避免把用户正在编辑的笔记一起卷进去。
const WRITE_PATHS = ['00 Inbox', '00 raw', '01 wiki', '02 outputs/health', '02 outputs/drafts', '02 outputs/builder/ideas']
// applied 不算「在跑」：同一篇被 worker 重新推回 Inbox 时应该再走一遍，
// 重复写入由 triage 的幂等保护兜住（复用摘要编号、跳过已写段落）。
const OPEN = new Set(['queued', 'running', 'proposal'])
const LOCK_TTL = 120_000

/** 两套实例（桌面 app 与 co.dsh.web）共用 ~/.dsh，只允许一个跑自动闭环。 */
async function acquireLock() {
  const file = join(dataDir(), 'watcher.lock')
  try {
    const raw = JSON.parse(await readFile(file, 'utf8'))
    if (raw?.pid && raw.pid !== process.pid && Date.now() - (raw.at || 0) < LOCK_TTL) {
      try {
        process.kill(raw.pid, 0)
        return false
      } catch {
        // 持锁进程已经没了，接管
      }
    }
  } catch {
    // 没有锁文件或内容坏了，直接抢
  }
  await writeFile(file, JSON.stringify({ pid: process.pid, at: Date.now(), profile: process.env.DSH_PROFILE || null }), 'utf8')
  return true
}

let timer = null
let ticking = false
let lastRunAt = null
let lastError = null
let lastReport = null

const statePath = () => join(dataDir(), 'watcher-state.json')

/** 把上一轮结果落盘：否则「为什么没动」只活在内存里，重启即失忆。 */
async function persistState() {
  try {
    await writeFile(statePath(), JSON.stringify({ lastRunAt, lastError, lastReport }, null, 1), 'utf8')
  } catch {
    // 写不了状态不影响闭环
  }
}

function readPersistedState() {
  try {
    return JSON.parse(readFileSync(statePath(), 'utf8'))
  } catch {
    return null
  }
}

export function watcherState() {
  if (lastRunAt == null) {
    const saved = readPersistedState()
    if (saved && saved.lastReport) return { running: Boolean(timer), ticking, ...saved }
  }
  return { running: Boolean(timer), ticking, lastRunAt, lastError, lastReport }
}

/** 判废的提案要记进报告，不能「安静地消失」。 */
async function dropStuckProposals(root, settings, report, options) {
  const expired = await expireStaleProposals(null, root, settings, options)
  for (const job of expired) {
    report.notes.push(`提案作废：${String(job.path).split('/').pop()} — ${job.error}`)
  }
  return expired.length
}

async function tick(ctx) {
  if (ticking) return
  const settings = readSettings()
  const owner = settings.watcherOwner
  const profile = process.env.DSH_PROFILE || null
  if (owner && profile && profile !== owner) {
    lastReport = { skipped: `自动闭环由 ${owner} 实例负责` }
    return
  }
  if (!(await acquireLock())) {
    lastReport = { skipped: '另一个实例正在跑自动闭环' }
    return
  }
  ticking = true
  const report = { pulled: 0, enqueued: 0, applied: 0, expired: 0, dropped: 0, pushed: false, notes: [] }
  try {
    await triageReady()
    // 两台宿主共用同一份队列文件：先对齐磁盘，避免各跑一份内存、后写覆盖先写
    await syncFromDisk()
    const root = settings.vault

    // 1) 先放掉已经不可能落盘的提案。它占着「有活在跑」的名额，
    //    会让第 3 步的提交永远不执行，于是产出全卡在内存里。
    report.expired += await dropStuckProposals(root, settings, report, { afterApply: false })

    // 2) 提案好了就写盘
    if (settings.autoApply) {
      for (const job of listJobs().filter((item) => item.status === 'proposal')) {
        try {
          await apply(job.id, ctx, root)
          report.applied += 1
        } catch (error) {
          report.notes.push(`${job.title || job.path}: ${error?.message || error}`)
        }
      }
      // 这一轮尝试过仍然没落盘的，超过 TTL 就判废，别一直卡着
      report.expired += await dropStuckProposals(root, settings, report, { afterApply: true })
    } else {
      report.notes.push('写入方式为「先给我确认」，等人工落盘')
    }

    // 3) 提交推送：只要没有正在跑的整理就推，不再等「全局队列空闲」
    if (settings.autoPush && !hasRunning()) {
      const after = await gitOverview(root)
      if (after.ok && after.dirty) {
        const commit = await gitCommitAndPush(root, `kb: 自动整理 Inbox（${new Date().toISOString().slice(0, 10)}）`, { paths: WRITE_PATHS })
        if (commit.ok && /已提交并推送/.test(commit.message || '')) report.pushed = true
        else if (!commit.ok) report.notes.push(commit.message)
      } else if (after.ok && after.ahead > 0) {
        const push = await gitPush(root)
        report.pushed = push.ok
        if (!push.ok) report.notes.push(push.message)
      }
    } else if (settings.autoPush) {
      report.notes.push('还有整理任务在跑，这一轮先不提交')
    }

    // 4) 收远端提交：上一步已经把本地出品推走，这里通常不会再被脏工作区挡住
    const before = await gitOverview(root, { fetch: true })
    if (before.ok && before.behind > 0) {
      // 未跟踪文件（刚推进 Inbox 的稿）不该挡住拉取，只有已跟踪改动才会冲突。
      if (before.trackedDirty) {
        report.notes.push(`本地有 ${before.trackedDirty} 个未提交改动，先不 pull`)
      } else {
        const pull = await pullVault(root)
        if (pull.ok) report.pulled = before.behind
        else report.notes.push(pull.message)
      }
    }

    // 5) 新文件入队：配额冷却中、或这篇已经失败超预算，就先停手
    if (settings.autoIngest) {
      const cooldown = quotaCooldownLeft(settings)
      if (cooldown > 0) {
        report.notes.push(`模型配额报错冷却中，还剩 ${Math.ceil(cooldown / 60_000)} 分钟不再入队`)
      } else {
        const docs = await listInbox(root)
        const known = new Set(listJobs().filter((job) => OPEN.has(job.status)).map((job) => job.path))
        const fresh = docs.filter((doc) => !known.has(doc.path))
        const budget = Math.max(1, Number(settings.maxAttemptsPerDoc) || 1)
        // worker 重投、手工补录都会把同一篇再推一次：入队前按 URL 查一遍 raw，别再多长一篇
        const lookup = await localIngestIndex(root)
        const allowed = []
        for (const doc of fresh) {
          const hit = doc.url ? lookup(doc.url) : null
          if (hit?.raw) {
            try {
              await dropDuplicateInbox(root, doc, hit)
              report.dropped += 1
              report.notes.push(`重复投递已丢弃：${doc.title || doc.path}（已有 ${hit.raw}）`)
              continue
            } catch (error) {
              report.notes.push(`丢弃重复失败：${doc.title || doc.path} — ${error?.message || error}`)
            }
          }
          const tried = attemptsFor(doc.path)
          if (tried >= budget) {
            report.notes.push(`${doc.title || doc.path} 已失败 ${tried} 次，先停下等人看`)
            continue
          }
          allowed.push(doc)
        }
        if (allowed.length) report.enqueued = (await enqueue(ctx, root, allowed)).length
      }
    } else {
      report.notes.push('自动处理已暂停，只同步不整理')
    }

    lastReport = report
    lastError = null
    lastRunAt = Date.now()
  } catch (error) {
    lastError = error?.message || String(error)
    lastReport = report
    lastRunAt = Date.now()
  } finally {
    await persistState()
    ticking = false
  }
}

/** 挂到插件生命周期上：ctx.effect 返回的清理函数负责停表。 */
export function startWatcher(ctx) {
  const seconds = Math.max(15, Number(readSettings().watchSeconds) || 60)
  const kick = () => {
    tick(ctx).catch(() => {})
  }
  kick()
  timer = setInterval(kick, seconds * 1000)
  if (timer.unref) timer.unref()
  return () => {
    clearInterval(timer)
    timer = null
  }
}

/** 面板上的「立刻跑一轮」。 */
export function runWatcherNow(ctx) {
  return tick(ctx)
}
