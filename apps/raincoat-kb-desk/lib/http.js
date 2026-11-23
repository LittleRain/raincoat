// /kb-desk/api 路由。所有响应都是 JSON（聊天走 SSE），错误统一 {error}。
import { existsSync } from 'node:fs'
import { callModel, LEARN_SYSTEM, learnUserPrompt, modelInfo, parseJsonLoose, TOPIC_SYSTEM, topicsUserPrompt } from './ai.js'
import { readCredentials, readSettings, vaultRoot, writeSettings } from './config.js'
import { fetchArticle } from './learn.js'
import { diagnoseFailure, gatherFailure } from './diagnose.js'
import { createIngest } from './ingest.js'
import { markResubmitted, readMarks } from './retry-marks.js'
import { applyTriage, gitCommitAndPush, proposeTriage } from './triage.js'
import { activeCount, apply as applyQueued, dismiss as dismissQueued, enqueue, getJob, listJobs, ready as triageReady } from './triage-queue.js'
import { runWatcherNow, watcherState } from './watcher.js'
import {
  gitOverview,
  healthCheck,
  listInbox,
  localIngestIndex,
  pullVault,
  readDoc,
  recentDocs,
  scanLocalIngests,
  searchVault,
  urlKeys,
  writeDraft,
  writeHealthReport,
  writeInboxDoc,
} from './vault.js'


/** 归一化链接，用来判断「同一个来源」：去掉 hash、尾斜杠与常见分享参数。 */
function urlKeyOf(url) {
  if (!url) return ''
  try {
    const u = new URL(String(url))
    u.hash = ''
    for (const k of [...u.searchParams.keys()]) {
      if (/^(s|spm|from|share|scene|srcid|sharer|ref|source)$/i.test(k)) u.searchParams.delete(k)
    }
    return `${u.origin}${u.pathname.replace(/\/+$/, '')}${u.search}`
  } catch {
    return String(url).trim()
  }
}

const PREFIX = '/kb-desk/api'

function json(res, status, body) {
  if (res.headersSent) return res.end()
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(payload),
  })
  res.end(payload)
}

function readJson(req) {
  return new Promise((done) => {
    let raw = ''
    req.on('data', (chunk) => {
      raw += chunk
      if (raw.length > 2_000_000) req.destroy()
    })
    req.on('end', () => {
      try {
        done(raw ? JSON.parse(raw) : {})
      } catch {
        done({})
      }
    })
    req.on('error', () => done({}))
  })
}

function query(url, key, fallback = null) {
  const value = url.searchParams.get(key)
  return value === null ? fallback : value
}

