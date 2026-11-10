// raincoat-kb-desk 浏览器半片：主页面 + 侧栏入口。手写 CJS，无构建步骤。
window.__ModuleLoader__.load({
  id: '@local/raincoat-kb-desk',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const { useCallback, useEffect, useMemo, useRef, useState } = React
    const useRefLoose = React.useRef || ((initial) => ({ current: initial }))

    const API = '/kb-desk/api'
    const BUILD = '20261110-1135-kbdesk'
    const TABS = [
      { id: 'ingest', label: '摄入' },
      { id: 'health', label: '健康' },
      { id: 'learn', label: '学习' },
      { id: 'create', label: '创作' },
    ]

    // ───────────────────────── 基础工具 ─────────────────────────

    async function api(path, options = {}) {
      const res = await fetch(API + path, {
        method: options.method || 'GET',
        headers: options.body ? { 'content-type': 'application/json' } : undefined,
        body: options.body ? JSON.stringify(options.body) : undefined,
      })
      const text = await res.text()
      let payload = null
      try {
        payload = text ? JSON.parse(text) : null
      } catch {
        payload = { error: text.slice(0, 300) }
      }
      if (!res.ok) {
        const error = new Error(payload?.error || `请求失败（${res.status}）`)
        error.payload = payload
        error.status = res.status
        throw error
      }
      return payload
    }

    async function readSSE(res, onEvent) {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let index = buffer.indexOf('\n\n')
        while (index >= 0) {
          const raw = buffer.slice(0, index)
          buffer = buffer.slice(index + 2)
          let event = 'message'
          let data = ''
          for (const line of raw.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim()
            else if (line.startsWith('data:')) data += line.slice(5).trim()
          }
          if (data) {
            try {
              onEvent(event, JSON.parse(data))
            } catch {
              // 单条事件解析失败就跳过，不中断整条流
            }
          }
          index = buffer.indexOf('\n\n')
        }
      }
    }

    async function streamPost(path, payload, onEvent, signal) {
      const res = await fetch(API + path, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
        signal,
      })
      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => '')
        let message = `请求失败（${res.status}）`
        try {
          message = JSON.parse(text)?.error || message
        } catch {
          // 保持默认提示
        }
        throw new Error(message)
      }
      await readSSE(res, onEvent)
    }

    async function streamChat(payload, onEvent) {
      await streamPost('/learn/chat', payload, onEvent)
    }

    function ago(ms) {
      if (!ms) return '—'
      const diff = Date.now() - ms
      if (diff < 60_000) return '刚刚'
      if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
      if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
      const days = Math.floor(diff / 86_400_000)
      return days < 30 ? `${days} 天前` : new Date(ms).toLocaleDateString('zh-CN')
    }

    function duration(ms) {
      if (!ms || ms < 0) return '—'
      if (ms < 1000) return '<1s'
      if (ms < 60_000) return `${Math.round(ms / 1000)}s`
      const minutes = Math.floor(ms / 60_000)
      return minutes < 60 ? `${minutes}m${Math.round((ms % 60_000) / 1000)}s` : `${Math.floor(minutes / 60)}h${minutes % 60}m`
    }

    async function copyText(text) {
      try {
        await navigator.clipboard.writeText(text)
        return true
      } catch {
        return false
      }
    }

    // ───────────────────────── 小部件 ─────────────────────────

    function Btn({ children, onClick, kind = 'ghost', disabled, title, size }) {
      return h('button', {
        type: 'button',
        className: `kbd-btn kbd-btn-${kind}${size === 'sm' ? ' kbd-btn-sm' : ''}`,
        onClick,
        disabled: Boolean(disabled),
        title,
      }, children)
    }

    function Pill({ children, tone = 'idle', onClick, active }) {
      return h(onClick ? 'button' : 'span', {
        className: `kbd-pill kbd-pill-${tone}${active ? ' is-active' : ''}`,
        onClick,
        type: onClick ? 'button' : undefined,
      }, children)
    }

    function Card({ title, value, hint, tone }) {
      return h('div', { className: `kbd-card${tone ? ` kbd-card-${tone}` : ''}` }, [
        h('div', { className: 'kbd-card-label', key: 'l' }, title),
        h('div', { className: 'kbd-card-value', key: 'v' }, value),
        hint ? h('div', { className: 'kbd-card-hint', key: 'h' }, hint) : null,
      ])
    }

    function Empty({ children }) {
      return h('div', { className: 'kbd-empty' }, children)
    }

    function Notice({ kind = 'error', children, onClose }) {
      if (!children) return null
      return h('div', { className: `kbd-notice kbd-notice-${kind}` }, [
        h('span', { key: 't' }, children),
        onClose ? h('button', { key: 'x', type: 'button', className: 'kbd-notice-x', onClick: onClose }, '×') : null,
      ])
    }

    function Spinner({ label = '加载中' }) {
      return h('div', { className: 'kbd-loading' }, [h('span', { className: 'kbd-dot', key: 'd' }), label])
    }

    const LEVEL_META = {
      red: { label: '必须处理', tone: 'error' },
      yellow: { label: '待处理', tone: 'warn' },
      blue: { label: '建议关注', tone: 'idle' },
    }
    const CATEGORY_LABEL = {
      inbox: 'Inbox 待整理',
      frontmatter: 'frontmatter',
      links: '连接度',
      'open-questions': '待确认',
      contradiction: '矛盾',
      threads: 'Open Threads',
      stale: '长期未更新',
      log: '操作日志',
      pipeline: '摄入链路',
    }
    const TRIAGE_META = {
      queued: { label: '排队中', tone: 'idle' },
      running: { label: '整理中', tone: 'warn' },
      proposal: { label: '待确认', tone: 'warn' },
      applied: { label: '已写入', tone: 'ok' },
      failed: { label: '失败', tone: 'error' },
    }
    const STATUS_META = {
      queued: { label: '排队中', tone: 'warn' },
      claimed: { label: '处理中', tone: 'warn' },
      done: { label: '已完成', tone: 'success' },
      failed: { label: '失败', tone: 'error' },
    }

    // ───────────────────────── 摄入 ─────────────────────────

    function IngestTab({ boot, refreshBoot }) {
      const [stats, setStats] = useState(null)
      const [status, setStatus] = useState('queued')
      const [jobs, setJobs] = useState([])
      const [selected, setSelected] = useState(null)
      const [run, setRun] = useState(null)
      const [inbox, setInbox] = useState([])
      const [url, setUrl] = useState('')
      const [busy, setBusy] = useState(false)
      const [notice, setNotice] = useState(null)
      const [preview, setPreview] = useState(null)
      const [triageJobs, setTriageJobs] = useState([])
      const [openJobId, setOpenJobId] = useState(null)
      const [openJob, setOpenJob] = useState(null)
      const [diagnoseJob, setDiagnoseJob] = useState(null)
      const [mechanism, setMechanism] = useState(false)
      const alive = useRefLoose(true)

      const loadTriage = useCallback(async () => {
        try {
          const payload = await api('/triage/jobs')
          if (alive.current) setTriageJobs(payload.jobs || [])
          return payload.jobs || []
        } catch {
          return []
        }
      }, [])

      const enqueueTriage = useCallback(async (docs) => {
        const paths = docs.map((doc) => ({ path: doc.path, title: doc.title }))
        if (!paths.length) return
        try {
          const payload = await api('/triage/enqueue', { method: 'POST', body: { paths } })
          if (!alive.current) return
          setNotice(`已经排上 ${payload.jobs.length} 条，模型在后台跑，可以先去别的页`)
          await loadTriage()
        } catch (error) {
          if (alive.current) setNotice(error.message)
        }
      }, [loadTriage])

      const load = useCallback(async (nextStatus = status) => {
        try {
          const [statsPayload, jobsPayload] = await Promise.all([
            api('/ingest/stats'),
            // 服务端按创建时间升序返回并从最早的开始截断，所以多要一些再在前端取最新的
            api(`/ingest/jobs?status=${nextStatus}&limit=120`),
          ])
          if (!alive.current) return
          setStats(statsPayload.stats)
          // 队列按时间倒序：最近的在最前面
          setJobs(
            [...(jobsPayload.jobs || [])]
              .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0))
              .slice(0, 40),
          )
        } catch (error) {
          if (alive.current) setNotice(error.message)
        }
      }, [status])

      const loadInbox = useCallback(async () => {
        try {
          const payload = await api('/vault/inbox')
          if (alive.current) setInbox(payload.docs || [])
        } catch {
          // Inbox 读不到不影响任务列表
        }
      }, [])

      useEffect(() => {
        alive.current = true
        load(status)
        loadInbox()
        loadTriage()
        const timer = setInterval(() => load(status), 15_000)
        const triageTimer = setInterval(loadTriage, 4_000)
        return () => {
          alive.current = false
          clearInterval(timer)
          clearInterval(triageTimer)
        }
      }, [load, loadInbox, loadTriage, status])

      useEffect(() => {
        if (!openJobId) {
          setOpenJob(null)
          return
        }
        let cancelled = false
        const tick = async () => {
          try {
            const job = await api(`/triage/job?id=${encodeURIComponent(openJobId)}`)
            if (!cancelled) setOpenJob(job)
          } catch (error) {
            if (!cancelled) setOpenJob({ id: openJobId, error: error.message, status: 'failed' })
          }
        }
        tick()
        const timer = setInterval(() => {
          tick().then(() => {})
        }, 3_000)
        return () => {
          cancelled = true
          clearInterval(timer)
        }
      }, [openJobId])

      useEffect(() => {
        if (!selected) {
          setRun(null)
          return
        }
        let cancelled = false
        api(`/ingest/run?jobId=${encodeURIComponent(selected.id)}`)
          .then((payload) => {
            if (!cancelled) setRun(payload.stages || [])
          })
          .catch(() => {
            if (!cancelled) setRun([])
          })
        return () => {
          cancelled = true
        }
      }, [selected])

      async function submit() {
        const target = url.trim()
        if (!target) return
        setBusy(true)
        try {
          const result = await api('/ingest/submit', { method: 'POST', body: { url: target } })
          setUrl('')
          setNotice(result?.duplicate ? '这条链接已经在队列里了（去重命中）' : `已提交：${result?.job_id || 'ok'}`)
          setStatus('queued')
          await load('queued')
          refreshBoot?.()
        } catch (error) {
          setNotice(error.message)
        } finally {
          setBusy(false)
        }
      }

      async function openDoc(path) {
        setPreview({ path, loading: true })
        try {
          const doc = await api(`/vault/doc?path=${encodeURIComponent(path)}`)
          setPreview({ ...doc, loading: false })
        } catch (error) {
          setPreview({ path, loading: false, error: error.message })
        }
      }

      const localJob = selected ? triageJobs.find((item) => item.path === selected.vaultPath) : null
      const stages = (() => {
        if (!selected) return []
        const rows = (Array.isArray(run) ? run : []).map((stage) => ({
          stage: stage.stage,
          status: stage.status,
          at: stage.at,
          note: stage.note,
          meta: `${stage.actor || 'worker'}${stage.durationSec ? ` · ${duration(stage.durationSec * 1000)}` : ''}`,
        }))
        if (!rows.length) {
          rows.push({ stage: '入队', status: 'ok', at: selected.createdAt, note: '客户端提交后进队列' })
          if (selected.claimedAt) rows.push({ stage: 'worker 领取', status: 'ok', at: selected.claimedAt, note: `worker ${selected.worker || 'mac-mini'}` })
          if (selected.finishedAt) rows.push({ stage: '写入 Inbox', status: selected.status === 'failed' ? 'failed' : 'ok', at: selected.finishedAt, note: selected.vaultPath || selected.error || '' })
          if (selected.status === 'queued') rows.push({ stage: '等待领取', status: 'running', at: Date.now(), note: 'worker 每 60 秒轮询一次' })
        }
        if (localJob) {
          const label = TRIAGE_META[localJob.status]?.label || localJob.status
          rows.push({
            stage: '本地整理',
            status: localJob.status === 'failed' ? 'failed' : localJob.status === 'applied' ? 'ok' : 'running',
            at: localJob.startedAt || localJob.createdAt,
            note: localJob.status === 'applied' ? `${label}：raw + 摘要 + 概念页` : label,
            meta: localJob.status === 'applied' ? '插件' : '插件',
          })
        }
        return rows
      })()
      const automation = boot?.automation || {}
      const saveAutomation = async (patch) => {
        try {
          await api('/settings', { method: 'POST', body: patch })
          refreshBoot?.()
        } catch (error) {
          setNotice(error.message)
        }
      }

      const runNow = async () => {
        try {
          await api('/auto/run', { method: 'POST' })
          await Promise.all([loadTriage(), loadInbox(), load(status)])
          setNotice('已经跑了一轮：拉取 → 排队 → 写入 → 推送')
        } catch (error) {
          setNotice(error.message)
        }
      }

      const statCards = [
        { title: '排队中', value: stats?.queued ?? '—', hint: stats?.oldestQueuedAt ? `最早已等 ${duration(Date.now() - stats.oldestQueuedAt)}` : '队列是空的', tone: stats?.queued ? 'warn' : null },
        { title: '处理中', value: stats?.claimed ?? '—', hint: 'worker 已领取' },
        { title: '已完成', value: stats?.done ?? '—', hint: '累计写入 vault' },
        { title: '失败', value: stats?.failed ?? '—', hint: stats?.failed ? '看失败页的原因' : '没有失败', tone: stats?.failed ? 'error' : null },
        { title: 'Inbox 待整理', value: inbox.length || (boot?.vault?.inboxCount ?? 0), hint: inbox.length ? '等 triage' : '已经清空', tone: inbox.length > 5 ? 'warn' : null },
      ]

      return h('div', { className: 'kbd-tab' }, [
        notice ? h(Notice, { key: 'n', kind: /已提交|去重/.test(notice) ? 'ok' : 'error', onClose: () => setNotice(null) }, notice) : null,
        h('div', { className: 'kbd-cards', key: 'cards' }, statCards.map((card, index) => h(Card, { key: index, ...card }))),

        h('div', { className: 'kbd-submit', key: 'submit' }, [
          h('input', {
            key: 'i',
            className: 'kbd-input',
            value: url,
            placeholder: '粘贴一个链接，交给远端 worker 抓进 Inbox',
            onChange: (event) => setUrl(event.target.value),
            onKeyDown: (event) => {
              if (event.key === 'Enter') submit()
            },
          }),
          h(Btn, { key: 'b', kind: 'primary', onClick: submit, disabled: busy || !url.trim() }, busy ? '提交中…' : '提交摄入'),
          h(Btn, { key: 'm', onClick: () => setMechanism(true) }, '机制说明'),
          h('span', { key: 'h', className: 'kbd-muted kbd-small' }, '手机也能用同一套接口：POST /api/ingest'),
        ]),

        h('div', { key: 'auto', className: 'kbd-auto' }, [
          h('span', { key: 'l', className: 'kbd-small kbd-muted' }, '自动闭环'),
          h(Pill, { key: 'i', tone: 'idle', active: Boolean(automation.autoIngest), onClick: () => saveAutomation({ autoIngest: !automation.autoIngest }) }, '整理新摄入'),
          h(Pill, { key: 'a', tone: 'idle', active: Boolean(automation.autoApply), onClick: () => saveAutomation({ autoApply: !automation.autoApply }) }, '自动写入'),
          h(Pill, { key: 'p', tone: 'idle', active: Boolean(automation.autoPush), onClick: () => saveAutomation({ autoPush: !automation.autoPush }) }, '自动推送'),
          h(Btn, { key: 'r', size: 'sm', onClick: runNow }, '立刻跑一轮'),
          automation.autoIngest === false
            ? h('span', { key: 'w', className: 'kbd-small kbd-warn-text' }, '自动摄入已关闭，Inbox 会堆积')
            : h('span', { key: 'hint', className: 'kbd-small kbd-muted' }, `每 ${automation.watchSeconds || 60} 秒跑一轮`),
        ]),

        h('div', { className: 'kbd-split', key: 'split' }, [
          h('section', { className: 'kbd-pane', key: 'left' }, [
            h('div', { className: 'kbd-pane-head', key: 'h' }, [
              h('div', { className: 'kbd-pills', key: 'p' }, Object.entries(STATUS_META).map(([id, meta]) => {
                const count = stats?.[id]
                return h(Pill, {
                  key: id,
                  tone: meta.tone,
                  active: status === id,
                  onClick: () => setStatus(id),
                }, count === undefined ? meta.label : `${meta.label} ${count}`)
              })),
              h('span', { className: 'kbd-muted kbd-small', key: 'c' }, `${jobs.length} 条`),
            ]),
            h('div', { className: 'kbd-list', key: 'l' }, jobs.length
              ? jobs.map((job) => h('button', {
                key: job.id,
                type: 'button',
                className: `kbd-row${selected?.id === job.id ? ' is-active' : ''}`,
                onClick: () => setSelected(job),
              }, [
                h('span', { key: 'dot', className: `kbd-dot kbd-dot-${STATUS_META[job.status]?.tone || 'idle'}` }),
                h('span', { key: 'main', className: 'kbd-row-main' }, [
                  h('span', { key: 't', className: 'kbd-row-title' }, job.title || job.url),
                  h('span', { key: 'u', className: 'kbd-row-sub' }, `${job.client || 'unknown'} · ${ago(job.createdAt)}${job.attempts ? ` · 第 ${job.attempts} 次` : ''}`),
                ]),
                job.duplicate ? h(Pill, { key: 'd', tone: 'idle' }, '重复') : null,
              ]))
              : h(Empty, { key: 'e' }, status === 'queued' ? '队列空了。粘一个链接试试。' : '这一栏暂时没有任务。')),
          ]),

          h('section', { className: 'kbd-pane', key: 'right' }, selected
            ? h('div', { className: 'kbd-detail' }, [
              h('div', { className: 'kbd-detail-head', key: 'h' }, [
                h(Pill, { key: 's', tone: STATUS_META[selected.status]?.tone || 'idle' }, STATUS_META[selected.status]?.label || selected.status),
                h('span', { key: 'w', className: 'kbd-muted kbd-small' }, selected.worker || '未领取'),
                h('span', { key: 'i', className: 'kbd-muted kbd-small' }, selected.id),
              ]),
              h('h3', { key: 't', className: 'kbd-detail-title' }, selected.title || '（还没拿到标题）'),
              h('a', { key: 'u', className: 'kbd-link', href: selected.url, target: '_blank', rel: 'noreferrer' }, selected.url),
              h('div', { key: 'meta', className: 'kbd-kv' }, [
                ['创建', ago(selected.createdAt)],
                ['领取', selected.claimedAt ? ago(selected.claimedAt) : '—'],
                ['结束', selected.finishedAt ? ago(selected.finishedAt) : '—'],
                ['耗时', duration(selected.elapsedMs)],
              ].map(([k, v]) => h('div', { key: k, className: 'kbd-kv-item' }, [h('span', { key: 'k' }, k), h('b', { key: 'v' }, v)]))),

              selected.error && selected.status !== 'failed' ? h('div', { key: 'err', className: 'kbd-error-box' }, [
                h('div', { key: 't', className: 'kbd-error-title' }, '失败原因'),
                h('div', { key: 'm' }, selected.error),
              ]) : null,

              selected.status === 'failed' ? h('div', { key: 'fail', className: 'kbd-fail' }, [
                h('div', { key: 'box', className: 'kbd-error-box' }, [
                  h('div', { key: 't', className: 'kbd-error-title' }, selected.error ? '失败原因' : '远端没留错误文本'),
                  h('div', { key: 'm' }, selected.error || '点「排查原因」，把本机 vault、阶段记录和源站一起对一遍。'),
                ]),
                h(Btn, { key: 'd', kind: 'primary', onClick: () => setDiagnoseJob(selected) }, '排查原因'),
              ]) : null,

              selected.vaultPath ? h('div', { key: 'vp', className: 'kbd-line' }, [
                h('span', { key: 'k', className: 'kbd-muted' }, '落盘位置 '),
                h('button', { key: 'b', type: 'button', className: 'kbd-link', onClick: () => openDoc(selected.vaultPath) }, selected.vaultPath),
              ]) : null,

              h('div', { key: 'stages', className: 'kbd-stages' }, [
                h('div', { key: 't', className: 'kbd-section-title' }, '摄入进度'),
                run === null && !selected.finishedAt
                  ? h(Spinner, { key: 's', label: '读运行记录' })
                  : !stages.length
                    ? h('div', { key: 'e', className: 'kbd-muted kbd-small' }, '还没有阶段记录。')
                    : h('ol', { key: 'ol', className: 'kbd-timeline' }, stages.map((stage, index) => h('li', { key: index, className: `kbd-stage kbd-stage-${stage.status}` }, [
                      h('span', { key: 'd', className: 'kbd-stage-dot' }),
                      h('div', { key: 'b' }, [
                        h('div', { key: 'n', className: 'kbd-stage-name' }, [stage.stage, stage.meta ? h('span', { key: 'a', className: 'kbd-muted kbd-small' }, ` · ${stage.meta}`) : null]),
                        h('div', { key: 's', className: 'kbd-small kbd-muted' }, `${stage.status}${stage.at ? ` · ${ago(stage.at)}` : ''}`),
                        stage.note ? h('div', { key: 'note', className: 'kbd-stage-note' }, stage.note) : null,
                      ]),
                    ]))),
              ]),
            ])
            : h(Empty, { key: 'e' }, '左边选一条任务看详情和进度。')),

          mechanism ? h(MechanismModal, { key: 'mech', onClose: () => setMechanism(false) }) : null,
          preview ? h(DocPreview, { key: 'pv', doc: preview, onClose: () => setPreview(null) }) : null,
          openJobId ? h(TriageModal, {
            key: 'tri',
            job: openJob,
            jobId: openJobId,
            onClose: () => setOpenJobId(null),
            onChanged: (job) => setOpenJob(job),
            onDone: () => {
              setOpenJobId(null)
              loadInbox()
              loadTriage()
              refreshBoot?.()
            },
          }) : null,
          diagnoseJob ? h(DiagnoseModal, {
            key: 'diag',
            job: diagnoseJob,
            onClose: () => setDiagnoseJob(null),
          }) : null,
        ]),

        h('section', { className: 'kbd-section', key: 'inbox' }, [
          h('div', { key: 'h', className: 'kbd-section-head' }, [
            h('h3', { key: 't' }, 'Inbox 待整理'),
            h('span', { key: 'c', className: 'kbd-muted kbd-small' }, '这些是落盘了但还没 triage 的原文'),
            inbox.length
              ? h(Btn, { key: 'all', size: 'sm', onClick: () => enqueueTriage(inbox.filter((doc) => !triageJobs.some((job) => job.path === doc.path && (job.status === 'queued' || job.status === 'running' || job.status === 'proposal')))) }, '全部整理')
              : null,
          ]),
          inbox.length
            ? h('div', { key: 'l', className: 'kbd-inbox' }, inbox.map((doc) => {
              const job = triageJobs.find((item) => item.path === doc.path)
              const state = job ? TRIAGE_META[job.status] : null
              const canOpen = job && (job.status === 'proposal' || job.status === 'applied')
              return h('div', {
                key: doc.path,
                className: 'kbd-inbox-item',
              }, [
                h('button', {
                  key: 'b',
                  type: 'button',
                  className: 'kbd-inbox-open',
                  onClick: () => (canOpen ? setOpenJobId(job.id) : openDoc(doc.path)),
                }, [
                  h('div', { key: 't', className: 'kbd-row-title' }, doc.title),
                  h('div', { key: 'm', className: 'kbd-small kbd-muted' }, `${doc.ageDays === null ? '时间未知' : `停留 ${doc.ageDays} 天`} · ${doc.source || '来源未知'}`),
                  h('div', { key: 'e', className: 'kbd-inbox-excerpt' }, doc.excerpt),
                ]),
                h('div', { key: 'a', className: 'kbd-inbox-actions' }, [
                  state ? h(Pill, { key: 's', tone: state.tone }, state.label) : null,
                  h(Btn, {
                    key: 'tr',
                    size: 'sm',
                    disabled: Boolean(state) && job.status !== 'failed',
                    kind: job?.status === 'proposal' ? 'primary' : 'ghost',
                    onClick: () => (canOpen ? setOpenJobId(job.id) : enqueueTriage([doc])),
                  }, job?.status === 'proposal' ? '看提案' : job?.status === 'failed' ? '重试' : state ? state.label : '整理'),
                ]),
              ])
            }))
            : h(Empty, { key: 'e' }, 'Inbox 是空的，摄入链路是通的。'),
        ]),
      ])
    }

    const MECH_STEPS = [
      {
        n: '01',
        who: '远端 · rainpark.cn',
        title: '接住你粘的链接',
        body: 'POST /api/ingest 只做三件事：按 URL 去重、落一条 job、把 job 交给排队。提交完就可以关页面，手机、浏览器插件、命令行走的是同一个接口。',
      },
      {
        n: '02',
        who: 'mac-mini worker · 每 60 秒',
        title: '抓成原文，写进 Inbox',
        body: 'worker 领取 job，抓取正文和元信息，写到 00 Inbox/YYYY/MM/DD/标题.md，然后把结果上报给 /api/runs。这一步不判断内容，只保证原文完整落盘——所以你在 Inbox 里看到的永远是原样，不是压缩过的摘要。',
      },
      {
        n: '03',
        who: '插件宿主 · 本机 · 每 60 秒',
        title: '收提交、排队、让模型出提案',
        body: '先 fetch + pull 把 worker 刚推上来的提交收进本地（工作区有未提交改动就跳过，不动你手写的内容）；Inbox 里没排过队的文件逐个入队；模型读原文和 vault 里已有的概念页，给出判定（raw / idea / drop）、归到哪个 space、抽象成哪几条概念。',
      },
      {
        n: '04',
        who: '插件宿主 · 本地代码',
        title: '按提案落盘，再同步索引',
        body: '写 00 raw/<space>/<年>/<月>/、01 wiki/<space>/summaries/S-<编号>-<slug>.md，概念页只追加段落 + Timeline + 回链（不整页重写），然后重算 01 wiki/index.md 的计数、往 _index.md 的摘要列表补一行、往 log.md 记一条。',
      },
      {
        n: '05',
        who: '插件宿主 · 队列空了才跑',
        title: '提交并推送',
        body: '只 git add 五个路径：00 Inbox、00 raw、01 wiki、02 outputs/health、02 outputs/drafts。commit 后 pull --rebase 再 push，被拒就重来一次。你的手写笔记不会被卷进这次提交。',
      },
    ]

    function MechanismModal({ onClose }) {
      return h('div', { className: 'kbd-overlay', onClick: onClose }, [
        h('div', { className: 'kbd-modal kbd-modal-wide', key: 'm', onClick: (event) => event.stopPropagation() }, [
          h('div', { key: 'h', className: 'kbd-modal-head' }, [
            h('div', { key: 't' }, [
              h('div', { key: 'a', className: 'kbd-modal-title' }, '这套摄入是怎么跑的'),
              h('div', { key: 'b', className: 'kbd-small kbd-muted' }, '从你粘贴一个链接，到 vault 里出现一篇可引用的笔记'),
            ]),
            h('div', { key: 'r' }, h(Btn, { size: 'sm', onClick: onClose }, '关闭')),
          ]),
          h('div', { key: 'body', className: 'kbd-mech' }, MECH_STEPS.map((step) => h('div', { key: step.n, className: 'kbd-mech-step' }, [
            h('div', { key: 'n', className: 'kbd-mech-n' }, step.n),
            h('div', { key: 'b', className: 'kbd-mech-body' }, [
              h('div', { key: 'w', className: 'kbd-mech-who' }, step.who),
              h('div', { key: 't', className: 'kbd-mech-title' }, step.title),
              h('div', { key: 'd', className: 'kbd-small kbd-muted' }, step.body),
            ]),
          ]))),
          h('div', { key: 'notes', className: 'kbd-mech-notes' }, [
            h('div', { key: 'a', className: 'kbd-mech-note' }, [
              h('strong', { key: 's' }, '幂等 '),
              '摘要按 slug 和标题双重匹配，同一篇重投不会长出第二条；已存在的原文不覆盖；同一段内容已经在页面里就跳过。',
            ]),
            h('div', { key: 'b', className: 'kbd-mech-note' }, [
              h('strong', { key: 's' }, '冲突 '),
              'push 被拒就 rebase 后重试一次；本地脏就跳过 pull，宁可慢一轮也不覆盖你的编辑。',
            ]),
            h('div', { key: 'c', className: 'kbd-mech-note' }, [
              h('strong', { key: 's' }, '人工关卡 '),
              '关掉「自动写入」，提案会停在待确认，弹窗里看过再点确认；关掉「自动推送」，写盘和推送分开走。',
            ]),
          ]),
          h('div', { key: 'f', className: 'kbd-modal-foot' }, [
            h('span', { key: 's', className: 'kbd-small kbd-muted' }, '更细的字段和文件规范见插件目录的 README.md'),
            h(Btn, { key: 'c', kind: 'primary', onClick: onClose }, '知道了'),
          ]),
        ]),
      ])
    }

    function TriageModal({ job, jobId, onClose, onChanged, onDone }) {
      const [applying, setApplying] = useState(false)
      const [committing, setCommitting] = useState(false)
      const [commitMsg, setCommitMsg] = useState(null)
      const [localError, setLocalError] = useState(null)
      const [result, setResult] = useState(null)
      const proposal = job?.proposal
      const status = job?.status || 'queued'
      const meta = TRIAGE_META[status] || TRIAGE_META.queued

      const apply = async () => {
        setApplying(true)
        setLocalError(null)
        try {
          const payload = await api('/triage/apply', { method: 'POST', body: { id: jobId } })
          setResult(payload)
          onChanged?.({ ...job, status: 'applied', result: payload })
        } catch (error) {
          setLocalError(error.message)
        } finally {
          setApplying(false)
        }
      }

      const commit = async () => {
        setCommitting(true)
        try {
          const payload = await api('/triage/commit', {
            method: 'POST',
            body: { message: `kb: 整理「${proposal?.title || job?.title || ''}」` },
          })
          setCommitMsg(payload.ok ? '已提交并推送' : `没推上去：${payload.message}`)
          if (payload.ok) onDone?.()
        } catch (error) {
          setCommitMsg(error.message)
        } finally {
          setCommitting(false)
        }
      }

      const decisionLabel = proposal?.decision === 'drop' ? '丢弃' : proposal?.decision === 'idea' ? '只留灵感' : '归档为 raw'
      const changes = result?.changes || job?.result?.changes || []

      const body = job?.error
        ? h(Notice, { key: 'e', kind: 'error' }, job.error)
        : status === 'queued' || status === 'running'
          ? h('div', { key: 'b', className: 'kbd-triage-busy' }, [
            h('div', { key: 's', className: 'kbd-spinner' }),
            h('div', { key: 't' }, [
              h('div', { key: 'a', className: 'kbd-small' }, status === 'queued' ? '排队中，前面还有别的任务…' : '模型在读这篇原文，按 vault 规范出整理提案…'),
              h('div', { key: 'b', className: 'kbd-small kbd-muted' }, '可以关掉这个窗口，跑完会在 Inbox 卡片上标「待确认」。'),
            ]),
          ])
          : proposal
            ? h('div', { key: 'b', className: 'kbd-triage-body' }, [
              h('div', { key: 'meta', className: 'kbd-triage-meta' }, [
                h(Pill, { key: 'd', tone: proposal.decision === 'drop' ? 'warn' : 'ok' }, decisionLabel),
                h(Pill, { key: 's' }, `space: ${proposal.space}`),
                h('code', { key: 'slug', className: 'kbd-file' }, proposal.slug),
              ]),
              proposal.reason ? h('p', { key: 'r', className: 'kbd-triage-reason' }, proposal.reason) : null,

              h('section', { key: 'sum', className: 'kbd-section' }, [
                h('div', { key: 'h', className: 'kbd-section-head' }, [h('h3', { key: 't' }, '摘要')]),
                h('p', { key: 'tl', className: 'kbd-triage-tldr' }, proposal.summary?.tldr || '（模型没给摘要）'),
                Array.isArray(proposal.summary?.keyPoints) && proposal.summary.keyPoints.length
                  ? h('ul', { key: 'kp', className: 'kbd-triage-list' }, proposal.summary.keyPoints.map((line, i) => h('li', { key: i }, line)))
                  : null,
                proposal.summary?.judgement ? h('p', { key: 'j', className: 'kbd-triage-judgement' }, proposal.summary.judgement) : null,
                Array.isArray(proposal.summary?.openQuestions) && proposal.summary.openQuestions.length
                  ? h('div', { key: 'oq', className: 'kbd-triage-oq' }, [
                    h('span', { key: 'l', className: 'kbd-small kbd-muted' }, '待验证：'),
                    ...proposal.summary.openQuestions.map((line, i) => h('div', { key: i, className: 'kbd-small' }, `· ${line}`)),
                  ])
                  : null,
              ]),

              h('section', { key: 'con', className: 'kbd-section' }, [
                h('div', { key: 'h', className: 'kbd-section-head' }, [
                  h('h3', { key: 't' }, '概念页改动'),
                  h('span', { key: 'c', className: 'kbd-small kbd-muted' }, '只做增量，不重写既有段落'),
                ]),
                proposal.concepts?.length
                  ? h('div', { key: 'l', className: 'kbd-triage-concepts' }, proposal.concepts.map((item, i) => h('div', { key: i, className: 'kbd-triage-concept' }, [
                    h('div', { key: 'p', className: 'kbd-small kbd-file' }, item.action === 'create' ? `新建：${item.title || '（未命名）'}` : item.path),
                    h('div', { key: 's', className: 'kbd-small kbd-muted' }, `写入 ${item.section || 'State'}${item.heading ? ` · ${item.heading}` : ''}`),
                    h('p', { key: 'x', className: 'kbd-triage-text' }, item.text),
                  ])))
                  : h('div', { key: 'e', className: 'kbd-muted kbd-small' }, '这篇没有触发概念页改动。'),
              ]),

              changes.length
                ? h('section', { key: 'res', className: 'kbd-section' }, [
                  h('div', { key: 'h', className: 'kbd-section-head' }, [h('h3', { key: 't' }, '已写入')]),
                  h('ul', { key: 'l', className: 'kbd-triage-changes' }, changes.map((item, i) => h('li', { key: i }, [
                    h('code', { key: 'p', className: 'kbd-file' }, item.path),
                    h('span', { key: 'n', className: 'kbd-small kbd-muted' }, ` ${item.note}`),
                  ]))),
                  job?.warnings?.length
                    ? h('div', { key: 'w', className: 'kbd-small kbd-warn-text' }, job.warnings.join('；'))
                    : null,
                  commitMsg ? h('div', { key: 'cm', className: 'kbd-small kbd-muted' }, commitMsg) : null,
                ])
                : null,
            ])
            : h('div', { key: 'e', className: 'kbd-muted' }, '没有提案内容。')

      const written = status === 'applied' || Boolean(changes.length)

      return h('div', { className: 'kbd-overlay', onClick: onClose }, [
        h('div', { className: 'kbd-modal kbd-modal-wide', key: 'm', onClick: (event) => event.stopPropagation() }, [
          h('div', { key: 'h', className: 'kbd-modal-head' }, [
            h('div', { key: 't' }, [
              h('div', { key: 'a', className: 'kbd-modal-title' }, '整理这篇 Inbox'),
              h('div', { key: 'b', className: 'kbd-small kbd-muted' }, job?.title || job?.path || '读取中…'),
            ]),
            h('div', { key: 'r', className: 'kbd-triage-meta' }, [
              h(Pill, { key: 's', tone: meta.tone }, meta.label),
              h(Btn, { key: 'c', size: 'sm', onClick: onClose }, '关闭'),
            ]),
          ]),
          localError ? h(Notice, { key: 'le', kind: 'error' }, localError) : null,
          body,
          h('div', { key: 'f', className: 'kbd-modal-foot' }, [
            written
              ? h(Btn, { key: 'cm', onClick: commit, disabled: committing }, committing ? '推送中…' : '提交并推送 git')
              : null,
            written
              ? h(Btn, { key: 'd', kind: 'primary', onClick: onDone }, '完成')
              : h(Btn, {
                key: 'a',
                kind: 'primary',
                onClick: apply,
                disabled: applying || status !== 'proposal' || !proposal,
              }, applying ? '写入中…' : status === 'proposal' ? '确认写入 vault' : '等模型跑完'),
          ]),
        ]),
      ])
    }

    function inlineRich(text) {
      const parts = []
      const pattern = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g
      let last = 0
      let match
      let key = 0
      while ((match = pattern.exec(text))) {
        if (match.index > last) parts.push(text.slice(last, match.index))
        const token = match[0]
        if (token.startsWith('**')) parts.push(h('b', { key: `b${key++}` }, token.slice(2, -2)))
        else parts.push(h('code', { key: `c${key++}` }, token.slice(1, -1)))
        last = match.index + token.length
      }
      if (last < text.length) parts.push(text.slice(last))
      return parts
    }

    function DiagnosisBody({ text }) {
      const nodes = []
      String(text || '').split('\n').forEach((line, index) => {
        const trimmed = line.trim()
        if (!trimmed) return
        const heading = /^#{2,4}\s+(.*)$/.exec(trimmed)
        if (heading) nodes.push(h('div', { key: index, className: 'kbd-diag-h' }, heading[1]))
        else if (/^[-*]\s+/.test(trimmed)) nodes.push(h('div', { key: index, className: 'kbd-diag-li' }, inlineRich(trimmed.replace(/^[-*]\s+/, ''))))
        else if (/^\d+[.、]\s*/.test(trimmed)) nodes.push(h('div', { key: index, className: 'kbd-diag-li kbd-diag-num' }, inlineRich(trimmed)))
        else nodes.push(h('p', { key: index, className: 'kbd-diag-p' }, inlineRich(trimmed)))
      })
      return h('div', { className: 'kbd-diag-body' }, nodes)
    }

    const SIGNAL_TONE = { error: 'error', warn: 'warn', ok: 'success', info: 'idle' }

    function DiagnoseModal({ job, onClose }) {
      const [context, setContext] = useState(null)
      const [text, setText] = useState('')
      const [phase, setPhase] = useState('collect')
      const [error, setError] = useState(null)
      const [note, setNote] = useState('')
      const [runId, setRunId] = useState(0)
      const [copied, setCopied] = useState(false)
      const alive = useRefLoose(true)

      useEffect(() => {
        alive.current = true
        const controller = new AbortController()
        setContext(null)
        setText('')
        setError(null)
        setPhase('collect')
        setCopied(false)
        streamPost('/ingest/diagnose', { jobId: job.id, job, note }, (event, data) => {
          if (!alive.current) return
          if (event === 'context') {
            setContext(data)
            setPhase('stream')
          } else if (event === 'delta') {
            setText((prev) => prev + (data?.text || ''))
            setPhase('stream')
          } else if (event === 'done') {
            setText(data?.text || '')
            setPhase('done')
          } else if (event === 'error') {
            setError(data?.message || '排查失败')
            setPhase('error')
          }
        }, controller.signal).catch((err) => {
          if (!alive.current || err?.name === 'AbortError') return
          setError(err.message)
          setPhase('error')
        })
        return () => {
          alive.current = false
          controller.abort()
        }
        // 只在换任务或手动重跑时重开；note 通过按钮显式提交，避免打字时反复调模型
      }, [job.id, runId])

      const busy = phase === 'collect' || phase === 'stream'
      const facts = context?.job || job
      const signals = context?.signals || []
      const stages = context?.stages || []

      const copyAll = async () => {
        const lines = [
          `# 排查：${facts.title || facts.url || job.id}`,
          '',
          `- 任务：${job.id}`,
          `- 状态：${facts.status || 'failed'}｜尝试 ${facts.attempts || 0} 次｜worker ${facts.worker || '未知'}`,
          `- 链接：${facts.url || '—'}`,
          `- 错误：${facts.error || '（无）'}`,
          context?.errorClass ? `- 机器归类：${context.errorClass.label}（${context.errorClass.code}）` : '',
          '',
          '## 机器证据',
          ...(signals.length ? signals.map((item) => `- [${item.level}] ${item.title}${item.detail ? ` —— ${item.detail}` : ''}`) : ['- （还没收到证据）']),
          '',
          '## 模型排查',
          text || '（还没出结论）',
        ].filter((line) => line !== '')
        if (await copyText(lines.join('\n'))) {
          setCopied(true)
          setTimeout(() => setCopied(false), 1600)
        }
      }

      return h('div', { className: 'kbd-overlay', onClick: onClose }, [
        h('div', { className: 'kbd-modal kbd-modal-wide', key: 'm', onClick: (event) => event.stopPropagation() }, [
          h('div', { key: 'h', className: 'kbd-modal-head' }, [
            h('div', { key: 't', style: { minWidth: 0 } }, [
              h('div', { key: 'a', className: 'kbd-modal-title' }, '排查失败原因'),
              h('div', { key: 'b', className: 'kbd-small kbd-muted', style: { wordBreak: 'break-all' } }, `${job.id} · ${job.url || '（无链接）'}`),
            ]),
            h('div', { key: 'r', className: 'kbd-triage-meta' }, [
              h(Pill, { key: 's', tone: 'error' }, '失败'),
              h(Btn, { key: 'x', size: 'sm', onClick: onClose }, '关闭'),
            ]),
          ]),

          !context
            ? h('div', { key: 'collect', className: 'kbd-diag-collect' }, [
              h('span', { key: 's', className: 'kbd-spinner' }),
              h('span', { key: 't' }, phase === 'error' ? '证据没收齐' : '正在核对远端记录、本机 vault / git 和源站…'),
            ])
            : h('div', { key: 'ctx', className: 'kbd-diag-context' }, [
              h('div', { key: 'kv', className: 'kbd-kv' }, [
                ['尝试', `${facts.attempts || 0} 次`],
                ['worker', facts.worker || '未领取'],
                ['耗时', duration(facts.elapsedMs)],
                ['归类', context.errorClass?.label || '未归类'],
              ].map(([k, v]) => h('div', { key: k, className: 'kbd-kv-item' }, [h('span', { key: 'k' }, k), h('b', { key: 'v' }, v)]))),

              facts.error ? h('div', { key: 'err', className: 'kbd-error-box' }, [
                h('div', { key: 't', className: 'kbd-error-title' }, '远端错误'),
                h('div', { key: 'm' }, facts.error),
              ]) : null,

              h('div', { key: 'sig', className: 'kbd-diag-signals' }, signals.map((item, index) => h('div', {
                key: index,
                className: `kbd-diag-signal kbd-diag-signal-${item.level}`,
              }, [
                h('span', { key: 'd', className: `kbd-dot kbd-dot-${SIGNAL_TONE[item.level] || 'idle'}` }),
                h('div', { key: 'b' }, [
                  h('div', { key: 't', className: 'kbd-diag-signal-title' }, item.title),
                  item.detail ? h('div', { key: 'd', className: 'kbd-small kbd-muted' }, item.detail) : null,
                ]),
              ]))),

              stages.length ? h('details', { key: 'st', className: 'kbd-diag-stages' }, [
                h('summary', { key: 's', className: 'kbd-small kbd-muted' }, `阶段记录 ${stages.length} 条`),
                h('ol', { key: 'ol', className: 'kbd-timeline' }, stages.map((stage, index) => h('li', { key: index, className: `kbd-stage kbd-stage-${stage.status}` }, [
                  h('span', { key: 'd', className: 'kbd-stage-dot' }),
                  h('div', { key: 'b' }, [
                    h('div', { key: 'n', className: 'kbd-stage-name' }, stage.stage),
                    h('div', { key: 's', className: 'kbd-small kbd-muted' }, `${stage.status}${stage.at ? ` · ${ago(stage.at)}` : ''}${stage.durationSec ? ` · ${duration(stage.durationSec * 1000)}` : ''}`),
                    stage.note ? h('div', { key: 'note', className: 'kbd-stage-note' }, stage.note) : null,
                  ]),
                ]))),
              ]) : null,
            ]),

          h('div', { key: 'model', className: 'kbd-diag-model' }, [
            h('div', { key: 'h', className: 'kbd-diag-model-head' }, [
              h('span', { key: 't' }, '模型排查'),
              h('span', { key: 'm', className: 'kbd-small kbd-muted' }, phase === 'done' ? '结论已出' : busy ? '在读证据…' : ''),
            ]),
            error ? h(Notice, { key: 'e', kind: 'error' }, error) : null,
            text ? h(DiagnosisBody, { key: 'b', text }) : null,
            busy && !text && !error ? h(Spinner, { key: 's', label: context ? '模型在读证据，给原因和处置步骤…' : '先收证据' }) : null,
          ]),

          h('div', { key: 'note', className: 'kbd-diag-note' }, [
            h('textarea', {
              key: 't',
              className: 'kbd-textarea',
              rows: 2,
              value: note,
              placeholder: '有模型看不到的信息就写在这里：比如「刚重启了 mac-mini 上的 worker」「这份 vault 有两台机器在推」',
              onChange: (event) => setNote(event.target.value),
            }),
            h(Btn, { key: 'r', size: 'sm', onClick: () => setRunId((value) => value + 1), disabled: busy }, busy ? '排查中…' : '带上补充重新排查'),
          ]),

          h('div', { key: 'f', className: 'kbd-modal-foot' }, [
            h('span', { key: 'h', className: 'kbd-small kbd-muted' }, copied ? '已复制' : '证据是现场快照，修完后再排查一次看变化'),
            h(Btn, { key: 'c', onClick: copyAll, disabled: !context }, '复制结论'),
            h(Btn, { key: 'd', kind: 'primary', onClick: onClose }, '关闭'),
          ]),
        ]),
      ])
    }

    function DocPreview({ doc, onClose }) {
      return h('div', { className: 'kbd-overlay', onClick: onClose }, [
        h('div', { className: 'kbd-modal', key: 'm', onClick: (event) => event.stopPropagation() }, [
          h('div', { key: 'h', className: 'kbd-modal-head' }, [
            h('div', { key: 't' }, [
              h('div', { key: 'ti', className: 'kbd-modal-title' }, doc.title || doc.path),
              h('div', { key: 'p', className: 'kbd-small kbd-muted' }, doc.path),
            ]),
            h('button', { key: 'x', type: 'button', className: 'kbd-notice-x', onClick: onClose }, '×'),
          ]),
          doc.loading
            ? h(Spinner, { key: 'l' })
            : doc.error
              ? h('div', { key: 'e', className: 'kbd-error-box' }, doc.error)
              : h('pre', { key: 'b', className: 'kbd-pre' }, doc.body || '（空文件）'),
        ]),
      ])
    }

    // ───────────────────────── 健康 ─────────────────────────

    function HealthTab({ boot }) {
      const [result, setResult] = useState(null)
      const [loading, setLoading] = useState(false)
      const [saving, setSaving] = useState(false)
      const [notice, setNotice] = useState(null)
      const alive = useRefLoose(true)

      const scan = useCallback(async () => {
        setLoading(true)
        try {
          const payload = await api('/health')
          if (alive.current) {
            setResult(payload)
            setNotice(null)
          }
        } catch (error) {
          if (alive.current) setNotice(error.message)
        } finally {
          if (alive.current) setLoading(false)
        }
      }, [])

      useEffect(() => {
        alive.current = true
        scan()
        return () => {
          alive.current = false
        }
      }, [scan])

      async function saveReport() {
        setSaving(true)
        try {
          const payload = await api('/health/report', { method: 'POST', body: {} })
          setNotice(`报告已写入 ${payload.report?.path}`)
        } catch (error) {
          setNotice(error.message)
        } finally {
          setSaving(false)
        }
      }

      const grouped = useMemo(() => {
        if (!result) return []
        const map = new Map()
        for (const issue of result.issues) {
          if (!map.has(issue.category)) map.set(issue.category, [])
          map.get(issue.category).push(issue)
        }
        return [...map.entries()].sort((a, b) => {
          const rank = { red: 0, yellow: 1, blue: 2 }
          return rank[a[1][0].level] - rank[b[1][0].level]
        })
      }, [result])

      return h('div', { className: 'kbd-tab' }, [
        notice ? h(Notice, { key: 'n', kind: /报告已写入/.test(notice) ? 'ok' : 'error', onClose: () => setNotice(null) }, notice) : null,
        h('div', { className: 'kbd-cards', key: 'cards' }, [
          h(Card, { key: 'r', title: '🔴 必须处理', value: result?.counts?.red ?? '—', tone: result?.counts?.red ? 'error' : null, hint: '矛盾、孤儿页、卡住摄入的阻塞' }),
          h(Card, { key: 'y', title: '🟡 待处理', value: result?.counts?.yellow ?? '—', tone: result?.counts?.yellow ? 'warn' : null, hint: '待确认、Inbox 积压、过期 thread' }),
          h(Card, { key: 'b', title: '🔵 建议关注', value: result?.counts?.blue ?? '—', hint: '长期未更新的页、日志断更' }),
          h(Card, { key: 'f', title: '扫描文件', value: result?.files ?? '—', hint: result ? ago(result.generatedAt) : '还没扫描' }),
        ]),
        h('div', { key: 'actions', className: 'kbd-actions' }, [
          h(Btn, { key: 'r', kind: 'primary', onClick: scan, disabled: loading }, loading ? '体检中…' : '重新体检'),
          h(Btn, { key: 's', onClick: saveReport, disabled: saving || !result }, saving ? '写入中…' : '写入 health-check 报告'),
          result?.git ? h('span', { key: 'g', className: 'kbd-muted kbd-small' }, result.git.dirty ? `vault 有 ${result.git.dirty} 个未提交文件` : 'vault 工作区干净') : null,
        ]),
        loading && !result
          ? h(Spinner, { key: 'l', label: '扫描 vault' })
          : result?.issues?.length
            ? h('div', { key: 'groups', className: 'kbd-groups' }, grouped.map(([category, items]) => h('section', { key: category, className: 'kbd-group' }, [
              h('div', { key: 'h', className: 'kbd-group-head' }, [
                h('h3', { key: 't' }, CATEGORY_LABEL[category] || category),
                h('span', { key: 'c', className: 'kbd-muted kbd-small' }, `${items.length} 条`),
              ]),
              h('div', { key: 'l', className: 'kbd-group-list' }, items.map((issue, index) => h('div', { key: `${issue.file || 'x'}-${index}`, className: 'kbd-issue' }, [
                h(Pill, { key: 'p', tone: LEVEL_META[issue.level].tone }, LEVEL_META[issue.level].label),
                h('div', { key: 'b', className: 'kbd-issue-body' }, [
                  h('div', { key: 't', className: 'kbd-issue-title' }, issue.title),
                  h('div', { key: 'd', className: 'kbd-small kbd-muted' }, issue.detail),
                  issue.file ? h('code', { key: 'f', className: 'kbd-file' }, `${issue.file}${issue.line ? `:${issue.line}` : ''}`) : null,
                ]),
              ]))),
            ])))
            : result
              ? h(Empty, { key: 'e' }, '这次体检没有发现问题。')
              : null,
      ])
    }

    // ───────────────────────── 学习 ─────────────────────────

    const SEED_KEYS = [
      { id: 'position', label: '① 定位', hint: '它要解决什么问题，其实没解决什么' },
      { id: 'decompose', label: '② 拆解', hint: '结论 / 机制 / 前提，哪层最脆弱' },
      { id: 'connect', label: '③ 连接', hint: '和已知的哪句话对不上' },
      { id: 'output', label: '④ 输出', hint: '下一个动作 + 怎么验证' },
    ]

    const SEED_PROMPT = [
      '先不要展开成段落。只输出一个 JSON 对象，四个键：position、decompose、connect、output；每个值 1–2 句中文，必须是判断句，不是复述。',
      'position = 这篇真正要解决的具体问题，以及它其实没有解决什么；',
      'decompose = 结论、支撑机制、隐含前提三层里哪一层最脆弱；',
      'connect = 和常识或我可能已有的认知具体在哪一句对不上；',
      'output = 读完应该做的下一个动作，以及怎么判断有效。',
      '每条都要指向文中的一句原话（可以短引）。判断不出来就写「没看出来：原因」。只输出 JSON，不要解释，不要多余文字。',
    ].join('\n')

    function readJsonLoose(text) {
      const value = String(text || '')
      const start = value.indexOf('{')
      if (start < 0) return null
      let depth = 0
      for (let i = start; i < value.length; i += 1) {
        if (value[i] === '{') depth += 1
        else if (value[i] === '}') {
          depth -= 1
          if (depth === 0) {
            try {
              return JSON.parse(value.slice(start, i + 1))
            } catch {
              return null
            }
          }
        }
      }
      return null
    }

    const LEARN_ACTIONS = [
      { id: 'structure', label: '拆成三层结构', prompt: '把这篇的核心论点拆成三层：表层结论、支撑机制、隐含前提。每层一句话，并指出哪一层最容易被误读。' },
      { id: 'conflict', label: '和我已知的什么冲突', prompt: '结合我知识库里相关的页，指出这篇和我已有的认知哪里冲突、哪里互补。冲突要具体到哪一句话对不上。' },
      { id: 'use', label: '我能拿它做什么', prompt: '我是一名产品/技术从业者。基于这篇，给我 3 个下周就能动手的动作，每个动作说清「做什么、怎么验证有效」。' },
    ]

    function LearnTab({ boot }) {
      const [urlInput, setUrlInput] = useState('')
      const [article, setArticle] = useState(null)
      const [view, setView] = useState('read')
      const [loading, setLoading] = useState(false)
      const [notice, setNotice] = useState(null)
      const [quote, setQuote] = useState(null)
      const [messages, setMessages] = useState([])
      const [draft, setDraft] = useState('')
      const [busy, setBusy] = useState(false)
      const [streaming, setStreaming] = useState('')
      const [model, setModel] = useState(null)
      const [saving, setSaving] = useState(false)
      const [saveOpen, setSaveOpen] = useState(false)
      const [saveBody, setSaveBody] = useState('')
      const [saveTitle, setSaveTitle] = useState('')
      const [seed, setSeed] = useState(null)
      const [seedBusy, setSeedBusy] = useState(false)
      const [seedError, setSeedError] = useState(null)
      const chatRef = useRefLoose(null)

      useEffect(() => {
        if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight
      }, [messages, streaming])

      async function openUrl(target) {
        const value = String(target || urlInput).trim()
        if (!value) return
        setLoading(true)
        setNotice(null)
        try {
          const payload = await api(`/learn/article?url=${encodeURIComponent(value)}`)
          setArticle(payload)
          setUrlInput(payload.url || value)
          if (payload.thin) setView('web')
          setMessages([])
          setQuote(null)
          setSeed(null)
          setSeedError(null)
          seedDraft(payload)
        } catch (error) {
          setNotice(error.message)
        } finally {
          setLoading(false)
        }
      }

      async function seedDraft(target) {
        if (!target) return
        setSeedBusy(true)
        let buffer = ''
        try {
          await streamChat({ article: target, history: [], message: SEED_PROMPT, useVault: true }, (event, data) => {
            if (event === 'delta') buffer += data.text || ''
            else if (event === 'done') {
              if (data.text) buffer = data.text
              setModel(data.model)
            } else if (event === 'error') {
              setSeedError(data.message)
            }
          })
          const parsed = readJsonLoose(buffer)
          if (parsed) {
            setSeed(SEED_KEYS.map((key) => ({ id: key.id, label: key.label, hint: key.hint, text: String(parsed[key.id] || '').trim() })).filter((item) => item.text))
          } else if (buffer.trim()) {
            setSeedError('初稿没解析成四条，你可以直接问它')
          }
        } catch (error) {
          setSeedError(error.message)
        } finally {
          setSeedBusy(false)
        }
      }

      function expandSeed(item) {
        send(`就「${item.label}」这一条展开：结论 / 支撑机制 / 隐含前提三层各一句，指出哪一层最脆弱，并引一句原文作为依据。`)
      }

      async function send(text) {
        const message = String(text ?? draft).trim()
        if (!message || !article || busy) return
        const withQuote = quote ? `（引用这一段：${quote}\n）\n\n${message}` : message
        const history = messages.map(({ role, content }) => ({ role, content }))
        setMessages((prev) => [...prev, { role: 'user', content: message }])
        setDraft('')
        setQuote(null)
        setBusy(true)
        setStreaming('')
        let buffer = ''
        try {
          await streamChat({ article, history, message: withQuote, useVault: true }, (event, data) => {
            if (event === 'delta') {
              buffer += data.text || ''
              setStreaming(buffer)
            } else if (event === 'done') {
              setModel(data.model)
              setMessages((prev) => [...prev, { role: 'assistant', content: data.text || buffer }])
            } else if (event === 'error') {
              setNotice(data.message)
              setMessages((prev) => [...prev, { role: 'assistant', content: `（模型调用失败：${data.message}）` }])
            }
          })
        } catch (error) {
          setNotice(error.message)
        } finally {
          setStreaming('')
          setBusy(false)
        }
      }

      function openSave() {
        const transcript = messages
          .map((message) => `${message.role === 'user' ? '**我：**' : '**教练：**'} ${message.content}`)
          .join('\n\n')
        setSaveTitle(article?.title || '学习笔记')
        setSaveBody([
          `> 来源：[${article?.title || article?.url}](${article?.url})${article?.site ? `（${article.site}）` : ''}`,
          '',
          '## 我的结论',
          '',
          '<!-- 一句话写清这篇改变了你什么 -->',
          '',
          '## 对话存档',
          '',
          transcript || '（还没有对话）',
        ].join('\n'))
        setSaveOpen(true)
      }

      async function save() {
        setSaving(true)
        try {
          const payload = await api('/learn/save', {
            method: 'POST',
            body: { title: saveTitle, url: article?.url, body: saveBody, author: article?.author, publishedAt: article?.publishedAt },
          })
          setSaveOpen(false)
          setNotice(`已写入 Inbox：${payload.path}，等 triage 进 raw/wiki`)
        } catch (error) {
          setNotice(error.message)
        } finally {
          setSaving(false)
        }
      }

      const paragraphs = article?.paragraphs || []

      return h('div', { className: 'kbd-tab kbd-learn' }, [
        notice ? h(Notice, { key: 'n', kind: /已写入 Inbox/.test(notice) ? 'ok' : 'error', onClose: () => setNotice(null) }, notice) : null,
        h('div', { key: 'bar', className: 'kbd-learn-bar' }, [
          h('input', {
            key: 'i',
            className: 'kbd-input',
            value: urlInput,
            placeholder: '粘贴要学的链接（公众号 / 博客 / 文档都行）',
            onChange: (event) => setUrlInput(event.target.value),
            onKeyDown: (event) => {
              if (event.key === 'Enter') openUrl()
            },
          }),
          h(Btn, { key: 'b', kind: 'primary', onClick: () => openUrl(), disabled: loading || !urlInput.trim() }, loading ? '抓取中…' : '开始学习'),
          article ? h(Btn, { key: 's', onClick: openSave }, '沉淀进知识库') : null,
        ]),

        article
          ? h('div', { key: 'body', className: 'kbd-learn-body' }, [
            h('section', { key: 'left', className: 'kbd-reader' }, [
              h('div', { key: 'h', className: 'kbd-reader-head' }, [
                h('div', { key: 't' }, [
                  h('div', { key: 'ti', className: 'kbd-reader-title' }, article.title),
                  h('div', { key: 'm', className: 'kbd-small kbd-muted' }, [
                    article.site,
                    article.author ? ` · ${article.author}` : '',
                    article.publishedAt ? ` · ${article.publishedAt}` : '',
                    ` · ${paragraphs.length} 段`,
                  ].join('')),
                ]),
                h('div', { key: 'v', className: 'kbd-pills' }, [
                  h(Pill, { key: 'r', active: view === 'read', onClick: () => setView('read') }, '阅读视图'),
                  h(Pill, { key: 'w', active: view === 'web', onClick: () => setView('web') }, '原文'),
                  h(Btn, { key: 'o', size: 'sm', onClick: () => window.open(article.url, '_blank', 'noreferrer') }, '新窗口打开'),
                ]),
              ]),
              article.thin ? h('div', { key: 'thin', className: 'kbd-notice kbd-notice-warn' }, '正文没抽到多少内容，可能是登录墙或 JS 渲染页；切到「原文」看。') : null,
              view === 'read'
                ? h('div', { key: 'r', className: 'kbd-read-scroll' }, paragraphs.map((line, index) =>
                  h('p', {
                    key: index,
                    className: `kbd-para${quote && quote === line ? ' is-quoted' : ''}`,
                    onClick: () => setQuote(quote === line ? null : line),
                    title: '点一下把这一段带进对话',
                  }, line)))
                : h('iframe', { key: 'w', className: 'kbd-frame', src: article.url, title: article.title, referrerPolicy: 'no-referrer' }),
            ]),

            h('section', { key: 'right', className: 'kbd-chat' }, [
              h('div', { key: 'h', className: 'kbd-chat-head' }, [
                h('span', { key: 't' }, '学习对话'),
                h('span', { key: 'm', className: 'kbd-small kbd-muted' }, model ? `模型 ${model}` : (boot?.model?.label ? `模型 ${boot.model.label}` : '跟随默认模型')),
              ]),
              seed || seedBusy ? h('div', { key: 'seed', className: 'kbd-seed' }, [
                h('div', { key: 'h', className: 'kbd-seed-head' }, [
                  h('span', { key: 't' }, seedBusy ? '四问初稿 · 在读…' : '四问初稿'),
                  seedBusy
                    ? null
                    : h('button', { key: 'r', type: 'button', className: 'kbd-link', onClick: () => seedDraft(article) }, '重出一版'),
                ]),
                seed && seed.length
                  ? h('div', { key: 'c', className: 'kbd-seed-list' }, seed.map((item) => h('div', { key: item.id, className: 'kbd-seed-card' }, [
                    h('div', { key: 't', className: 'kbd-seed-title' }, [
                      h('span', { key: 'l' }, item.label),
                      h('span', { key: 'h2', className: 'kbd-small kbd-muted' }, item.hint),
                    ]),
                    h('div', { key: 'x', className: 'kbd-seed-text' }, item.text),
                    h('div', { key: 'a', className: 'kbd-seed-actions' }, [
                      h('button', { key: 'e', type: 'button', className: 'kbd-link', onClick: () => expandSeed(item), disabled: busy }, '展开这条 →'),
                      h('button', { key: 'd', type: 'button', className: 'kbd-link kbd-link-muted', onClick: () => setSeed((prev) => (prev || []).filter((x) => x.id !== item.id)) }, '划掉'),
                    ]),
                  ])))
                  : null,
                seedError ? h('div', { key: 'e', className: 'kbd-small kbd-muted' }, seedError) : null,
              ]) : null,
              h('div', { key: 'list', className: 'kbd-chat-list', ref: chatRef },
                messages.length
                  ? [
                    ...messages.map((message, index) => h('div', { key: index, className: `kbd-msg kbd-msg-${message.role}` }, [
                      h('div', { key: 'r', className: 'kbd-msg-role' }, message.role === 'user' ? '我' : '教练'),
                      h('div', { key: 'c', className: 'kbd-msg-content' }, message.content),
                    ])),
                    streaming ? h('div', { key: 's', className: 'kbd-msg kbd-msg-assistant' }, [
                      h('div', { key: 'r', className: 'kbd-msg-role' }, '教练'),
                      h('div', { key: 'c', className: 'kbd-msg-content' }, streaming),
                    ]) : null,
                    busy && !streaming ? h('div', { key: 'b', className: 'kbd-loading' }, '想想…') : null,
                  ]
                  : h(Empty, { key: 'e' }, seed && seed.length ? '上面是初稿，点「展开这条」深挖，或直接问。' : seedBusy ? '正在读这篇，先出一版四问。' : '先自己写一句：这篇最想解决的问题是什么？'),
              ),
              quote ? h('div', { key: 'q', className: 'kbd-quote' }, [
                h('span', { key: 't' }, `引用：${quote.slice(0, 80)}${quote.length > 80 ? '…' : ''}`),
                h('button', { key: 'x', type: 'button', className: 'kbd-notice-x', onClick: () => setQuote(null) }, '×'),
              ]) : null,
              h('div', { key: 'actions', className: 'kbd-chat-actions' }, LEARN_ACTIONS.map((action) =>
                h(Pill, { key: action.id, tone: 'brand', onClick: () => send(action.prompt) }, action.label))),
              h('div', { key: 'in', className: 'kbd-chat-input' }, [
                h('textarea', {
                  key: 't',
                  className: 'kbd-textarea',
                  value: draft,
                  rows: 2,
                  placeholder: '问它：这段的隐含前提是什么？我该反驳哪一句？',
                  onChange: (event) => setDraft(event.target.value),
                  onKeyDown: (event) => {
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) send()
                  },
                }),
                h(Btn, { key: 'b', kind: 'primary', onClick: () => send(), disabled: busy || !draft.trim() }, busy ? '生成中…' : '发送'),
              ]),
            ]),
          ])
          : h('div', { key: 'empty', className: 'kbd-learn-empty' }, [
            h(Empty, { key: 'e' }, '左边缺的不是一个输入框，是四件事：定位、拆解、连接、输出。'),
            h('div', { key: 'steps', className: 'kbd-steps' }, [
              ['① 定位', '为什么读它：它回答你什么问题，还是只是看起来相关？'],
              ['② 拆解', '它说了什么：结论 / 机制 / 前提，哪一层最脆弱？'],
              ['③ 连接', '它和你已知的什么冲突：具体到哪句话对不上。'],
              ['④ 输出', '你能拿它做什么：下一个动作 + 怎么验证有效。'],
            ].map(([title, desc]) => h('div', { key: title, className: 'kbd-step' }, [
              h('div', { key: 't', className: 'kbd-step-title' }, title),
              h('div', { key: 'd', className: 'kbd-small kbd-muted' }, desc),
            ]))),
          ]),

        saveOpen ? h('div', { key: 'save', className: 'kbd-overlay', onClick: () => setSaveOpen(false) }, [
          h('div', { key: 'm', className: 'kbd-modal', onClick: (event) => event.stopPropagation() }, [
            h('div', { key: 'h', className: 'kbd-modal-head' }, [
              h('div', { key: 'ti', className: 'kbd-modal-title' }, '沉淀成 Inbox 笔记'),
              h('button', { key: 'x', type: 'button', className: 'kbd-notice-x', onClick: () => setSaveOpen(false) }, '×'),
            ]),
            h('input', { key: 't', className: 'kbd-input', value: saveTitle, onChange: (event) => setSaveTitle(event.target.value), placeholder: '标题' }),
            h('textarea', { key: 'b', className: 'kbd-textarea kbd-textarea-lg', rows: 14, value: saveBody, onChange: (event) => setSaveBody(event.target.value) }),
            h('div', { key: 'a', className: 'kbd-actions' }, [
              h(Btn, { key: 's', kind: 'primary', onClick: save, disabled: saving }, saving ? '写入中…' : '写进 00 Inbox'),
              h('span', { key: 'h', className: 'kbd-muted kbd-small' }, '写入后走正常的 triage 流程，不绕过 vault 规范。'),
            ]),
          ]),
        ]) : null,
      ])
    }

    // ───────────────────────── 创作 ─────────────────────────

    // 创作素材只要沉淀物：原文、摘要、概念页。索引/日志/周报是元信息，拿来选题只会写出对策。
    const MATERIAL_DIR = /^(00 raw\/|01 wiki\/[^/]+\/(concepts|entities|summaries)\/)/
    const MATERIAL_SKIP = /(^|\/)(_?index|log|README)\.md$|\/(weekly|daily|monthly)\//i
    function isMaterial(path) {
      return MATERIAL_DIR.test(path) && !MATERIAL_SKIP.test(path)
    }

    function CreateTab({ boot }) {
      const [days, setDays] = useState(30)
      const [docs, setDocs] = useState([])
      const [picked, setPicked] = useState({})
      const [topics, setTopics] = useState([])
      const [loading, setLoading] = useState(false)
      const [busy, setBusy] = useState(false)
      const [notice, setNotice] = useState(null)
      const [model, setModel] = useState(null)
      const alive = useRefLoose(true)

      const load = useCallback(async (nextDays = days) => {
        setLoading(true)
        try {
          const payload = await api(`/create/recent?days=${nextDays}&limit=120`)
          let next = (payload.docs || []).filter((doc) => isMaterial(doc.path))
          if (!next.length) {
            // 窗口内只剩索引/周报这类元信息时，退回全库按时间取一页再筛
            const wider = await api('/vault/recent?days=365&limit=100').catch(() => null)
            next = (wider?.docs || []).filter((doc) => isMaterial(doc.path))
          }
          if (alive.current) setDocs(next)
        } catch (error) {
          if (alive.current) setNotice(error.message)
        } finally {
          if (alive.current) setLoading(false)
        }
      }, [days])

      useEffect(() => {
        alive.current = true
        load(days)
        return () => {
          alive.current = false
        }
      }, [load, days])

      async function generate() {
        setBusy(true)
        setNotice(null)
        try {
          const paths = Object.keys(picked).filter((path) => picked[path])
          const payload = await api('/create/topics', { method: 'POST', body: { days, paths } })
          setTopics(payload.topics || [])
          setModel(payload.model)
        } catch (error) {
          setNotice(error.message)
        } finally {
          setBusy(false)
        }
      }

      function topicMarkdown(topic) {
        return [
          `# ${topic.title}`,
          '',
          `平台：${topic.platform}`,
          `钩子：${topic.hook}`,
          `为什么现在写：${topic.angle}`,
          '',
          '## 提纲',
          ...topic.outline.map((line, index) => `${index + 1}. ${line}`),
          '',
          '## 素材',
          ...topic.sources.map((line) => `- ${line}`),
        ].join('\n')
      }

      async function saveDraft(topic) {
        try {
          const payload = await api('/create/draft', { method: 'POST', body: { title: topic.title, platform: topic.platform, body: topicMarkdown(topic) } })
          setNotice(`草稿已写入 ${payload.path}`)
        } catch (error) {
          setNotice(error.message)
        }
      }

      async function copyTopic(topic) {
        const ok = await copyText(topicMarkdown(topic))
        setNotice(ok ? '提纲已复制' : '复制失败，手动选一下')
      }

      const pickedCount = Object.values(picked).filter(Boolean).length

      return h('div', { className: 'kbd-tab kbd-create' }, [
        notice ? h(Notice, { key: 'n', kind: /已写入|已复制/.test(notice) ? 'ok' : 'error', onClose: () => setNotice(null) }, notice) : null,
        h('div', { key: 'bar', className: 'kbd-create-bar' }, [
          h('span', { key: 'l', className: 'kbd-muted kbd-small' }, '素材窗口'),
          h('div', { key: 'd', className: 'kbd-pills' }, [7, 30, 90].map((value) =>
            h(Pill, { key: value, active: days === value, onClick: () => setDays(value) }, `${value} 天`))),
          h(Btn, { key: 'g', kind: 'primary', onClick: generate, disabled: busy }, busy ? '等模型…' : '生成选题'),
          h('span', { key: 'm', className: 'kbd-muted kbd-small' }, pickedCount ? `只用了选中的 ${pickedCount} 篇` : '不选就用全部素材'),
          model ? h('span', { key: 'mm', className: 'kbd-muted kbd-small' }, `模型 ${model}`) : null,
        ]),
        h('div', { key: 'split', className: 'kbd-split kbd-split-wide' }, [
          h('section', { key: 'left', className: 'kbd-pane' }, [
            h('div', { key: 'h', className: 'kbd-pane-head' }, [
              h('h3', { key: 't' }, '最近的内容'),
              h('span', { key: 'c', className: 'kbd-muted kbd-small' }, `${docs.length} 篇`),
            ]),
            loading
              ? h(Spinner, { key: 'l' })
              : h('div', { key: 'l', className: 'kbd-pick-list' }, docs.length
                ? docs.map((doc) => h('label', { key: doc.path, className: `kbd-pick${picked[doc.path] ? ' is-active' : ''}` }, [
                  h('input', {
                    key: 'i',
                    type: 'checkbox',
                    checked: Boolean(picked[doc.path]),
                    onChange: (event) => setPicked((prev) => ({ ...prev, [doc.path]: event.target.checked })),
                  }),
                  h('div', { key: 'b' }, [
                    h('div', { key: 't', className: 'kbd-row-title' }, doc.title),
                    h('div', { key: 'm', className: 'kbd-small kbd-muted' }, `${doc.space || doc.type || '未分类'} · ${ago(doc.updatedAt)}`),
                    h('div', { key: 'e', className: 'kbd-pick-excerpt' }, doc.excerpt),
                  ]),
                ]))
                : h(Empty, { key: 'e' }, '这个窗口里没有新内容，换 90 天看看。')),
          ]),
          h('section', { key: 'right', className: 'kbd-pane' }, [
            h('div', { key: 'h', className: 'kbd-pane-head' }, [
              h('h3', { key: 't' }, '选题'),
              h('span', { key: 'c', className: 'kbd-muted kbd-small' }, topics.length ? `${topics.length} 条` : '还没生成'),
            ]),
            topics.length
              ? h('div', { key: 'l', className: 'kbd-topics' }, topics.map((topic, index) => h('article', { key: index, className: 'kbd-topic' }, [
                h('div', { key: 'h', className: 'kbd-topic-head' }, [
                  h(Pill, { key: 'p', tone: topic.platform === '小红书' ? 'brand' : 'success' }, topic.platform),
                  h('h4', { key: 't', className: 'kbd-topic-title' }, topic.title),
                ]),
                topic.hook ? h('p', { key: 'k', className: 'kbd-topic-hook' }, topic.hook) : null,
                topic.angle ? h('p', { key: 'a', className: 'kbd-small kbd-muted' }, topic.angle) : null,
                h('ol', { key: 'o', className: 'kbd-topic-outline' }, topic.outline.map((line, i) => h('li', { key: i }, line))),
                topic.sources.length ? h('div', { key: 's', className: 'kbd-topic-sources' }, topic.sources.map((line, i) => h('span', { key: i, className: 'kbd-source' }, line))) : null,
                h('div', { key: 'act', className: 'kbd-topic-actions' }, [
                  h(Btn, { key: 'c', size: 'sm', onClick: () => copyTopic(topic) }, '复制提纲'),
                  h(Btn, { key: 'd', size: 'sm', onClick: () => saveDraft(topic) }, '存为草稿'),
                ]),
              ])))
              : h(Empty, { key: 'e' }, '点「生成选题」：先从素材里找张力，再决定写什么。'),
          ]),
        ]),
      ])
    }

    // ───────────────────────── 外壳 ─────────────────────────

    function shortPath(path) {
      if (!path) return ''
      return String(path).replace(/^\/Users\/[^/]+/, '~').replace(/^\/home\/[^/]+/, '~')
    }

    function Panel() {
      const [tab, setTab] = useState('ingest')
      const [boot, setBoot] = useState(null)
      const [error, setError] = useState(null)
      const [pulling, setPulling] = useState(false)
      const [pullNote, setPullNote] = useState(null)

      const refreshBoot = useCallback(async () => {
        try {
          const payload = await api('/bootstrap')
          setBoot(payload)
          setError(null)
        } catch (err) {
          setError(err.message)
        }
      }, [])

      const pull = useCallback(async () => {
        setPulling(true)
        setPullNote(null)
        try {
          const result = await api('/vault/pull', { method: 'POST' })
          setPullNote(result.message || (result.ok ? '已拉取' : '拉取失败'))
          await refreshBoot()
        } catch (err) {
          setPullNote(err.message)
        } finally {
          setPulling(false)
        }
      }, [refreshBoot])

      useEffect(() => {
        refreshBoot()
        const timer = setInterval(refreshBoot, 60_000)
        return () => clearInterval(timer)
      }, [refreshBoot])

      return h('div', { className: 'kbd' }, [
        h('style', { key: 'css' }, CSS),
        h('header', { key: 'top', className: 'kbd-top' }, [
          h('div', { key: 'brand', className: 'kbd-brand' }, [
            h('span', { key: 't', className: 'kbd-brand-title' }, '个人知识库'),
            h('span', { key: 's', className: 'kbd-brand-sub', title: boot?.vault?.path || '' }, shortPath(boot?.vault?.path) || '读取中…'),
          ]),
          h('nav', { key: 'tabs', className: 'kbd-tabs' }, TABS.map((item) =>
            h('button', {
              key: item.id,
              type: 'button',
              className: `kbd-tab-btn${tab === item.id ? ' is-active' : ''}`,
              onClick: () => setTab(item.id),
            }, item.label))),
          h('div', { key: 'right', className: 'kbd-top-right' }, [
            boot?.vault?.git?.behind > 0
              ? h(Pill, { key: 'g', tone: 'warn', onClick: pulling ? undefined : pull }, pulling ? '拉取中…' : `落后 origin ${boot.vault.git.behind}`)
              : null,
            boot && !boot.ingest?.ok ? h(Pill, { key: 'i', tone: 'warn' }, '摄入服务离线') : null,
            boot?.vault && !boot.vault.exists ? h(Pill, { key: 'v', tone: 'error' }, 'vault 路径不存在') : null,
            h(Btn, { key: 'r', size: 'sm', onClick: refreshBoot }, '刷新'),
          ]),
        ]),
        error ? h(Notice, { key: 'e', kind: 'error' }, error) : null,
        pullNote ? h(Notice, { key: 'p', kind: /失败|有 \d+ 个未提交/.test(pullNote) ? 'error' : 'ok', onClose: () => setPullNote(null) }, pullNote) : null,
        h('main', { key: 'main', className: 'kbd-main' }, [
          tab === 'ingest' ? h(IngestTab, { key: 'ingest', boot, refreshBoot }) : null,
          tab === 'health' ? h(HealthTab, { key: 'health', boot }) : null,
          tab === 'learn' ? h(LearnTab, { key: 'learn', boot }) : null,
          tab === 'create' ? h(CreateTab, { key: 'create', boot }) : null,
        ]),
        h('div', { key: 'build', className: 'kbd-build' }, BUILD),
      ])
    }

    function Icon() {
      return h('svg', { viewBox: '0 0 64 64', width: 20, height: 20, 'aria-hidden': true, style: { display: 'block' } }, [
        h('rect', { key: 'bg', x: 2, y: 2, width: 60, height: 60, rx: 15, fill: '#1f6f5c' }),
        h('path', { key: 'l', d: 'M18 17h12a6 6 0 0 1 6 6v25a5 5 0 0 0-5-5H18z', fill: '#f4fff9' }),
        h('path', { key: 'r', d: 'M46 17H34a6 6 0 0 0-6 6v25a5 5 0 0 1 5-5h13z', fill: '#c7f2e0' }),
        h('circle', { key: 'c', cx: 45, cy: 21, r: 7, fill: '#ffcf5c' }),
      ])
    }

    const CSS = `
.kbd{position:relative;flex:1 1 auto;width:100%;height:100%;min-width:0;min-height:0;display:flex;flex-direction:column;background:var(--dsw-alias-bg-base);color:var(--dsw-alias-label-primary);font-size:13px;overflow:hidden}
.kbd *{box-sizing:border-box}
.kbd-top{display:flex;align-items:center;gap:14px;padding:9px 16px;border-bottom:1px solid var(--dsw-alias-border-l1);background:var(--dsw-alias-bg-base);flex:0 0 auto}
.kbd-brand{display:flex;align-items:baseline;gap:8px;min-width:0}
.kbd-brand-title{font-size:13px;font-weight:640;letter-spacing:.01em;white-space:nowrap}
.kbd-brand-sub{font-size:11px;color:var(--dsw-alias-label-secondary);max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.72}
.kbd-tabs{display:flex;gap:1px;padding:2px;border-radius:9px;background:var(--dsw-specific-sidebar-fill);background:color-mix(in srgb, var(--dsw-alias-label-primary) 6%, transparent);flex:0 0 auto}
.kbd-tab-btn{border:0;background:transparent;color:var(--dsw-alias-label-secondary);min-width:58px;padding:4px 6px;border-radius:7px;cursor:pointer;font-size:12.5px;line-height:20px;font-weight:500;text-align:center;transition:background .16s ease,color .16s ease,box-shadow .16s ease}
.kbd-tab-btn:hover{color:var(--dsw-alias-label-primary)}
.kbd-tab-btn.is-active{background:var(--dsw-alias-bg-base);color:var(--dsw-alias-label-primary);font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.09)}
.kbd-top-right{display:flex;align-items:center;gap:8px;margin-left:auto}
.kbd-main{flex:1;min-height:0;overflow:hidden;display:flex}
.kbd-tab{flex:1;min-height:0;overflow:auto;padding:16px 18px 28px;display:flex;flex-direction:column;gap:14px}
.kbd-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:10px}
.kbd-card{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);border-radius:12px;padding:11px 13px;display:flex;flex-direction:column;gap:5px}
.kbd-card-warn{border-color:var(--dsw-alias-state-warn-primary)}
.kbd-card-error{border-color:var(--dsw-alias-state-error-primary)}
.kbd-card-label{font-size:11.5px;color:var(--dsw-alias-label-secondary)}
.kbd-card-value{font-size:22px;font-weight:680;line-height:1.1;font-variant-numeric:tabular-nums}
.kbd-card-hint{font-size:11px;color:var(--dsw-alias-label-secondary);opacity:.85}
.kbd-btn{border:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);border-radius:8px;padding:6px 12px;font-size:12.5px;cursor:pointer;white-space:nowrap;font-weight:520}
.kbd-btn:hover:not(:disabled){border-color:var(--dsw-alias-brand-primary);color:var(--dsw-alias-brand-primary)}
.kbd-btn:disabled{opacity:.45;cursor:not-allowed}
.kbd-btn-primary{background:var(--dsw-alias-brand-primary);border-color:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base)}
.kbd-btn-primary:hover:not(:disabled){color:var(--dsw-alias-bg-base);filter:brightness(1.08)}
.kbd-btn-sm{padding:3px 9px;font-size:11.5px}
.kbd-pill{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:2px 9px;font-size:11.5px;border:1px solid var(--dsw-alias-border-l1);background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-secondary);white-space:nowrap}
button.kbd-pill{cursor:pointer}
button.kbd-pill:hover{border-color:var(--dsw-alias-border-l2);color:var(--dsw-alias-label-primary)}
.kbd-pill.is-active{border-color:var(--dsw-alias-brand-primary);color:var(--dsw-alias-brand-primary);background:transparent}
.kbd-pill-brand{color:var(--dsw-alias-brand-primary);border-color:var(--dsw-alias-brand-primary)}
.kbd-pill-success{color:color-mix(in srgb,var(--dsw-alias-state-success-primary) 55%,var(--dsw-alias-label-primary));border-color:var(--dsw-alias-state-success-primary)}
.kbd-pill-warn{color:color-mix(in srgb,var(--dsw-alias-state-warn-primary) 55%,var(--dsw-alias-label-primary));border-color:var(--dsw-alias-state-warn-primary)}
.kbd-pill-error{color:color-mix(in srgb,var(--dsw-alias-state-error-primary) 55%,var(--dsw-alias-label-primary));border-color:var(--dsw-alias-state-error-primary)}
.kbd-input,.kbd-textarea{width:100%;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);padding:7px 10px;font-size:12.5px;font-family:inherit;outline:none}
.kbd-input:focus,.kbd-textarea:focus{border-color:var(--dsw-alias-brand-primary)}
.kbd-textarea{resize:vertical;line-height:1.55}
.kbd-textarea-lg{min-height:220px}
.kbd-submit{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.kbd-submit .kbd-input{flex:1;min-width:280px;width:auto}
.kbd-split{display:grid;grid-template-columns:minmax(300px,0.85fr) minmax(360px,1.15fr);gap:14px;min-height:320px}
.kbd-split-wide{grid-template-columns:minmax(280px,0.7fr) minmax(420px,1.3fr)}
.kbd-pane{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);border-radius:12px;display:flex;flex-direction:column;min-height:0;overflow:hidden}
.kbd-pane-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 12px;border-bottom:1px solid var(--dsw-alias-border-l1)}
.kbd-pane-head h3{margin:0;font-size:12.5px;font-weight:640}
.kbd-pills{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.kbd-list{overflow:auto;flex:1;padding:6px}
.kbd-row{display:flex;align-items:center;gap:9px;width:100%;text-align:left;border:0;background:transparent;color:inherit;padding:8px 9px;border-radius:8px;cursor:pointer}
.kbd-row:hover{background:var(--dsw-alias-bg-layer-2)}
.kbd-row.is-active{background:var(--dsw-alias-bg-layer-2);box-shadow:inset 2px 0 0 var(--dsw-alias-brand-primary)}
.kbd-row-main{display:flex;flex-direction:column;gap:3px;min-width:0;flex:1}
.kbd-row-title{font-size:12.5px;font-weight:550;line-height:1.4;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.kbd-row-sub{font-size:11px;color:var(--dsw-alias-label-secondary)}
.kbd-dot{width:7px;height:7px;border-radius:50%;background:var(--dsw-alias-state-idle-primary);flex:0 0 auto;display:inline-block}
.kbd-dot-success{background:var(--dsw-alias-state-success-primary)}
.kbd-dot-warn{background:var(--dsw-alias-state-warn-primary)}
.kbd-dot-error{background:var(--dsw-alias-state-error-primary)}
.kbd-detail{padding:14px;display:flex;flex-direction:column;gap:10px;overflow:auto}
.kbd-detail-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.kbd-detail-title{margin:0;font-size:14.5px;font-weight:640;line-height:1.45}
.kbd-link{color:var(--dsw-alias-brand-primary);text-decoration:none;font-size:11.5px;word-break:break-all;background:none;border:0;padding:0;cursor:pointer;text-align:left;font-family:inherit}
.kbd-link:hover{text-decoration:underline}
.kbd-kv{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.kbd-kv-item{display:flex;flex-direction:column;gap:2px;font-size:11px;color:var(--dsw-alias-label-secondary)}
.kbd-kv-item b{font-size:12px;color:var(--dsw-alias-label-primary);font-weight:560}
.kbd-error-box{border:1px solid var(--dsw-alias-state-error-primary);border-radius:8px;padding:9px 11px;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-primary);background:color-mix(in srgb,var(--dsw-alias-state-error-primary) 8%,transparent)}
.kbd-error-title{font-weight:600;color:color-mix(in srgb,var(--dsw-alias-state-error-primary) 55%,var(--dsw-alias-label-primary));margin-bottom:3px;font-size:11.5px}
.kbd-section{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);border-radius:12px;padding:12px}
.kbd-section-head{display:flex;align-items:baseline;gap:10px;margin-bottom:9px}
.kbd-section-head h3{margin:0;font-size:12.5px;font-weight:640}
.kbd-section-title{font-size:12px;font-weight:640;margin-bottom:8px;color:var(--dsw-alias-label-secondary)}
.kbd-inbox{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px}
.kbd-inbox-item{display:flex;flex-direction:column;border:1px solid var(--dsw-alias-border-l1);background:var(--dsw-alias-bg-layer-2);border-radius:9px;overflow:hidden}
.kbd-inbox-open{text-align:left;border:0;background:transparent;padding:9px 10px 6px;display:flex;flex-direction:column;gap:4px;cursor:pointer;color:inherit;font:inherit}
.kbd-inbox-item:hover{border-color:var(--dsw-alias-brand-primary)}
.kbd-inbox-actions{display:flex;justify-content:flex-end;gap:6px;padding:0 8px 8px}
.kbd-auto{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:8px 10px;border:1px dashed var(--dsw-alias-border-l1);border-radius:9px}
.kbd-auto .kbd-pill.is-active{background:var(--dsw-alias-brand-primary);border-color:var(--dsw-alias-brand-primary);color:var(--dsw-alias-bg-base)}
.kbd-triage-body{display:flex;flex-direction:column;gap:12px;padding:2px 0 4px}
.kbd-triage-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.kbd-triage-reason{margin:0;font-size:12.5px;line-height:1.6;color:var(--dsw-alias-label-secondary)}
.kbd-triage-tldr{margin:0;font-size:13px;line-height:1.65}
.kbd-triage-list{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:3px;font-size:12.5px;line-height:1.6}
.kbd-triage-judgement{margin:0;font-size:12.5px;line-height:1.65;padding:8px 10px;border-left:2px solid var(--dsw-alias-brand-primary);background:var(--dsw-alias-bg-layer-2);border-radius:0 6px 6px 0}
.kbd-triage-oq{display:flex;flex-direction:column;gap:2px}
.kbd-triage-concepts{display:flex;flex-direction:column;gap:8px}
.kbd-triage-concept{border:1px solid var(--dsw-alias-border-l1);border-radius:8px;padding:8px 10px;display:flex;flex-direction:column;gap:3px;background:var(--dsw-alias-bg-layer-1)}
.kbd-triage-text{margin:0;font-size:12.5px;line-height:1.6;color:var(--dsw-alias-label-primary)}
.kbd-triage-changes{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:4px;font-size:12px}
.kbd-triage-busy{display:flex;align-items:center;gap:10px;padding:18px 2px}
.kbd-modal-wide{width:min(760px,92vw)}
.kbd-fail{display:flex;align-items:flex-start;gap:10px}
.kbd-fail .kbd-error-box{flex:1;min-width:0}
.kbd-diag-collect{display:flex;align-items:center;gap:10px;padding:18px 2px;font-size:12.5px;color:var(--dsw-alias-label-secondary)}
.kbd-diag-context{display:flex;flex-direction:column;gap:10px;padding:2px 0}
.kbd-diag-signals{display:flex;flex-direction:column;gap:6px}
.kbd-diag-signal{display:flex;gap:8px;padding:6px 9px;border-left:2px solid var(--dsw-alias-border-l2);border-radius:0 6px 6px 0;background:var(--dsw-alias-bg-layer-2)}
.kbd-diag-signal .kbd-dot{margin-top:6px}
.kbd-diag-signal-error{border-left-color:var(--dsw-alias-state-error-primary)}
.kbd-diag-signal-warn{border-left-color:var(--dsw-alias-state-warn-primary)}
.kbd-diag-signal-ok{border-left-color:var(--dsw-alias-state-success-primary)}
.kbd-diag-signal-title{font-size:12.5px;line-height:1.5;font-weight:520}
.kbd-diag-stages>summary{cursor:pointer;padding:2px 0;user-select:none}
.kbd-diag-stages .kbd-timeline{margin-top:8px}
.kbd-diag-model{display:flex;flex-direction:column;gap:8px;border-top:1px solid var(--dsw-alias-border-l1);padding-top:12px}
.kbd-diag-model-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;font-size:12.5px;font-weight:600}
.kbd-diag-body{display:flex;flex-direction:column;gap:5px;font-size:12.5px;line-height:1.65}
.kbd-diag-body code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;background:var(--dsw-alias-bg-layer-2);border-radius:4px;padding:0 4px}
.kbd-diag-h{font-weight:600;color:var(--dsw-alias-label-primary)}
.kbd-diag-h:not(:first-child){margin-top:7px}
.kbd-diag-p{margin:0}
.kbd-diag-li{padding-left:14px;position:relative}
.kbd-diag-li::before{content:'·';position:absolute;left:3px;color:var(--dsw-alias-label-secondary)}
.kbd-diag-num{padding-left:0}
.kbd-diag-num::before{content:none}
.kbd-diag-note{display:flex;flex-direction:column;gap:6px;align-items:flex-start;border-top:1px solid var(--dsw-alias-border-l1);padding-top:10px;margin-top:2px}
.kbd-diag-note .kbd-textarea{width:100%}
.kbd-inbox-excerpt{font-size:11px;line-height:1.5;color:var(--dsw-alias-label-secondary);overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.kbd-stages{margin-top:4px}
.kbd-timeline{list-style:none;margin:0;padding:0 0 0 4px;display:flex;flex-direction:column;gap:10px}
.kbd-stage{display:flex;gap:9px;position:relative;padding-left:14px}
.kbd-stage::before{content:'';position:absolute;left:3px;top:12px;bottom:-12px;width:1px;background:var(--dsw-alias-border-l1)}
.kbd-stage:last-child::before{display:none}
.kbd-stage-dot{position:absolute;left:0;top:5px;width:7px;height:7px;border-radius:50%;background:var(--dsw-alias-state-idle-primary)}
.kbd-stage-ok .kbd-stage-dot,.kbd-stage-done .kbd-stage-dot{background:var(--dsw-alias-state-success-primary)}
.kbd-stage-failed .kbd-stage-dot,.kbd-stage-error .kbd-stage-dot{background:var(--dsw-alias-state-error-primary)}
.kbd-stage-running .kbd-stage-dot{background:var(--dsw-alias-state-warn-primary)}
.kbd-stage-name{font-size:12px;font-weight:560}
.kbd-stage-note{font-size:11px;line-height:1.5;color:var(--dsw-alias-label-secondary);margin-top:3px;word-break:break-word}
.kbd-muted{color:var(--dsw-alias-label-secondary)}
.kbd-small{font-size:11px}
.kbd-empty{border:1px dashed var(--dsw-alias-border-l2);border-radius:10px;padding:22px 16px;text-align:center;color:var(--dsw-alias-label-secondary);font-size:12px;line-height:1.6}
.kbd-loading{display:flex;align-items:center;gap:7px;color:var(--dsw-alias-label-secondary);font-size:12px;padding:10px 2px}
.kbd-notice{display:flex;align-items:flex-start;gap:8px;border-radius:9px;padding:8px 11px;font-size:12px;line-height:1.5;border:1px solid var(--dsw-alias-border-l1);background:var(--dsw-alias-bg-layer-2)}
.kbd-notice-error{border-color:var(--dsw-alias-state-error-primary);color:var(--dsw-alias-label-primary)}
.kbd-notice-ok{border-color:var(--dsw-alias-state-success-primary)}
.kbd-notice-warn{border-color:var(--dsw-alias-state-warn-primary)}
.kbd-notice-x{margin-left:auto;border:0;background:none;color:var(--dsw-alias-label-secondary);font-size:15px;line-height:1;cursor:pointer;padding:0 2px}
.kbd-overlay{position:fixed;inset:0;background:rgba(0,0,0,.42);display:flex;align-items:center;justify-content:center;z-index:60;padding:28px}
.kbd-modal{background:var(--dsw-alias-bg-overlay,var(--dsw-alias-bg-layer-1));border:1px solid var(--dsw-alias-border-l2);border-radius:14px;width:min(880px,100%);max-height:86vh;display:flex;flex-direction:column;gap:10px;padding:16px;overflow:auto;box-shadow:0 18px 48px rgba(0,0,0,.28)}
.kbd-modal-head{display:flex;align-items:flex-start;gap:10px}
.kbd-modal-title{font-size:14px;font-weight:640}
.kbd-modal-foot{display:flex;align-items:center;justify-content:flex-end;gap:9px;padding-top:4px}
.kbd-mech{display:flex;flex-direction:column;gap:2px;padding:4px 0}
.kbd-mech-step{display:flex;gap:12px;padding:11px 2px;border-bottom:1px solid var(--dsw-alias-border-l1)}
.kbd-mech-step:last-child{border-bottom:0}
.kbd-mech-n{flex:0 0 auto;width:26px;font-size:11px;font-weight:700;letter-spacing:.04em;color:color-mix(in srgb,var(--dsw-alias-brand-primary) 70%,var(--dsw-alias-label-secondary));padding-top:2px}
.kbd-mech-body{display:flex;flex-direction:column;gap:3px;min-width:0}
.kbd-mech-who{font-size:11px;letter-spacing:.02em;color:var(--dsw-alias-label-secondary)}
.kbd-mech-title{font-size:13px;font-weight:640;line-height:1.4}
.kbd-mech-notes{display:flex;flex-direction:column;gap:6px;margin-top:8px;padding:10px 12px;border-radius:9px;background:color-mix(in srgb,var(--dsw-alias-label-primary) 4%,transparent)}
.kbd-mech-note{font-size:12px;line-height:1.6;color:var(--dsw-alias-label-secondary)}
.kbd-mech-note strong{color:var(--dsw-alias-label-primary);font-weight:620}
.kbd-warn-text{color:var(--dsw-alias-state-warn-primary);line-height:1.5}
.kbd-spinner{width:13px;height:13px;border-radius:50%;border:2px solid var(--dsw-alias-border-l2);border-top-color:var(--dsw-alias-brand-primary);animation:kbd-spin .8s linear infinite;flex:0 0 auto}
@keyframes kbd-spin{to{transform:rotate(360deg)}}

.kbd-pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.65;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--dsw-alias-label-primary)}
.kbd-actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.kbd-groups{display:flex;flex-direction:column;gap:12px}
.kbd-group{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);border-radius:12px;padding:11px 13px}
.kbd-group-head{display:flex;align-items:baseline;gap:9px;margin-bottom:8px}
.kbd-group-head h3{margin:0;font-size:12.5px;font-weight:640}
.kbd-group-list{display:flex;flex-direction:column;gap:7px}
.kbd-issue{display:flex;gap:9px;align-items:flex-start;padding:7px 0;border-top:1px solid var(--dsw-alias-border-l1)}
.kbd-issue:first-child{border-top:0}
.kbd-issue-body{display:flex;flex-direction:column;gap:3px;min-width:0}
.kbd-issue-title{font-size:12.5px;font-weight:550;line-height:1.4}
.kbd-file{font-size:10.5px;color:var(--dsw-alias-label-secondary);background:var(--dsw-alias-bg-layer-2);border-radius:5px;padding:1px 6px;align-self:flex-start;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.kbd-learn{gap:10px;overflow:hidden}
.kbd-learn-bar{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
.kbd-learn-bar .kbd-input{flex:1;min-width:280px;width:auto}
.kbd-learn-body{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,0.75fr);gap:12px}
.kbd-reader,.kbd-chat{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);border-radius:12px;display:flex;flex-direction:column;min-height:0;overflow:hidden}
.kbd-reader-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding:11px 13px;border-bottom:1px solid var(--dsw-alias-border-l1)}
.kbd-reader-title{font-size:13.5px;font-weight:640;line-height:1.4}
.kbd-read-scroll{flex:1;overflow:auto;padding:14px 18px 26px}
.kbd-para{margin:0 0 12px;font-size:13.5px;line-height:1.85;cursor:pointer;border-radius:6px;padding:2px 6px;margin-left:-6px;transition:background .12s}
.kbd-para:hover{background:var(--dsw-alias-bg-layer-2)}
.kbd-para.is-quoted{background:color-mix(in srgb,var(--dsw-alias-brand-primary) 12%,transparent);box-shadow:inset 2px 0 0 var(--dsw-alias-brand-primary)}
.kbd-frame{flex:1;width:100%;border:0;background:var(--dsw-alias-bg-base)}
.kbd-chat-head{display:flex;justify-content:space-between;align-items:baseline;padding:10px 12px;border-bottom:1px solid var(--dsw-alias-border-l1);font-size:12.5px;font-weight:620}
.kbd-chat-list{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:10px}
.kbd-msg{display:flex;flex-direction:column;gap:4px;max-width:100%}
.kbd-msg-role{font-size:10.5px;color:var(--dsw-alias-label-secondary)}
.kbd-msg-content{font-size:12.5px;line-height:1.72;white-space:pre-wrap;word-break:break-word;border-radius:9px;padding:8px 11px;background:var(--dsw-alias-bg-layer-2)}
.kbd-msg-user .kbd-msg-content{background:color-mix(in srgb,var(--dsw-alias-brand-primary) 12%,transparent);border:1px solid color-mix(in srgb,var(--dsw-alias-brand-primary) 30%,transparent)}
.kbd-msg-assistant .kbd-msg-content{background:var(--dsw-alias-bg-layer-2)}
.kbd-quote{display:flex;gap:8px;align-items:flex-start;margin:0 12px;padding:6px 9px;border-left:2px solid var(--dsw-alias-brand-primary);background:var(--dsw-alias-bg-layer-2);border-radius:6px;font-size:11px;color:var(--dsw-alias-label-secondary);line-height:1.5}
.kbd-chat-actions{display:flex;gap:6px;flex-wrap:wrap;padding:8px 12px 0}
.kbd-chat-input{display:flex;gap:8px;padding:8px 12px 12px;align-items:flex-end}
.kbd-chat-input .kbd-textarea{flex:1}
.kbd-learn-empty{flex:1;display:flex;flex-direction:column;gap:14px;justify-content:center;max-width:760px;margin:0 auto;width:100%}
.kbd-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.kbd-step{background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);border-radius:11px;padding:11px 13px;display:flex;flex-direction:column;gap:5px}
.kbd-step-title{font-size:12.5px;font-weight:640;color:var(--dsw-alias-brand-primary)}
.kbd-create-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.kbd-seed{border-bottom:1px solid var(--dsw-alias-border-l1);padding:10px 12px;display:flex;flex-direction:column;gap:8px;max-height:46%;overflow:auto}
.kbd-seed-head{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px;font-weight:600}
.kbd-seed-list{display:flex;flex-direction:column;gap:8px}
.kbd-seed-card{border:1px solid var(--dsw-alias-border-l1);border-radius:9px;padding:9px 10px;background:var(--dsw-alias-bg-layer-1);display:flex;flex-direction:column;gap:5px}
.kbd-seed-title{display:flex;align-items:baseline;gap:7px;font-size:12px;font-weight:600}
.kbd-seed-text{font-size:12px;line-height:1.65;color:var(--dsw-alias-label-primary);white-space:pre-wrap}
.kbd-seed-actions{display:flex;gap:12px;align-items:center}
.kbd-link{background:none;border:0;padding:0;font:inherit;font-size:12px;color:var(--dsw-alias-brand-primary);cursor:pointer}
.kbd-link:disabled{opacity:.45;cursor:default}
.kbd-link-muted{color:var(--dsw-alias-label-secondary)}
.kbd-pick-list{overflow:auto;flex:1;padding:6px}
.kbd-pick{display:flex;gap:9px;align-items:flex-start;padding:8px 9px;border-radius:8px;cursor:pointer}
.kbd-pick:hover{background:var(--dsw-alias-bg-layer-2)}
.kbd-pick.is-active{background:var(--dsw-alias-bg-layer-2);box-shadow:inset 2px 0 0 var(--dsw-alias-brand-primary)}
.kbd-pick input{margin-top:3px}
.kbd-pick-excerpt{font-size:11px;line-height:1.5;color:var(--dsw-alias-label-secondary);overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.kbd-topics{overflow:auto;flex:1;padding:10px;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;align-content:start}
.kbd-topic{background:var(--dsw-alias-bg-layer-2);border:1px solid var(--dsw-alias-border-l1);border-radius:11px;padding:11px 12px;display:flex;flex-direction:column;gap:7px}
.kbd-topic-head{display:flex;align-items:center;gap:8px}
.kbd-topic-title{margin:0;font-size:13px;font-weight:640;line-height:1.4}
.kbd-topic-hook{margin:0;font-size:12px;line-height:1.6}
.kbd-topic-outline{margin:0;padding-left:16px;font-size:11.5px;line-height:1.7;color:var(--dsw-alias-label-secondary)}
.kbd-topic-sources{display:flex;gap:5px;flex-wrap:wrap}
.kbd-source{font-size:10.5px;padding:1px 7px;border-radius:999px;background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l1);color:var(--dsw-alias-label-secondary)}
.kbd-topic-actions{display:flex;gap:6px;margin-top:2px}
.kbd-build{position:absolute;right:8px;bottom:4px;font-size:9px;color:var(--dsw-alias-label-secondary);opacity:.4;pointer-events:none}
@media (max-width:1080px){
  .kbd-learn-body{grid-template-columns:1fr;grid-template-rows:minmax(240px,1fr) minmax(260px,1fr)}
  .kbd-split,.kbd-split-wide{grid-template-columns:1fr}
}
`

    return {
      inject: ['slots'],
      apply(ctx) {
        ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: 'raincoat-kb-desk' }, Panel))
        ctx.slots.inject('sidebar.panellist', () =>
          ctx.slots.register({ name: 'sidebar.panellist', id: 'raincoat-kb-desk', order: 24, label: () => '个人知识库' }, Icon),
        )
      },
    }
  },
})
