// rainpark 摄入服务客户端。只读任务/运行记录；唯一的写操作是提交新链接。
import { readCredentials, readSettings } from './config.js'

const TIMEOUT_MS = 9000

export class IngestUnavailable extends Error {
  constructor(message, status = 502) {
    super(message)
    this.status = status
  }
}

async function request(settings, path, { method = 'GET', body, token } = {}) {
  const cred = readCredentials(settings)
  const base = String(cred.apiBase || settings.apiBase).replace(/\/+$/, '')
  const secret = token === 'ingest' ? cred.ingestToken : cred.workerToken
  if (!secret) {
    throw new IngestUnavailable(
      `缺少${token === 'ingest' ? ' INGEST_TOKEN' : ' WORKER_TOKEN'}：在 ${cred.source || settings.credentialsFile} 里配置后重试`,
      428,
    )
  }
  let res
  try {
    res = await fetch(`${base}${path}`, {
      method,
      headers: {
        'x-worker-token': secret,
        ...(token === 'ingest' ? { authorization: `Bearer ${cred.ingestToken}` } : {}),
        ...(body ? { 'content-type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    })
  } catch (error) {
    throw new IngestUnavailable(`连不上摄入服务 ${base}：${error?.message || error}`)
  }
  const text = await res.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = { raw: text.slice(0, 400) }
  }
  if (res.status === 401 || res.status === 403) {
    throw new IngestUnavailable(`摄入服务拒绝了凭据（${res.status}），检查 credentials.env`, 401)
  }
  if (!res.ok) {
    const error = new IngestUnavailable(payload?.error || `摄入服务返回 ${res.status}`, res.status)
    // 重试路径要区分「这条任务不能再重排」（JSON 错误）和「远端没有重试接口」（404 + HTML）
    error.payload = payload
    throw error
  }
  return payload
}

/** 把客户端返回的 ISO/epoch 时间统一成毫秒。 */
export function toMillis(value) {
  if (value == null) return null
  if (typeof value === 'number') return value
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

export function normalizeJob(raw) {
  const finished = toMillis(raw.finished_at) ?? toMillis(raw.updated_at)
  // 历史归档里有些记录来自 worker 日志，只有完成时间，没有 created_at；
  // 这类记录用 finished_at 兜底，否则会显示成 1970。
  const created = toMillis(raw.created_at) || finished
  const started = toMillis(raw.claimed_at)
  return {
    id: raw.id,
    url: raw.url,
    title: raw.title || null,
    client: raw.client || null,
    status: raw.status,
    worker: raw.worker || null,
    duplicate: Boolean(raw.duplicate),
    attempts: Number(raw.attempts || 0),
    error: raw.error || null,
    vaultPath: raw.vault_path || null,
    createdAt: created,
    claimedAt: started,
    finishedAt: finished,
    // 已等待/已耗时：界面直接显示，避免每行各自算
    waitedMs: created && !started ? Date.now() - created : null,
    elapsedMs: started ? (finished || Date.now()) - started : null,
  }
}

export function createIngest() {
  const settings = () => readSettings()

  /** 历史归档：VPS 的 /kb/history.json，队列里已经清理掉的旧任务只在这里。 */
  async function loadHistory() {
    const cred = readCredentials(settings())
    const base = String(cred.apiBase || settings().apiBase).replace(/\/+$/, '')
    const root = base.replace(/\/api$/, '')
    if (!cred.workerToken) throw new IngestUnavailable('缺少 WORKER_TOKEN，读不到历史记录', 428)
    let res
    try {
      res = await fetch(`${root}/kb/history.json`, {
        headers: { 'x-worker-token': cred.workerToken },
        signal: AbortSignal.timeout(TIMEOUT_MS),
      })
    } catch (error) {
      throw new IngestUnavailable(`读不到历史归档：${error?.message || error}`)
    }
    if (!res.ok) throw new IngestUnavailable(`历史归档返回 ${res.status}`, res.status)
    const payload = await res.json().catch(() => null)
    return (payload?.jobs || []).map((raw) => ({ ...normalizeJob(raw), archived: true }))
  }

  /** 重排被拒时按 id 找回原链接：先看实时队列，再去历史归档里找。 */
  async function lookupUrl(id) {
    try {
      const live = await request(settings(), '/jobs?status=failed&limit=100', { token: 'worker' })
      const hit = (live?.jobs || []).find((job) => job.id === id)
      if (hit?.url) return { url: hit.url, title: hit.title || null }
    } catch {
      // 实时队列读不到就只查归档
    }
    try {
      const archived = await loadHistory()
      const hit = archived.find((job) => job.id === id)
      if (hit?.url) return { url: hit.url, title: hit.title || null }
    } catch {
      return null
    }
    return null
  }

  const service = {
    async stats() {
      const payload = await request(settings(), '/queue/stats', { token: 'worker' })
      return {
        queued: Number(payload?.queued || 0),
        claimed: Number(payload?.claimed || 0),
        done: Number(payload?.done || 0),
        failed: Number(payload?.failed || 0),
        oldestQueuedAt: toMillis(payload?.oldest_queued_at),
      }
    },
    async jobs(status = 'queued', limit = 20) {
      const payload = await request(settings(), `/jobs?status=${encodeURIComponent(status)}&limit=${limit}`, { token: 'worker' })
      return { status, count: Number(payload?.count || 0), jobs: (payload?.jobs || []).map(normalizeJob) }
    },
    /** 队列目录是工作区，会被清理；VPS 另外留了一份 /kb/history.json，历史任务从这里补。 */
    async history() {
      return loadHistory()
    },
    async runs(limit = 12) {
      const payload = await request(settings(), `/runs?limit=${limit}`, { token: 'worker' })
      return (payload?.runs || []).map((run) => ({
        jobId: run.job_id,
        createdAt: toMillis(run.created_at),
        updatedAt: toMillis(run.updated_at),
        stages: (run.stages || []).map((stage) => ({
          stage: stage.stage,
          status: stage.status,
          at: toMillis(stage.at),
          actor: stage.actor || null,
          durationSec: stage.duration_sec ?? null,
          note: stage.note || null,
        })),
      }))
    },
    async run(jobId) {
      const payload = await request(settings(), `/runs/${encodeURIComponent(jobId)}`, { token: 'worker' })
      return {
        jobId: payload?.job_id || jobId,
        stages: (payload?.stages || []).map((stage) => ({
          stage: stage.stage,
          status: stage.status,
          at: toMillis(stage.at),
          actor: stage.actor || null,
          durationSec: stage.duration_sec ?? null,
          note: stage.note || null,
        })),
      }
    },
    /**
     * 把失败任务放回远端队列；重排不了的就按原链接重新提交。
     *
     * 传 ids 只处理这几条；不传就把远端当前 failed 的任务全重试一遍（面板上的
     * 「全部重试」走这条，避免前端只重试加载到的那 40 条）。
     *
     * 历史归档里的失败任务已经不在远端队列，重排接口会回 409「job is not retryable」；
     * 旧版服务没有这个接口时是 404 + HTML。这两种情况下「重试」只能是重新摄入一遍，
     * 否则用户点了永远没反应、记录永远挂在失败里。
     */
    async retry(ids, hints = []) {
      const wanted = Array.isArray(ids) ? [...new Set(ids.map((id) => String(id || '').trim()).filter(Boolean))] : []
      const hintMap = new Map()
      for (const hint of Array.isArray(hints) ? hints : []) {
        const id = String(hint?.id || '').trim()
        if (id) hintMap.set(id, hint)
      }
      let targets
      if (wanted.length) {
        targets = wanted.map((id) => ({ id, url: hintMap.get(id)?.url || null, title: hintMap.get(id)?.title || null }))
      } else {
        const live = await request(settings(), '/jobs?status=failed&limit=100', { token: 'worker' })
        targets = (live?.jobs || []).map((job) => ({ id: job.id, url: job.url || null, title: job.title || null }))
      }
      const retried = []
      const resubmitted = []
      const failed = []
      for (const target of targets) {
        try {
          const payload = await request(settings(), `/jobs/${encodeURIComponent(target.id)}/retry`, { method: 'POST', token: 'worker' })
          retried.push(payload?.job?.id || target.id)
          continue
        } catch (error) {
          const status = error?.status || 0
          // 404 + 非 JSON 是旧版服务没有这个路由；409 / 404 + JSON 是这条任务不能再重排
          const noEndpoint = status === 404 && !error?.payload?.error
          if (status !== 404 && status !== 409) {
            failed.push({ id: target.id, error: error?.message || String(error) })
            continue
          }
          const found = target.url ? { url: target.url, title: target.title } : await lookupUrl(target.id)
          if (!found?.url) {
            failed.push({
              id: target.id,
              error: noEndpoint
                ? '远端服务还没有重试接口（需要部署新版摄入服务）'
                : '这条已经不在远端队列，也拿不到原链接，只能从历史记录里复制链接重新提交',
            })
            continue
          }
          try {
            const result = await service.submit({ url: found.url, title: target.title || found.title || undefined })
            resubmitted.push({
              id: target.id,
              url: found.url,
              jobId: result?.job_id || null,
              duplicate: Boolean(result?.duplicate),
            })
          } catch (submitError) {
            failed.push({ id: target.id, error: submitError?.message || String(submitError) })
          }
        }
      }
      return { total: targets.length, retried, resubmitted, failed }
    },
    async submit({ url, title, note }) {
      const cred = readCredentials(settings())
      const base = String(cred.apiBase || settings().apiBase).replace(/\/+$/, '')
      if (!cred.ingestToken) {
        throw new IngestUnavailable('缺少 INGEST_TOKEN，无法提交链接', 428)
      }
      let res
      try {
        res = await fetch(`${base}/ingest`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', authorization: `Bearer ${cred.ingestToken}` },
          body: JSON.stringify({ url, client_type: 'kb-desk', ...(title ? { title } : {}), ...(note ? { note } : {}) }),
          signal: AbortSignal.timeout(TIMEOUT_MS),
        })
      } catch (error) {
        throw new IngestUnavailable(`连不上摄入服务 ${base}：${error?.message || error}`)
      }
      const payload = await res.json().catch(() => ({}))
      if (res.status === 409) return { duplicate: true, ...payload }
      if (!res.ok) throw new IngestUnavailable(payload?.error || `提交失败 ${res.status}`, res.status)
      return payload
    },
  }
  return service
}