export function registerHttp(ctx) {
  const ingest = createIngest()

  return ctx.webServer.register({
    kind: 'prefix',
    path: PREFIX,
    handler: async (req, res) => {
      const connection = ctx.get('connection') ?? ctx.connection
      if (typeof connection?.requestRejection !== 'function') {
        return json(res, 503, { error: 'DSH 请求保护不可用，知识库接口已关闭' })
      }
      const rejection = connection.requestRejection({ headers: req.headers })
      if (rejection === 401 || rejection === 403) {
        return json(res, rejection, { error: '未授权：请在 DSH 里打开这个页面' })
      }
      try {
        await route(ctx, { ingest }, req, res)
      } catch (error) {
        json(res, error?.status || 500, { error: error?.message || String(error) })
      }
    },
  })

  async function route(ctx, services, req, res) {
    const url = new URL(req.url || '/', 'http://localhost')
    const path = url.pathname.replace(/^\/kb-desk\/api/, '') || '/'
    const settings = readSettings()
    const root = vaultRoot(settings)
    const method = req.method || 'GET'

    if (path === '/bootstrap' && method === 'GET') {
      const cred = readCredentials(settings)
      let stats = null
      let ingestError = null
      try {
        stats = await services.ingest.stats()
      } catch (error) {
        ingestError = error?.message || String(error)
      }
      let inbox = []
      try {
        inbox = await listInbox(root)
      } catch {
        inbox = []
      }
      let git = null
      try {
        git = await gitOverview(root)
      } catch {
        git = null
      }
      return json(res, 200, {
        vault: { path: root, exists: existsSync(root), inboxCount: inbox.length, git },
        settings: { vault: settings.vault, apiBase: settings.apiBase, credentialsFile: settings.credentialsFile },
        credentials: { ingestToken: Boolean(cred.ingestToken), workerToken: Boolean(cred.workerToken), file: cred.source },
        ingest: { ok: !ingestError, error: ingestError, stats },
        triage: { active: activeCount(), jobs: listJobs().slice(0, 20), watcher: watcherState() },
        automation: {
          autoIngest: settings.autoIngest,
          autoApply: settings.autoApply,
          autoPush: settings.autoPush,
          watchSeconds: settings.watchSeconds,
        },
        model: modelInfo(ctx),
      })
    }

    if (path === '/settings' && method === 'POST') {
      const body = await readJson(req)
      const next = writeSettings({
        vault: body.vault,
        apiBase: body.apiBase,
        autoIngest: typeof body.autoIngest === 'boolean' ? body.autoIngest : undefined,
        autoApply: typeof body.autoApply === 'boolean' ? body.autoApply : undefined,
        autoPush: typeof body.autoPush === 'boolean' ? body.autoPush : undefined,
        watchSeconds: body.watchSeconds == null ? undefined : Number(body.watchSeconds),
      })
      return json(res, 200, {
        settings: { vault: next.vault, apiBase: next.apiBase },
        automation: { autoIngest: next.autoIngest, autoApply: next.autoApply, autoPush: next.autoPush, watchSeconds: next.watchSeconds },
      })
    }

    if (path === '/ingest/stats' && method === 'GET') {
      const stats = await services.ingest.stats()
      // 数字必须和列表同源：实时队列里的任务往往也在历史归档里，按 id 去重后再计数，
      // 不能把两边直接相加，否则卡片会比列表多。
      let history = []
      try {
        history = await services.ingest.history()
      } catch {
        history = []
      }
      let liveDone = []
      let liveFailed = []
      try {
        const [done, failed] = await Promise.all([
          services.ingest.jobs('done', 120),
          services.ingest.jobs('failed', 120),
        ])
        liveDone = done.jobs || []
        liveFailed = failed.jobs || []
      } catch {
        // 实时队列读不到就只报归档
      }
      // 失败要与「已解决」对账：同一个 id 或同一个链接已经有 done 记录时，
      // 这条失败只是历史上同步阶段的假失败（内容其实已进库），不该继续报警。
      const resolvedIds = new Set()
      const resolvedUrls = new Set()
      for (const job of [...liveDone, ...history.filter((item) => item.status === 'done')]) {
        resolvedIds.add(job.id)
        const key = urlKeyOf(job.url)
        if (key) resolvedUrls.add(key)
      }
      const isResolved = (job) =>
        resolvedIds.has(job.id) || Boolean(job.url && resolvedUrls.has(urlKeyOf(job.url)))
      // 没有链接的历史失败既不能重试也不能回填，留在原始归档里，不作为面板待办
      const historyFailed = history.filter(
        (item) => item.status === 'failed' && Boolean(item.url) && !isResolved(item),
      )
      const mergeCount = (status, liveList, archivedList) => {
        const map = new Map()
        const source = archivedList || history.filter((item) => item.status === status)
        for (const job of source) map.set(job.id, job)
        for (const job of liveList) map.set(job.id, job)
        return { total: map.size, archivedOnly: [...map.values()].filter((job) => job.archived).length }
      }
      const done = mergeCount('done', liveDone)
      const failed = mergeCount('failed', liveFailed, historyFailed)
      // 心跳还没上线的旧 worker 没有 /workers 记录，用「最近一次抓取完成」兜底判断活性
      const lastDoneAt = Math.max(
        0,
        ...liveDone.map((job) => Number(job.finishedAt) || 0),
        ...history.filter((job) => job.status === 'done').map((job) => Number(job.finishedAt) || 0),
      )
      let workers = null
      try {
        workers = await services.ingest.workers()
      } catch {
        // 老版本服务没有 /workers：心跳显示为空，不影响其它统计
        workers = null
      }
      return json(res, 200, {
        stats: {
          ...stats,
          done: done.total,
          failed: failed.total,
          archived: { done: done.archivedOnly, failed: failed.archivedOnly },
        lastDoneAt: lastDoneAt || null,
        },
        workers,
      })
    }

    if (path === '/ingest/jobs' && method === 'GET') {
      const status = query(url, 'status', 'queued')
      const limit = Math.min(Number(query(url, 'limit', 20)) || 20, 120)
      const live = await services.ingest.jobs(status, limit)
      let archivedAll = []
      try {
        archivedAll = await services.ingest.history()
      } catch {
        archivedAll = []
      }
      let archived = archivedAll.filter((job) => job.status === status)
      if (status === 'failed') {
        // 失败列表同样按「同一 id / 同一链接已有 done」对账，避免展示假失败
        let liveDone = []
        try {
          liveDone = (await services.ingest.jobs('done', 120)).jobs || []
        } catch {}
        const resolvedIds = new Set(liveDone.map((job) => job.id))
        const resolvedUrls = new Set()
        for (const job of [...liveDone, ...archivedAll.filter((item) => item.status === 'done')]) {
          resolvedIds.add(job.id)
          const key = urlKeyOf(job.url)
          if (key) resolvedUrls.add(key)
        }
        archived = archived.filter(
          (job) =>
            Boolean(job.url) &&
            !resolvedIds.has(job.id) &&
            !resolvedUrls.has(urlKeyOf(job.url)),
        )
      }
      const seen = new Set(live.jobs.map((job) => job.id))
      // 重新提交过的历史失败记录带一个本地标记，界面据此说明「已经换成新任务」，
      // 不再让它看起来像一条没人处理、点了也没反应的失败。
      const marks = readMarks()
      // 远端只记「有没有写 Inbox」，本地落成哪篇 raw/摘要得由 vault 反查：history 里
      // 缺 vault_path、或当时的摄入不是插件整理的，都不该显示成「只在 Inbox」。
      let lookupLocal = null
      try {
        lookupLocal = await localIngestIndex(root)
      } catch {
        lookupLocal = null
      }
      const merged = [...live.jobs, ...archived.filter((job) => !seen.has(job.id))]
        .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))
        .slice(0, limit)
        .map((job) => {
          const enriched = marks[job.id] ? { ...job, resubmitted: marks[job.id] } : job
          if (!lookupLocal || !job.url) return enriched
          const local = lookupLocal(job.url)
          return local ? { ...enriched, local } : enriched
        })
      return json(res, 200, { status, count: merged.length, jobs: merged, live: live.jobs.length, archived: archived.length })
    }

    if (path === '/ingest/local' && method === 'GET') {
      const days = Math.min(Number(query(url, 'days', 30)) || 30, 365)
      const limit = Math.min(Number(query(url, 'limit', 20)) || 20, 120)
      let rows = []
      try {
        rows = await scanLocalIngests(root, { days, limit: Math.min(limit * 3, 200) })
      } catch {
        rows = []
      }
      // 已经走过远端队列的链接会在「摄入」列表里出现，这里只列没有再补一遍。
      const remote = new Set()
      const remember = (job) => {
        for (const key of urlKeys(job?.url)) remote.add(key)
      }
      try {
        for (const job of await services.ingest.history()) remember(job)
      } catch {
        // 远端读不到就当成「全是本地」，页面标清楚即可
      }
      try {
        for (const job of (await services.ingest.jobs('done', 120)).jobs || []) remember(job)
      } catch {
        // 同上
      }
      const filtered = rows.filter((row) => !urlKeys(row.url).some((key) => remote.has(key))).slice(0, limit)
      return json(res, 200, { count: filtered.length, remoteCount: remote.size, rows: filtered })
    }

    if (path === '/ingest/runs' && method === 'GET') {
      return json(res, 200, { runs: await services.ingest.runs(Math.min(Number(query(url, 'limit', 12)) || 12, 40)) })
    }

    if (path === '/ingest/run' && method === 'GET') {
      const jobId = query(url, 'jobId')
      if (!jobId) return json(res, 400, { error: '缺少 jobId' })
      return json(res, 200, await services.ingest.run(jobId))
    }

    // 失败任务排查：先把本机证据收齐（SSE 的 context 事件），再流式给模型结论（delta）。
    if (path === '/ingest/diagnose' && method === 'POST') {
      const body = await readJson(req)
      const jobId = String(body.jobId || body.job?.id || '').trim()
      if (!jobId) return json(res, 400, { error: '缺少 jobId' })
      const note = String(body.note || '').slice(0, 1200)
      const controller = new AbortController()
      let finished = false
      res.on('close', () => {
        if (!finished) controller.abort()
      })
      res.writeHead(200, {
        'content-type': 'text/event-stream; charset=utf-8',
        'cache-control': 'no-store',
        connection: 'keep-alive',
      })
      const send = (event, data) => {
        if (!res.writableEnded) res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
      }
      try {
        const gathered = await gatherFailure({
          ingest: services.ingest,
          root,
          job: body.job,
          jobId,
          note,
          probe: body.probe !== false,
        })
        send('context', gathered.context)
        if (!controller.signal.aborted) {
          const result = await diagnoseFailure(ctx, {
            evidence: gathered.evidence,
            signal: controller.signal,
            onText: (text) => send('delta', { text }),
          })
          send('done', { text: result.text, model: result.model })
        }
      } catch (error) {
        send('error', { message: error?.message || String(error) })
      } finally {
        finished = true
        if (!res.writableEnded) res.end()
      }
      return undefined
    }

    if (path === '/ingest/retry' && method === 'POST') {
      const body = await readJson(req)
      const ids = Array.isArray(body.ids) ? body.ids.slice(0, 100) : []
      const hints = Array.isArray(body.jobs) ? body.jobs.slice(0, 100) : []
      try {
        const result = await services.ingest.retry(ids, hints)
        for (const item of result.resubmitted || []) {
          markResubmitted(item.id, { jobId: item.jobId || null, url: item.url, duplicate: Boolean(item.duplicate) })
        }
        return json(res, 200, result)
      } catch (err) {
        return json(res, err.status || 502, { error: err.message || '重试失败' })
      }
    }

    if (path === '/ingest/submit' && method === 'POST') {
      const body = await readJson(req)
      const target = String(body.url || '').trim()
      if (!/^https?:\/\//i.test(target)) return json(res, 400, { error: '请填 http(s) 链接' })
      const result = await services.ingest.submit({ url: target, title: body.title, note: body.note })
      return json(res, 200, result)
    }

    if (path === '/vault/inbox' && method === 'GET') {
      return json(res, 200, { docs: await listInbox(root) })
    }

    if (path === '/vault/doc' && method === 'GET') {
      const rel = query(url, 'path')
      if (!rel) return json(res, 400, { error: '缺少 path' })
      const doc = await readDoc(root, rel)
      return json(res, 200, doc)
    }

    if (path === '/vault/recent' && method === 'GET') {
      const days = Math.min(Number(query(url, 'days', 30)) || 30, 365)
      const limit = Math.min(Number(query(url, 'limit', 40)) || 40, 100)
      return json(res, 200, { docs: await recentDocs(root, { days, limit, material: true }) })
    }

    if (path === '/triage/propose' && method === 'POST') {
      const body = await readJson(req)
      const inboxPath = String(body.path || '').trim()
      if (!inboxPath) return json(res, 400, { error: '缺少 Inbox 文件路径' })
      try {
        return json(res, 200, await proposeTriage(ctx, root, inboxPath))
      } catch (err) {
        return json(res, err.status || 502, { error: err.message || '整理提案失败' })
      }
    }

    if (path === '/triage/enqueue' && method === 'POST') {
      const body = await readJson(req)
      const entries = Array.isArray(body.paths) ? body.paths : body.path ? [{ path: body.path, title: body.title }] : []
      if (!entries.length) return json(res, 400, { error: '缺少要整理的文件' })
      try {
        const queued = await enqueue(ctx, root, entries)
        return json(res, 200, { jobs: queued, active: activeCount() })
      } catch (err) {
        return json(res, err.status || 500, { error: err.message || '入队失败' })
      }
    }

    if (path === '/triage/jobs' && method === 'GET') {
      await triageReady()
      return json(res, 200, { jobs: listJobs(), active: activeCount() })
    }

    if (path === '/triage/job' && method === 'GET') {
      const id = query(url, 'id', '')
      const job = id ? getJob(id) : null
      if (!job) return json(res, 404, { error: '找不到这个整理任务' })
      return json(res, 200, job)
    }

    if (path === '/triage/dismiss' && method === 'POST') {
      const body = await readJson(req)
      await dismissQueued(String(body.id || ''))
      return json(res, 200, { ok: true, active: activeCount() })
    }

    if (path === '/triage/apply' && method === 'POST') {
      const body = await readJson(req)
      if (body.id) {
        try {
          const result = await applyQueued(String(body.id), ctx, root)
          return json(res, 200, result)
        } catch (err) {
          return json(res, err.status || 500, { error: err.message || '写入失败' })
        }
      }
      const proposal = body.proposal
      if (!proposal || typeof proposal !== 'object') return json(res, 400, { error: '缺少提案' })
      proposal.inboxPath = proposal.inboxPath || body.path || ''
      if (!proposal.inboxPath) return json(res, 400, { error: '缺少 Inbox 文件路径' })
      try {
        return json(res, 200, await applyTriage(ctx, root, proposal))
      } catch (err) {
        return json(res, err.status || 500, { error: err.message || '写入失败' })
      }
    }

    if (path === '/triage/commit' && method === 'POST') {
      const body = await readJson(req)
      try {
        return json(res, 200, await gitCommitAndPush(root, String(body.message || '').trim()))
      } catch (err) {
        return json(res, 500, { error: err.message || 'git 操作失败' })
      }
    }

    if (path === '/auto/run' && method === 'POST') {
      await runWatcherNow(ctx)
      return json(res, 200, { ok: true, watcher: watcherState() })
    }

    if (path === '/vault/git' && method === 'GET') {
      const fetched = url.includes('fetch=1')
      return json(res, 200, await gitOverview(root, { fetch: fetched }))
    }

    if (path === '/vault/pull' && method === 'POST') {
      return json(res, 200, await pullVault(root))
    }

    if (path === '/health' && method === 'GET') {
      const result = await healthCheck(root, settings, services.ingest)
      let report = null
      if (query(url, 'save') === '1') report = await writeHealthReport(root, result)
      return json(res, 200, { ...result, report })
    }

    if (path === '/health/report' && method === 'POST') {
      const result = await healthCheck(root, settings, services.ingest)
      const report = await writeHealthReport(root, result)
      return json(res, 200, { report, counts: result.counts })
    }

    if (path === '/learn/article' && method === 'GET') {
      const target = query(url, 'url')
      if (!target) return json(res, 400, { error: '缺少 url' })
      return json(res, 200, await fetchArticle(target))
    }

    if (path === '/learn/chat' && method === 'POST') {
      const body = await readJson(req)
      const message = String(body.message || '').trim()
      if (!message) return json(res, 400, { error: '说点什么再发' })
      const article = {
        title: body.article?.title || '未命名文章',
        url: body.article?.url || '',
        paragraphs: Array.isArray(body.article?.paragraphs) ? body.article.paragraphs : [],
      }
      let related = []
      if (body.useVault !== false) {
        try {
          related = await searchVault(root, `${message} ${article.title}`, 4)
        } catch {
          related = []
        }
      }
      res.writeHead(200, {
        'content-type': 'text/event-stream; charset=utf-8',
        'cache-control': 'no-store',
        connection: 'keep-alive',
      })
      const send = (event, data) => {
        res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
      }
      try {
        const result = await callModel(ctx, {
          system: LEARN_SYSTEM,
          messages: [{ role: 'user', content: learnUserPrompt({ article, related, history: body.history || [], message }) }],
          maxTokens: 1600,
          onText: (delta) => send('delta', { text: delta }),
        })
        send('related', { items: related.map((item) => ({ path: item.path, title: item.title })) })
        send('done', { text: result.text, model: result.model })
      } catch (error) {
        send('error', { message: error?.message || String(error) })
      }
      res.end()
      return undefined
    }

    if (path === '/learn/save' && method === 'POST') {
      const body = await readJson(req)
      const title = String(body.title || '').trim()
      if (!title) return json(res, 400, { error: '缺少标题' })
      const doc = await writeInboxDoc(root, {
        title,
        url: body.url || '',
        source: body.url ? 'learning:web' : 'learning',
        body: String(body.body || ''),
        tags: Array.isArray(body.tags) ? body.tags : ['学习笔记'],
        author: body.author || '',
        publishedAt: body.publishedAt || '',
      })
      return json(res, 200, doc)
    }

    if (path === '/create/recent' && method === 'GET') {
      const days = Math.min(Number(query(url, 'days', 30)) || 30, 365)
      const limit = Math.min(Number(query(url, 'limit', 60)) || 60, 200)
      const material = query(url, 'material') !== '0'
      return json(res, 200, { docs: await recentDocs(root, { days, limit, material }) })
    }

    if (path === '/create/topics' && method === 'POST') {
      const body = await readJson(req)
      const days = Math.min(Number(body.days) || 30, 365)
      const picked = []
      if (Array.isArray(body.paths) && body.paths.length) {
        for (const rel of body.paths.slice(0, 12)) {
          try {
            const doc = await readDoc(root, rel)
            picked.push({ title: doc.title, path: doc.path, space: doc.frontmatter?.space || null, type: doc.frontmatter?.type || null, excerpt: String(doc.body).replace(/\s+/g, ' ').slice(0, 600) })
          } catch {
            // 单个文件读不到不影响整体选题
          }
        }
      }
      const docs = picked.length ? picked : await recentDocs(root, { days, limit: 20, material: true })
      if (!docs.length) return json(res, 409, { error: '这段时间知识库里没有新内容，换个天数或先摄入几篇' })
      const result = await callModel(ctx, {
        system: TOPIC_SYSTEM,
        messages: [{ role: 'user', content: topicsUserPrompt({ docs, days }) }],
        maxTokens: 2600,
      })
      const topics = parseJsonLoose(result.text)
      if (!Array.isArray(topics)) {
        return json(res, 502, { error: '模型没有返回可解析的选题 JSON', raw: String(result.text).slice(0, 800) })
      }
      return json(res, 200, {
        model: result.model,
        topics: topics.slice(0, 10).map((topic) => ({
          platform: topic.platform === '小红书' ? '小红书' : '公众号',
          title: String(topic.title || '').slice(0, 60),
          hook: String(topic.hook || '').slice(0, 120),
          angle: String(topic.angle || '').slice(0, 160),
          outline: Array.isArray(topic.outline) ? topic.outline.map((line) => String(line).slice(0, 200)).slice(0, 6) : [],
          sources: Array.isArray(topic.sources) ? topic.sources.map((line) => String(line).slice(0, 120)).slice(0, 6) : [],
        })),
      })
    }

    if (path === '/create/draft' && method === 'POST') {
      const body = await readJson(req)
      if (!String(body.title || '').trim()) return json(res, 400, { error: '缺少标题' })
      return json(res, 200, await writeDraft(root, { title: body.title, platform: body.platform, body: String(body.body || '') }))
    }

    return json(res, 404, { error: '接口不存在' })
  }
}
