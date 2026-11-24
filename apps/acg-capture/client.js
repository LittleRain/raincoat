window.__ModuleLoader__.load({
  id: '@local/acg-capture',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const { useEffect, useState, useCallback, useRef } = React

    const API = '/acg-capture/api'
    const TABS = [
      { key: 'discover', label: '抓新品' },
      { key: 'backfill', label: '补齐信息' },
      { key: 'channels', label: '抓取渠道' },
      { key: 'guide', label: '流程说明' },
    ]
    const REASON = {
      no_candidate: '没拿到候选',
      price_missing: '价格未找到',
      price_not_published: '来源未公布价格',
      count_missing: '数量未找到',
      count_not_published: '来源未公布数量',
      counts_unverified: '数量没核成',
      source_missing: '缺来源',
      source_unreachable: '来源打不开',
      quote_mismatch: '原文对不上',
      value_mismatch: '数字对不上',
      value_unverifiable: '原文找不到这个数',
      value_ambiguous: '页面里这个赏别有多个数',
      sum_mismatch: 'Σ 不等于抽数',
      total_missing: '缺整套抽数',
      total_not_published: '缺整套抽数',
      secondhand_forbidden: '二手来源',
      duplicate: '表内已存在',
      currency_unknown: '币种不明',
      manual_channel: '人工渠道',
      manual_reject: '人工判废',
      agent_timeout: 'Agent 超时',
      render_failed: '页面渲染不出',
      render_incomplete: '页面只渲染出一小段',
      quote_missing: '没给原文引用',
      quote_too_short: '原文引用太短',
      name_missing: '缺盘名',
      source_not_url: '来源不是链接',
    }
    const STAGES = ['准备', '分派', '等待', '验收', '写表', '完成']
    const STAGE_INDEX = {
      preparing: 0,
      discovering: 0,
      dispatch: 1,
      dispatching: 1,
      waiting: 2,
      accepting: 3,
      writing: 4,
      done: 5,
    }

    // ------------------------------------------------------------ 样式（全部走 token）
    const S = {
      page: {
        padding: '18px 22px 40px',
        color: 'var(--dsw-alias-label-primary)',
        background: 'var(--dsw-alias-bg-base)',
        // 宿主把面板放进 overflow:hidden 的固定高度容器里，内容再高也不会出现滚动条，
        // 下面的行会被直接裁掉（渠道表 21 条就踩过）。这里自己撑满并内部滚动。
        height: '100%',
        maxHeight: '100%',
        overflowY: 'auto',
        fontSize: 13,
        lineHeight: 1.55,
        boxSizing: 'border-box',
      },
      titleRow: { display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 12 },
      title: { fontSize: 16, fontWeight: 600 },
      muted: { color: 'var(--dsw-alias-label-tertiary)', fontSize: 12 },
      secondary: { color: 'var(--dsw-alias-label-secondary)' },
      tabBar: {
        display: 'flex',
        gap: 18,
        borderBottom: '1px solid var(--dsw-alias-border-l1)',
        marginBottom: 16,
      },
      tab: (active) => ({
        padding: '6px 0 8px',
        border: 'none',
        background: 'transparent',
        cursor: 'pointer',
        fontSize: 13,
        color: active ? 'var(--dsw-alias-label-primary)' : 'var(--dsw-alias-label-tertiary)',
        fontWeight: active ? 600 : 400,
        borderBottom: `2px solid ${active ? 'var(--dsw-alias-brand-primary)' : 'transparent'}`,
        marginBottom: -1,
      }),
      card: {
        border: '1px solid var(--dsw-alias-border-l1)',
        borderRadius: 10,
        background: 'var(--dsw-alias-bg-layer-1)',
        padding: '14px 16px',
        marginBottom: 14,
      },
      cardTight: {
        border: '1px solid var(--dsw-alias-border-l1)',
        borderRadius: 8,
        background: 'var(--dsw-alias-bg-layer-1)',
        padding: '8px 12px',
        marginBottom: 6,
      },
      row: { display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' },
      spacer: { flex: 1 },
      button: (primary) => ({
        padding: '6px 14px',
        borderRadius: 8,
        border: `1px solid ${primary ? 'transparent' : 'var(--dsw-alias-border-l1)'}`,
        background: primary ? 'var(--dsw-alias-brand-primary)' : 'var(--dsw-alias-bg-layer-2)',
        color: primary ? 'var(--dsw-alias-label-primary-inverted)' : 'var(--dsw-alias-label-primary)',
        cursor: 'pointer',
        fontSize: 13,
      }),
      ghost: {
        padding: '3px 10px',
        borderRadius: 6,
        border: '1px solid var(--dsw-alias-border-l1)',
        background: 'transparent',
        color: 'var(--dsw-alias-label-secondary)',
        cursor: 'pointer',
        fontSize: 12,
      },
      filterRow: { display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', margin: '2px 0 8px' },
      filterChip: (active) => ({
        padding: '2px 9px',
        borderRadius: 999,
        border: `1px solid ${active ? 'transparent' : 'var(--dsw-alias-border-l1)'}`,
        background: active ? 'var(--dsw-alias-brand-primary)' : 'transparent',
        color: active ? 'var(--dsw-alias-label-primary-inverted)' : 'var(--dsw-alias-label-secondary)',
        cursor: 'pointer',
        fontSize: 11.5,
        fontVariantNumeric: 'tabular-nums',
      }),
      input: {
        padding: '4px 8px',
        borderRadius: 6,
        border: '1px solid var(--dsw-alias-border-l1)',
        background: 'var(--dsw-alias-bg-base)',
        color: 'var(--dsw-alias-label-primary)',
        fontSize: 12,
        minWidth: 220,
      },
      statLabel: { fontSize: 11, color: 'var(--dsw-alias-label-tertiary)' },
      statValue: { fontSize: 18, fontWeight: 600 },
      rail: { display: 'flex', alignItems: 'center', gap: 6, margin: '14px 0 10px' },
      railDot: (state) => ({
        width: 8,
        height: 8,
        borderRadius: 4,
        background:
          state === 'done'
            ? 'var(--dsw-alias-state-success-primary)'
            : state === 'active'
              ? 'var(--dsw-alias-brand-primary)'
              : 'var(--dsw-alias-border-l2)',
      }),
      railLabel: (state) => ({
        fontSize: 12,
        color:
          state === 'active'
            ? 'var(--dsw-alias-label-primary)'
            : state === 'done'
              ? 'var(--dsw-alias-label-secondary)'
              : 'var(--dsw-alias-label-tertiary)',
      }),
      railLine: { flex: 1, height: 1, background: 'var(--dsw-alias-border-l1)', minWidth: 12 },
      table: { width: '100%', borderCollapse: 'collapse', fontSize: 12.5 },
      th: {
        textAlign: 'left',
        padding: '6px 8px',
        color: 'var(--dsw-alias-label-tertiary)',
        fontWeight: 500,
        borderBottom: '1px solid var(--dsw-alias-border-l1)',
        whiteSpace: 'nowrap',
      },
      td: {
        padding: '7px 8px',
        borderBottom: '1px solid var(--dsw-alias-border-l1)',
        verticalAlign: 'top',
      },
      badge: (tone) => ({
        display: 'inline-block',
        padding: '1px 8px',
        borderRadius: 999,
        fontSize: 11.5,
        whiteSpace: 'nowrap',
        background:
          tone === 'ok'
            ? 'color-mix(in srgb, var(--dsw-alias-state-success-primary) 12%, transparent)'
            : tone === 'bad'
              ? 'color-mix(in srgb, var(--dsw-alias-state-error-primary) 12%, transparent)'
              : tone === 'warn'
                ? 'color-mix(in srgb, var(--dsw-alias-state-warn-primary) 14%, transparent)'
                : 'color-mix(in srgb, var(--dsw-alias-label-tertiary) 12%, transparent)',
        color:
          tone === 'ok' || tone === 'bad' || tone === 'warn'
            ? `color-mix(in srgb, var(--dsw-alias-state-${tone === 'ok' ? 'success' : tone === 'bad' ? 'error' : 'warn'}-primary) 55%, var(--dsw-alias-label-primary))`
            : 'var(--dsw-alias-label-secondary)',
      }),
      // 三个任务页的「抓取配置」和「当前状态」都用这一套尺寸，
      // 换 tab 时按钮、下拉、统计块的位置不该跳。
      configRow: { display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap' },
      field: { display: 'flex', flexDirection: 'column', gap: 3 },
      fieldLabel: { fontSize: 11, color: 'var(--dsw-alias-label-tertiary)' },
      select: {
        padding: '4px 8px',
        borderRadius: 6,
        border: '1px solid var(--dsw-alias-border-l1)',
        background: 'var(--dsw-alias-bg-base)',
        color: 'var(--dsw-alias-label-primary)',
        fontSize: 12,
      },
      chip: {
        padding: '4px 10px',
        borderRadius: 6,
        border: '1px dashed var(--dsw-alias-border-l2)',
        color: 'var(--dsw-alias-label-secondary)',
        fontSize: 12,
      },
      runRow: (active, hover) => ({
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        padding: '8px 10px',
        borderRadius: 8,
        cursor: 'pointer',
        outline: 'none',
        borderLeft: `2px solid ${active ? 'var(--dsw-alias-brand-primary)' : 'transparent'}`,
        background: active
          ? 'color-mix(in srgb, var(--dsw-alias-brand-primary) 10%, transparent)'
          : hover
            ? 'var(--dsw-alias-bg-layer-2)'
            : 'transparent',
      }),
      query: {
        display: 'flex',
        alignItems: 'flex-start',
        gap: 4,
        marginTop: 8,
        padding: '6px 10px',
        borderRadius: 6,
        background: 'var(--dsw-alias-bg-layer-2)',
        color: 'var(--dsw-alias-label-secondary)',
        lineHeight: 1.5,
      },
      step: { display: 'flex', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--dsw-alias-border-l1)' },
      stepLast: { display: 'flex', gap: 12, padding: '10px 0' },
      stepNum: {
        flex: '0 0 24px',
        width: 24,
        height: 24,
        borderRadius: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 12,
        fontWeight: 600,
        color: 'var(--dsw-alias-label-primary-inverted)',
        background: 'var(--dsw-alias-brand-primary)',
      },
      stepTitle: { fontWeight: 600, marginBottom: 2 },
      stepBody: { fontSize: 12.5, color: 'var(--dsw-alias-label-secondary)', lineHeight: 1.6 },
      kbd: {
        padding: '0 5px',
        borderRadius: 4,
        border: '1px solid var(--dsw-alias-border-l2)',
        background: 'var(--dsw-alias-bg-layer-2)',
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 11.5,
      },
      faqQ: { fontWeight: 600, marginTop: 10, fontSize: 12.5 },
      faqA: { fontSize: 12.5, color: 'var(--dsw-alias-label-secondary)', lineHeight: 1.6 },
      pill: {
        padding: '0 6px',
        borderRadius: 999,
        fontSize: 10.5,
        lineHeight: '16px',
        color: 'color-mix(in srgb, var(--dsw-alias-brand-primary) 70%, var(--dsw-alias-label-primary))',
        background: 'color-mix(in srgb, var(--dsw-alias-brand-primary) 14%, transparent)',
        whiteSpace: 'nowrap',
      },
      empty: { padding: '18px 6px', color: 'var(--dsw-alias-label-tertiary)', fontSize: 12.5 },
      error: {
        marginTop: 8,
        padding: '6px 10px',
        borderRadius: 6,
        fontSize: 12,
        color: 'color-mix(in srgb, var(--dsw-alias-state-error-primary) 55%, var(--dsw-alias-label-primary))',
        background: 'color-mix(in srgb, var(--dsw-alias-state-error-primary) 10%, transparent)',
      },
      code: { fontSize: 11.5, color: 'var(--dsw-alias-label-tertiary)' },
      // 「为什么要你看」那一行：待确认是正文色，未公布（不用你管）压成次要色
      ask: (muted) => ({
        fontSize: 12,
        lineHeight: 1.5,
        color: muted ? 'var(--dsw-alias-label-tertiary)' : 'var(--dsw-alias-label-primary)',
        borderLeft: '2px solid var(--dsw-alias-border-l2)',
        paddingLeft: 8,
      }),
      evidence: {
        margin: '6px 0 10px 8px',
        padding: '8px 10px',
        borderLeft: '2px solid var(--dsw-alias-border-l2)',
        fontSize: 11.5,
        color: 'var(--dsw-alias-label-secondary)',
      },
    }

    // ------------------------------------------------------------ 数据
    async function api(path, options = {}) {
      const response = await fetch(`${API}${path}`, {
        credentials: 'same-origin',
        headers: options.body ? { 'content-type': 'application/json' } : undefined,
        ...options,
      })
      const text = await response.text()
      let body = null
      try {
        body = text ? JSON.parse(text) : null
      } catch {
        body = { error: text.slice(0, 200) }
      }
      if (!response.ok) throw new Error(body?.error || `HTTP ${response.status}`)
      return body
    }

    // ------------------------------------------------------------ 界面状态持久化
    // 侧边栏切到别的面板时宿主会卸载这棵树，useState 全丢，回来就回到「抓新品 + 没选中运行」。
    // 上一轮看到哪儿（哪个一级 tab、哪个子页、选中的是哪条运行、滚到哪）写进 localStorage，
    // 回来原样恢复；换台机器/清缓存就退回默认值，不影响功能。
    const UI_KEY = 'acg-ui-state'

    function readUiState() {
      try {
        const raw = window.localStorage.getItem(UI_KEY)
        const parsed = raw ? JSON.parse(raw) : null
        return parsed && typeof parsed === 'object' ? parsed : {}
      } catch {
        return {}
      }
    }

    function writeUiState(key, value) {
      try {
        const state = readUiState()
        state[key] = value
        window.localStorage.setItem(UI_KEY, JSON.stringify(state))
      } catch {
        /* 隐私模式写不了，不影响使用 */
      }
    }

    /** useState 的持久化版：初值优先取上次的，变了就写回去。 */
    function useUi(key, initial) {
      const [value, setValue] = useState(() => {
        const stored = readUiState()[key]
        if (stored === undefined || stored === null) return typeof initial === 'function' ? initial() : initial
        return stored
      })
      useEffect(() => {
        writeUiState(key, value)
      }, [key, value])
      return [value, setValue]
    }

    function initialScene() {
      const stored = readUiState().scene
      if (['kuji', 'bag', 'vg'].includes(stored)) return stored
      try {
        const legacy = window.localStorage.getItem('acg-scene')
        if (['kuji', 'bag', 'vg'].includes(legacy)) return legacy
      } catch {
        /* 老版本存的是单个 key，读不到就用默认 */
      }
      return 'kuji'
    }

    function fmtTime(iso) {
      if (!iso) return '—'
      const date = new Date(iso)
      if (Number.isNaN(date.getTime())) return iso
      const pad = (n) => String(n).padStart(2, '0')
      return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    }

    function ago(iso) {
      if (!iso) return ''
      const diff = Date.now() - new Date(iso).getTime()
      if (Number.isNaN(diff)) return ''
      if (diff < 60_000) return '刚刚'
      if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
      if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
      return `${Math.floor(diff / 86_400_000)} 天前`
    }

    function statusTone(status) {
      if (status === 'accepted') return 'ok'
      if (status === 'rejected') return 'bad'
      if (status === 'pending_review' || status === 'partial') return 'warn'
      if (status === 'interrupted' || status === 'failed') return 'bad'
      return undefined
    }

    function statusLabel(status) {
      return (
        {
          accepted: '已采纳',
          rejected: '判废',
          pending_review: '待确认',
          duplicate: '重复',
          // 来源没公布：没有可确认的内容，不进人工裁决队列
          unavailable: '来源未公布',
          done: '完成',
          running: '执行中',
          partial: '部分完成',
          failed: '失败',
          interrupted: '中断',
        }[status] || status
      )
    }

    // 逐条候选按结论筛选：三个 tab 的任务详情共用同一套口径。
    // 顺序固定（待确认在最前，人要先看它），未列出的状态按出现顺序补在后面。
    const ITEM_STATUS_ORDER = ['pending_review', 'accepted', 'rejected', 'duplicate', 'unavailable']

    function itemStatusCounts(items) {
      const counts = new Map()
      for (const item of items || []) {
        const status = item.status || 'unknown'
        counts.set(status, (counts.get(status) || 0) + 1)
      }
      const ordered = ITEM_STATUS_ORDER.filter((status) => counts.has(status))
      for (const status of counts.keys()) if (!ordered.includes(status)) ordered.push(status)
      return ordered.map((status) => ({ status, count: counts.get(status) }))
    }

    function filterItemsByStatus(items, filter) {
      if (!filter || filter === 'all') return items
      return items.filter((item) => (item.status || 'unknown') === filter)
    }

    function ItemStatusFilter({ items, value, onChange, labelOf = statusLabel }) {
      const groups = itemStatusCounts(items)
      // 只有一种结论时没什么可筛的，别多摆一排按钮
      if (groups.length < 2) return null
      const options = [
        { status: 'all', label: '全部', count: (items || []).length },
        ...groups.map((group) => ({ status: group.status, label: labelOf(group.status), count: group.count })),
      ]
      return h(
        'div',
        { style: S.filterRow },
        options.map((option) => {
          const active = (value || 'all') === option.status
          return h(
            'button',
            {
              key: option.status,
              type: 'button',
              'aria-pressed': active,
              title: `只看${option.label}`,
              style: S.filterChip(active),
              onClick: () => onChange(option.status),
            },
            `${option.label} ${option.count}`,
          )
        }),
      )
    }

    function reasonText(reasons) {
      if (!reasons || !reasons.length) return '—'
      const labels = []
      for (const reason of reasons) {
        const key = String(reason).split(':')[0]
        const label = REASON[key] || String(reason)
        if (!labels.includes(label)) labels.push(label)
        if (labels.length >= 3) break
      }
      return labels.join('、')
    }

    // ------------------------------------------------------------ 组件
    function Badge({ status, label, tone }) {
      return h('span', { style: S.badge(tone || statusTone(status)) }, label || statusLabel(status))
    }

    function Rail({ stage }) {
      const active = STAGE_INDEX[stage] ?? 0
      const nodes = []
      STAGES.forEach((label, index) => {
        if (index > 0) nodes.push(h('div', { key: `l${index}`, style: S.railLine }))
        const state = index < active ? 'done' : index === active ? 'active' : 'idle'
        nodes.push(
          h(
            'div',
            { key: `s${index}`, style: { display: 'flex', alignItems: 'center', gap: 6 } },
            h('div', { style: S.railDot(state) }),
            h('span', { style: S.railLabel(state) }, label),
          ),
        )
      })
      return h('div', { style: S.rail }, nodes)
    }

    function Stat({ label, value }) {
      return h(
        'div',
        null,
        h('div', { style: S.statLabel }, label),
        h('div', { style: S.statValue }, value),
      )
    }

    // ------------------------------------------------------------ 三个任务页共用的两块
    // 2026-11-18：以前只有「游戏虚拟商品」有配置项和当前状态，另外两个 tab 只有一个开始按钮，
    // 同一件事在三个页面长得不一样。现在三页都用下面两个组件，结构和间距对齐：
    //   抓取配置（想抓什么 / 通道 / 是否写表）→ 当前状态（台账现在缺什么）→ 运行记录 → 详情。

    /** 带小标签的下拉：标签在控件上方，三个任务页的配置项长得一样。 */
    function ConfigField({ label, children }) {
      return h('div', { style: S.field }, h('span', { style: S.fieldLabel }, label), children)
    }

    function Select({ value, options, onChange, disabled }) {
      return h(
        'select',
        {
          value,
          disabled,
          style: S.select,
          onChange: (event) => onChange(event.target.value),
        },
        options.map(([optionValue, label]) => h('option', { key: String(optionValue), value: optionValue }, label)),
      )
    }

    /**
     * 抓取配置卡：标题固定「抓取配置」，下面是这个任务自己的几项参数，
     * 右边统一是「写回表格」+ 开始按钮（位置不随任务变）。
     */
    function TaskConfig({ hint, fields, note, write, onWrite, onStart, busy, running, actionLabel }) {
      const disabled = busy || running
      return h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 10 } },
          h('span', { style: S.title }, '抓取配置'),
          h('span', { style: S.secondary, fontSize: 12 }, hint),
        ),
        h(
          'div',
          { style: S.configRow },
          ...(fields || []),
          note ? h('span', { style: S.chip }, note) : null,
          h('div', { style: S.spacer }),
          h(
            'label',
            { style: { ...S.secondary, display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 } },
            h('input', { type: 'checkbox', checked: write, onChange: (event) => onWrite(event.target.checked) }),
            '写回表格',
          ),
          h('button', { type: 'button', style: S.button(true), onClick: onStart, disabled }, busy ? '启动中…' : actionLabel || '开始抓取'),
        ),
      )
    }

    /**
     * 当前状态卡：这个任务要补的台账现在什么样。数据没回来时也占位，
     * 免得卡片在加载完成后突然把下面的运行记录顶下去。
     */
    function StatusCard({ subtitle, stats, onRefresh }) {
      const rows = stats && stats.length ? stats : [{ label: '读取中', value: '—' }]
      return h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 10 } },
          h('span', { style: S.title }, '当前状态'),
          h('span', { style: S.secondary, fontSize: 12 }, subtitle || '读取中…'),
          h('div', { style: S.spacer }),
          onRefresh ? h('button', { type: 'button', style: S.ghost, onClick: onRefresh }, '刷新') : null,
        ),
        h('div', { style: S.row }, rows.map((row) => h(Stat, { key: row.label, label: row.label, value: row.value }))),
      )
    }

    function isoDay(daysAgo) {
      const date = new Date(Date.now() - Number(daysAgo || 0) * 86_400_000)
      const pad = (n) => String(n).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    }

    const FIELD_LABEL = { price: '单抽价', count: '数量', new: '新盘' }

    function fieldLabel(field) {
      return FIELD_LABEL[field] || field
    }

    /** 这条缺哪几项：新运行有 fields（逐字段结论），老运行只有 gap 字符串。 */
    function gapFields(item) {
      if (Array.isArray(item?.gaps) && item.gaps.length) return item.gaps
      if (item?.fields && typeof item.fields === 'object') return Object.keys(item.fields)
      return String(item?.gap || '').split('+').filter(Boolean)
    }

    /** 候选里真的有值、能写进表的那几项 —— 一个都没有就不该让点「采纳」。 */
    function writableFields(item) {
      const candidate = item.candidate || {}
      return gapFields(item).filter((field) => {
        if (item.fields && item.fields[field] === 'accepted') return true
        if (field === 'price') {
          const value = (candidate.price || {}).value
          return value !== undefined && value !== null
        }
        if (field === 'count') {
          return (candidate.prizes || []).some(
            (prize) => prize.kind && prize.count !== undefined && prize.count !== null,
          )
        }
        return false
      })
    }

    /** 老运行没有 ask 字段：用 reason 拼一句，至少说清是「机器核不了」还是「来源没有」。 */
    function askFallback(item) {
      const reason = reasonText(item.reasons)
      const tail = reason && reason !== '—' ? `（${reason}）` : ''
      if (item.status === 'unavailable') return `来源没有这个数${tail}，这轮没有可确认的东西，等下一轮自动再补。`
      return `机器判断不了${tail}，需要你打开来源核对：核对得上就采纳，对不上就判废。`
    }

    function ItemRow({ item, run, onChanged }) {
      const [source, setSource] = useState('')
      const [note, setNote] = useState('')
      const [busy, setBusy] = useState('')
      const [error, setError] = useState('')
      const pending = item.status === 'pending_review'
      // 来源未公布：没有可确认的内容，不给「采纳」，也不装作在等人
      const unavailable = item.status === 'unavailable'
      const columns = run.kind === 'discover' ? 6 : 5
      // 抓新品的待确认没有「缺口字段」要写：采纳就是建一行新盘，永远可写
      const writable = run.kind === 'discover' ? ['new'] : writableFields(item)
      // 老运行没有逐条 written 标记：发现类「采纳数 == 写入数」时可以安全反推
      const inferred =
        item.written ??
        (run.kind === 'discover' &&
          item.status === 'accepted' &&
          !run.dryRun &&
          (run.counts?.accepted || 0) > 0 &&
          (run.counts?.written || 0) >= (run.counts?.accepted || 0))
      const written = inferred
        ? { tone: 'ok', label: item.writtenParts?.length ? `已写入（${item.writtenParts.join('+')}）` : '已写入表' }
        : item.status === 'accepted'
          ? { tone: 'warn', label: run.dryRun ? '仅候选（dry-run）' : '未写入' }
          : { tone: null, label: '—' }

      const decide = async (decision) => {
        setBusy(decision)
        setError('')
        try {
          const result = await api(`/runs/${run.id}/items/${item.id}/decide`, {
            method: 'POST',
            body: JSON.stringify({ decision, note, source }),
          })
          if (result?.written) {
            const total = (result.written.price || 0) + (result.written.counts || 0)
            setNote(`已写入 ${total} 条`)
          }
          await onChanged()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy('')
        }
      }

      const main = h(
        'tr',
        { key: item.id },
        h('td', { style: S.td }, item.pan || '—'),
        run.kind === 'discover' ? h('td', { style: S.td }, item.brand || '—') : h('td', { style: S.td }, item.gap === 'price+count' ? '价格 + 数量' : item.gap === 'price' ? '价格' : '数量'),
        run.kind === 'discover' ? h('td', { style: S.td }, item.candidate?.release || '—') : null,
        h('td', { style: S.td }, h(Badge, { status: item.status })),
        h('td', { style: S.td }, h(Badge, { tone: written.tone, label: written.label })),
        h(
          'td',
          { style: { ...S.td, color: 'var(--dsw-alias-label-secondary)' } },
          // 待确认/未公布先说人话「为什么要人看」，再补机器原因，最后才是已采纳的值
          pending || unavailable ? h('div', { style: { ...S.ask(unavailable), marginBottom: 4 } }, item.ask || askFallback(item)) : null,
          pending || unavailable ? null : reasonText(item.reasons),
          item.price ? h('div', { style: S.code }, `价格 ${item.price.value}（${item.price.currency}）`) : null,
          item.counts ? h('div', { style: S.code }, `数量 ${item.counts.length} 赏 · Σ=${item.total}`) : null,
          item.decidedBy === 'human' ? h('div', { style: S.code }, `人工裁决${item.note ? `：${item.note}` : ''}`) : null,
        ),
      )

      if (!pending && !unavailable) return main

      if (unavailable) {
        const notice = h(
          'tr',
          { key: `${item.id}-act` },
          h(
            'td',
            { colSpan: columns, style: { ...S.td, background: 'var(--dsw-alias-bg-layer-2)' } },
            h('div', { style: { ...S.muted } },
              '不需要你确认：来源没有这个数，采纳也写不进任何东西。下一轮按表内缺口自动再补。'),
          ),
        )
        return [main, notice]
      }

      const action = h(
        'tr',
        { key: `${item.id}-act` },
        h(
          'td',
          { colSpan: columns, style: { ...S.td, background: 'var(--dsw-alias-bg-layer-2)' } },
          h(
            'div',
            { style: S.row },
            h('input', {
              value: source,
              onChange: (event) => setSource(event.target.value),
              placeholder: '你人工核对过的来源 URL（可留空）',
              style: S.input,
            }),
            h('input', {
              value: note,
              onChange: (event) => setNote(event.target.value),
              placeholder: '备注（判废原因 / 采纳依据）',
              style: { ...S.input, flex: 1, minWidth: 200 },
            }),
            h('button', {
              type: 'button',
              style: S.button(true),
              disabled: Boolean(busy) || !writable.length,
              title: writable.length ? '' : '候选里没有可写入的值，采纳写不进任何东西',
              onClick: () => decide('accept'),
            }, busy === 'accept' ? '写入中…' : `采纳并写入（${writable.map(fieldLabel).join('+') || '无可写字段'}）`),
            h('button', { type: 'button', style: S.ghost, disabled: Boolean(busy), onClick: () => decide('reject') },
              busy === 'reject' ? '处理中…' : '判废'),
          ),
          h('div', { style: { ...S.muted, marginTop: 4 } },
            !writable.length
              ? '候选里没有能写进表的数字，采纳按钮不可用；这条只能判废，或者等下一轮。'
              : run.kind === 'discover'
                ? '采纳：把这条候选建进主表（新盘一行），记下你的来源与备注；判废：只标记，不写表。'
                : `采纳：把候选的${writable.map(fieldLabel).join('、')}写进表格（你要是核对过，填上来源 URL），记下你的来源与备注；判废：只标记，不写表。`),
          error ? h('div', { style: S.error }, error) : null,
        ),
      )
      return [main, action]
    }

    function ItemTable({ run, onChanged }) {
      const [filter, setFilter] = useUi(`items:filter:${run?.kind || 'discover'}`, 'all')
      const items = run.items || []
      if (!items.length) {
        return h('div', { style: S.empty }, run.status === 'running' ? '正在跑，结果还没出来…' : '本轮没有产出条目')
      }
      const discover = run.kind === 'discover'
      const shown = filterItemsByStatus(items, filter)
      return h(
        'div',
        null,
        h(ItemStatusFilter, { items, value: filter, onChange: setFilter }),
        shown.length
          ? h(
              'table',
              { style: S.table },
              h(
                'thead',
                null,
                h(
                  'tr',
                  null,
                  h('th', { style: S.th }, discover ? '盘名' : '赏盘'),
                  discover ? h('th', { style: S.th }, '品牌') : h('th', { style: S.th }, '缺什么'),
                  discover ? h('th', { style: S.th }, '发售日') : null,
                  h('th', { style: S.th }, '结论'),
                  h('th', { style: S.th }, '写入'),
                  h('th', { style: S.th }, '说明 / 来源'),
                ),
              ),
              h(
                'tbody',
                null,
                shown.map((item, index) => h(ItemRow, { key: item.id || index, item, run, onChanged })),
              ),
            )
          : h('div', { style: S.empty }, `「${statusLabel(filter)}」下没有条目`),
      )
    }

    function md(iso) {
      if (!iso) return ''
      const date = new Date(iso)
      if (Number.isNaN(date.getTime())) return ''
      const pad = (n) => String(n).padStart(2, '0')
      return `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    }

    function durationText(run) {
      if (!run?.startedAt || !run?.endedAt) return ''
      const ms = new Date(run.endedAt).getTime() - new Date(run.startedAt).getTime()
      if (!Number.isFinite(ms) || ms < 0) return ''
      const total = Math.round(ms / 1000)
      if (total < 60) return `${total} 秒`
      const minutes = Math.floor(total / 60)
      const seconds = total % 60
      return seconds ? `${minutes} 分 ${seconds} 秒` : `${minutes} 分`
    }

    function triggerLabel(trigger) {
      return { schedule: '定时', resume: '回收结果', reaccept: '重跑验收' }[trigger] || '手动'
    }

    function runHeadline(run) {
      if (!run) return '未选择运行'
      if (run.kind === 'backfill') {
        // params.batchSize 只是上限（默认 999 = 全部），说「补几个盘」要看本批实际派了几个
        const size = run.batchCount || run.batch?.length || 0
        return size ? `补齐信息 · 本轮补 ${size} 个盘` : '补齐信息'
      }
      const since = md(run.params?.since)
      const until = md(run.params?.until)
      return since && until ? `抓新品 ${since} → ${until}` : '抓新品'
    }

    function runStats(run) {
      const counts = run?.counts || {}
      // 列表接口给 itemCount，详情接口只有 items 数组
      const items = run?.itemCount ?? (Array.isArray(run?.items) ? run.items.length : 0)
      const stats = [
        ['候选', items],
        ['采纳', counts.accepted || 0],
        ['判废', counts.rejected || 0],
        ['待确认', counts.pending || 0],
      ]
      // 来源未公布：不用人管，单列出来，免得跟「待确认」混成一片
      if (counts.unavailable) stats.push(['未公布', counts.unavailable])
      stats.push(['写入', counts.written || 0])
      return stats
    }

    function runMeta(run) {
      const bits = [triggerLabel(run.trigger), fmtTime(run.startedAt)]
      const spent = durationText(run)
      if (spent) bits.push(`用时 ${spent}`)
      if (run.dryRun) bits.push('dry-run 未写表')
      if (run.params?.groups) bits.push(`${run.params.groups} 组并行`)
      return bits.join(' · ')
    }

    const CHANNEL_LABEL = { weibo: '微博', wechat: '公众号', xhs: '小红书', static: '官网', miniapp: '小程序' }
    const CHANNEL_ORDER = { weibo: 0, wechat: 1, xhs: 2, static: 3, miniapp: 4 }

    const GAP_LABEL = { price: '价格', count: '数量', sub: '子品结构', new: '新盘' }

    function gapLabel(gap) {
      const parts = String(gap || '').split('+').filter(Boolean)
      return parts.length ? parts.map((part) => GAP_LABEL[part] || part).join('+') : ''
    }

    function batchItems(run) {
      return (Array.isArray(run?.batch) ? run.batch : []).map((item) => ({
        name: item.pan || '未命名',
        gaps: Array.isArray(item.gaps) ? item.gaps : [],
      }))
    }

    function gapTally(items) {
      let price = 0
      let count = 0
      let sub = 0
      for (const item of items) {
        if (item.gaps.includes('price')) price += 1
        if (item.gaps.includes('count')) count += 1
        if (item.gaps.includes('sub')) sub += 1
      }
      return { price, count, sub }
    }

    /** 一句话说清「这一轮在抓什么」：渠道？哪类盘？补什么？ */
    function scopeLines(run) {
      if (!run) return []
      const scope = run.scope || {}
      if (run.kind === 'backfill' || scope.mode === 'fill_gaps') {
        const items = batchItems(run).length
          ? batchItems(run)
          : (scope.pans || []).map((pan) => ({ name: pan.name || '', gaps: pan.gaps || [] }))
        if (!items.length) return ['补缺口：本批盘子还没算出来']
        const tally = gapTally(items)
        const parts = [
          tally.sub ? `子品结构 ${tally.sub}` : '',
          tally.price ? `价格 ${tally.price}` : '',
          tally.count ? `数量 ${tally.count}` : '',
        ].filter(Boolean)
        return [
          `补缺口：${items.length} 个盘${parts.length ? `（${parts.join(' · ')}）` : ''}`,
          items.map((item) => `${item.name}${item.gaps.length ? `（${item.gaps.map(gapLabel).join('+')}）` : ''}`).join('、'),
        ]
      }
      const brands = Array.isArray(scope.brands) ? scope.brands : []
      const types = scope.channels || {}
      const feeds = run.feeds || {}
      const groups = Array.isArray(scope.groups) ? scope.groups : []
      if (!brands.length && !Object.keys(types).length) {
        // 老运行没存 scope：退回「渠道数 / 原文条数 / 分组」，至少看得出规模
        const paramsOld = run.params || {}
        return [
          `${run.table?.confirmed ?? '—'} 个已确认渠道 · 原文 ${feeds.items ?? 0} 条`,
          `${paramsOld.groups ?? '—'} 组 · 每号 ${paramsOld.pages ?? '—'} 页`,
        ]
      }
      const channelText = Object.keys(types)
        .sort((a, b) => (CHANNEL_ORDER[a] ?? 9) - (CHANNEL_ORDER[b] ?? 9))
        .map((key) => `${CHANNEL_LABEL[key] || key} ${types[key]}`)
        .join(' · ')
      const lines = [`抓新盘：${brands.length} 个品牌 / ${channelText || '—'}`]
      lines.push(
        `窗口 ${md(scope.window?.since) || '—'} → ${md(scope.window?.until) || '—'} · 每号 ${scope.pages ?? run.params?.pages ?? '—'} 页 · 原文 ${feeds.items ?? 0} 条${feeds.errors ? `（${feeds.errors} 个渠道失败）` : ''}`,
      )
      if (groups.length) {
        lines.push(`分组 ${groups.map((group) => `${group.name}：${group.brands.join('、')}`).join(' ｜ ')}`)
      }
      const ds = feeds.ds || {}
      if (ds.queries) {
        lines.push(
          `DS 搜索 ${ds.queries} 次 · 公众号候选 ${ds.hits ?? 0} 条${ds.errors ? ` · ${ds.errors} 次失败` : ''}（公众号渠道交给 workbuddy 判定）`,
        )
      }
      return lines
    }

    function scopeBrief(run, compact) {
      if (!run) return ''
      const lines = scopeLines(run)
      if (!compact) return lines.join('　')
      if (run.kind === 'backfill' || (run.scope || {}).mode === 'fill_gaps') {
        const names = lines[1] ? lines[1].split('、') : []
        return `${lines[0]}　${names.slice(0, 2).map(shortName).join('、')}${names.length > 2 ? ' 等' : ''}`
      }
      const scope = run.scope || {}
      const types = scope.channels || {}
      if (!Object.keys(types).length) return lines.join(' · ')
      const channelText = Object.keys(types)
        .sort((a, b) => (CHANNEL_ORDER[a] ?? 9) - (CHANNEL_ORDER[b] ?? 9))
        .map((key) => `${CHANNEL_LABEL[key] || key} ${types[key]}`)
        .join(' · ')
      const feeds = run.feeds || {}
      const dsCount = feeds.ds?.queries ? ` · DS ${feeds.ds.hits ?? 0} 条` : ''
      return `${(scope.brands || []).length} 个品牌 / ${channelText}　原文 ${feeds.items ?? 0} 条 · ${(scope.groups || []).length || run.params?.groups || '—'} 组${dsCount}`
    }

    function shortName(name) {
      return name.length > 20 ? `${name.slice(0, 20)}…` : name
    }

    function RunList({ runs, current, onPick, limit }) {
      const [hover, setHover] = useState('')
      if (!runs.length) return h('div', { style: S.empty }, '还没有运行记录，点上面的按钮跑一轮')
      return h(
        'div',
        { style: { display: 'flex', flexDirection: 'column', gap: 2 } },
        runs.slice(0, limit || 5).map((run) => {
          const active = run.id === current
          return h(
            'div',
            {
              key: run.id,
              role: 'button',
              tabIndex: 0,
              'aria-current': active ? 'true' : undefined,
              style: S.runRow(active, hover === run.id),
              onClick: () => onPick(run.id),
              onKeyDown: (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onPick(run.id)
                }
              },
              onMouseEnter: () => setHover(run.id),
              onMouseLeave: () => setHover(''),
            },
            h(
              'div',
              { style: { flex: 1, minWidth: 0 } },
              h(
                'div',
                { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
                h(Badge, { status: run.status }),
                h('span', { style: { fontWeight: active ? 600 : 500 } }, runHeadline(run)),
                active ? h('span', { style: S.pill }, '查看中') : null,
                run.error && run.status !== 'running'
                  ? h('span', { style: { ...S.muted, color: 'color-mix(in srgb, var(--dsw-alias-state-warn-primary) 55%, var(--dsw-alias-label-primary))' } }, '有异常')
                  : null,
              ),
              h(
                'div',
                { style: { ...S.muted, marginTop: 2 } },
                runStats(run)
                  .filter(([label, value], index) => index === 0 || value)
                  .map(([label, value], index) => h('span', { key: label }, `${index ? ' · ' : ''}${label} ${value}`)),
                h('span', null, `　${runMeta(run)}`),
              ),
              h('div', { style: { ...S.muted, marginTop: 2, fontSize: 11.5 } }, scopeBrief(run, true)),
            ),
            h('span', { style: { ...S.muted, whiteSpace: 'nowrap' } }, ago(run.startedAt)),
          )
        }),
      )
    }

    function RunView({ kind }) {
      const [runs, setRuns] = useState([])
      const [run, setRun] = useState(null)
      // 恢复上次看的那条运行；它已经被清理时退回最新一条
      const [selected, setSelected] = useUi('run:' + kind, '')
      const [snapshot, setSnapshot] = useState(null)
      const [channelRows, setChannelRows] = useState([])
      // 配置项记在 localStorage 里：换 tab 再回来还是上次选的那组参数。
      // 「写回表格」故意不记：默认永远是 dry-run，免得下次打开手一滑就写表。
      const [windowDays, setWindowDays] = useUi('kuji:window', 'auto')
      const [batch, setBatch] = useUi('kuji:batch', '999')
      const [write, setWrite] = useState(false)
      const [busy, setBusy] = useState(false)
      const [error, setError] = useState('')
      const [expanded, setExpanded] = useUi('runs:expanded:' + kind, false)
      const detailRef = useRef(null)

      const pick = (id) => {
        setSelected(id)
        // 列表在上、详情在下：点一行就把详情带到眼前，免得还要自己往下滚
        requestAnimationFrame(() => {
          detailRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
        })
      }

      const loadRuns = useCallback(async () => {
        try {
          const data = await api(`/runs?kind=${kind}`)
          const list = data.runs || []
          setRuns(list)
          // 上次看的那条可能已经被清理：只有它还在列表里才保留，否则退回最新一条
          if (list.length && !list.some((item) => item.id === selected)) setSelected(list[0].id)
          return list
        } catch (err) {
          setError(String(err.message || err))
          return []
        }
      }, [kind, selected])

      useEffect(() => {
        loadRuns()
        // 当前状态两个子页都要看：抓新品看「表里现在有多少盘」，补齐信息看「缺口还剩多少」
        api('/snapshot')
          .then((data) => setSnapshot(data))
          .catch(() => setSnapshot({ error: '台账读取失败' }))
        api('/channels')
          .then((data) => setChannelRows(data.brands || []))
          .catch(() => setChannelRows([]))
      }, [kind])

      useEffect(() => {
        if (!selected) return undefined
        let alive = true
        const load = async () => {
          try {
            const data = await api(`/runs/${selected}`)
            if (alive) {
              setRun(data.run)
              setError('')
            }
          } catch (err) {
            if (alive) setError(String(err.message || err))
          }
        }
        load()
        const timer = setInterval(async () => {
          const list = await loadRuns()
          if (!alive) return
          const current = list.find((item) => item.id === selected)
          if (!run || current?.status === 'running') await load()
        }, 2500)
        return () => {
          alive = false
          clearInterval(timer)
        }
      }, [selected, run?.status])

      const reload = useCallback(async () => {
        await loadRuns()
        try {
          const data = await api(`/runs/${selected}`)
          setRun(data.run)
        } catch {
          /* 运行可能刚被清理，保留上一次视图 */
        }
      }, [selected, loadRuns])

      const reloadStatus = useCallback(async () => {
        setSnapshot(null)
        try {
          setSnapshot(await api('/snapshot?force=1'))
        } catch (err) {
          setSnapshot({ error: String(err.message || err) })
        }
        try {
          const data = await api('/channels')
          setChannelRows(data.brands || [])
        } catch {
          /* 渠道读不到不影响缺口状态 */
        }
      }, [])

      const start = async () => {
        setBusy(true)
        setError('')
        try {
          const body = { kind, write }
          if (kind === 'discover') {
            // auto = 交给引擎按「上次成功日 −1 天」算；选了天数就显式传 since
            if (windowDays !== 'auto') body.since = isoDay(Number(windowDays) || 0)
          } else {
            body.batch = Number(batch) || 999
          }
          const result = await api('/runs', { method: 'POST', body: JSON.stringify(body) })
          setError('')
          setSelected(result.runId)
          setTimeout(loadRuns, 900)
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy(false)
        }
      }

      const running = run?.status === 'running'
      const stats = run?.counts || {}
      const snapshotStats = snapshot?.stats
      const confirmedChannels = channelRows.filter((row) => row.status === 'confirmed').length

      const startHint =
        kind === 'discover'
          ? '只用已确认渠道抓新品；微博 / 小红书由 ego-browser 先抓原文，再分组派 Agent 判定。'
          : '按缺口补单抽价、子品结构与单套数量；拿不到就留空，不猜。'

      const config = h(TaskConfig, {
        hint: startHint,
        // note 统一写「本轮会碰哪些东西」，三个任务页语义一致
        note:
          kind === 'discover'
            ? channelRows.length
              ? `只用已确认渠道（${confirmedChannels} 个）`
              : '只用已确认渠道'
            : '只补空缺字段，不覆盖已有值',
        write,
        onWrite: setWrite,
        onStart: start,
        busy,
        running,
        actionLabel: kind === 'backfill' ? '开始补齐' : '开始抓取',
        fields:
          kind === 'discover'
            ? [
                h(ConfigField, { key: 'window', label: '抓取窗口' },
                  h(Select, {
                    value: windowDays,
                    onChange: setWindowDays,
                    options: [
                      ['auto', '自动（上次成功日 −1 天 → 今天）'],
                      ['3', '最近 3 天'],
                      ['7', '最近 7 天'],
                    ],
                  })),
              ]
            : [
                h(ConfigField, { key: 'batch', label: '本轮派发' },
                  h(Select, {
                    value: batch,
                    onChange: setBatch,
                    options: [['999', '全部缺口'], ['20', '最多 20 盘'], ['50', '最多 50 盘']],
                  })),
              ],
      })

      // 缺口口径在三个 tab 里一致：先看「表里现在是什么样」，再看「还缺什么」
      const status = h(StatusCard, {
        subtitle: snapshot
          ? snapshot.error
            ? `台账读取失败：${snapshot.error}`
            : `表里 ${snapshotStats?.pans ?? '—'} 个盘 · ${snapshotStats?.subs ?? '—'} 条子品 · ${confirmedChannels} 个已确认渠道${snapshot.at ? ` · 按 ${snapshot.at} 台账` : ''}`
          : '读取中…',
        onRefresh: reloadStatus,
        stats:
          kind === 'discover'
            ? [
                { label: '已收录盘', value: snapshotStats?.pans ?? '—' },
                { label: '子品', value: snapshotStats?.subs ?? '—' },
                { label: '缺单抽价', value: snapshotStats ? `${snapshotStats.pricePans} 盘` : '—' },
                { label: '缺单套数量', value: snapshotStats ? `${snapshotStats.countPans} 盘` : '—' },
                { label: '待补盘', value: snapshotStats ? `${snapshotStats.queuePans ?? snapshotStats.actionablePans} 盘` : '—' },
                { label: '已确认渠道', value: channelRows.length ? confirmedChannels : '—' },
              ]
            : [
                { label: '缺单抽价', value: snapshotStats ? `${snapshotStats.pricePans} 盘` : '—' },
                { label: '缺子品结构', value: snapshotStats ? `${snapshotStats.subPans ?? snapshotStats.noSubPans} 盘` : '—' },
                { label: '缺单套数量', value: snapshotStats ? `${snapshotStats.countPans} 盘` : '—' },
                { label: '其中需补', value: snapshotStats ? `${snapshotStats.actionablePans} 盘` : '—' },
                { label: '本轮可补', value: snapshotStats ? `${snapshotStats.queuePans ?? snapshotStats.actionablePans} 盘` : '—' },
                { label: '已收录盘', value: snapshotStats?.pans ?? '—' },
              ],
      })

      const listCard = h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 8 } },
          h('span', { style: S.title }, '运行记录'),
          h('span', { style: S.muted }, `共 ${runs.length} 条，点一行查看详情`),
          h('div', { style: S.spacer }),
          h('button', { type: 'button', style: S.ghost, onClick: loadRuns }, '刷新'),
        ),
        h(RunList, { runs, current: selected, onPick: pick, limit: expanded ? 20 : 5 }),
        runs.length > 5
          ? h(
              'button',
              { type: 'button', style: { ...S.ghost, marginTop: 8 }, onClick: () => setExpanded((v) => !v) },
              expanded ? '收起' : `展开全部 ${runs.length} 条`,
            )
          : null,
      )

      const detailHead = run
        ? h(
            'div',
            null,
            h(
              'div',
              { style: { ...S.row, marginBottom: 2 } },
              h('span', { style: { ...S.title, fontSize: 14 } }, runHeadline(run)),
              h(Badge, { status: run.status }),
              running ? h('span', { style: S.muted }, '执行中…') : null,
              h('div', { style: S.spacer }),
              running
                ? h(
                    'button',
                    { type: 'button', style: S.ghost, onClick: () => api(`/runs/${run.id}/stop`, { method: 'POST' }) },
                    '停止',
                  )
                : null,
            ),
            h('div', { style: S.muted }, `${run.id} · ${runMeta(run)}${run.error ? ` · ${run.error}` : ''}`),
            h(
              'div',
              { style: S.query },
              h('span', { style: { ...S.statLabel, marginRight: 8, whiteSpace: 'nowrap' } }, '抓取逻辑'),
              h(
                'div',
                { style: { fontSize: 12, flex: 1, display: 'flex', flexDirection: 'column', gap: 2 } },
                scopeLines(run).map((line, index) => h('div', { key: index }, line)),
              ),
            ),
          )
        : null

      const detailCard = h(
        'div',
        { style: S.card, ref: detailRef },
        run
          ? h(
              'div',
              null,
              detailHead,
              h(Rail, { stage: run.stage || (running ? 'preparing' : 'done') }),
              h(
                'div',
                { style: { ...S.row, marginBottom: 10 } },
                h(Stat, { label: '已采纳', value: stats.accepted ?? 0 }),
                h(Stat, { label: '判废', value: stats.rejected ?? 0 }),
                h(Stat, { label: '待确认', value: stats.pending ?? 0 }),
                stats.unavailable ? h(Stat, { label: '未公布', value: stats.unavailable }) : null,
                h(Stat, { label: '已写入', value: stats.written ?? 0 }),
                kind === 'discover'
                  ? h(Stat, { label: '渠道', value: run.table?.confirmed ?? '—' })
                  : null,
              ),
              h(ItemTable, { run, onChanged: reload }),
            )
          : h('div', { style: S.empty }, '上面选一行运行记录，这里显示它的逐条结果'),
      )

      return h(
        'div',
        null,
        config,
        status,
        error ? h('div', { style: S.error }, error) : null,
        listCard,
        detailCard,
      )
    }

    function ChannelsPanel() {
      const [rows, setRows] = useState([])
      const [evidence, setEvidence] = useState({})
      const [busyId, setBusyId] = useState('')
      const [error, setError] = useState('')

      const load = useCallback(async () => {
        try {
          const data = await api('/channels')
          setRows(data.brands || [])
        } catch (err) {
          setError(String(err.message || err))
        }
      }, [])

      useEffect(() => {
        load()
      }, [])

      const probe = async (row) => {
        setBusyId(row.id)
        try {
          const data = await api(`/channels/${row.id}/probe`, { method: 'POST' })
          setEvidence((prev) => ({ ...prev, [row.id]: data.evidence }))
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusyId('')
        }
      }

      const setStatus = async (row, status) => {
        try {
          await api(`/channels/${row.id}`, { method: 'PUT', body: JSON.stringify({ status }) })
          await load()
        } catch (err) {
          setError(String(err.message || err))
        }
      }

      const statusText = { confirmed: '已确认', pending: '待对齐', dead: '失效' }
      const cell = { ...S.td, padding: '4px 8px' }
      const head = { ...S.th, padding: '4px 8px' }

      return h(
        'div',
        null,
        h(
          'div',
          { style: { ...S.card, ...S.row, padding: '10px 14px', marginBottom: 10 } },
          h('span', { style: S.secondary },
            '只有「已确认」的渠道会被抓新品使用；「试抓」看 HTTP 状态与页面样例。'),
          h('div', { style: S.spacer }),
          h('span', { style: S.muted },
            `共 ${rows.length} 条 · 已确认 ${rows.filter((r) => r.status === 'confirmed').length} · 待对齐 ${rows.filter((r) => r.status === 'pending').length} · 失效 ${rows.filter((r) => r.status === 'dead').length}`),
          h('button', { type: 'button', style: S.ghost, onClick: load }, '刷新'),
        ),
        error ? h('div', { style: S.error }, error) : null,
        rows.length
          ? h(
              'table',
              { style: S.table },
              h(
                'thead',
                null,
                h('tr', null,
                  h('th', { style: head }, '品牌'),
                  h('th', { style: head }, '渠道'),
                  h('th', { style: head }, '方式'),
                  h('th', { style: head }, '状态'),
                  h('th', { style: head }, '最近验证'),
                  h('th', { style: head }, '操作'),
                ),
              ),
              h(
                'tbody',
                null,
                rows.flatMap((row) => {
                  const main = h(
                    'tr',
                    { key: row.id },
                    h('td', { style: { ...cell, fontWeight: 600, whiteSpace: 'nowrap' } }, row.brand || '—'),
                    h('td', { style: cell, title: [row.url, row.note].filter(Boolean).join(' | ') }, row.channel || '—'),
                    h('td', { style: { ...cell, color: 'var(--dsw-alias-label-tertiary)' } }, row.type || '—'),
                    h('td', { style: cell }, h(Badge, {
                      tone: row.status === 'confirmed' ? 'ok' : row.status === 'dead' ? 'bad' : 'warn',
                      label: statusText[row.status] || row.status,
                    })),
                    h('td', { style: { ...cell, color: 'var(--dsw-alias-label-tertiary)', whiteSpace: 'nowrap' } },
                      row.lastVerified || row.lastProbe?.at?.slice(0, 10) || '—'),
                    h(
                      'td',
                      { style: { ...cell, whiteSpace: 'nowrap' } },
                      h('button', { type: 'button', style: S.ghost, onClick: () => probe(row), disabled: busyId === row.id },
                        busyId === row.id ? '试抓中…' : '试抓'),
                      row.status !== 'confirmed'
                        ? h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, onClick: () => setStatus(row, 'confirmed') }, '标为已确认')
                        : h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, onClick: () => setStatus(row, 'pending') }, '撤回'),
                    ),
                  )
                  const ev = evidence[row.id]
                    ? h(
                        'tr',
                        { key: `${row.id}-ev` },
                        h('td', { colSpan: 6, style: { ...cell, background: 'var(--dsw-alias-bg-layer-2)', fontSize: 11.5, color: 'var(--dsw-alias-label-secondary)' } },
                          `HTTP ${ev.status || '—'} · ${ev.title || ev.error || ''}`,
                          (ev.samples || []).slice(0, 3).map((sample, index) => h('div', { key: index }, `· ${sample}`)),
                        ),
                      )
                    : null
                  return ev ? [main, ev] : [main]
                }),
              ),
            )
          : h('div', { style: S.empty }, '渠道表还是空的'),
        h('div', { style: { ...S.muted, marginTop: 6 } },
          '渠道文件：workflows/kuji-tracking/references/channels.json（悬停「渠道」看账号与备注）。'),
      )
    }

    // ------------------------------------------------------------ 流程说明（三个 tab 共用一套排版）
    // 2026-11-18：官方福袋 / 游戏虚拟商品也补上「流程说明」，内容和各自引擎的真实口径对齐，
    // 排版和官方赏那份完全一样（标题卡 → 七步 → 分工 → 常见疑问 → 词表 → 想自己跑一遍）。

    const GUIDE_KUJI = {
      title: '这套东西是怎么跑的',
      intro:
        '一句话：脚本去官方渠道抓原文，WorkBuddy 判断有没有新赏盘，机器再逐条核对证据，'
        + '只有核对通过的才写进企微表。插件只是仪表盘，真正干活的是 '
        + 'workflows/kuji-tracking/scripts/acg_run.py。',
      stepsTitle: '一轮任务的七步',
      stepsNote: '从「查哪几天」到「写进表」，每一步都能在「抓新品」页里看到对应状态。',
      steps: [
        {
          title: '定窗口：这次查哪几天',
          body: '窗口 = 上次成功日往前倒 1 天 → 今天。比如上次是 11-17 跑成，这次就查 11-16 → 11-17。'
            + '多倒一天是为了防漏：上一轮跑完到半夜之间发的帖子，也还在这一轮里。',
        },
        {
          title: '定范围：查哪些渠道',
          body: '只查渠道表里标了「已确认」的渠道（具体多少个看「抓取渠道」页）。渠道就是官方或授权代理的发布口，'
            + '没确认的号不会被抓，避免把路人号、二手号的内容写进表。',
        },
        {
          title: '抓原文：先把官方说了什么拿到手',
          body: '微博、小红书要登录才看得到，所以用你登录过的浏览器直接抓，这也是为什么脚本能在本机拿到正文；'
            + '公众号没有「列表页」可抓，先让 DeepSeek 搜索找到文章链接，再打开正文。'
            + '同一个账号被几个品牌共用（一番赏 / 万花赏 / 田野赏 共用一个微博号）时只抓一次。',
        },
        {
          title: '派 Agent：判断哪条是新盘',
          body: '把抓到的原文按品牌分组交给 WorkBuddy，每组只回答一件事：这里面有没有新发售 / 要发售的赏盘？'
            + '要它给出盘名、品牌、发售日、来源链接和一段原文引用。分组是为了互不牵连：一组超时只丢自己那组。',
        },
        {
          title: '机器验收：四道门全过才算数',
          body: '① 来源必须是 http 链接（写「微博某某号」这种直接判废）；② 不能是二手平台；'
            + '③ 引用的那段原文要能在页面上原样找到（找不到就是编的）；④ 表里没出现过这个名字'
            + '（「第4弹」和「Vol.4」算同一盘）。四条全过 → 采纳。',
        },
        {
          title: '写表：只写采纳的',
          body: '采纳的才会写进企微表；品牌按盘名前缀定（一番赏 / 万花赏 / …），不按发帖账号；'
            + '价格只认「数字 + 元 / 円 + 每抽」，认不出一律写「未公布」，绝不猜。',
        },
        {
          title: '没过的去哪了',
          body: '三种结论，别混：'
            + '「判废」= 数据本身有问题（二手、原文对不上、Σ 不等于抽数），不用管；'
            + '「待确认」= 值已经找到，但那个页面机器打不开、你打得开（渠道限流、需要登录、只渲染出外壳），'
            + '所以只有这种才找人：打开来源核对得上就填 URL 采纳，对不上就判废；'
            + '「来源未公布」= 页面压根没写这个数（一番赏预告页只写「全 N 種」的款式数，不写每款几个），'
            + '没有可确认的东西，不进待确认队列，下一轮按表内缺口自动再补。',
        },
      ],
      tasksTitle: '两种任务的区别',
      tasks: [
        {
          title: '抓新品（discover）',
          body: '找窗口内新发售的赏盘，只往后加新行，不改已有的行。跑完看「候选 / 采纳 / 判废 / 待确认 / 写入」五个数。',
        },
        {
          title: '补齐信息（backfill）',
          body: '三类缺口一起补：缺单抽价、缺子品结构（表里 0 条子品，要按来源把赏别和赏名建出来）、缺单套数量。'
            + '一轮把全部缺口盘放进同一个任务派出去；补不到就留空，不猜。',
        },
      ],
      faq: [
        {
          q: '为什么写入是 0？',
          a: '三种可能：这轮没找到新盘；找到的都因为重复/来源不对被判废；或者只是没勾「写回表格」（dry-run 只算不写）。看详情表最后一列「写入」和「说明」里的原因。',
        },
        {
          q: '为什么这轮只补了几个盘，而缺口清单里有更多？',
          a: '补齐信息是一轮派一个任务、把当时算出来的全部缺口盘一起装进去（默认不截断）。老运行写死了每轮 3 个盘，'
            + '看到的「本轮补 3 个盘」就是那时候的上限；现在「抓取配置 · 本轮派发」选「全部缺口」时就等于缺口总数，也可以收窄到 20 / 50 盘。'
            + '另外「子品结构」以前只统计不派单，现在也进同一批任务。',
        },
        {
          q: '为什么一轮要跑好几分钟？',
          a: '抓原文约 1 分钟（要逐个账号登录态抓），Agent 判断 3～5 分钟，验收和写表几秒钟。慢的这一段是 Agent 在读原文。',
        },
        {
          q: '同一个窗口能跑两次吗？',
          a: '能，每个任务都是独立的，不继承上一轮任何结果。重复的盘会在验收时以「表内已存在」判废，不会被写两遍。',
        },
        {
          q: '为什么有的盘写着「来源未公布」，不让我确认？',
          a: '因为它缺的那个数在来源页上根本不存在，你点「采纳」也写不进任何东西 —— 硬让你确认只会让人以为补上了。'
            + '这类盘按表内缺口留在那里，等官方或代理页更新后下一轮会自动再补；真需要人工兜底的只有「待确认」。',
        },
        {
          q: '采纳之后为什么表里还是空的？',
          a: '以前会出现这种假成功：条目缺数量，但候选里有价格，点了采纳就把价格又写一遍、数量没动，条目却显示「已采纳」。'
            + '现在采纳只写这条缺的字段，一个都写不进去就直接报错、状态不动，不会再骗人。',
        },
        {
          q: '渠道没确认会怎样？',
          a: '不会被抓。去「抓取渠道」里点「试抓」看能不能拿到内容，确认是对的公号/账号再标为「已确认」。',
        },
        {
          q: '表里的盘和抓到的盘对不上怎么办？',
          a: '先看是不是写法不同（「一番赏 「XX」 第4弹」和「一番赏 XX Vol.4」算同一盘）。判断不了的会停在「待确认」，人工看一眼即可。',
        },
      ],
      glossary: [
        ['赏盘', '一套抽赏商品（一个主题一套）'],
        ['子品', '一套里的每一档赏（A 赏、B 赏…最后赏）'],
        ['LAST / 最终赏', '抽走最后一张才会送的赏，不计入整套抽数'],
        ['整套抽数', '一套总共能抽多少抽'],
        ['单抽价', '抽一次多少钱'],
        ['dry-run', '只算不写，用来先看结果'],
        ['判废', '有明确问题，不写表'],
        ['待确认', '值找到了，但页面机器打不开、人打得开 → 交给人核对'],
        ['来源未公布', '来源页没写这个数，不需要人确认'],
      ],
      cli: [
        ['抓新品', 'python3 workflows/kuji-tracking/scripts/acg_run.py --kind discover --write'],
        ['补齐信息', 'python3 workflows/kuji-tracking/scripts/acg_run.py --kind backfill --write'],
        ['只看缺口', 'python3 workflows/kuji-tracking/scripts/acg_run.py --snapshot'],
      ],
    }

    const GUIDE_BAG = {
      title: '官方福袋是怎么跑的',
      intro:
        '一句话：线索表里一条线索 = 一个 IP（订阅，不是待办），脚本按启用中的线索去官方渠道和搜索里找福袋'
        + '（含盲袋 / 礼盒 / 惊喜袋这类等价载体），两路候选合并后逐条核对「官方渠道 + 原文命中 + 档位一致」，'
        + '通过才写进企微「官方福袋」表。真正干活的是 workflows/kuji-tracking/scripts/bag_run.py。',
      stepsTitle: '一轮任务的七步',
      stepsNote: '和官方赏共用同一套阶段轨（准备 / 分派 / 等待 / 验收 / 写表 / 完成），每一步在「抓取任务」的详情里都能看到。',
      steps: [
        {
          title: '定窗口：这次查哪几天',
          body: '窗口 = 上次「写表成功」那天往前倒 1 天 → 今天（dry-run 不算，免得空跑把窗口推走）；'
            + '从没写成功过就默认往前 60 天。窗口外的候选按「窗口已过期」判废。',
        },
        {
          title: '定范围：跑哪些线索',
          body: '默认跑全部启用中（active）的线索；「抓取配置 · 线索范围」还能收窄到 P0·P1 或只 P0。'
            + '每条线索都会派出去：有没有绑渠道都抓，差别只在「能不能自动采纳」——官方性和渠道对齐仍然决定验收结论。',
        },
        {
          title: '派 Agent：全量扫街 + 定向补抓',
          body: '第一路「全量扫街」覆盖全部线索，不按发行方分组、按顺序每 5 条一块（68 条约 14 个 job），全部一把起跑，'
            + '让 agent 先全网找官方页，已知渠道只当优先入口；'
            + '第二路「定向渠道」只挑绑了 available 渠道的线索，单独派一组只翻这些官方渠道的任务，抓得更准。'
            + 'DeepSeek 同时按「IP + 载体词」逐条搜索，三份候选末尾一起合并。',
        },
        {
          title: '合并：同一条只留一条',
          body: '按「IP + 官方商品名」合并各路候选，档位逐档对齐；lane 标 both、mode 记下是扫街还是定向找到的。'
            + '合并完才开始验收，所以重复发现不会写成两行。',
        },
        {
          title: '机器验收：四道门全过才算数',
          body: '① 来源得是该线索绑定渠道的域名；② 页面能打开，且候选引用的那段原文能在页面上原样找到；'
            + '③ 每一档的价格要在它自己引用的原文里命中；④ 二手/代充域名直接判废。'
            + '渠道等级不影响过不过，只影响置信度：A/B 自营 0.95、C 平台官旗店 0.85，两路都命中再 +0.03。',
        },
        {
          title: '写表：一行一个福袋',
          body: '写进企微「官方福袋」子表（tvZwq0）。官方原名和等价载体分开记：不是官方叫法的（盲袋、礼盒）在备注里标「等价载体」，'
            + '不冒充官方原名；价格按档位记，缺哪档就写缺。',
        },
        {
          title: '没过的去哪了',
          body: '「判废」= 二手、原文对不上、缺载体词、窗口过期，不用管；'
            + '「待确认」= 页面机器打不开、渠道还没对齐（你打得开），只有这种才找人核对；'
            + 'DeepSeek 搜到的第三方页（9game / 游民 / 百科这类）只当线索，直接判废、不占待确认队列。',
        },
      ],
      tasksTitle: '两个子页的分工',
      tasks: [
        {
          title: '抓取任务',
          body: '按线索跑一轮：配置 → 当前状态 → 运行记录 → 逐条候选。待确认的条目可以填来源 URL 采纳并写入，或直接判废。',
        },
        {
          title: '线索',
          body: '线索表：一条 = 一个 IP，可增删改、启停、调优先级与载体词；渠道库折在同一页，只有 confirmed 且 A/B/C 级会被抓取使用。',
        },
      ],
      faq: [
        {
          q: '为什么这一轮只出几条候选？',
          a: '线索是订阅不是待办：那个 IP 这段时间没有新品，结果就是空的。要看有没有漏，看运行记录第三行的「16 条线索 / 命中 wb 0 · ds 8」。',
        },
        {
          q: '为什么候选被判「渠道未对齐」？',
          a: '来源域名不在这个 IP 绑定的渠道 URL 里，或者这条线索压根没绑渠道。这类进待确认而不是判废 —— 页面本身可能是对的，'
            + '只是渠道还没对齐：去「线索」页把渠道确认掉，或人工核对后填来源采纳。',
        },
        {
          q: 'A/B/C/D 级到底管什么？',
          a: '只管两件事：抓取时只用 confirmed 的 A/B/C 级渠道；置信度按等级给（A/B 0.95、C 0.85、D 0.8）。'
            + 'D 级（游戏内、线下）拿不到可打开的 URL，只能人工录入。',
        },
        {
          q: '为什么某条线索从来没结果？',
          a: '它会被抓（全量扫街一轮不漏），但没绑渠道的 IP 拿不到「渠道未对齐」以外的官方性证明，'
            + '所以结果只会进「待确认」，不会自动写表。想让某条线索自动出结论，去「线索」页给它绑一个 confirmed 渠道。',
        },
        {
          q: '和官方赏有什么区别？',
          a: '官方赏按「品牌渠道」扫新赏盘，福袋按「IP 订阅」扫福袋类商品；官方性的判定也不同——前者看渠道表，后者看这条线索绑的是哪一级渠道。',
        },
        {
          q: '为什么勾了写回表格，表里还是没变？',
          a: '三种可能：这轮没有候选；候选都判废或停在待确认；或者写表那一步失败（看运行详情里的 error）。dry-run 只算不写。',
        },
        {
          q: '「停止」是真的停吗？',
          a: '是 SIGTERM，引擎会落一条 interrupted 并把已完成的部分留下，不会卡在「执行中」。宿主重启时残留的 running 也会被标成「中断」。',
        },
      ],
      glossary: [
        ['线索', '一条 = 一个 IP，订阅式（active / paused）'],
        ['载体', '商品形态：福袋 / 神秘盒子 / 礼盒 / 惊喜袋 / 盲袋'],
        ['等价载体', '不是官方原名、但同一类东西（盲袋、礼盒）'],
        ['档位', '一档一个价格（99 元档 / 199 元档…）'],
        ['A/B/C/D 级', 'A、B 官方自营；C 平台品牌官旗店；D 游戏内/线下只能人工'],
        ['双源', 'workbuddy + DeepSeek 两路都出候选'],
        ['待对齐', '渠道还没确认，只能试抓看证据'],
        ['dry-run', '只算不写，用来先看结果'],
      ],
      cli: [
        ['跑一轮（只看不写）', 'python3 workflows/kuji-tracking/scripts/bag_run.py --kind discover'],
        ['跑一轮并写表', 'python3 workflows/kuji-tracking/scripts/bag_run.py --kind discover --write'],
        ['只跑指定线索', 'python3 workflows/kuji-tracking/scripts/bag_run.py --kind discover --leads lead-genshin,lead-starrail'],
        ['只看线索与渠道状态', 'python3 workflows/kuji-tracking/scripts/bag_run.py --snapshot'],
      ],
    }

    const GUIDE_VG = {
      title: '游戏虚拟商品是怎么跑的',
      intro:
        '一句话：先把行业里有热度的游戏找出来，过热度门槛后去 App Store 内购页、workbuddy（官网公告）、'
        + 'DeepSeek 三路取证，按「游戏 + 商品名」去重，只补表里缺的行。'
        + '真正干活的是 workflows/kuji-tracking/scripts/vg_run.py。',
      stepsTitle: '一轮任务的七步',
      stepsNote: '每一步在「抓取任务」的详情里都能看到：发现了几只游戏、丢掉的原因、三路各出多少候选。',
      steps: [
        {
          title: '定窗口：多大范围算新',
          body: '「游戏窗口」默认最近 60 天，只影响提示词里「什么算新公布」；它不改变台账范围，也不会把老游戏排掉 —— '
            + '表里没有的游戏都可能被抓。',
        },
        {
          title: '找游戏：谁值得抓',
          body: '新游戏从发行商名单、预约量 ≥ 10 万、畅销榜 Top 50 里挑（阈值在 references/vg-sources.json），'
            + '每轮最多新发现 10 个。不维护「游戏库」：台账里的游戏名就是清单，'
            + '本轮抓取目标 = 新发现的游戏 ∪ 表里已有的游戏，合计最多 20 个 —— 老游戏也重抓一遍，补它缺的行。',
        },
        {
          title: '过热度门槛',
          body: '新发现要过门槛：预约量、榜单名次、发行商名单。被丢掉的会写在「丢弃」那行：'
            + '热度不够、看不出内购、不在窗口、超出每轮上限。',
        },
        {
          title: '三路取证',
          body: 'App Store 中国区内购页做确定性解析（零模型，游戏之间留 1 秒防 429）；'
            + 'workbuddy 一个 job 翻全部游戏的官网公告；DeepSeek 按游戏并行反查。三路都只交候选。',
        },
        {
          title: '机器验收：四类证据齐全才算数',
          body: '① 商品名和游戏名要对得上；② 来源得是该游戏的官方渠道（C 级应用商店页要双源或 store 通道）；'
            + '③ 页面能打开、引用的原文命中、价格在原文里；④ 代币还要能算出面额，面额/价格 小于 1 视为对不上。'
            + '全过才采纳，D 级（游戏内/线下）只能人工录。',
        },
        {
          title: '写表：一个商品名一行',
          body: '写进企微「游戏虚拟商品」子表（ty2XMk）9 列。一个商品名一行，各面额 / 渠道的价格全写进备注'
            + '（`60 档 6 元（App Store）`），首充双倍、赠送、限购也在备注里说明。',
        },
        {
          title: '没过的去哪了',
          body: '「判废」= 二手/代充、DeepSeek 搜到的非官方页（只留线索，不占待确认）；'
            + '「待确认」= C 级单源、页面打不开、App Store 429 限流，下一轮会自动再试；'
            + '「表内已有」= 按「游戏 + 商品名」去重命中，不重复写。',
        },
      ],
      tasksTitle: '两个子页的分工',
      tasks: [
        {
          title: '抓取任务',
          body: '跑一轮：发现 + 首抓（或只发现新游戏），看运行记录、本轮热门游戏、逐条候选与人工裁决。',
        },
        {
          title: '游戏汇总',
          body: '按游戏看已抓到的商品：代币 / 月卡 / 通行证标缺口，点行展开明细（价格看备注）；底部折叠是渠道库。',
        },
      ],
      faq: [
        {
          q: '为什么表里没有某款游戏？',
          a: '三种：没过热度门槛（看运行记录的「丢弃」那行）、看不出内购，或者表里游戏已经很多、'
            + '它没进本轮 20 个抓取目标（新发现 ∪ 表里已有，按顺序截断）。',
        },
        {
          q: '为什么价格在备注里，不单列一列？',
          a: '一个商品名一行：同一款代币有多个面额、多个渠道，拆成多列会丢信息。备注里按「面额 档 价格（渠道）」写，够用也好核对。',
        },
        {
          q: '首充双倍、赠送怎么记？',
          a: '备注里写清楚，价格只记官方标价，不把赠送折算成单价 —— 否则算毛利时会失真。',
        },
        {
          q: '和「只发现新游戏」有什么区别？',
          a: '默认是「发现 + 首抓」：找游戏、过门槛、再抓商品写表。「只发现新游戏」只跑到发现层，看有哪些新游戏值得抓，不抓商品、不写表。',
        },
        {
          q: '为什么有的候选一直停在待确认？',
          a: 'C 级（应用商店）单源、页面打不开、App Store 429 都会进待确认，下一轮自动再试；人工核对得上可以填来源采纳。',
        },
        {
          q: '窗口改成 90 天，为什么记录没变？',
          a: '窗口只作提示词参考，不改变台账范围；要抓更多游戏，等下一轮发现（或把渠道全部打完）。',
        },
        {
          q: '为什么一轮要跑十几二十分钟？',
          a: 'workbuddy 翻官网公告要 5–10 分钟，DeepSeek 每个游戏一路并行；store 通道是秒级。慢的那一段在等 Agent。',
        },
      ],
      glossary: [
        ['代币 / 充值代币', '游戏内充值货币（原石、钻石…）'],
        ['面额', '一个档位换多少币（60 元 = 648 钻）'],
        ['月卡', '按天返利的订阅型商品'],
        ['通行证', '赛季 / 战令类商品'],
        ['首充双倍', '首充送等额，写备注、不进价格'],
        ['store 通道', '直接读 App Store 内购页，零模型'],
        ['C 级单源', '应用商店页只有一路来源，进待确认'],
        ['dry-run', '只算不写，用来先看结果'],
      ],
      cli: [
        ['跑一轮（只看不写）', 'python3 workflows/kuji-tracking/scripts/vg_run.py --kind discover'],
        ['只发现新游戏', 'python3 workflows/kuji-tracking/scripts/vg_run.py --kind discover --discover-only'],
        ['换窗口 / 通道并写表', 'python3 workflows/kuji-tracking/scripts/vg_run.py --kind discover --window-days 30 --lanes deepseek --write'],
        ['只看台账状态', 'python3 workflows/kuji-tracking/scripts/vg_run.py --snapshot'],
      ],
    }

    /** 三个 tab 共用的「流程说明」排版；内容各不相同，结构一模一样。 */
    function GuidePanel({ guide }) {
      const section = (title, subtitle, children) =>
        h(
          'div',
          { style: S.card },
          h('div', { style: { ...S.title, fontSize: 14 } }, title),
          subtitle ? h('div', { style: { ...S.muted, marginBottom: 6 } }, subtitle) : null,
          children,
        )

      const steps = guide.steps.map((step, index) =>
        h(
          'div',
          { key: step.title, style: index === guide.steps.length - 1 ? S.stepLast : S.step },
          h('div', { style: S.stepNum }, String(index + 1)),
          h(
            'div',
            null,
            h('div', { style: S.stepTitle }, step.title),
            h('div', { style: S.stepBody }, step.body),
          ),
        ),
      )

      return h(
        'div',
        null,
        h(
          'div',
          { style: S.card },
          h('div', { style: { ...S.title, fontSize: 15 } }, guide.title),
          h('div', { style: { ...S.stepBody, marginTop: 4 } }, guide.intro),
        ),
        section(guide.stepsTitle, guide.stepsNote, h('div', null, steps)),
        section(
          guide.tasksTitle,
          null,
          guide.tasks.map((task, index) =>
            h(
              'div',
              { key: task.title, style: index === guide.tasks.length - 1 ? S.stepLast : S.step },
              h('div', { style: { ...S.stepTitle, flex: '0 0 132px' } }, task.title),
              h('div', { style: S.stepBody }, task.body),
            ),
          ),
        ),
        section(
          '常见疑问',
          null,
          guide.faq.map((item) =>
            h('div', { key: item.q }, h('div', { style: S.faqQ }, item.q), h('div', { style: S.faqA }, item.a)),
          ),
        ),
        section(
          '词表',
          '表里这些词是这个意思',
          h(
            'div',
            { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '6px 18px' } },
            guide.glossary.map(([term, meaning]) =>
              h(
                'div',
                { key: term, style: { fontSize: 12.5, display: 'flex', gap: 8 } },
                h('span', { style: { ...S.kbd, flex: '0 0 auto' } }, term),
                h('span', { style: S.faqA }, meaning),
              ),
            ),
          ),
        ),
        section(
          '想自己跑一遍',
          '不勾「写回表格」就是 dry-run，只看结果不动表',
          h(
            'div',
            { style: S.stepBody },
            guide.cli.map(([label, command]) =>
              h('div', { key: label, style: { marginTop: 4 } }, `${label}：`, h('span', { style: S.kbd }, command)),
            ),
          ),
        ),
      )
    }


    // ------------------------------------------------------------ 官方福袋（交互对齐官方赏）
    const APP_TABS = [
      { key: 'kuji', label: '官方赏' },
      { key: 'bag', label: '官方福袋' },
      { key: 'vg', label: '游戏虚拟商品' },
    ]
    const BAG_TABS = [
      { key: 'tasks', label: '抓取任务' },
      { key: 'leads', label: '线索' },
      { key: 'guide', label: '流程说明' },
    ]
    const IP_TYPES = [
      ['game', '游戏'],
      ['toy', '潮玩'],
      ['anime', '动漫'],
      ['other', '其他'],
    ]
    const BAG_PRIORITIES = ['P0', 'P1', 'P2']
    const BAG_REASON = {
      source_missing: '缺来源',
      source_unreachable: '来源打不开',
      channel_unverified: '渠道未对齐',
      deepseek_non_official: 'DS 非官方来源（线索）',
      quote_mismatch: '原文对不上',
      quote_unverified: '原文取不到',
      carrier_missing: '缺载体词',
      tier_missing: '缺档位/价格',
      tier_conflict: '档位对不上',
      tier_unverified: '价格取不到',
      out_of_window: '窗口已过期',
      window_missing: '缺窗口',
      publisher_mismatch: 'IP 对不上',
      name_missing: '缺商品名',
      duplicate: '表内已存在',
      secondhand_forbidden: '二手来源',
      manual_reject: '人工判废',
    }
    const BAG_STATUS = {
      accepted: '已采纳',
      pending_review: '待确认',
      rejected: '判废',
    }
    // 候选是从哪条路找到的：sweep = 全量扫街任务（每条线索都派），channel = 只翻已确认渠道的定向任务
    const BAG_MODE = { sweep: '全量扫街', channel: '定向渠道' }
    const bagModeText = (modes) => (Array.isArray(modes) ? modes.map((mode) => BAG_MODE[mode] || mode).join(' + ') : '')
    const bagLaneText = (lane) =>
      lane === 'both' ? 'WorkBuddy + DeepSeek' : lane === 'workbuddy' ? 'WorkBuddy' : lane === 'deepseek' ? 'DeepSeek' : lane || ''
    const BAG_RESULT = {
      captured: '有产出',
      empty: '无新增',
      partial: '部分产出',
      blocked: '渠道阻塞',
      error: '失败',
    }

    function bagReason(reasons) {
      if (!reasons || !reasons.length) return '—'
      const out = []
      for (const reason of reasons) {
        const key = String(reason).split(':')[0]
        const label = BAG_REASON[key] || key
        if (!out.includes(label)) out.push(label)
        if (out.length >= 3) break
      }
      return out.join('、')
    }

    function bagTierText(tiers) {
      if (!tiers || !tiers.length) return '—'
      return (
        tiers
          .filter((tier) => tier.price)
          .map((tier) => `${tier.price} 元${tier.items ? `/${tier.items}` : ''}`)
          .join('；') || '—'
      )
    }

    function splitList(text) {
      return String(text || '')
        .split(/[,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean)
    }

    function bagLeadCount(run) {
      const scope = run?.scope || {}
      if (Array.isArray(scope.leads)) return scope.leads.length
      const params = run?.params || {}
      return Array.isArray(params.leads) ? params.leads.length : 0
    }

    function bagRunHeadline(run) {
      if (!run) return '未选择运行'
      const since = md(run.params?.since)
      const until = md(run.params?.until)
      if (since && until) return `抓福袋 ${since} → ${until}`
      return '抓福袋'
    }

    function bagRunStats(run) {
      const counts = run?.counts || {}
      const items = run?.itemCount ?? (Array.isArray(run?.items) ? run.items.length : 0)
      const stats = [
        ['候选', items],
        ['采纳', counts.accepted || 0],
        ['判废', counts.rejected || 0],
        ['待确认', counts.pending || 0],
      ]
      // 来源未公布：不用人管，单列出来，免得跟「待确认」混成一片
      if (counts.unavailable) stats.push(['未公布', counts.unavailable])
      stats.push(['写入', counts.written || 0])
      return stats
    }

    function bagRunMeta(run) {
      const bits = [triggerLabel(run.trigger), fmtTime(run.startedAt)]
      const spent = durationText(run)
      if (spent) bits.push(`用时 ${spent}`)
      if (run.dryRun) bits.push('dry-run 未写表')
      const leads = bagLeadCount(run)
      if (leads) bits.push(`${leads} 条线索`)
      return bits.join(' · ')
    }

    /** 一句话说清「这一轮在抓什么」：多少线索、哪些发行方、双源各命中多少、怎么分组。 */
    function bagScopeLines(run) {
      if (!run) return []
      const scope = run.scope || {}
      const window = scope.window || { since: run.params?.since, until: run.params?.until }
      const leads = Array.isArray(scope.leads) ? scope.leads : []
      const publishers = scope.publishers || {}
      const feeds = run.feeds || {}
      const lines = []

      if (leads.length) {
        const byPublisher = Object.entries(publishers)
          .sort((a, b) => b[1] - a[1])
          .map(([publisher, count]) => `${publisher} ${count}`)
          .join('、')
        lines.push(`抓福袋：${leads.length} 条线索 / ${byPublisher || '—'}`)
      } else {
        lines.push(`抓福袋：${bagLeadCount(run) || '—'} 条线索（本轮线索清单未落盘）`)
      }

      const laneText = (scope.lanes && scope.lanes.length ? scope.lanes : ['workbuddy', 'deepseek'])
        .map((lane) => (lane === 'workbuddy' ? 'workbuddy' : 'DeepSeek'))
        .join(' + ')
      const laneBits = []
      if (feeds.sweep != null) laneBits.push(`扫街命中 ${feeds.sweep}`)
      if (feeds.channel != null) laneBits.push(`定向命中 ${feeds.channel}`)
      if (feeds.workbuddy != null && feeds.sweep == null) laneBits.push(`workbuddy 命中 ${feeds.workbuddy}`)
      if (feeds.deepseek != null) laneBits.push(`DeepSeek 命中 ${feeds.deepseek}`)
      if (feeds.errors) laneBits.push(`${feeds.errors} 个 lane 失败`)
      lines.push(
        `窗口 ${md(window.since) || '—'} → ${md(window.until) || '—'} · ${laneText}${laneBits.length ? ` · ${laneBits.join(' · ')}` : ''}`,
      )

      // 两套任务分开说：全量扫街覆盖全部线索，定向渠道只补有 confirmed 渠道的那批
      const modes = scope.modes || {}
      const jobBits = []
      if (modes.sweep) jobBits.push(`全量扫街 ${modes.sweep.jobs} 组 / ${modes.sweep.leads} 条线索`)
      if (modes.channel && modes.channel.jobs) jobBits.push(`定向渠道 ${modes.channel.jobs} 组 / ${modes.channel.leads} 条线索`)
      if (jobBits.length) lines.push(`任务 ${jobBits.join(' + ')}`)

      // 整轮硬预算：到点会取消没跑完的 job，这里把用掉多少、砍掉了多少说清楚
      const budget = feeds.budget || {}
      if (budget.seconds) {
        const bits = [`预算 ${Math.round(budget.seconds / 60)} 分钟`]
        if (budget.used) bits.push(`实际 ${Math.round(budget.used / 60)} 分钟`)
        if (budget.cancelled) bits.push(`到点取消 ${budget.cancelled} 个 job`)
        if (budget.skipped) bits.push(`预算不足未跑 ${budget.skipped} 项`)
        lines.push(`耗时 ${bits.join(' · ')}`)
      }

      const groups = Array.isArray(scope.groups) ? scope.groups : []
      if (groups.length) {
        lines.push(`分组 ${groups.map((group) => `${group.name}：${group.publisher}（${(group.leads || []).join('、')}）`).join(' ｜ ')}`)
      } else if (leads.length) {
        const names = leads.map((lead) => lead.ip).filter(Boolean)
        lines.push(`线索 ${names.slice(0, 8).join('、')}${names.length > 8 ? ' 等' : ''}`)
      }
      return lines
    }

    function bagScopeBrief(run) {
      if (!run) return ''
      const scope = run.scope || {}
      const leads = Array.isArray(scope.leads) ? scope.leads : []
      const publishers = scope.publishers || {}
      const feeds = run.feeds || {}
      if (!leads.length) return `${bagLeadCount(run) || '—'} 条线索`
      const top = Object.entries(publishers)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([publisher, count]) => `${publisher} ${count}`)
        .join('、')
      const hits = []
      if (feeds.workbuddy != null) hits.push(`wb ${feeds.workbuddy}`)
      if (feeds.deepseek != null) hits.push(`ds ${feeds.deepseek}`)
      const modes = scope.modes || {}
      const jobs = modes.sweep ? `全量 ${modes.sweep.jobs} 组` : ''
      return `${leads.length} 条线索 / ${top}${jobs ? `　${jobs}` : ''}${hits.length ? `　命中 ${hits.join(' · ')}` : ''}`
    }

    function BagRunList({ runs, current, onPick, limit }) {
      const [hover, setHover] = useState('')
      if (!runs.length) return h('div', { style: S.empty }, '还没有运行记录，点右上「开始抓取」跑一轮')
      return h(
        'div',
        { style: { display: 'flex', flexDirection: 'column', gap: 2 } },
        runs.slice(0, limit || 5).map((run) => {
          const active = run.id === current
          return h(
            'div',
            {
              key: run.id,
              role: 'button',
              tabIndex: 0,
              'aria-current': active ? 'true' : undefined,
              style: S.runRow(active, hover === run.id),
              onClick: () => onPick(run.id),
              onKeyDown: (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onPick(run.id)
                }
              },
              onMouseEnter: () => setHover(run.id),
              onMouseLeave: () => setHover(''),
            },
            h(
              'div',
              { style: { flex: 1, minWidth: 0 } },
              h(
                'div',
                { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
                h(Badge, { status: run.status }),
                h('span', { style: { fontWeight: active ? 600 : 500 } }, bagRunHeadline(run)),
                active ? h('span', { style: S.pill }, '查看中') : null,
                run.error && run.status !== 'running'
                  ? h('span', { style: { ...S.muted, color: 'color-mix(in srgb, var(--dsw-alias-state-warn-primary) 55%, var(--dsw-alias-label-primary))' } }, '有异常')
                  : null,
              ),
              h(
                'div',
                { style: { ...S.muted, marginTop: 2 } },
                bagRunStats(run)
                  .filter(([label, value], index) => index === 0 || value)
                  .map(([label, value], index) => h('span', { key: label }, `${index ? ' · ' : ''}${label} ${value}`)),
                h('span', null, `　${bagRunMeta(run)}`),
              ),
              h('div', { style: { ...S.muted, marginTop: 2, fontSize: 11.5 } }, bagScopeBrief(run)),
            ),
            h('span', { style: { ...S.muted, whiteSpace: 'nowrap' } }, ago(run.startedAt)),
          )
        }),
      )
    }

    function BagRunItem({ item, run, onChanged }) {
      const [note, setNote] = useState('')
      const [source, setSource] = useState(item.source || '')
      const [busy, setBusy] = useState('')
      const [error, setError] = useState('')
      const pending = item.status === 'pending_review'

      const decide = async (decision) => {
        setBusy(decision)
        setError('')
        try {
          await api(`/bag/runs/${run.id}/items/${item.id}/decide`, {
            method: 'POST',
            body: JSON.stringify({ decision, note, source, write: true }),
          })
          await onChanged()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy('')
        }
      }

      const written = item.status === 'accepted'
        ? item.written
          ? '已写入表'
          : run.dryRun
            ? '仅候选（dry-run）'
            : '未写入'
        : '—'

      const main = h(
        'tr',
        { key: item.id },
        h('td', { style: S.td }, item.ip || '—'),
        h('td', { style: { ...S.td, maxWidth: 260 } }, item.officialName || '—'),
        h('td', { style: S.td }, bagTierText(item.tiers)),
        h(
          'td',
          { style: { ...S.td, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis' } },
          item.source
            ? h('a', { href: item.source, target: '_blank', rel: 'noreferrer', style: { color: 'inherit' } }, item.carrier || '链接')
            : '—',
        ),
        h('td', { style: S.td }, h(Badge, {
          tone: item.status === 'accepted' ? 'ok' : item.status === 'rejected' ? 'bad' : 'warn',
          label: BAG_STATUS[item.status] || item.status,
        })),
        h('td', { style: { ...S.td, whiteSpace: 'nowrap', color: 'var(--dsw-alias-label-tertiary)' } }, written),
        h(
          'td',
          { style: { ...S.td, color: 'var(--dsw-alias-label-secondary)' } },
          bagReason(item.reasons),
          item.confidence ? h('div', { style: S.code }, `置信度 ${item.confidence}`) : null,
          item.lane
            ? h(
                'div',
                { style: S.code },
                `来源 ${bagLaneText(item.lane)}${item.modes && item.modes.length ? ` · ${bagModeText(item.modes)}` : ''}`,
              )
            : null,
          item.decidedBy === 'human' ? h('div', { style: S.code }, `人工裁决${item.note ? `：${item.note}` : ''}`) : null,
        ),
      )

      if (!pending) return main
      return [
        main,
        h(
          'tr',
          { key: `${item.id}-act` },
          h('td', { colSpan: 7, style: { ...S.td, background: 'var(--dsw-alias-bg-layer-2)' } },
            h('div', { style: S.row },
              h('input', { value: source, onChange: (event) => setSource(event.target.value), placeholder: '来源 URL（可留空）', style: S.input }),
              h('input', { value: note, onChange: (event) => setNote(event.target.value), placeholder: '备注（采纳依据 / 判废原因）', style: { ...S.input, flex: 1, minWidth: 180 } }),
              h('button', { type: 'button', style: S.button(true), disabled: Boolean(busy), onClick: () => decide('accept') }, busy === 'accept' ? '写入中…' : '采纳并写表'),
              h('button', { type: 'button', style: S.ghost, disabled: Boolean(busy), onClick: () => decide('reject') }, busy === 'reject' ? '处理中…' : '判废'),
            ),
            h('div', { style: { ...S.muted, marginTop: 4 } }, '采纳：按候选值写进「官方福袋」表；判废：只标记，不写表。'),
            error ? h('div', { style: S.error }, error) : null,
          ),
        ),
      ]
    }

    function BagItemTable({ run, onChanged }) {
      const [filter, setFilter] = useUi('items:filter:bag', 'all')
      const items = run?.items || []
      if (!items.length) {
        return h('div', { style: S.empty }, run?.status === 'running' ? '正在跑，结果还没出来…' : '本轮没有产出候选')
      }
      const shown = filterItemsByStatus(items, filter)
      const labelOf = (status) => BAG_STATUS[status] || statusLabel(status)
      return h(
        'div',
        null,
        h(ItemStatusFilter, { items, value: filter, onChange: setFilter, labelOf }),
        shown.length
          ? h(
              'table',
              { style: S.table },
              h('thead', null, h('tr', null,
                ['IP', '官方商品名', '档位', '证据', '结论', '写入', '说明 / 来源'].map((label) => h('th', { key: label, style: S.th }, label)),
              )),
              h('tbody', null, shown.map((item, index) => h(BagRunItem, { key: `${item.id}-${index}`, item, run, onChanged }))),
            )
          : h('div', { style: S.empty }, `「${labelOf(filter)}」下没有条目`),
      )
    }

    function BagTasks() {
      const [runs, setRuns] = useState([])
      const [run, setRun] = useState(null)
      const [selected, setSelected] = useUi('run:bag', '')
      const [write, setWrite] = useState(false)
      // 线索范围记在本地；「写回表格」不记，默认永远是 dry-run
      const [scope, setScope] = useUi('bag:scope', 'all')
      const [leads, setLeads] = useState([])
      const [snapshot, setSnapshot] = useState(null)
      const [busy, setBusy] = useState(false)
      const [error, setError] = useState('')
      const [expanded, setExpanded] = useUi('runs:expanded:bag', false)
      const detailRef = useRef(null)

      const pick = (id) => {
        setSelected(id)
        requestAnimationFrame(() => {
          detailRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
        })
      }

      const loadRuns = useCallback(async () => {
        try {
          const data = await api('/bag/runs')
          const list = data.runs || []
          setRuns(list)
          // 上次看的那条可能已经被清理：只有它还在列表里才保留，否则退回最新一条
          if (list.length && !list.some((item) => item.id === selected)) setSelected(list[0].id)
          return list
        } catch (err) {
          setError(String(err.message || err))
          return []
        }
      }, [selected])

      const loadStatus = useCallback(async (force) => {
        if (force) setSnapshot(null)
        try {
          setSnapshot(await api(`/bag/snapshot${force ? '?force=1' : ''}`))
        } catch (err) {
          setSnapshot({ error: String(err.message || err) })
        }
        try {
          const data = await api('/bag/leads')
          setLeads(data.leads || [])
        } catch {
          /* 线索读不到不影响运行记录 */
        }
      }, [])

      useEffect(() => {
        loadRuns()
        loadStatus(false)
      }, [])

      useEffect(() => {
        if (!selected) return undefined
        let alive = true
        const load = async () => {
          try {
            const data = await api(`/bag/runs/${selected}`)
            if (alive) {
              setRun(data.run)
              setError('')
            }
          } catch (err) {
            if (alive) setError(String(err.message || err))
          }
        }
        load()
        const timer = setInterval(async () => {
          const list = await loadRuns()
          if (!alive) return
          const current = list.find((item) => item.id === selected)
          if (!run || current?.status === 'running') await load()
        }, 2500)
        return () => {
          alive = false
          clearInterval(timer)
        }
      }, [selected, run?.status])

      const reload = useCallback(async () => {
        await loadRuns()
        try {
          const data = await api(`/bag/runs/${selected}`)
          setRun(data.run)
        } catch {
          /* 运行可能刚被清理，保留上一次视图 */
        }
      }, [selected, loadRuns])

      const start = async () => {
        const picked = scopedLeads
        if (!picked.length) {
          setError('这个范围下没有启用中的线索；去「线索」页启用或放宽范围')
          return
        }
        setBusy(true)
        setError('')
        try {
          // 两个来源固定一起跑（单源排障走 CLI --lanes）；范围按优先级筛线索
          const result = await api('/bag/runs', {
            method: 'POST',
            body: JSON.stringify({ write, leads: scope === 'all' ? '' : picked.map((lead) => lead.id).join(',') }),
          })
          setSelected(result.runId)
          setTimeout(loadRuns, 900)
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy(false)
        }
      }

      const running = run?.status === 'running'
      const stats = run?.counts || {}
      const activeLeads = leads.filter((lead) => lead.status === 'active')
      const scopedLeads = activeLeads.filter((lead) =>
        scope === 'p0p1' ? ['P0', 'P1'].includes(lead.priority) : scope === 'p0' ? lead.priority === 'P0' : true,
      )
      const leadStats = snapshot?.leads || {}
      const channelStats = snapshot?.channels || {}
      const ledgerRows = snapshot?.ledger?.rows

      const config = h(TaskConfig, {
        hint: '按线索抓品牌官方福袋：官方渠道原文命中、档位一致才写表；两个来源固定一起跑。',
        note: leads.length ? `通道 workbuddy + DeepSeek · 本轮 ${scopedLeads.length} 条线索` : '通道 workbuddy + DeepSeek',
        write,
        onWrite: setWrite,
        onStart: start,
        busy,
        running,
        actionLabel: '开始抓取',
        fields: [
          h(ConfigField, { key: 'scope', label: '线索范围' },
            h(Select, {
              value: scope,
              onChange: setScope,
              options: [
                ['all', `全部启用中的线索（${activeLeads.length}）`],
                ['p0p1', '只要 P0 · P1'],
                ['p0', '只要 P0'],
              ],
            })),
        ],
      })

      const status = h(StatusCard, {
        subtitle: snapshot
          ? snapshot.error
            ? `台账读取失败：${snapshot.error}`
            : `${leadStats.active ?? '—'} 条线索参与抓取 · 表里 ${ledgerRows ?? '—'} 条福袋${snapshot.at ? ` · 按 ${snapshot.at} 快照` : ''}`
          : '读取中…',
        onRefresh: () => loadStatus(true),
        stats: [
          { label: '线索', value: leadStats.total ?? '—' },
          { label: '启用中', value: leadStats.active ?? '—' },
          { label: '无渠道', value: leadStats.noChannel ?? '—' },
          { label: '可用渠道', value: channelStats.usable ?? '—' },
          { label: '待对齐渠道', value: channelStats.pending ?? '—' },
          { label: '已入库福袋', value: ledgerRows ?? '—' },
        ],
      })

      const listCard = h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 8 } },
          h('span', { style: S.title }, '运行记录'),
          h('span', { style: S.muted }, `共 ${runs.length} 条，点一行查看详情`),
          h('div', { style: S.spacer }),
          h('button', { type: 'button', style: S.ghost, onClick: loadRuns }, '刷新'),
        ),
        h(BagRunList, { runs, current: selected, onPick: pick, limit: expanded ? 20 : 5 }),
        runs.length > 5
          ? h(
              'button',
              { type: 'button', style: { ...S.ghost, marginTop: 8 }, onClick: () => setExpanded((v) => !v) },
              expanded ? '收起' : `展开全部 ${runs.length} 条`,
            )
          : null,
      )

      const detailHead = run
        ? h(
            'div',
            null,
            h(
              'div',
              { style: { ...S.row, marginBottom: 2 } },
              h('span', { style: { ...S.title, fontSize: 14 } }, bagRunHeadline(run)),
              h(Badge, { status: run.status }),
              running ? h('span', { style: S.muted }, '执行中…') : null,
              h('div', { style: S.spacer }),
              running
                ? h('button', { type: 'button', style: S.ghost, onClick: () => api(`/bag/runs/${run.id}/stop`, { method: 'POST' }) }, '停止')
                : null,
            ),
            h('div', { style: S.muted }, `${run.id} · ${bagRunMeta(run)}${run.error ? ` · ${run.error}` : ''}`),
            h(
              'div',
              { style: S.query },
              h('span', { style: { ...S.statLabel, marginRight: 8, whiteSpace: 'nowrap' } }, '抓取逻辑'),
              h(
                'div',
                { style: { fontSize: 12, flex: 1, display: 'flex', flexDirection: 'column', gap: 2 } },
                bagScopeLines(run).map((line, index) => h('div', { key: index }, line)),
              ),
            ),
          )
        : null

      const detailCard = h(
        'div',
        { style: S.card, ref: detailRef },
        run
          ? h(
              'div',
              null,
              detailHead,
              h(Rail, { stage: run.stage || (running ? 'preparing' : 'done') }),
              h(
                'div',
                { style: { ...S.row, marginBottom: 10 } },
                h(Stat, { label: '已采纳', value: stats.accepted ?? 0 }),
                h(Stat, { label: '判废', value: stats.rejected ?? 0 }),
                h(Stat, { label: '待确认', value: stats.pending ?? 0 }),
                stats.unavailable ? h(Stat, { label: '未公布', value: stats.unavailable }) : null,
                h(Stat, { label: '已写入', value: stats.written ?? 0 }),
                h(Stat, { label: '线索', value: bagLeadCount(run) || '—' }),
              ),
              h(BagItemTable, { run, onChanged: reload }),
            )
          : h('div', { style: S.empty }, '上面选一行运行记录，这里显示它的逐条结果'),
      )

      return h('div', null, config, status, error ? h('div', { style: S.error }, error) : null, listCard, detailCard)
    }

    function BagLeadEditor({ lead, channels, onCancel, onSaved, compact }) {
      const [form, setForm] = useState({ ...lead })
      const [busy, setBusy] = useState(false)
      const [error, setError] = useState('')
      const set = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

      const save = async () => {
        setBusy(true)
        setError('')
        try {
          const payload = {
            ...form,
            carriers: splitList(form.carriersText ?? (form.carriers || []).join(',')),
            keywords: splitList(form.keywordsText ?? (form.keywords || []).join(',')),
          }
          delete payload.carriersText
          delete payload.keywordsText
          await api('/bag/leads', { method: 'POST', body: JSON.stringify(payload) })
          await onSaved()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy(false)
        }
      }

      const toggleChannel = (id) => {
        const current = new Set(form.channelIds || [])
        if (current.has(id)) current.delete(id)
        else current.add(id)
        set('channelIds', [...current])
      }

      return h('div', { style: compact ? null : S.card },
        h('div', { style: { ...S.title, fontSize: 13, marginBottom: 8 } }, lead.id ? `编辑线索 ${lead.id}` : '新建线索'),
        h('div', { style: { ...S.row, marginBottom: 8 } },
          h('input', { value: form.id || '', onChange: (e) => set('id', e.target.value), placeholder: 'id（lead-xxx）', style: { ...S.input, minWidth: 180 } }),
          h('input', { value: form.ip || '', onChange: (e) => set('ip', e.target.value), placeholder: 'IP', style: S.input }),
          h('select', { value: form.ipType || 'game', onChange: (e) => set('ipType', e.target.value), style: { ...S.input, minWidth: 100 } },
            IP_TYPES.map(([value, label]) => h('option', { key: value, value }, label))),
          h('input', { value: form.publisher || '', onChange: (e) => set('publisher', e.target.value), placeholder: '发行方', style: S.input }),
        ),
        h('div', { style: { ...S.row, marginBottom: 8 } },
          h('input', { value: form.carriersText ?? (form.carriers || []).join(','), onChange: (e) => set('carriersText', e.target.value), placeholder: '载体词，逗号分隔', style: { ...S.input, flex: 1, minWidth: 240 } }),
          h('input', { value: form.keywordsText ?? (form.keywords || []).join(','), onChange: (e) => set('keywordsText', e.target.value), placeholder: '关键词，逗号分隔', style: { ...S.input, flex: 1, minWidth: 220 } }),
        ),
        h('div', { style: { ...S.row, marginBottom: 8 } },
          h('select', { value: form.priority || 'P2', onChange: (e) => set('priority', e.target.value), style: { ...S.input, minWidth: 90 } },
            BAG_PRIORITIES.map((value) => h('option', { key: value, value }, value))),
          h('select', { value: form.status || 'active', onChange: (e) => set('status', e.target.value), style: { ...S.input, minWidth: 100 } },
            h('option', { value: 'active' }, '启用'), h('option', { value: 'paused' }, '暂停')),
          h('input', { value: form.windowHint || '', onChange: (e) => set('windowHint', e.target.value), placeholder: '节点提示（双11、周年）', style: { ...S.input, minWidth: 170 } }),
          h('input', { value: form.note || '', onChange: (e) => set('note', e.target.value), placeholder: '备注', style: { ...S.input, flex: 1, minWidth: 180 } }),
        ),
        h('div', { style: { ...S.muted, marginBottom: 4 } }, '关联渠道（只列可用：confirmed 且 A/B/C）'),
        h('div', { style: { ...S.row, marginBottom: 8 } },
          channels.map((channel) => h('label', { key: channel.id, style: { ...S.secondary, display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 } },
            h('input', { type: 'checkbox', checked: (form.channelIds || []).includes(channel.id), onChange: () => toggleChannel(channel.id) }),
            `${channel.publisher} · ${channel.channel}（${channel.tier}${channel.status === 'confirmed' ? '' : '·待对齐'}）`,
          )),
        ),
        h('div', { style: S.row },
          h('button', { type: 'button', style: S.button(true), onClick: save, disabled: busy }, busy ? '保存中…' : '保存'),
          h('button', { type: 'button', style: S.ghost, onClick: onCancel, disabled: busy }, '取消'),
        ),
        error ? h('div', { style: S.error }, error) : null,
      )
    }

    function BagLeads() {
      const [leads, setLeads] = useState([])
      const [channels, setChannels] = useState([])
      const [editingId, setEditingId] = useState('')
      const [creating, setCreating] = useState(false)
      const [editingChannel, setEditingChannel] = useState(null)
      const [showChannels, setShowChannels] = useState(false)
      const [busyId, setBusyId] = useState('')
      const [evidence, setEvidence] = useState({})
      const [error, setError] = useState('')

      const load = useCallback(async () => {
        const data = await api('/bag/leads')
        setLeads(data.leads || [])
        setChannels(data.channels || [])
      }, [])

      useEffect(() => {
        load().catch((err) => setError(String(err.message || err)))
      }, [])

      const afterWrite = async () => {
        await load()
        setEditingId('')
        setCreating(false)
        setEditingChannel(null)
      }

      const setStatus = async (lead, status) => {
        setBusyId(lead.id)
        try {
          await api(`/bag/leads/${lead.id}/status`, { method: 'PUT', body: JSON.stringify({ status }) })
          await load()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusyId('')
        }
      }

      const removeLead = async (lead) => {
        if (!window.confirm(`删除线索 ${lead.ip}？`)) return
        setBusyId(lead.id)
        try {
          await api(`/bag/leads/${lead.id}`, { method: 'DELETE' })
          await load()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusyId('')
        }
      }

      const probe = async (channel) => {
        setBusyId(channel.id)
        try {
          const data = await api(`/bag/channels/${channel.id}/probe`, { method: 'POST' })
          setEvidence((prev) => ({ ...prev, [channel.id]: data.evidence }))
          await load()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusyId('')
        }
      }

      const setChannelStatus = async (channel, status) => {
        setBusyId(channel.id)
        try {
          await api('/bag/channels', { method: 'POST', body: JSON.stringify({ ...channel, status }) })
          await load()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusyId('')
        }
      }

      const channelById = Object.fromEntries(channels.map((channel) => [channel.id, channel]))
      const active = leads.filter((lead) => lead.status === 'active').length
      const usableChannels = channels.filter((channel) => channel.status === 'confirmed' && ['A', 'B', 'C'].includes(channel.tier))

      const leadCard = h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 8 } },
          h('span', { style: S.title }, '线索'),
          h('span', { style: S.muted }, '一条线索 = 一个 IP；点是订阅，不是待办'),
          h('div', { style: S.spacer }),
          h(Stat, { label: '线索', value: leads.length }),
          h(Stat, { label: '启用中', value: active }),
          h(Stat, { label: '无渠道', value: leads.filter((lead) => !(lead.channelIds || []).length).length }),
          h(Stat, { label: '可用渠道', value: `${usableChannels.length} / ${channels.length}` }),
          h('button', { type: 'button', style: S.ghost, onClick: load }, '刷新'),
          h('button', { type: 'button', style: S.ghost, onClick: () => setShowChannels((value) => !value) }, showChannels ? '收起渠道库' : '渠道库'),
          h('button', { type: 'button', style: S.button(true), onClick: () => setCreating(true) }, '新建线索'),
        ),
        error ? h('div', { style: S.error }, error) : null,
        creating
          ? h(BagLeadEditor, {
              lead: { id: '', ip: '', ipType: 'game', publisher: '', carriers: [], keywords: [], channelIds: [], priority: 'P2', status: 'active', windowHint: '', note: '' },
              channels,
              onCancel: () => setCreating(false),
              onSaved: afterWrite,
              compact: true,
            })
          : null,
        h('table', { style: S.table },
          h('thead', null, h('tr', null,
            ['IP', '类型', '发行方', '载体词', '渠道', '优先级', '状态', '最近结果', '操作'].map((label) => h('th', { key: label, style: S.th }, label)),
          )),
          h('tbody', null, leads.flatMap((lead) => {
            const main = h('tr', { key: lead.id },
              h('td', { style: { ...S.td, fontWeight: 600 } }, lead.ip, h('div', { style: S.code }, lead.id)),
              h('td', { style: S.td }, (IP_TYPES.find(([value]) => value === lead.ipType) || [null, lead.ipType])[1]),
              h('td', { style: S.td }, lead.publisher),
              h('td', { style: { ...S.td, maxWidth: 220 } }, (lead.carriers || []).join('、')),
              h('td', { style: { ...S.td, maxWidth: 260, fontSize: 11.5, color: 'var(--dsw-alias-label-secondary)' } },
                (lead.channelIds || []).map((id) => (channelById[id]?.channel || id)).join('、') || '—'),
              h('td', { style: S.td }, lead.priority),
              h('td', { style: S.td }, h(Badge, {
                tone: lead.status === 'active' ? 'ok' : 'warn',
                label: lead.status === 'active' ? '启用' : '暂停',
              })),
              h('td', { style: S.td }, BAG_RESULT[lead.lastResult] || lead.lastResult || '—'),
              h('td', { style: { ...S.td, whiteSpace: 'nowrap' } },
                h('button', {
                  type: 'button',
                  style: S.ghost,
                  onClick: () => setEditingId(editingId === lead.id ? '' : lead.id),
                }, editingId === lead.id ? '收起' : '编辑'),
                h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, disabled: busyId === lead.id, onClick: () => setStatus(lead, lead.status === 'active' ? 'paused' : 'active') },
                  lead.status === 'active' ? '暂停' : '启用'),
                h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, disabled: busyId === lead.id, onClick: () => removeLead(lead) }, '删除'),
              ),
            )
            if (editingId !== lead.id) return [main]
            const editor = h('tr', { key: `${lead.id}-edit` },
              h('td', { colSpan: 9, style: { ...S.td, background: 'var(--dsw-alias-bg-layer-2)' } },
                h(BagLeadEditor, { lead, channels, onCancel: () => setEditingId(''), onSaved: afterWrite, compact: true }),
              ),
            )
            return [main, editor]
          })),
        ),
      )

      const channelCard = showChannels
        ? h(
            'div',
            { style: S.card },
            h(
              'div',
              { style: { ...S.row, marginBottom: 8 } },
              h('span', { style: S.title }, '渠道库'),
              h('span', { style: S.muted }, '只有 confirmed 且 A/B/C 级会被抓取使用；D 级只能人工录入'),
              h('div', { style: S.spacer }),
              h('button', { type: 'button', style: S.ghost, onClick: load }, '刷新'),
              h('button', { type: 'button', style: S.ghost, onClick: () => setEditingChannel({ id: '', publisher: '', channel: '', type: 'official-site', tier: 'C', url: '', ipScope: [], canAnswer: ['name', 'price', 'window'], status: 'pending', note: '' }) }, '新建渠道'),
            ),
            editingChannel
              ? h('div', { style: { ...S.cardTight, padding: 12 } },
                  h('div', { style: { ...S.row, marginBottom: 6 } },
                    h('input', { value: editingChannel.id || '', onChange: (e) => setEditingChannel({ ...editingChannel, id: e.target.value }), placeholder: 'id', style: { ...S.input, minWidth: 160 } }),
                    h('input', { value: editingChannel.publisher || '', onChange: (e) => setEditingChannel({ ...editingChannel, publisher: e.target.value }), placeholder: '发行方', style: S.input }),
                    h('input', { value: editingChannel.channel || '', onChange: (e) => setEditingChannel({ ...editingChannel, channel: e.target.value }), placeholder: '渠道名', style: S.input }),
                    h('select', { value: editingChannel.tier || 'C', onChange: (e) => setEditingChannel({ ...editingChannel, tier: e.target.value }), style: { ...S.input, minWidth: 90 } },
                      ['A', 'B', 'C', 'D'].map((tier) => h('option', { key: tier, value: tier }, `${tier} 级`))),
                    h('select', { value: editingChannel.status || 'pending', onChange: (e) => setEditingChannel({ ...editingChannel, status: e.target.value }), style: { ...S.input, minWidth: 110 } },
                      h('option', { value: 'confirmed' }, '已确认'), h('option', { value: 'pending' }, '待对齐'), h('option', { value: 'dead' }, '失效')),
                  ),
                  h('div', { style: { ...S.row, marginBottom: 6 } },
                    h('input', { value: editingChannel.url || '', onChange: (e) => setEditingChannel({ ...editingChannel, url: e.target.value }), placeholder: 'https://…（留空 = 只能人工核对）', style: { ...S.input, flex: 1, minWidth: 260 } }),
                    h('input', { value: editingChannel.note || '', onChange: (e) => setEditingChannel({ ...editingChannel, note: e.target.value }), placeholder: '备注', style: { ...S.input, flex: 1, minWidth: 200 } }),
                  ),
                  h('div', { style: S.row },
                    h('button', { type: 'button', style: S.button(true), onClick: async () => {
                      try {
                        await api('/bag/channels', { method: 'POST', body: JSON.stringify(editingChannel) })
                        await afterWrite()
                      } catch (err) {
                        setError(String(err.message || err))
                      }
                    } }, '保存渠道'),
                    h('button', { type: 'button', style: S.ghost, onClick: () => setEditingChannel(null) }, '取消'),
                  ),
                )
              : null,
            h('table', { style: S.table },
              h('thead', null, h('tr', null,
                ['发行方', '渠道', '等级', '状态', '能回答', '操作'].map((label) => h('th', { key: label, style: S.th }, label)),
              )),
              h('tbody', null, channels.flatMap((channel) => {
                const row = h('tr', { key: channel.id },
                  h('td', { style: S.td }, channel.publisher),
                  h('td', { style: { ...S.td, maxWidth: 240 } }, channel.channel, channel.url ? h('div', { style: S.code }, channel.url) : null),
                  h('td', { style: S.td }, `${channel.tier} 级`),
                  h('td', { style: S.td }, h(Badge, {
                    tone: channel.status === 'confirmed' ? 'ok' : channel.status === 'dead' ? 'bad' : 'warn',
                    label: channel.status === 'confirmed' ? '已确认' : channel.status === 'dead' ? '失效' : '待对齐',
                  })),
                  h('td', { style: { ...S.td, fontSize: 11.5, color: 'var(--dsw-alias-label-secondary)' } }, (channel.canAnswer || []).join('、')),
                  h('td', { style: { ...S.td, whiteSpace: 'nowrap' } },
                    h('button', { type: 'button', style: S.ghost, disabled: busyId === channel.id, onClick: () => probe(channel) }, busyId === channel.id ? '试抓中…' : '试抓'),
                    h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, onClick: () => setEditingChannel(channel) }, '编辑'),
                    channel.status !== 'confirmed'
                      ? h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, onClick: () => setChannelStatus(channel, 'confirmed') }, '标为已确认')
                      : h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, onClick: () => setChannelStatus(channel, 'pending') }, '撤回'),
                  ),
                )
                const ev = evidence[channel.id]
                  ? h('tr', { key: `${channel.id}-ev` },
                      h('td', { colSpan: 6, style: { ...S.td, background: 'var(--dsw-alias-bg-layer-2)', fontSize: 11.5, color: 'var(--dsw-alias-label-secondary)' } },
                        ev.error ? `失败：${ev.error}` : `HTTP ${ev.status || '—'} · ${ev.title || ''}`,
                        (ev.samples || []).slice(0, 3).map((sample, index) => h('div', { key: index }, `· ${sample}`)),
                      ))
                  : null
                return ev ? [row, ev] : [row]
              })),
            ),
          )
        : null

      return h('div', null, leadCard, channelCard)
    }

    // ------------------------------------------------------------ 游戏虚拟商品
    const VG_TABS = [
      { key: 'tasks', label: '抓取任务' },
      { key: 'summary', label: '游戏汇总' },
      { key: 'guide', label: '流程说明' },
    ]
    const VG_TYPE_ORDER = ['充值代币', '月卡', '通行证', '礼包', '其他']
    const VG_WINDOWS = [30, 60, 90]
    const VG_LANES = [
      { value: 'workbuddy,deepseek', label: 'workbuddy + DeepSeek' },
      { value: 'workbuddy', label: '只用 workbuddy' },
      { value: 'deepseek', label: '只用 DeepSeek' },
    ]
    const VG_REASON = {
      name_missing: '缺商品名',
      name_mismatch: '商品名对不上',
      game_mismatch: '游戏对不上',
      source_missing: '缺来源',
      source_unreachable: '来源打不开',
      channel_unverified: '渠道未对齐',
      deepseek_non_official: 'DS 非官方来源（线索）',
      channel_missing: '渠道未配置',
      quote_missing: '缺原文引用',
      quote_unverified: '原文取不到',
      price_missing: '缺价格',
      price_conflict: '价格对不上',
      denom_missing: '缺面额/权益',
      ratio_conflict: '面额与价格不成比例',
      c_tier_single_lane: 'C 级单源',
      d_tier_manual: 'D 级需人工',
      secondhand_forbidden: '二手/代充来源',
      duplicate: '表内已存在',
      manual_reject: '人工判废',
    }
    const VG_DROP = {
      name_missing: '缺游戏名',
      duplicate: '表里已有',
      not_launched: '不在窗口/未上线',
      no_monetization: '看不出内购',
      source_missing: '缺来源',
      threshold_missed: '热度不够',
      over_limit: '超出每轮上限',
    }
    const VG_STATUS = {
      accepted: '已采纳',
      pending_review: '待确认',
      rejected: '判废',
      duplicate: '表内已有',
    }
    const VG_RESULT = {
      captured: '有产出',
      empty: '无新增',
      partial: '部分产出',
      blocked: '渠道阻塞',
      error: '失败',
    }
    const VG_CHANNEL_STATUS = { confirmed: '已确认', pending: '待对齐', dead: '失效' }

    function vgReason(reasons) {
      if (!reasons || !reasons.length) return '—'
      const out = []
      for (const reason of reasons) {
        const key = String(reason).split(':')[0]
        const label = VG_REASON[key] || key
        if (!out.includes(label)) out.push(label)
        if (out.length >= 3) break
      }
      return out.join('、')
    }

    function vgDropText(dropped) {
      if (!dropped || !dropped.length) return '—'
      const out = []
      for (const row of dropped) {
        const key = String(row?.reason || '').split(':')[0]
        out.push(`${row?.game || '未命名'}（${VG_DROP[key] || key || '原因未知'}）`)
        if (out.length >= 8) break
      }
      return out.join('、')
    }

    function vgWindowLabel(days) {
      return `最近 ${Number(days) || 60} 天新游戏`
    }

    function vgPrice(item) {
      if (Array.isArray(item?.prices) && item.prices.length) {
        return item.prices
          .map((row) => `${row.denom ? `${row.denom} 档 ` : ''}${Number(row.price)} 元`)
          .join('；')
      }
      if (item?.price == null || item.price === '') return '—'
      return `${Number(item.price)} 元`
    }

    function vgMode(run) {
      const params = run?.params || {}
      return params.discoverOnly ? '只发现新游戏' : '发现新游戏 + 首抓入库'
    }

    function vgGameCount(run) {
      const scope = run?.scope || {}
      return Number(scope.knownGames || 0)
    }

    function vgRunHeadline(run) {
      if (!run) return '未选择运行'
      return `抓游戏虚拟商品 · ${vgMode(run)}`
    }

    function vgRunStats(run) {
      const counts = run?.counts || {}
      const discovery = run?.discovery || {}
      const items = run?.itemCount ?? (Array.isArray(run?.items) ? run.items.length : 0)
      return [
        ['候选', items],
        ['采纳', counts.accepted || 0],
        ['待确认', counts.pending || 0],
        ['新游戏', discovery.kept || 0],
        ['写入', counts.written || 0],
      ]
    }

    function vgRunMeta(run) {
      const bits = [triggerLabel(run.trigger), fmtTime(run.startedAt)]
      const spent = durationText(run)
      if (spent) bits.push(`用时 ${spent}`)
      if (run.dryRun) bits.push('dry-run 未写表')
      const known = vgGameCount(run)
      if (known) bits.push(`表里已有 ${known} 个游戏`)
      return bits.join(' · ')
    }

    function vgScopeLines(run) {
      if (!run) return []
      const scope = run.scope || {}
      const params = run.params || {}
      const window = scope.window || { since: params.since, until: params.until }
      const feeds = run.feeds || {}
      const discovery = run.discovery || {}
      const lines = []
      const laneText = (scope.lanes && scope.lanes.length ? scope.lanes : ['workbuddy', 'deepseek'])
        .map((lane) => (lane === 'workbuddy' ? 'workbuddy' : 'DeepSeek'))
        .join(' + ')
      const laneBits = []
      if (feeds.store != null) laneBits.push(`App Store ${feeds.store}`)
      if (feeds.workbuddy != null) laneBits.push(`workbuddy ${feeds.workbuddy}`)
      if (feeds.deepseek != null) laneBits.push(`DeepSeek ${feeds.deepseek}`)
      lines.push(`窗口 ${md(window.since) || '—'} → ${md(window.until) || '—'} · ${laneText || '不派 Agent'}${laneBits.length ? ` · 命中 ${laneBits.join(' · ')}` : ''}`)
      lines.push(`表里已有 ${vgGameCount(run) || 0} 个游戏：按商品名去重，只补缺的行，不更新已有行`)
      lines.push(
        `热门游戏：候选 ${discovery.raw || 0} → 过热度门槛 ${discovery.kept || 0} → 丢弃 ${discovery.dropped || 0}`,
      )
      return lines
    }

    function vgScopeBrief(run) {
      if (!run) return ''
      const discovery = run.discovery || {}
      return `表里 ${vgGameCount(run)} 个游戏 / 本轮新游戏 ${discovery.kept || 0}`
    }

    function VGRunList({ runs, current, onPick, limit }) {
      const [hover, setHover] = useState('')
      if (!runs.length) return h('div', { style: S.empty }, '还没有运行记录，点右上「开始抓取」跑一轮')
      return h(
        'div',
        { style: { display: 'flex', flexDirection: 'column', gap: 2 } },
        runs.slice(0, limit || 5).map((run) => {
          const active = run.id === current
          return h(
            'div',
            {
              key: run.id,
              role: 'button',
              tabIndex: 0,
              'aria-current': active ? 'true' : undefined,
              style: S.runRow(active, hover === run.id),
              onClick: () => onPick(run.id),
              onKeyDown: (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onPick(run.id)
                }
              },
              onMouseEnter: () => setHover(run.id),
              onMouseLeave: () => setHover(''),
            },
            h(
              'div',
              { style: { flex: 1, minWidth: 0 } },
              h(
                'div',
                { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
                h(Badge, { status: run.status }),
                h('span', { style: { fontWeight: active ? 600 : 500 } }, vgRunHeadline(run)),
                active ? h('span', { style: S.pill }, '查看中') : null,
              ),
              h(
                'div',
                { style: { ...S.muted, marginTop: 2 } },
                vgRunStats(run)
                  .filter(([, value], index) => index === 0 || value)
                  .map(([label, value], index) => h('span', { key: label }, `${index ? ' · ' : ''}${label} ${value}`)),
                h('span', null, `　${vgRunMeta(run)}`),
              ),
              h('div', { style: { ...S.muted, marginTop: 2, fontSize: 11.5 } }, vgScopeBrief(run)),
            ),
            h('span', { style: { ...S.muted, whiteSpace: 'nowrap' } }, ago(run.startedAt)),
          )
        }),
      )
    }

    function VGItemRow({ item, run, onChanged }) {
      const [note, setNote] = useState('')
      const [source, setSource] = useState(item.source || '')
      const [busy, setBusy] = useState('')
      const [error, setError] = useState('')
      const pending = item.status === 'pending_review'

      const decide = async (decision) => {
        setBusy(decision)
        setError('')
        try {
          await api(`/vg/runs/${run.id}/items/${item.id}/decide`, {
            method: 'POST',
            body: JSON.stringify({ decision, note, source, write: true }),
          })
          await onChanged()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy('')
        }
      }

      const written = item.status === 'accepted'
        ? item.written
          ? '已写入表'
          : run.dryRun
            ? '仅候选（dry-run）'
            : '未写入'
        : item.status === 'duplicate'
          ? '已入库跳过'
          : '—'

      const main = h(
        'tr',
        { key: item.id },
        h('td', { style: S.td }, item.game || '—'),
        h('td', { style: S.td }, item.typeLabel || '—'),
        h('td', { style: { ...S.td, maxWidth: 220 } }, item.name || '—'),
        h('td', { style: { ...S.td, maxWidth: 220 } }, vgPrice(item)),
        h(
          'td',
          { style: { ...S.td, maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis' } },
          item.source
            ? h('a', { href: item.source, target: '_blank', rel: 'noreferrer', style: { color: 'inherit' } }, item.channel || '链接')
            : '—',
        ),
        h('td', { style: S.td }, h(Badge, {
          tone: item.status === 'accepted' || item.status === 'duplicate' ? 'ok' : item.status === 'rejected' ? 'bad' : 'warn',
          label: VG_STATUS[item.status] || item.status,
        })),
        h('td', { style: { ...S.td, whiteSpace: 'nowrap', color: 'var(--dsw-alias-label-tertiary)' } }, written),
        h(
          'td',
          { style: { ...S.td, color: 'var(--dsw-alias-label-secondary)' } },
          vgReason(item.reasons),
          item.confidence ? h('div', { style: S.code }, `置信度 ${item.confidence}`) : null,
          item.lane
            ? h(
                'div',
                { style: S.code },
                `来源 ${bagLaneText(item.lane)}${item.modes && item.modes.length ? ` · ${bagModeText(item.modes)}` : ''}`,
              )
            : null,
          item.decidedBy === 'human' ? h('div', { style: S.code }, `人工裁决${item.note ? `：${item.note}` : ''}`) : null,
        ),
      )

      if (!pending) return main
      return [
        main,
        h(
          'tr',
          { key: `${item.id}-act` },
          h('td', { colSpan: 8, style: { ...S.td, background: 'var(--dsw-alias-bg-layer-2)' } },
            h('div', { style: S.row },
              h('input', { value: source, onChange: (event) => setSource(event.target.value), placeholder: '来源 URL（可留空）', style: S.input }),
              h('input', { value: note, onChange: (event) => setNote(event.target.value), placeholder: '备注（采纳依据 / 判废原因）', style: { ...S.input, flex: 1, minWidth: 180 } }),
              h('button', { type: 'button', style: S.button(true), disabled: Boolean(busy), onClick: () => decide('accept') }, busy === 'accept' ? '写入中…' : '采纳并写表'),
              h('button', { type: 'button', style: S.ghost, disabled: Boolean(busy), onClick: () => decide('reject') }, busy === 'reject' ? '处理中…' : '判废'),
            ),
            h('div', { style: { ...S.muted, marginTop: 4 } }, '采纳：按候选值写进「游戏虚拟商品」表；判废：只标记，不写表。'),
            error ? h('div', { style: S.error }, error) : null,
          ),
        ),
      ]
    }

    function VGItemTable({ run, onChanged }) {
      const [filter, setFilter] = useUi('items:filter:vg', 'all')
      const items = run?.items || []
      if (!items.length) {
        return h('div', { style: S.empty }, run?.status === 'running' ? '正在跑，结果还没出来…' : '本轮没有产出候选')
      }
      const shown = filterItemsByStatus(items, filter)
      const labelOf = (status) => VG_STATUS[status] || statusLabel(status)
      return h(
        'div',
        null,
        h(ItemStatusFilter, { items, value: filter, onChange: setFilter, labelOf }),
        shown.length
          ? h(
              'table',
              { style: S.table },
              h('thead', null, h('tr', null,
                ['游戏', '类型', '商品名', '价格', '渠道', '结论', '写入', '说明 / 来源'].map((label) => h('th', { key: label, style: S.th }, label)),
              )),
              h('tbody', null, shown.map((item, index) => h(VGItemRow, { key: `${item.id}-${index}`, item, run, onChanged }))),
            )
          : h('div', { style: S.empty }, `「${labelOf(filter)}」下没有条目`),
      )
    }

    function VGNewGames({ run }) {
      const discovery = run?.discovery || {}
      const rows = discovery.games || []
      const dropped = discovery.droppedGames || []
      if (!rows.length && !dropped.length) return null
      return h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 8 } },
          h('span', { style: S.title }, '本轮新游戏'),
          h('span', { style: S.muted }, `窗口内候选 ${discovery.raw || 0} 个，过热度门槛 ${discovery.kept || 0} 个；过了门槛才抓一次商品`),
        ),
        rows.length
          ? h(
              'table',
              { style: S.table },
              h('thead', null, h('tr', null,
                ['游戏', '发行商', '优先级', '热度', '商店页', '状态'].map((label) => h('th', { key: label, style: S.th }, label)),
              )),
              h('tbody', null, rows.map((row) => h('tr', { key: row.game },
                h('td', { style: S.td }, row.game || '—'),
                h('td', { style: S.td }, row.publisher || '—'),
                h('td', { style: S.td }, row.priority || '—'),
                h('td', { style: { ...S.td, fontSize: 11.5, color: 'var(--dsw-alias-label-secondary)' } }, (row.heat || []).join(' · ') || '—'),
                h('td', { style: S.td },
                  row.appStore
                    ? h('a', { href: row.appStore, target: '_blank', rel: 'noreferrer', style: { color: 'inherit' } }, 'App Store')
                    : '—'),
                h('td', { style: S.td }, row.status || '—'),
              ))),
            )
          : h('div', { style: S.muted }, '本轮窗口里没有过门槛的新游戏'),
        dropped.length
          ? h('div', { style: { ...S.muted, marginTop: 8, fontSize: 11.5 } },
              `丢弃：${dropped.slice(0, 10).map((row) => `${row.game || '未命名'}（${VG_DROP[row.reason] || row.reason}）`).join('、')}${dropped.length > 10 ? ' …' : ''}`)
          : null,
      )
    }

    function VGTasks() {
      const [runs, setRuns] = useState([])
      const [run, setRun] = useState(null)
      const [selected, setSelected] = useUi('run:vg', '')
      // 和另外两个任务页一致：写回表格不记，默认 dry-run
      const [write, setWrite] = useState(false)
      const [mode, setMode] = useUi('vg:mode', 'all')
      const [windowDays, setWindowDays] = useUi('vg:window', 60)
      const [lanes, setLanes] = useUi('vg:lanes', 'workbuddy,deepseek')
      const [busy, setBusy] = useState(false)
      const [error, setError] = useState('')
      const [snapshot, setSnapshot] = useState(null)
      const [expanded, setExpanded] = useUi('runs:expanded:vg', false)
      const detailRef = useRef(null)

      const pick = (id) => {
        setSelected(id)
        requestAnimationFrame(() => {
          detailRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
        })
      }

      const loadRuns = useCallback(async () => {
        try {
          const data = await api('/vg/runs')
          const list = data.runs || []
          setRuns(list)
          if (list.length && !list.some((item) => item.id === selected)) setSelected(list[0].id)
          return list
        } catch (err) {
          setError(String(err.message || err))
          return []
        }
      }, [selected])

      const loadSnapshot = useCallback(async () => {
        try {
          const data = await api('/vg/snapshot')
          setSnapshot(data)
        } catch (err) {
          setError(String(err.message || err))
        }
      }, [])

      useEffect(() => {
        loadRuns()
        loadSnapshot()
      }, [])

      useEffect(() => {
        if (!selected) return undefined
        let alive = true
        const load = async () => {
          try {
            const data = await api(`/vg/runs/${selected}`)
            if (alive) {
              setRun(data.run)
              setError('')
            }
          } catch (err) {
            if (alive) setError(String(err.message || err))
          }
        }
        load()
        const timer = setInterval(async () => {
          const list = await loadRuns()
          if (!alive) return
          const current = list.find((item) => item.id === selected)
          if (!run || current?.status === 'running') await load()
        }, 2500)
        return () => {
          alive = false
          clearInterval(timer)
        }
      }, [selected, run?.status])

      const reload = useCallback(async () => {
        await loadRuns()
        try {
          const data = await api(`/vg/runs/${selected}`)
          setRun(data.run)
        } catch {
          /* 运行可能刚被清理，保留上一次视图 */
        }
      }, [selected, loadRuns])

      const start = async () => {
        setBusy(true)
        setError('')
        try {
          const result = await api('/vg/runs', {
            method: 'POST',
            body: JSON.stringify({
              write,
              lanes,
              windowDays: Number(windowDays) || 0,
              mode: mode === 'discover' ? 'discover' : '',
            }),
          })
          setSelected(result.runId)
          setTimeout(loadRuns, 900)
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusy(false)
        }
      }

      const running = run?.status === 'running'
      const stats = run?.counts || {}

      const config = h(TaskConfig, {
        hint: '每周把行业里有热度的游戏抓一遍（不限新老），按「游戏 + 商品名」去重，只补表里缺的代币·月卡·通行证。',
        note: mode === 'discover' ? '本轮只发现新游戏，不写表' : '只补表里缺的行，已有行不更新',
        write,
        onWrite: setWrite,
        onStart: start,
        busy,
        running,
        actionLabel: '开始抓取',
        fields: [
          h(ConfigField, { key: 'mode', label: '抓取模式' },
            h(Select, {
              value: mode,
              onChange: setMode,
              options: [['all', '发现 + 首抓'], ['discover', '只发现新游戏']],
            })),
          h(ConfigField, { key: 'window', label: '游戏窗口' },
            h(Select, {
              value: String(windowDays),
              onChange: (value) => setWindowDays(Number(value)),
              options: VG_WINDOWS.map((days) => [String(days), `最近 ${days} 天`]),
            })),
          h(ConfigField, { key: 'lanes', label: '取证通道' },
            h(Select, {
              value: lanes,
              onChange: setLanes,
              options: VG_LANES.map((lane) => [lane.value, lane.label]),
            })),
        ],
      })

      const status = h(StatusCard, {
        subtitle: snapshot
          ? snapshot.error
            ? `台账读取失败：${snapshot.error}`
            : `表里 ${snapshot.ledger?.rows ?? 0} 条商品 · ${snapshot.games?.total ?? 0} 个游戏${snapshot.at ? ` · 按 ${snapshot.at} 快照` : ''}`
          : '读取中…',
        onRefresh: async () => {
          setSnapshot(null)
          try {
            setSnapshot(await api('/vg/snapshot?force=1'))
          } catch (err) {
            setSnapshot({ error: String(err.message || err) })
          }
        },
        stats: [
          { label: '已入库游戏', value: snapshot?.games?.total ?? '—' },
          { label: '三类齐全', value: snapshot?.games?.withAllTypes ?? '—' },
          { label: '有缺口', value: snapshot?.games?.missingTypes ?? '—' },
          { label: '可用渠道', value: snapshot?.channels?.usable ?? '—' },
          { label: '表内商品', value: snapshot?.ledger?.rows ?? '—' },
        ],
      })

      const listCard = h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 8 } },
          h('span', { style: S.title }, '运行记录'),
          h('span', { style: S.muted }, `共 ${runs.length} 条，点一行查看详情`),
          h('div', { style: S.spacer }),
          h('button', { type: 'button', style: S.ghost, onClick: loadRuns }, '刷新'),
        ),
        h(VGRunList, { runs, current: selected, onPick: pick, limit: expanded ? 20 : 5 }),
        runs.length > 5
          ? h(
              'button',
              { type: 'button', style: { ...S.ghost, marginTop: 8 }, onClick: () => setExpanded((v) => !v) },
              expanded ? '收起' : `展开全部 ${runs.length} 条`,
            )
          : null,
      )

      const detailCard = h(
        'div',
        { style: S.card, ref: detailRef },
        run
          ? h(
              'div',
              null,
              h(
                'div',
                { style: { ...S.row, marginBottom: 2 } },
                h('span', { style: { ...S.title, fontSize: 14 } }, vgRunHeadline(run)),
                h(Badge, { status: run.status }),
                running ? h('span', { style: S.muted }, '执行中…') : null,
                h('div', { style: S.spacer }),
                running
                  ? h('button', { type: 'button', style: S.ghost, onClick: () => api(`/vg/runs/${run.id}/stop`, { method: 'POST' }) }, '停止')
                  : null,
              ),
              h('div', { style: S.muted }, `${run.id} · ${vgRunMeta(run)}${run.error ? ` · ${run.error}` : ''}`),
              h(
                'div',
                { style: S.query },
                h('span', { style: { ...S.statLabel, marginRight: 8, whiteSpace: 'nowrap' } }, '抓取逻辑'),
                h(
                  'div',
                  { style: { fontSize: 12, flex: 1, display: 'flex', flexDirection: 'column', gap: 2 } },
                  vgScopeLines(run).map((line, index) => h('div', { key: index }, line)),
                ),
              ),
              h(Rail, { stage: run.stage || (running ? 'preparing' : 'done') }),
              h(
                'div',
                { style: { ...S.row, marginBottom: 10 } },
                h(Stat, { label: '候选', value: run.itemCount ?? 0 }),
                h(Stat, { label: '已采纳', value: stats.accepted ?? 0 }),
                h(Stat, { label: '待确认', value: stats.pending ?? 0 }),
                h(Stat, { label: '新游戏', value: run.discovery?.kept ?? 0 }),
                h(Stat, { label: '已写入', value: stats.written ?? 0 }),
              ),
              h(VGNewGames, { run }),
              h(VGItemTable, { run, onChanged: reload }),
            )
          : h('div', { style: S.empty }, '上面选一行运行记录，这里显示它的逐条结果'),
      )

      return h(
        'div',
        null,
        config,
        status,
        error ? h('div', { style: S.error }, error) : null,
        listCard,
        detailCard,
      )
    }

    function VGChannels() {
      const [channels, setChannels] = useState([])
      const [editing, setEditing] = useState(null)
      const [busyId, setBusyId] = useState('')
      const [evidence, setEvidence] = useState({})
      const [error, setError] = useState('')

      const load = useCallback(async () => {
        const data = await api('/vg/channels')
        setChannels(data.channels || [])
      }, [])

      useEffect(() => {
        load().catch((err) => setError(String(err.message || err)))
      }, [])

      const save = async (row) => {
        try {
          await api('/vg/channels', { method: 'POST', body: JSON.stringify(row) })
          await load()
          setEditing(null)
        } catch (err) {
          setError(String(err.message || err))
        }
      }

      const probe = async (channel) => {
        setBusyId(channel.id)
        try {
          const data = await api(`/vg/channels/${channel.id}/probe`, { method: 'POST' })
          setEvidence((prev) => ({ ...prev, [channel.id]: data.evidence }))
          await load()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusyId('')
        }
      }

      const remove = async (channel) => {
        if (!window.confirm(`删除渠道 ${channel.channel}？`)) return
        setBusyId(channel.id)
        try {
          await api(`/vg/channels/${channel.id}`, { method: 'DELETE' })
          await load()
        } catch (err) {
          setError(String(err.message || err))
        } finally {
          setBusyId('')
        }
      }

      return h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 8 } },
          h('span', { style: S.title }, '渠道库'),
          h('span', { style: S.muted }, '只有已确认且 A/B/C 级参与抓取；App Store 由确定性通道直接读内购页'),
          h('div', { style: S.spacer }),
          h('button', { type: 'button', style: S.ghost, onClick: load }, '刷新'),
          h('button', {
            type: 'button',
            style: S.ghost,
            onClick: () => setEditing({ id: '', publisher: '', channel: '', type: 'official-site', tier: 'C', url: '', gameScope: [], canAnswer: ['name', 'price', 'denom'], status: 'pending', note: '' }),
          }, '新建渠道'),
        ),
        error ? h('div', { style: S.error }, error) : null,
        editing
          ? h('div', { style: S.cardTight },
              h('div', { style: { ...S.row, marginBottom: 6 } },
                h('input', { value: editing.id || '', onChange: (e) => setEditing({ ...editing, id: e.target.value }), placeholder: 'id', style: { ...S.input, minWidth: 160 } }),
                h('input', { value: editing.publisher || '', onChange: (e) => setEditing({ ...editing, publisher: e.target.value }), placeholder: '发行商', style: S.input }),
                h('input', { value: editing.channel || '', onChange: (e) => setEditing({ ...editing, channel: e.target.value }), placeholder: '渠道名', style: S.input }),
                h('select', { value: editing.type || 'official-site', onChange: (e) => setEditing({ ...editing, type: e.target.value }), style: { ...S.input, minWidth: 130 } },
                  [['official-site', '官网'], ['official-mall', '官方商城'], ['official-social', '官方社媒'], ['appstore', '应用商店'], ['official-ingame', '游戏内']].map(([value, label]) => h('option', { key: value, value }, label))),
                h('select', { value: editing.tier || 'C', onChange: (e) => setEditing({ ...editing, tier: e.target.value }), style: { ...S.input, minWidth: 90 } },
                  ['A', 'B', 'C', 'D'].map((tier) => h('option', { key: tier, value: tier }, `${tier} 级`))),
                h('select', { value: editing.status || 'pending', onChange: (e) => setEditing({ ...editing, status: e.target.value }), style: { ...S.input, minWidth: 110 } },
                  h('option', { value: 'confirmed' }, '已确认'), h('option', { value: 'pending' }, '待对齐'), h('option', { value: 'dead' }, '失效')),
              ),
              h('div', { style: { ...S.row, marginBottom: 6 } },
                h('input', { value: editing.url || '', onChange: (e) => setEditing({ ...editing, url: e.target.value }), placeholder: 'https://…（留空 = 只能人工核对）', style: { ...S.input, flex: 1, minWidth: 300 } }),
                h('input', { value: editing.note || '', onChange: (e) => setEditing({ ...editing, note: e.target.value }), placeholder: '备注', style: { ...S.input, flex: 1, minWidth: 200 } }),
              ),
              h('div', { style: S.row },
                h('button', { type: 'button', style: S.button(true), onClick: () => save(editing) }, '保存渠道'),
                h('button', { type: 'button', style: S.ghost, onClick: () => setEditing(null) }, '取消'),
              ),
            )
          : null,
        h('table', { style: S.table },
          h('thead', null, h('tr', null,
            ['发行商', '渠道', '等级', '状态', '能回答', '操作'].map((label) => h('th', { key: label, style: S.th }, label)),
          )),
          h('tbody', null, channels.flatMap((channel) => {
            const row = h('tr', { key: channel.id },
              h('td', { style: S.td }, channel.publisher),
              h('td', { style: { ...S.td, maxWidth: 260 } }, channel.channel, channel.url ? h('div', { style: S.code }, channel.url) : null),
              h('td', { style: S.td }, `${channel.tier} 级`),
              h('td', { style: S.td }, h(Badge, {
                tone: channel.status === 'confirmed' ? 'ok' : channel.status === 'dead' ? 'bad' : 'warn',
                label: VG_CHANNEL_STATUS[channel.status] || channel.status,
              })),
              h('td', { style: { ...S.td, fontSize: 11.5, color: 'var(--dsw-alias-label-secondary)' } }, (channel.canAnswer || []).join('、') || '—'),
              h('td', { style: { ...S.td, whiteSpace: 'nowrap' } },
                h('button', { type: 'button', style: S.ghost, disabled: busyId === channel.id, onClick: () => probe(channel) }, busyId === channel.id ? '试抓中…' : '试抓'),
                h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, onClick: () => setEditing(channel) }, '编辑'),
                channel.status !== 'confirmed'
                  ? h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, disabled: busyId === channel.id, onClick: () => save({ ...channel, status: 'confirmed' }) }, '标为已确认')
                  : h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, disabled: busyId === channel.id, onClick: () => save({ ...channel, status: 'pending' }) }, '撤回'),
                h('button', { type: 'button', style: { ...S.ghost, marginLeft: 4 }, disabled: busyId === channel.id, onClick: () => remove(channel) }, '删除'),
              ),
            )
            const ev = evidence[channel.id]
              ? h('tr', { key: `${channel.id}-ev` },
                  h('td', { colSpan: 6, style: { ...S.td, background: 'var(--dsw-alias-bg-layer-2)', fontSize: 11.5, color: 'var(--dsw-alias-label-secondary)' } },
                    ev.error ? `失败：${ev.error}` : `HTTP ${ev.status || '—'} · ${ev.title || ''}`,
                    (ev.samples || []).slice(0, 3).map((sample, index) => h('div', { key: index }, `· ${sample}`)),
                  ))
              : null
            return ev ? [row, ev] : [row]
          })),
        ),
      )
    }

    function VGSummary() {
      const [summary, setSummary] = useState(null)
      const [items, setItems] = useState([])
      const [open, setOpen] = useState('')
      const [onlyGap, setOnlyGap] = useState(false)
      const [sortBy, setSortBy] = useState('count')
      const [showChannels, setShowChannels] = useState(false)
      const [error, setError] = useState('')

      const load = useCallback(async () => {
        try {
          const [snap, ledger] = await Promise.all([api('/vg/summary'), api('/vg/ledger')])
          setSummary(snap)
          setItems(ledger.items || [])
          setError('')
        } catch (err) {
          setError(String(err.message || err))
        }
      }, [])

      useEffect(() => {
        load()
      }, [])

      const coverage = summary?.coverage || []
      const rows = coverage
        .filter((row) => (onlyGap ? (row.missing || []).length > 0 : true))
        .sort((a, b) => {
          if (sortBy === 'gap') return (b.missing || []).length - (a.missing || []).length
          if (sortBy === 'recent') return String(b.capturedAt || '').localeCompare(String(a.capturedAt || ''))
          return (b.count || 0) - (a.count || 0)
        })
      const byGame = {}
      for (const item of items) {
        const name = item.game || '未命名'
        if (!byGame[name]) byGame[name] = []
        byGame[name].push(item)
      }
      const totals = {
        games: coverage.length,
        items: items.length,
        gaps: coverage.filter((row) => (row.missing || []).length > 0).length,
      }

      const header = h(
        'div',
        { style: S.card },
        h(
          'div',
          { style: { ...S.row, marginBottom: 8 } },
          h('span', { style: S.title }, '游戏汇总'),
          h('span', { style: S.muted }, `按游戏看已抓到的商品；数据来自表内 ${items.length} 条商品，${summary?.at || '—'} 读取`),
          h('div', { style: S.spacer }),
          h(
            'select',
            { value: sortBy, onChange: (event) => setSortBy(event.target.value), style: S.input },
            h('option', { value: 'count' }, '商品数排序'),
            h('option', { value: 'gap' }, '缺口优先'),
            h('option', { value: 'recent' }, '最近入库'),
          ),
          h(
            'label',
            { style: { ...S.secondary, display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 } },
            h('input', { type: 'checkbox', checked: onlyGap, onChange: (event) => setOnlyGap(event.target.checked) }),
            '只看有缺口',
          ),
          h('button', { type: 'button', style: S.ghost, onClick: () => setShowChannels((v) => !v) }, showChannels ? '收起渠道库' : '渠道库'),
          h('button', { type: 'button', style: S.ghost, onClick: load }, '刷新'),
        ),
        h(
          'div',
          { style: S.row },
          h(Stat, { label: '已收录游戏', value: totals.games }),
          h(Stat, { label: '商品条数', value: totals.items }),
          h(Stat, { label: '有缺口游戏', value: totals.gaps }),
        ),
      )

      const table = h(
        'div',
        { style: S.card },
        rows.length
          ? h(
              'table',
              { style: S.table },
              h('thead', null, h('tr', null,
                ['游戏', '代币', '月卡', '通行证', '商品数', '入库日期', '渠道'].map((label) => h('th', { key: label, style: S.th }, label)),
              )),
              h('tbody', null, rows.flatMap((row) => {
                const active = open === row.game
                const mine = (byGame[row.game] || []).slice().sort(
                  (a, b) => VG_TYPE_ORDER.indexOf(a.type) - VG_TYPE_ORDER.indexOf(b.type),
                )
                const cells = h('tr', {
                  key: row.game,
                  role: 'button',
                  tabIndex: 0,
                  style: { cursor: 'pointer', background: active ? 'var(--dsw-alias-bg-layer-2)' : undefined },
                  onClick: () => setOpen(active ? '' : row.game),
                  onKeyDown: (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setOpen(active ? '' : row.game)
                    }
                  },
                },
                  h('td', { style: S.td }, `${active ? '▾ ' : '▸ '}${row.game || '—'}`),
                  ...['充值代币', '月卡', '通行证'].map((kind) =>
                    h('td', {
                      key: kind,
                      style: {
                        ...S.td,
                        color: (row.types || {})[kind]
                          ? 'var(--dsw-alias-label-primary)'
                          : 'var(--dsw-alias-label-tertiary)',
                      },
                    }, (row.types || {})[kind] ? '✓' : '–'),
                  ),
                  h('td', { style: S.td }, row.count ?? 0),
                  h('td', { style: S.td }, row.capturedAt || '—'),
                  h('td', { style: { ...S.td, fontSize: 11.5, color: 'var(--dsw-alias-label-secondary)' } }, (row.channels || []).join('、') || '—'),
                )
                if (!active) return [cells]
                const detail = h('tr', { key: `${row.game}-detail` },
                  h('td', { colSpan: 7, style: { ...S.td, background: 'var(--dsw-alias-bg-layer-2)' } },
                    mine.length
                      ? h('table', { style: { ...S.table, marginTop: 4 } },
                          h('thead', null, h('tr', null,
                            ['类型', '商品名', '渠道', '证据', '状态', '入库日期', '备注（含价格）'].map((label) => h('th', { key: label, style: S.th }, label)),
                          )),
                          h('tbody', null, mine.map((item) => h('tr', { key: item.recordId || `${item.name}-${item.denom}` },
                            h('td', { style: S.td }, item.type || '—'),
                            h('td', { style: S.td }, item.name || '—'),
                            h('td', { style: S.td }, item.channel || '—'),
                            h('td', { style: { ...S.td, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' } },
                              item.source
                                ? h('a', { href: item.source, target: '_blank', rel: 'noreferrer', style: { color: 'inherit' } }, item.source)
                                : '—',
                            ),
                            h('td', { style: S.td }, item.status || '—'),
                            h('td', { style: S.td }, item.capturedAt || '—'),
                            h('td', { style: { ...S.td, maxWidth: 320, color: 'var(--dsw-alias-label-secondary)' } }, item.note || '—'),
                          ))),
                        )
                      : h('div', { style: S.muted }, '这个游戏表里还没有商品明细（缓存可能未刷新，点右上「刷新」）。'),
                  ),
                )
                return [cells, detail]
              })),
            )
          : h('div', { style: S.empty }, coverage.length ? '当前筛选下没有游戏' : '表里还没有游戏：先在「抓取任务」跑一轮发现 + 首抓'),
      )

      return h(
        'div',
        null,
        error ? h('div', { style: S.error }, error) : null,
        header,
        table,
        showChannels ? h(VGChannels) : null,
      )
    }

    function VGPanel() {
      const [tab, setTab] = useUi('vg:tab', 'tasks')
      return h(
        'div',
        null,
        h('div', { style: S.tabBar },
          VG_TABS.map((item) => h('button', { key: item.key, type: 'button', style: S.tab(tab === item.key), onClick: () => setTab(item.key) }, item.label)),
        ),
        tab === 'summary' ? h(VGSummary) : tab === 'guide' ? h(GuidePanel, { guide: GUIDE_VG }) : h(VGTasks),
      )
    }

    function bagApi(path, options = {}) {
      return api(path, options)
    }

    function BagPanel() {
      const [tab, setTab] = useUi('bag:tab', 'tasks')
      return h(
        'div',
        null,
        h('div', { style: S.tabBar },
          BAG_TABS.map((item) => h('button', { key: item.key, type: 'button', style: S.tab(tab === item.key), onClick: () => setTab(item.key) }, item.label)),
        ),
        tab === 'leads' ? h(BagLeads) : tab === 'guide' ? h(GuidePanel, { guide: GUIDE_BAG }) : h(BagTasks),
      )
    }

    const SCENES = {
      kuji: { title: '官方赏', hint: '企微「官方抽赏类商品追踪」· 抓新品 / 补齐信息 / 渠道对齐' },
      bag: { title: '官方福袋', hint: '企微「官方福袋」表 · 线索驱动的双源抓取（workbuddy + DeepSeek）' },
      vg: { title: '游戏虚拟商品', hint: '企微「游戏虚拟商品」表 · 每周抓行业热门游戏的代币 / 月卡 / 通行证，只补缺行' },
    }

    function KujiPanel() {
      const [tab, setTab] = useUi('kuji:tab', 'discover')
      return h(
        'div',
        null,
        h('div', { style: S.tabBar },
          TABS.map((item) => h('button', { key: item.key, type: 'button', style: S.tab(tab === item.key), onClick: () => setTab(item.key) }, item.label)),
        ),
        tab === 'channels' ? h(ChannelsPanel) : tab === 'guide' ? h(GuidePanel, { guide: GUIDE_KUJI }) : h(RunView, { key: tab, kind: tab }),
      )
    }

    function Panel() {
      const [scene, setScene] = useUi('scene', initialScene)
      const pageRef = useRef(null)

      // 切回来时把滚动位置也还原：内容要等接口回来才撑开高度，所以先试着滚，滚不到位再补几次
      useEffect(() => {
        const node = pageRef.current
        if (!node) return undefined
        const saved = Number(readUiState()[`scroll:${scene}`] || 0)
        let tries = 0
        let timer = 0
        const restore = () => {
          if (!node || !saved || tries >= 8) return
          if (node.scrollTop !== saved) node.scrollTop = saved
          tries += 1
          if (node.scrollTop !== saved) timer = window.setTimeout(restore, 200)
        }
        if (saved) restore()

        let saveTimer = 0
        const onScroll = () => {
          window.clearTimeout(saveTimer)
          saveTimer = window.setTimeout(() => writeUiState(`scroll:${scene}`, node.scrollTop), 250)
        }
        node.addEventListener('scroll', onScroll, { passive: true })
        return () => {
          window.clearTimeout(timer)
          window.clearTimeout(saveTimer)
          node.removeEventListener('scroll', onScroll)
          // 卸载前那一刻的位置才是「上次看到哪儿」
          writeUiState(`scroll:${scene}`, node.scrollTop)
        }
      }, [scene])

      const meta = SCENES[scene]
      return h(
        'div',
        { style: S.page, ref: pageRef },
        h('div', { style: S.titleRow },
          h('span', { style: S.title }, meta.title),
          h('span', { style: S.muted }, meta.hint),
        ),
        h('div', { style: { ...S.tabBar, gap: 22 } },
          APP_TABS.map((item) => h('button', {
            key: item.key,
            type: 'button',
            style: { ...S.tab(scene === item.key), fontSize: 14 },
            onClick: () => setScene(item.key),
          }, item.label)),
        ),
        scene === 'bag' ? h(BagPanel) : scene === 'vg' ? h(VGPanel) : h(KujiPanel),
      )
    }

    function Icon() {
      return h(
        'svg',
        { viewBox: '0 0 24 24', width: 18, height: 18, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': true },
        h('path', { d: 'M4 7.5 12 4l8 3.5v9L12 20l-8-3.5z' }),
        h('path', { d: 'M4 7.5 12 11l8-3.5' }),
        h('path', { d: 'M12 11v9' }),
      )
    }

    return {
      inject: ['slots'],
      // 只给离线冒烟用：格式化逻辑不住在渲染里，才能不启动宿主就验证「人可读」
      __test: {
        md,
        durationText,
        runHeadline,
        runStats,
        runMeta,
        scopeBrief,
        ago,
        fmtTime,
        statusLabel,
        itemStatusCounts,
        filterItemsByStatus,
        readUiState,
        writeUiState,
        askFallback,
        writableFields,
        gapFields,
        vgRunHeadline,
        vgRunStats,
        vgRunMeta,
        vgScopeLines,
        vgReason,
        vgDropText,
        vgWindowLabel,
      },
      apply(ctx) {
        ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: 'acg-capture' }, Panel))
        ctx.slots.inject('sidebar.panellist', () =>
          ctx.slots.register({ name: 'sidebar.panellist', id: 'acg-capture', order: 22, label: () => 'ACG信息抓取' }, Icon),
        )
      },
    }
  },
})
