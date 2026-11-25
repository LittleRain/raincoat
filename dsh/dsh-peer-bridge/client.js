window.__ModuleLoader__.load({
  id: '@local/dsh-peer-bridge',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const { useCallback, useEffect, useMemo, useRef, useState } = React

    const API = '/dsh-bridge/api'
    const POLL_MS = 5_000
    const HASH_HANDOFF = '#dsh-bridge='
    const HASH_OPEN = '#dsh-bridge-open='
    const HASH_OPEN_LEGACY = '#dsh-open='
    // 面板聚焦的深链：`#dsh-bridge-session=<id>`，刷新、贴给别人、从浏览器历史回来都能落到同一条。
    const HASH_PANEL = '#dsh-bridge-session='

    const T = {
      text: 'var(--dsw-alias-label-primary)',
      muted: 'var(--dsw-alias-label-secondary)',
      border: 'var(--dsw-alias-border-l1)',
      borderStrong: 'var(--dsw-alias-border-l2)',
      layer: 'var(--dsw-alias-bg-layer-1)',
      layer2: 'var(--dsw-alias-bg-layer-2)',
      overlay: 'var(--dsw-alias-bg-overlay)',
      brand: 'var(--dsw-alias-brand-primary)',
      ok: 'var(--dsw-alias-state-success-primary)',
      idle: 'var(--dsw-alias-state-idle-primary)',
      warn: 'var(--dsw-alias-state-warn-primary)',
      error: 'var(--dsw-alias-state-error-primary)',
    }

    /* ---------------------------------------------------------------- 数据 */

    const store = {
      data: null,
      error: null,
      loading: false,
      listeners: new Set(),
      timer: null,
      inflight: null,
    }

    function emit() {
      for (const listener of store.listeners) listener()
    }

    /**
     * 从会话头跳进来时只显示这一条：跨组件传参要走模块级状态，
     * 面板是整页挂载的，靠 props 传不进去。
     */
    const panelFocus = {
      sessionId: '',
      listeners: new Set(),
      set(sessionId) {
        panelFocus.sessionId = String(sessionId || '')
        for (const listener of panelFocus.listeners) listener(panelFocus.sessionId)
      },
      subscribe(listener) {
        panelFocus.listeners.add(listener)
        return () => {
          panelFocus.listeners.delete(listener)
        }
      },
    }

    const PANEL_ID = 'peer-bridge'
    const RETURN_KEY = 'peer-bridge:returnTo'

    /** 从面板回对话用：跳走之前记下当时打开的是哪条。 */
    function writeReturnTo(sessionId) {
      try {
        if (sessionId) window.sessionStorage.setItem(RETURN_KEY, String(sessionId))
      } catch {
        /* 隐私模式下写不进去，退化成没有回程按钮 */
      }
    }

    function readReturnTo() {
      try {
        return String(window.sessionStorage.getItem(RETURN_KEY) || '')
      } catch {
        return ''
      }
    }

    /** 地址栏里同步「只看这一条」，让聚焦状态可刷新、可分享。 */
    function syncPanelHash(sessionId) {
      try {
        const url = new URL(window.location.href)
        url.hash = sessionId ? `${HASH_PANEL}${encodeURIComponent(sessionId)}` : ''
        window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`)
      } catch {
        /* 地址栏不可写不影响面板本身 */
      }
    }

    /** 跳到「双端会话」面板并只看这条会话；宿主没给 layout 服务时退回提示。 */
    function openInPanel(sessionId, currentSessionId) {
      panelFocus.set(sessionId)
      writeReturnTo(currentSessionId || '')
      syncPanelHash(sessionId)
      const layout = runtime.layout
      if (layout && typeof layout.selectPanel === 'function') {
        layout.selectPanel(PANEL_ID)
        return true
      }
      showToast('这个界面切不到面板，左侧「双端会话」里能看到它', 'error')
      return false
    }

    /** 退出「只看这一条」：横幅按钮、Esc、打开别的会话都走这里。 */
    function clearPanelFocus() {
      panelFocus.set('')
      syncPanelHash('')
    }

    async function request(path, init) {
      const headers = { accept: 'application/json' }
      if (init && init.body !== undefined) headers['content-type'] = 'application/json'
      const response = await fetch(`${API}${path}`, {
        credentials: 'same-origin',
        method: (init && init.method) || 'GET',
        headers,
        body: init && init.body,
      })
      const body = await response.json().catch(() => null)
      if (response.status === 404) {
        // 客户端由页面加载，宿主侧却要重启才注册路由：这是最常见的"只加载了一半"。
        throw new Error('插件宿主侧还没加载：重启 web host 后再试')
      }
      if (!response.ok || (body && body.ok === false)) {
        const failure = new Error((body && body.message) || `HTTP ${response.status}`)
        // 让出失败时宿主会带 code / hint：界面要能按原因给下一步，不能只剩一句 message。
        failure.body = body || null
        failure.status = response.status
        throw failure
      }
      return body
    }

    function refresh() {
      if (store.inflight) return store.inflight
      store.loading = true
      emit()
      store.inflight = request('/overview')
        .then((data) => {
          store.data = data
          store.error = null
        })
        .catch((error) => {
          store.error = String((error && error.message) || error)
        })
        .finally(() => {
          store.loading = false
          store.inflight = null
          emit()
        })
      return store.inflight
    }

    function ensurePolling() {
      if (store.timer !== null) return
      store.timer = setInterval(() => {
        if (typeof document !== 'undefined' && document.hidden) return
        refresh()
      }, POLL_MS)
    }

    function subscribe(listener) {
      store.listeners.add(listener)
      ensurePolling()
      return () => {
        store.listeners.delete(listener)
        if (store.listeners.size === 0 && store.timer !== null) {
          clearInterval(store.timer)
          store.timer = null
        }
      }
    }

    function useOverview() {
      const [, bump] = useState(0)
      useEffect(() => {
        const unsubscribe = subscribe(() => bump((value) => value + 1))
        refresh()
        return unsubscribe
      }, [])
      return { data: store.data, error: store.error, loading: store.loading, refresh }
    }

    /* ---------------------------------------------------------------- 提示 */

    const toasts = { listeners: new Set(), items: [] }

    function showToast(message, tone) {
      const item = { id: `${Date.now()}-${Math.random()}`, message: String(message), tone: tone || 'info' }
      toasts.items = [...toasts.items, item]
      for (const listener of toasts.listeners) listener()
      setTimeout(() => {
        toasts.items = toasts.items.filter((entry) => entry.id !== item.id)
        for (const listener of toasts.listeners) listener()
        // 失败提示带「下一步怎么做」，4.5 秒读不完。
      }, tone === 'error' ? 9_000 : 4_500)
    }

    /** 让出失败：把「发生了什么」和「下一步怎么做」拼成一句人话。 */
    function describeReleaseError(error) {
      const body = error && error.body
      const message = String((body && body.message) || (error && error.message) || error)
      const hint = body && body.hint ? String(body.hint) : ''
      return hint && hint !== message ? `${message}：${hint}` : message
    }

    /**
     * 让出写锁靠接管 sessionPersistence。自检说不生效时，先把话说明白：
     * 这个版本点「切到本端」只能提示对端重启，别让用户以为点了就行。
     */
    function tapWarning(overview) {
      const tap = overview && overview.writeTap
      if (!tap || tap.selfCheck?.ok !== false) return null
      return h(
        'div',
        {
          style: {
            fontSize: 12,
            lineHeight: '18px',
            color: `color-mix(in srgb, var(--dsw-alias-state-warn-primary) 55%, var(--dsw-alias-label-primary))`,
          },
        },
        '这个宿主没能接管会话写句柄（DSH 版本可能变了）：从另一端点「切到本端」时，这里只能提示对方重启本端。诊断见 /dsh-bridge/api/_probe。',
      )
    }

    function ToastHost() {
      const [, bump] = useState(0)
      useEffect(() => {
        const listener = () => bump((value) => value + 1)
        toasts.listeners.add(listener)
        return () => toasts.listeners.delete(listener)
      }, [])
      if (toasts.items.length === 0) return null
      return h(
        'div',
        { style: { position: 'fixed', right: 20, bottom: 20, display: 'grid', gap: 8, zIndex: 60, pointerEvents: 'none' } },
        toasts.items.map((item) =>
          h(
            'div',
            {
              key: item.id,
              style: {
                maxWidth: 360,
                padding: '8px 12px',
                borderRadius: 8,
                border: `1px solid ${item.tone === 'error' ? T.error : T.border}`,
                background: T.overlay,
                color: item.tone === 'error' ? T.error : T.text,
                fontSize: 12,
                lineHeight: '18px',
                boxShadow: '0 6px 20px rgba(0,0,0,0.12)',
              },
            },
            item.message,
          ),
        ),
      )
    }

    /* ---------------------------------------------------------------- 小工具 */

    function shortId(id) {
      const text = String(id || '')
      return text.replace(/^session-/, '').slice(0, 8)
    }

    function timeText(at) {
      const value = Number(at)
      if (!Number.isFinite(value) || value <= 0) return '—'
      const date = new Date(value)
      const today = new Date()
      const sameDay = date.toDateString() === today.toDateString()
      return sameDay
        ? date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
        : date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
    }

    function baseName(dir) {
      return String(dir || '').split('/').filter(Boolean).pop() || '—'
    }

    /** 对端自述的名字可能是「未知端」（旧进程没重启时），界面上别直接显示这个词。 */
    function peerName(peer) {
      const label = peer && typeof peer.label === 'string' ? peer.label.trim() : ''
      return label === '' || label === '未知端' ? '另一端' : label
    }

    function ownerOf(data, sessionId) {
      if (!data) return { kind: 'unknown', label: '…', color: T.idle }
      if ((data.heldIds || []).includes(sessionId)) return { kind: 'self', label: '本端', color: T.ok }
      for (const peer of data.peers || []) {
        if ((peer.heldIds || []).includes(sessionId)) {
          return { kind: 'peer', label: peerName(peer), peer, color: T.brand }
        }
      }
      // 已让出写锁：agent 还在但写不进去，徽标要说清楚，不能显示成「空闲」。
      if ((data.sessions || []).some((row) => row.sessionId === sessionId && row.frozen)) {
        return { kind: 'frozen', label: '已让出', color: T.muted }
      }
      return { kind: 'free', label: '空闲', color: T.idle }
    }

    function peersOf(data) {
      return ((data && data.peers) || []).filter((peer) => peer.alive)
    }

    const chip = {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      height: 24,
      padding: '0 8px',
      borderRadius: 6,
      border: `1px solid ${T.border}`,
      background: 'transparent',
      color: T.text,
      font: 'inherit',
      fontSize: 12,
      lineHeight: '22px',
      cursor: 'pointer',
      whiteSpace: 'nowrap',
    }

    const dot = (color) => ({ width: 6, height: 6, borderRadius: 3, background: color, flex: '0 0 auto' })

    const menuItem = {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 12,
      width: '100%',
      padding: '7px 10px',
      border: 'none',
      borderRadius: 6,
      background: 'transparent',
      color: T.text,
      font: 'inherit',
      fontSize: 12,
      lineHeight: '18px',
      textAlign: 'left',
      cursor: 'pointer',
    }

    /* ------------------------------------------------- 会话头部的处理权徽标 */

    function OwnerChip({ sessionId }) {
      const { data } = useOverview()
      const [open, setOpen] = useState(false)
      const [rect, setRect] = useState(null)
      const buttonRef = useRef(null)
      const wrapRef = useRef(null)

      const owner = ownerOf(data, sessionId)
      const peers = peersOf(data)

      useEffect(() => {
        if (!open) return undefined
        const onPointer = (event) => {
          if (wrapRef.current && wrapRef.current.contains(event.target)) return
          setOpen(false)
        }
        const onKey = (event) => {
          if (event.key === 'Escape') setOpen(false)
        }
        window.addEventListener('mousedown', onPointer, true)
        window.addEventListener('keydown', onKey)
        return () => {
          window.removeEventListener('mousedown', onPointer, true)
          window.removeEventListener('keydown', onKey)
        }
      }, [open])

      const toggle = () => {
        if (!open && buttonRef.current) {
          const box = buttonRef.current.getBoundingClientRect()
          setRect({ top: box.bottom + 6, right: Math.max(12, window.innerWidth - box.right) })
        }
        setOpen((value) => !value)
      }

      const openOnPeer = useCallback(async () => {
        const peer = peers[0]
        if (!peer) return
        const base = String(peer.origin || '').replace(/\/$/, '')
        // 对端 URL 带进程 token，只有宿主编得出来；这里走 overview 里的 url 字段。
        const target = (peer.url || `${base}/`) + `#dsh-bridge-open=${encodeURIComponent(sessionId)}`
        const opened = window.open(target, '_blank', 'noopener,noreferrer')
        if (!opened) showToast('弹窗被浏览器拦截了', 'error')
        setOpen(false)
      }, [peers, sessionId])

      const label = owner.label
      const color = owner.color
      // 「不是本端打开」= 写锁在另一端，或者本端已经让出过（已冻结）。
      const notLocal = owner.kind === 'peer' || owner.kind === 'frozen'

      return h(
        'div',
        { ref: wrapRef, style: { position: 'relative', display: 'inline-flex' } },
        h(
          'button',
          {
            ref: buttonRef,
            type: 'button',
            onClick: toggle,
            title: '对话处理权：谁在跑这个会话（「已让出」= 本端放出过写锁，写不进去了）',
            style: { ...chip, color },
            'aria-haspopup': 'menu',
            'aria-expanded': open,
          },
          h('span', { style: dot(color) }),
          h('span', null, label),
        ),
        // 不是本端打开的会话：给一条直达面板的路，别让人再去侧栏里翻。
        notLocal
          ? h(
              'button',
              {
                type: 'button',
                onClick: () => openInPanel(sessionId, sessionId),
                title: '这条会话不是本端打开的：跳到「双端会话」只看它',
                style: { ...chip, marginLeft: 4, gap: 4, color: T.muted },
              },
              h(
                'svg',
                { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', 'aria-hidden': 'true' },
                h('rect', { x: 3, y: 4, width: 18, height: 16, rx: 3, stroke: 'currentColor', strokeWidth: 1.7 }),
                h('path', { d: 'M9 4v16', stroke: 'currentColor', strokeWidth: 1.7 }),
              ),
              h('span', null, '双端会话'),
            )
          : null,
        open && rect
          ? h(
              'div',
              {
                role: 'menu',
                style: {
                  position: 'fixed',
                  top: rect.top,
                  right: rect.right,
                  zIndex: 70,
                  minWidth: 236,
                  padding: 6,
                  borderRadius: 10,
                  border: `1px solid ${T.border}`,
                  background: T.overlay,
                  boxShadow: '0 10px 30px rgba(0,0,0,0.16)',
                },
              },
              h(
                'div',
                { style: { padding: '4px 10px 6px', fontSize: 11, color: T.muted } },
                owner.kind === 'peer'
                  ? `${owner.label} 持有写锁，本端只能读`
                  : owner.kind === 'self'
                    ? '本端持有写锁'
                    : '当前没有宿主持有这个会话',
              ),

              notLocal
                ? h(
                    'button',
                    {
                      type: 'button',
                      role: 'menuitem',
                      onClick: () => {
                        setOpen(false)
                        openInPanel(sessionId, sessionId)
                      },
                      style: menuItem,
                    },
                    h('span', null, '在「双端会话」里看这一条'),
                  )
                : null,

              h(
                'button',
                {
                  type: 'button',
                  role: 'menuitem',
                  onClick: () => {
                    Promise.resolve(navigator.clipboard?.writeText(String(sessionId))).catch(() => {})
                    showToast('会话 ID 已复制')
                    setOpen(false)
                  },
                  style: menuItem,
                },
                h('span', null, '复制会话 ID'),
              ),
            )
          : null,
      )
    }

    /* ------------------------------------------------------ 输入框上方的提示 */

    /** 请对端放掉写锁，然后在本端打开；失败原样抛出，由调用方按 code 翻译成人话。 */
    async function takeover(sessionId, peerPid) {
      const result = await request('/release', {
        method: 'POST',
        body: JSON.stringify({ sessionId, toPid: peerPid }),
      })
      if (!result || !(result.released || result.reason === 'not-held')) {
        const failure = new Error((result && result.message) || '对端没有让出这条会话')
        failure.body = result || null
        throw failure
      }
      if (result.frozen) showToast(result.message || '对端那条会话已冻结，本端接管', 'info')
      refresh()
      await new Promise((resolve) => setTimeout(resolve, 300))
      openSessionWithFallback(sessionId)
      return result
    }

    function MirrorDock({ sessionId }) {
      const { data } = useOverview()
      const owner = ownerOf(data, sessionId)
      const peers = peersOf(data)
      const row = data && (data.sessions || []).find((item) => item.sessionId === sessionId)
      const [confirming, setConfirming] = useState(false)
      const [taking, setTaking] = useState(false)

      // 打开这个会话时记下基线；之后 updatedAt 变大，说明对端往里写了新内容。
      const seen = useRef({ id: null, at: 0 })
      if (row && seen.current.id !== sessionId) seen.current = { id: sessionId, at: row.updatedAt }

      // 确认态 5 秒没点第二次就撤回，别一直挂在「确认接管」上。
      useEffect(() => {
        if (!confirming) return undefined
        const timer = setTimeout(() => setConfirming(false), 5_000)
        return () => clearTimeout(timer)
      }, [confirming])

      if (owner.kind !== 'peer' && owner.kind !== 'frozen') return null

      const frozen = owner.kind === 'frozen'
      const peerRunning = !frozen && (owner.peer.runningIds || []).includes(sessionId)
      const fresh = Boolean(row) && row.updatedAt > seen.current.at
      const tone = frozen ? T.muted : fresh ? T.warn : T.brand
      const text = frozen
        ? '本端已经让出过这条会话的写锁：现在只能看，要接回来得重启本端'
        : peerRunning
          ? `${owner.label}正在跑这一轮：等它跑完再接，别切断生成中的内容`
          : fresh
            ? `${owner.label}刚写了新内容，本端这份还是旧的（这里只能读，不能发）`
            : `处理权在${owner.label}：本端只能读，发消息会被拒绝`

      const runTakeover = async () => {
        if (taking) return
        if (!confirming) {
          setConfirming(true)
          return
        }
        setConfirming(false)
        setTaking(true)
        try {
          await takeover(sessionId, owner.peer.pid)
        } catch (error) {
          showToast(describeReleaseError(error), 'error')
        } finally {
          setTaking(false)
        }
      }

      const small = (label, onClick, options = {}) =>
        h(
          'button',
          {
            type: 'button',
            onClick,
            disabled: options.disabled,
            title: options.title,
            style: {
              ...chip,
              height: 22,
              padding: '0 8px',
              fontSize: 12,
              ...(options.primary ? { borderColor: T.brand, color: T.brand } : {}),
              ...(options.disabled ? { opacity: 0.45, cursor: 'default' } : {}),
            },
          },
          label,
        )

      return h(
        'div',
        {
          style: {
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 10,
            padding: '6px 12px',
            margin: '0 0 8px',
            borderRadius: 8,
            border: `1px solid ${confirming ? T.brand : T.border}`,
            background: T.layer2,
            color: T.muted,
            fontSize: 12,
            lineHeight: '18px',
          },
        },
        h('span', { style: dot(tone) }),
        h('span', { style: { flex: '1 1 auto', minWidth: 0 } }, text),
        !frozen && confirming
          ? h('span', { style: { color: T.brand, flex: '0 0 auto' } }, '对端会冻结这条会话，要重启它才能继续用')
          : null,
        !frozen
          ? small(taking ? '接管中…' : confirming ? '确认接管' : '接管到本端', runTakeover, {
              primary: true,
              disabled: taking || peerRunning,
              title: peerRunning
                ? `${owner.label}正在跑回合，等这一轮跑完再接`
                : `请${owner.label}放掉这条会话，然后在本端打开`,
            })
          : null,
        small('在双端会话里看', () => openInPanel(sessionId, sessionId), {
          title: '跳到「双端会话」只看这一条，面板里也能接管',
        }),
        fresh && !confirming ? small('刷新', () => window.location.reload()) : null,
        !fresh && !confirming && peers.length > 0
          ? small('在另一端打开', () => openOnPeer(peers[0], sessionId))
          : null,
      )
    }

    /* ------------------------------------------------------------ 管理面板 */

    const FILTERS = [
      { id: 'all', label: '全部' },
      { id: 'running', label: '运行中' },
      { id: 'mine', label: '本端持有' },
      { id: 'peer', label: '对端持有' },
    ]

    function PanelIcon({ size = 20, active }) {
      return h(
        'svg',
        {
          width: size,
          height: size,
          viewBox: '0 0 24 24',
          fill: 'none',
          'aria-hidden': 'true',
          style: { color: active ? T.brand : T.muted },
        },
        h('path', {
          d: 'M4 8h11a3 3 0 0 1 0 6H9',
          stroke: 'currentColor',
          strokeWidth: 1.6,
          strokeLinecap: 'round',
        }),
        h('path', { d: 'M7 5 4 8l3 3', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' }),
        h('path', { d: 'M20 16H9a3 3 0 0 1 0-6', stroke: 'currentColor', strokeWidth: 1.2, strokeLinecap: 'round', opacity: 0.55 }),
      )
    }

    /** 竖屏/窄屏：表格改用卡片，操作按钮换行铺满，避免横向挤没了。 */
    function useNarrow() {
      const query = '(max-width: 760px)'
      const [narrow, setNarrow] = useState(() => {
        try {
          return window.matchMedia(query).matches
        } catch {
          return false
        }
      })
      useEffect(() => {
        let media
        try {
          media = window.matchMedia(query)
        } catch {
          return undefined
        }
        const onChange = () => setNarrow(media.matches)
        media.addEventListener?.('change', onChange)
        return () => media.removeEventListener?.('change', onChange)
      }, [])
      return narrow
    }

    function PeerBridgePage() {
      return function PeerBridgePageView() {
        const narrow = useNarrow()
        const { data, error, loading, refresh } = useOverview()
        const [filter, setFilter] = useState('all')
        const [focus, setFocus] = useState(panelFocus.sessionId)

        useEffect(() => panelFocus.subscribe(setFocus), [])

        // 跳进来是「只看这一条」，跟上一轮的筛选条件会打架，先归到「全部」。
        useEffect(() => {
          if (focus) setFilter('all')
        }, [focus])

        const rows = useMemo(() => {
          const all = (data && data.sessions) || []
          const filtered = all.filter((row) => {
            if (focus && row.sessionId !== focus) return false
            if (filter === 'running') return row.running
            if (filter === 'mine') return row.held
            if (filter === 'peer') return ownerOf(data, row.sessionId).kind === 'peer'
            return true
          })
          return filtered.slice(0, 300)
        }, [data, filter, focus])

        const focusRow = focus ? ((data && data.sessions) || []).find((row) => row.sessionId === focus) : null

        const focusRowRef = useRef(null)
        const [confirmTake, setConfirmTake] = useState(false)
        const returnTo = readReturnTo()
        const canReturn = Boolean(returnTo) && Boolean(data) && (data.sessions || []).some((row) => row.sessionId === returnTo)
        const focusOwner = focus ? ownerOf(data, focus) : null
        const focusPeerHeld = Boolean(focusRow) && focusOwner !== null && focusOwner.kind === 'peer'
        const focusPeerRunning = focusPeerHeld && (focusOwner.peer.runningIds || []).includes(focus)
        const focusFrozen = Boolean(focusRow) && focusOwner !== null && focusOwner.kind === 'frozen'

        // 聚焦行要看得见：滚到视口中间，表格长的时候尤其重要。
        useEffect(() => {
          if (!focus) return undefined
          const node = focusRowRef.current
          if (!node || typeof node.scrollIntoView !== 'function') return undefined
          const timer = setTimeout(() => node.scrollIntoView({ block: 'center', behavior: 'smooth' }), 60)
          return () => clearTimeout(timer)
        }, [focus, rows.length])

        // Esc 退出「只看这一条」。
        useEffect(() => {
          if (!focus) return undefined
          const onKey = (event) => {
            if (event.key === 'Escape') clearPanelFocus()
          }
          window.addEventListener('keydown', onKey)
          return () => window.removeEventListener('keydown', onKey)
        }, [focus])

        // 「切到本端」的确认态 5 秒没点第二次就撤回。
        useEffect(() => {
          if (!confirmTake) return undefined
          const timer = setTimeout(() => setConfirmTake(false), 5_000)
          return () => clearTimeout(timer)
        }, [confirmTake])

        const peers = peersOf(data)
        const self = data && data.self

        const openSession = useCallback((sessionId) => openSessionWithFallback(sessionId), [])

        const head = h(
          'div',
          { style: { display: 'grid', gap: 6, marginBottom: 18 } },
          h('div', { style: { fontSize: 18, fontWeight: 600, color: T.text } }, '双端会话'),
          h(
            'div',
            { style: { fontSize: 12, color: T.muted, lineHeight: '18px' } },
            self
              ? `本端：${self.label}（pid ${self.pid}）${peers.length > 0 ? ` · 对端：${peers.map((peer) => `${peer.label} 持有 ${peer.heldIds.length}`).join(' · ')}` : ' · 对端未运行'}`
              : '正在读取两端状态…',
          ),
          h(
            'div',
            { style: { fontSize: 12, color: T.muted, lineHeight: '18px' } },
            '同一时刻只有一个端能发消息；另一端打开同一会话只能阅读。点「切到本端」会让对端放掉写锁并在这里打开；对端那条会话随后冻结（还能看，写不进去了），要恢复得重启那一端。',
          ),
          focus
            ? h(
                'div',
                {
                  style: {
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    marginTop: 2,
                    padding: '6px 10px',
                    borderRadius: 8,
                    border: `1px solid ${T.border}`,
                    background: T.layer2,
                    fontSize: 12,
                    color: T.muted,
                  },
                },
                h(
                  'span',
                  { style: { flex: '1 1 auto', minWidth: 0 } },
                  focusRow
                    ? `只看这一条：${String(focusRow.title || focusRow.sessionId)}`
                    : '这条会话不在这台机器上：它只在另一端，这里看不到它的记录',
                ),
                h(
                  'div',
                  { style: { display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' } },
                  focusPeerHeld && !focusPeerRunning
                    ? h(
                        'button',
                        {
                          type: 'button',
                          onClick: async () => {
                            if (!confirmTake) {
                              setConfirmTake(true)
                              return
                            }
                            setConfirmTake(false)
                            try {
                              await takeover(focus, focusOwner.peer.pid)
                            } catch (err) {
                              showToast(describeReleaseError(err), 'error')
                            }
                          },
                          style: {
                            ...chip,
                            height: 22,
                            padding: '0 8px',
                            fontSize: 12,
                            borderColor: T.brand,
                            color: T.brand,
                          },
                        },
                        confirmTake ? '确认接管（对端会冻结）' : '切到本端',
                      )
                    : null,
                  focusFrozen ? h('span', { style: { fontSize: 12 } }, '本端已让出，接回来要重启本端') : null,
                  peers.length > 0
                    ? h(
                        'button',
                        {
                          type: 'button',
                          onClick: () => openOnPeer(peers[0], focus),
                          style: { ...chip, height: 22, padding: '0 8px', fontSize: 12 },
                        },
                        '在对端打开',
                      )
                    : null,
                  canReturn
                    ? h(
                        'button',
                        {
                          type: 'button',
                          onClick: () => openSessionWithFallback(returnTo),
                          title: '回到跳进面板之前正在看的那条会话',
                          style: { ...chip, height: 22, padding: '0 8px', fontSize: 12 },
                        },
                        '← 回到刚才的会话',
                      )
                    : null,
                  h(
                    'button',
                    {
                      type: 'button',
                      onClick: () => clearPanelFocus(),
                      style: { ...chip, height: 22, padding: '0 8px', fontSize: 12 },
                    },
                    '显示全部',
                  ),
                ),
              )
            : null,
          tapWarning(data),
        )

        const toolbar = h(
          'div',
          { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' } },
          FILTERS.map((item) =>
            h(
              'button',
              {
                key: item.id,
                type: 'button',
                onClick: () => setFilter(item.id),
                style: {
                  ...chip,
                  height: narrow ? 32 : 26,
                  padding: narrow ? '0 12px' : '0 10px',
                  borderColor: filter === item.id ? T.brand : T.border,
                  color: filter === item.id ? T.brand : T.muted,
                },
              },
              item.label,
            ),
          ),
          h('span', { style: { flex: '1 1 auto' } }),
          loading ? h('span', { style: { fontSize: 12, color: T.muted } }, '刷新中…') : null,
          h('button', { type: 'button', onClick: () => refresh(), style: { ...chip, height: 26 } }, '刷新'),
        )

        const statusOf = (row, peerHeld, peerRunning) =>
          row.running
            ? '运行中'
            : row.frozen
              ? '已让出（本端冻结）'
              : peerRunning
              ? '运行中（对端）'
              : row.held
                ? '空闲（本端）'
                : peerHeld
                  ? '空闲（对端占用）'
                  : '冷'

        const statusTone = (row, peerRunning) => (row.running || peerRunning ? T.warn : row.frozen ? T.muted : T.idle)

        const busy = (row, owner, peerHeld, peerRunning, height) => {
          const size = height ?? 22
          return [
            peerHeld && !peerRunning
              ? h(
                  'button',
                  {
                    key: 'take',
                    type: 'button',
                    onClick: async () => {
                      try {
                        await takeover(row.sessionId, owner.peer.pid)
                      } catch (err) {
                        showToast(describeReleaseError(err), 'error')
                      }
                    },
                    title: `请${owner.label}放掉这条会话，然后在本端打开`,
                    style: { ...chip, height: size, padding: '0 10px', fontSize: size > 24 ? 12 : 11 },
                  },
                  '切到本端',
                )
              : null,
            h(
              'button',
              {
                key: 'open',
                type: 'button',
                disabled: peerHeld,
                onClick: () => openSession(row.sessionId),
                title: peerHeld
                  ? `由${owner.label}占用（${peerRunning ? '正在跑回合' : '没在跑回合，但会话仍被它的进程持有'}）：点「切到本端」让它放锁，或退出那一端`
                  : row.frozen
                    ? '本端已经让出过这条会话的写锁，接不回来：重启本端应用后再打开'
                    : '在当前端打开这条会话',
                style: {
                  ...chip,
                  height: size,
                  padding: '0 10px',
                  fontSize: size > 24 ? 12 : 11,
                  opacity: peerHeld ? 0.45 : 1,
                  cursor: peerHeld ? 'default' : 'pointer',
                },
              },
              peerHeld ? (peerRunning ? '对端运行中' : '对端占用') : row.held ? '打开' : '在本端继续',
            ),
          ].filter(Boolean)
        }

        const grid = narrow
          ? h(
              'div',
              { style: { display: 'grid', gap: 10 } },
              rows.length === 0
                ? h('div', { style: { padding: '24px 4px', fontSize: 12, color: T.muted } }, error ? `读取失败：${error}` : '没有符合条件的会话')
                : rows.map((row) => {
                    const owner = ownerOf(data, row.sessionId)
                    const peerHeld = owner.kind === 'peer'
                    const peerRunning = peerHeld && (owner.peer.runningIds || []).includes(row.sessionId)
                    return h(
                      'div',
                      {
                        key: row.sessionId,
                        ref: row.sessionId === focus ? focusRowRef : undefined,
                        style: {
                          // 聚焦行给个落点：左边一道品牌色，卡片底色提一档。
                          border: `1px solid ${row.sessionId === focus ? T.brand : T.border}`,
                          boxShadow: row.sessionId === focus ? `inset 3px 0 0 ${T.brand}` : 'none',
                          borderRadius: 10,
                          background: row.sessionId === focus ? T.layer2 : T.layer,
                          padding: '10px 12px',
                          display: 'grid',
                          gap: 8,
                          fontSize: 12,
                          color: T.text,
                        },
                      },
                      h(
                        'button',
                        {
                          type: 'button',
                          onClick: () => openSession(row.sessionId),
                          title: row.sessionId,
                          style: {
                            padding: 0,
                            border: 'none',
                            background: 'transparent',
                            color: T.text,
                            font: 'inherit',
                            fontSize: 13,
                            lineHeight: '18px',
                            textAlign: 'left',
                            cursor: 'pointer',
                          },
                        },
                        row.title || shortId(row.sessionId),
                      ),
                      h(
                        'div',
                        { style: { display: 'flex', flexWrap: 'wrap', gap: '2px 10px', fontSize: 11, color: T.muted } },
                        h('span', null, shortId(row.sessionId)),
                        h('span', null, baseName(row.cwd)),
                        h('span', null, timeText(row.updatedAt)),
                      ),
                      h(
                        'div',
                        { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
                        h(
                          'span',
                          {
                            style: {
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 6,
                              color: row.running || peerRunning ? T.warn : T.muted,
                            },
                          },
                          h('span', { style: dot(statusTone(row, peerRunning)) }),
                          statusOf(row, peerHeld, peerRunning),
                        ),
                        h(
                          'span',
                          { style: { display: 'inline-flex', alignItems: 'center', gap: 5, color: owner.color, marginLeft: 'auto' } },
                          h('span', { style: dot(owner.color) }),
                          owner.label,
                        ),
                      ),
                      h('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } }, busy(row, owner, peerHeld, peerRunning, 32)),
                    )
                  }),
            )
          : h(
              'div',
              { style: { border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden', background: T.layer } },
              h(
                'div',
                {
                  style: {
                    display: 'grid',
                    gridTemplateColumns: 'minmax(0,1fr) 110px 74px 88px 176px',
                    gap: 12,
                    padding: '8px 14px',
                    background: T.layer2,
                    borderBottom: `1px solid ${T.border}`,
                    fontSize: 11,
                    color: T.muted,
                  },
                },
                h('span', null, '会话'),
                h('span', null, '工作区'),
                h('span', null, '最后活动'),
                h('span', null, '状态'),
                h('span', null, '持有 / 操作'),
              ),
              rows.length === 0
                ? h('div', { style: { padding: '28px 14px', fontSize: 12, color: T.muted } }, error ? `读取失败：${error}` : '没有符合条件的会话')
                : rows.map((row) => {
                    const owner = ownerOf(data, row.sessionId)
                    const peerHeld = owner.kind === 'peer'
                    const peerRunning = peerHeld && (owner.peer.runningIds || []).includes(row.sessionId)
                    return h(
                      'div',
                      {
                        key: row.sessionId,
                        ref: row.sessionId === focus ? focusRowRef : undefined,
                        style: {
                          // 聚焦行给个落点：左边一道品牌色，底色提一档。
                          display: 'grid',
                          gridTemplateColumns: 'minmax(0,1fr) 110px 74px 88px 176px',
                          gap: 12,
                          alignItems: 'center',
                          padding: '9px 14px',
                          borderTop: `1px solid ${T.border}`,
                          background: row.sessionId === focus ? T.layer2 : 'transparent',
                          boxShadow: row.sessionId === focus ? `inset 3px 0 0 ${T.brand}` : 'none',
                          fontSize: 12,
                          color: T.text,
                        },
                      },
                      h(
                        'div',
                        { style: { minWidth: 0, display: 'grid', gap: 2 } },
                        h(
                          'button',
                          {
                            type: 'button',
                            onClick: () => openSession(row.sessionId),
                            title: row.sessionId,
                            style: {
                              padding: 0,
                              border: 'none',
                              background: 'transparent',
                              color: T.text,
                              font: 'inherit',
                              fontSize: 12,
                              textAlign: 'left',
                              cursor: 'pointer',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            },
                          },
                          row.title || shortId(row.sessionId),
                        ),
                        h('span', { style: { fontSize: 11, color: T.muted } }, shortId(row.sessionId)),
                      ),
                      h('span', { style: { color: T.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, baseName(row.cwd)),
                      h('span', { style: { color: T.muted } }, timeText(row.updatedAt)),
                      h(
                        'span',
                        {
                          style: {
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 6,
                            color: row.running || peerRunning ? T.warn : T.muted,
                          },
                        },
                        h('span', { style: dot(statusTone(row, peerRunning)) }),
                        statusOf(row, peerHeld, peerRunning),
                      ),
                      h(
                        'div',
                        { style: { display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' } },
                        h(
                          'span',
                          { style: { display: 'inline-flex', alignItems: 'center', gap: 5, color: owner.color, marginRight: 2 } },
                          h('span', { style: dot(owner.color) }),
                          owner.label,
                        ),
                        ...busy(row, owner, peerHeld, peerRunning, 22),
                      ),
                    )
                  }),
            )

        return h(
          'div',
          { style: { padding: narrow ? '14px 12px' : '24px 28px', maxWidth: 1040, minHeight: '100%', overflow: 'auto', color: T.text } },
          head,
          toolbar,
          grid,
        )
      }
    }

    /* --------------------------------------------------------------- 深链 */

    let runtime = { uiWorkspace: undefined, layout: undefined, ctx: undefined }

    /**
     * 现取 uiWorkspace，不要只用 inject 回调里缓存的那一份。
     * 缓存实例在依赖插件热重载后是旧的：调它的 openSession 不报错也不生效，
     * 表现就是「点了没反应」。这里每次点击都问一次容器要活的实例。
     */
    function liveWorkspace() {
      try {
        const ctx = runtime.ctx
        const service = ctx && typeof ctx.get === 'function' ? ctx.get('uiWorkspace') : undefined
        if (service && typeof service.openSession === 'function') return service
      } catch {
        /* ctx 取不到就退回缓存 */
      }
      const cached = runtime.uiWorkspace
      return cached && typeof cached.openSession === 'function' ? cached : undefined
    }

    function openSessionById(sessionId) {
      const workspace = liveWorkspace()
      if (!workspace) return false
      try {
        workspace.openSession(sessionId)
        return true
      } catch {
        return false
      }
    }

    /** 会话真的打开了吗：主区挂出输入框才算数，否则说明 openSession 被静默吞掉了。 */
    function conversationMounted() {
      try {
        return Boolean(document.querySelector('[contenteditable="true"], textarea'))
      } catch {
        return false
      }
    }

    /**
     * 打开会话：客户端服务（uiWorkspace）可能还没挂好，先短暂重试；
     * 仍不可用就带深链整页重载一次，让 consumeDeepLink 在启动时接管；
     * 同一次页面生命周期里只兜底一次，避免反复重载。
     */
    let reloadedFor = ''

    function openSessionWithFallback(sessionId) {
      // 从面板回到会话：面板的聚焦态和地址栏里的「只看这一条」都不该跟着走。
      if (panelFocus.sessionId) clearPanelFocus()
      const fallbackToReload = () => {
        if (reloadedFor === sessionId) {
          showToast('这个界面没能打开会话，刷新一下页面再点一次', 'error')
          return
        }
        try {
          const url = new URL(window.location.href)
          url.hash = HASH_OPEN + encodeURIComponent(sessionId)
          reloadedFor = sessionId
          window.location.replace(url.toString())
          // 同文档只改 hash 不会重新加载，consumeDeepLink 没机会跑，强制刷一次
          window.location.reload()
        } catch {
          showToast('这个界面没能打开会话，刷新一下页面再点一次', 'error')
        }
      }
      let attempts = 0
      const attempt = () => {
        attempts += 1
        if (openSessionById(sessionId)) {
          // 调用没抛错，但界面没切过去也算失败（旧的 uiWorkspace 实例就是这样）
          setTimeout(() => {
            if (!conversationMounted()) fallbackToReload()
          }, 1_200)
          return
        }
        if (attempts < 12) {
          setTimeout(attempt, 250)
          return
        }
        fallbackToReload()
      }
      attempt()
    }

    function openOnPeer(peer, sessionId) {
      if (!peer) return
      const base = peer.url || `${String(peer.origin || '').replace(/\/$/, '')}/`
      const opened = window.open(`${base}#dsh-bridge-open=${encodeURIComponent(sessionId)}`, '_blank', 'noopener,noreferrer')
      if (!opened) showToast('弹窗被浏览器拦截了', 'error')
    }

    /** 对端带 `#dsh-bridge=<child>` 打开时落到那个会话；等客户端服务挂好再落。 */
    function consumeDeepLink() {
      const hash = String(window.location.hash || '')
      let sessionId
      let panelId
      if (hash.startsWith(HASH_HANDOFF)) {
        sessionId = safeDecode(hash.slice(HASH_HANDOFF.length))
      } else if (hash.startsWith(HASH_OPEN)) {
        sessionId = safeDecode(hash.slice(HASH_OPEN.length))
      } else if (hash.startsWith(HASH_OPEN_LEGACY)) {
        // open-in-peer 时代的旧链接
        sessionId = safeDecode(hash.slice(HASH_OPEN_LEGACY.length))
      } else if (hash.startsWith(HASH_PANEL)) {
        panelId = safeDecode(hash.slice(HASH_PANEL.length))
      }

      // 「只看这一条」的深链保留在地址栏里（刷新还回到这一条），
      // 等 layout 服务挂好再切面板，切不了就重试。
      if (panelId) {
        let tries = 0
        const openPanel = () => {
          tries += 1
          if (openInPanel(panelId)) return
          if (tries < 40) setTimeout(openPanel, 250)
        }
        setTimeout(openPanel, 200)
        return
      }

      if (!sessionId) return

      try {
        window.history.replaceState(null, '', window.location.pathname + window.location.search)
      } catch {
        /* 地址栏不可写也不影响打开会话 */
      }

      let attempts = 0
      const attempt = () => {
        attempts += 1
        if (openSessionById(sessionId)) return
        if (attempts < 40) setTimeout(attempt, 250)
      }
      setTimeout(attempt, 200)
    }

    function safeDecode(text) {
      try {
        return decodeURIComponent(text)
      } catch {
        return ''
      }
    }

    /* --------------------------------------------------------------- 注册 */

    return {
      inject: ['slots'],
      apply(ctx) {
        runtime.ctx = ctx
        try {
          ctx.inject(['uiWorkspace'], (scope) => {
            runtime.uiWorkspace = scope && scope.uiWorkspace
            return () => {
              runtime.uiWorkspace = undefined
            }
          })
        } catch {
          /* 没有 uiWorkspace 时深链静默失败 */
        }

        try {
          ctx.inject(['layout'], (scope) => {
            runtime.layout = scope && scope.layout
            return () => {
              runtime.layout = undefined
            }
          })
        } catch {
          /* 没有 layout 时跳面板退化成提示，页面照常可用 */
        }

        consumeDeepLink()

        ctx.slots.inject('conversation.session.header.utilities', () =>
          ctx.slots.register({ name: 'conversation.session.header.utilities', id: 'peer-bridge', order: 8 }, OwnerChip),
        )
        ctx.slots.inject('conversation.input.dock', () =>
          ctx.slots.register({ name: 'conversation.input.dock', id: 'peer-bridge', order: 8 }, MirrorDock),
        )
        ctx.slots.inject('sidebar.panellist', () =>
          ctx.slots.register({ name: 'sidebar.panellist', id: 'peer-bridge', order: 40, label: '双端会话' }, PanelIcon),
        )
        ctx.slots.inject('main', () =>
          ctx.slots.register({ name: 'main', key: 'peer-bridge' }, PeerBridgePage()),
        )
        ctx.slots.inject('shell.overlay', () =>
          ctx.slots.register({ name: 'shell.overlay', id: 'peer-bridge-toast', order: 50 }, ToastHost),
        )
      },
    }
  },
})
