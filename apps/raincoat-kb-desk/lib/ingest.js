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
    throw new IngestUnavailable(payload?.error || `摄入服务返回 ${res.status}`, res.status)
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
  const created = toMillis(raw.created_at)
  const finished = toMillis(raw.finished_at) ?? toMillis(raw.updated_at)
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
  return {
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
}
