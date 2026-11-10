// 整理任务的异步队列：点「整理」只入队，模型在宿主里串行跑，界面轮询状态。
// 任务落盘到 ~/.dsh/raincoat-kb-desk/triage-jobs.json，重启后提案还在，不用重跑模型。
import { randomUUID } from 'node:crypto'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { dataDir } from './config.js'
import { applyTriage, proposeTriage } from './triage.js'

const ACTIVE = new Set(['queued', 'running', 'proposal'])
const jobs = new Map()
let loaded = false
let pumping = false

const storePath = () => join(dataDir(), 'triage-jobs.json')

function summary(job) {
  return {
    id: job.id,
    path: job.path,
    title: job.title,
    status: job.status,
    createdAt: job.createdAt,
    startedAt: job.startedAt,
    finishedAt: job.finishedAt,
    appliedAt: job.appliedAt,
    error: job.error || null,
    decision: job.proposal?.decision || null,
    space: job.proposal?.space || null,
    changes: job.changes?.length || 0,
  }
}

/** 路由/巡检在同步读 jobs 之前先 await 这个，否则新进程里 store 还没加载、列表永远是空。 */
export async function ready() {
  await ensureLoaded()
}

export function listJobs() {
  return [...jobs.values()].sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0)).map(summary)
}

export function getJob(id) {
  const job = jobs.get(id)
  return job ? { ...summary(job), proposal: job.proposal || null, result: job.result || null, warnings: job.warnings || [] } : null
}

export function findByPath(path, { activeOnly = false } = {}) {
  for (const job of jobs.values()) {
    if (job.path !== path) continue
    if (activeOnly && !ACTIVE.has(job.status)) continue
    return job
  }
  return null
}

async function persist() {
  try {
    await mkdir(dataDir(), { recursive: true })
    await writeFile(storePath(), JSON.stringify([...jobs.values()].slice(-200), null, 1), 'utf8')
  } catch {
    // 落盘失败不影响内存里的队列
  }
}

async function ensureLoaded() {
  if (loaded) return
  loaded = true
  try {
    const raw = JSON.parse(await readFile(storePath(), 'utf8'))
    for (const job of raw) {
      // 上次退出时还在跑的，标成 interrupted，允许重新入队
      if (job.status === 'running' || job.status === 'queued') {
        job.status = 'failed'
        job.error = '宿主重启，任务已中断'
      }
      jobs.set(job.id, job)
    }
  } catch {
    // 没有历史记录就是空的
  }
}

/** 入队：同一路径已有活跃任务时直接复用，不重复烧模型。 */
export async function enqueue(ctx, root, entries) {
  await ensureLoaded()
  const created = []
  for (const entry of entries) {
    const path = typeof entry === 'string' ? entry : entry?.path
    const title = typeof entry === 'string' ? null : entry?.title
    if (!path) continue
    const existing = findByPath(path, { activeOnly: true })
    if (existing) {
      created.push(summary(existing))
      continue
    }
    const job = {
      id: randomUUID(),
      path,
      title: title || path,
      status: 'queued',
      createdAt: Date.now(),
      startedAt: null,
      finishedAt: null,
      appliedAt: null,
      proposal: null,
      result: null,
      warnings: [],
      error: null,
    }
    jobs.set(job.id, job)
    created.push(summary(job))
  }
  await persist()
  if (created.length) queueMicrotask(() => pump(ctx, root))
  return created
}

async function pump(ctx, root) {
  if (pumping) return
  pumping = true
  try {
    for (;;) {
      const next = [...jobs.values()]
        .filter((job) => job.status === 'queued')
        .sort((a, b) => a.createdAt - b.createdAt)[0]
      if (!next) break
      next.status = 'running'
      next.startedAt = Date.now()
      await persist()
      try {
        const payload = await proposeTriage(ctx, root, next.path)
        next.proposal = payload.proposal
        next.title = payload.inbox?.title || next.title
        next.status = 'proposal'
      } catch (error) {
        next.status = 'failed'
        next.error = error?.message || String(error)
      } finally {
        next.finishedAt = Date.now()
        await persist()
      }
    }
  } finally {
    pumping = false
  }
}

/** 确认写入：只有 proposal 状态的能写。 */
export async function apply(id, ctx, root) {
  const job = jobs.get(id)
  if (!job) throw Object.assign(new Error('找不到这个整理任务'), { status: 404 })
  if (job.status === 'applied') return { already: true, ...job.result }
  if (job.status !== 'proposal' || !job.proposal) {
    throw Object.assign(new Error('提案还没准备好，稍等一下'), { status: 409 })
  }
  const proposal = { ...job.proposal, inboxPath: job.path }
  const result = await applyTriage(ctx, root, proposal)
  job.status = 'applied'
  job.appliedAt = Date.now()
  job.result = { changes: result.changes, warnings: result.warnings, summaryPath: result.summaryPath }
  job.warnings = result.warnings
  job.changes = result.changes
  await persist()
  return { ...result, id: job.id }
}

/** 丢弃一条坏掉的提案，重新入队时会给新 id。 */
export async function dismiss(id) {
  const job = jobs.get(id)
  if (!job) return false
  jobs.delete(id)
  await persist()
  return true
}

export function activeCount() {
  return [...jobs.values()].filter((job) => ACTIVE.has(job.status)).length
}
