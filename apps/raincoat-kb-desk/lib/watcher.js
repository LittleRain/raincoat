// 自动闭环：不再有 Hermes，worker 抓完之后的 pull → 整理 → 写入 → 提交推送由这里接管。
// 每轮都是幂等的：没新文件就什么都不做，队列里有活就不重复入队。
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { dataDir, readSettings } from './config.js'
import { gitCommitAndPush, gitPush } from './triage.js'
import { activeCount, apply, enqueue, listJobs, ready as triageReady } from './triage-queue.js'
import { gitOverview, listInbox, pullVault } from './vault.js'

// 只提交插件自己会写的路径，避免把用户正在编辑的笔记一起卷进去。
const WRITE_PATHS = ['00 Inbox', '00 raw', '01 wiki', '02 outputs/health', '02 outputs/drafts']
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

export function watcherState() {
  return { running: Boolean(timer), ticking, lastRunAt, lastError, lastReport }
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
  await triageReady()
  const report = { pulled: 0, enqueued: 0, applied: 0, pushed: false, notes: [] }
  try {
    const root = settings.vault

    // 1) 把 worker 推到远端的提交收进来，否则 Inbox 永远是空的
    const before = await gitOverview(root, { fetch: true })
    if (before.ok && before.behind > 0) {
      if (before.dirty) {
        report.notes.push(`本地有 ${before.dirty} 个未提交改动，先不 pull`)
      } else {
        const pull = await pullVault(root)
        if (pull.ok) report.pulled = before.behind
        else report.notes.push(pull.message)
      }
    }

    // 2) Inbox 里没进过队列的文件直接排队（「自动处理」暂停时不做这一步）
    if (settings.autoIngest) {
      const docs = await listInbox(root)
      const known = new Set(listJobs().filter((job) => OPEN.has(job.status)).map((job) => job.path))
      const fresh = docs.filter((doc) => !known.has(doc.path))
      if (fresh.length) {
        const queued = await enqueue(ctx, root, fresh)
        report.enqueued = queued.length
      }
    } else {
      report.notes.push('自动处理已暂停，只同步不整理')
    }

    // 3) 提案好了就写盘（人工关卡在这里绕过，可在设置里关掉）
    if (settings.autoApply) {
      for (const job of listJobs().filter((item) => item.status === 'proposal')) {
        try {
          await apply(job.id, ctx, root)
          report.applied += 1
        } catch (error) {
          report.notes.push(`${job.title || job.path}: ${error?.message || error}`)
        }
      }
    }

    // 4) 没有在跑的任务时收尾：提交并推送
    if (settings.autoPush && activeCount() === 0) {
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
    }

    lastReport = report
    lastError = null
    lastRunAt = Date.now()
  } catch (error) {
    lastError = error?.message || String(error)
    lastReport = report
  } finally {
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
