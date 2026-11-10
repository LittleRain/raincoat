// 模型调用：用 DSH 当前默认模型，插件不单独配 key。
import { randomUUID } from 'node:crypto'

export const PLUGIN_SESSION_ID = `raincoat-kb-desk-${randomUUID()}`

export function defaultSelection(ctx) {
  try {
    const selection = ctx.get('agentDefaultModel')?.currentSelection()
    return selection?.provider && selection?.model ? { provider: selection.provider, model: selection.model } : null
  } catch {
    return null
  }
}

export function modelInfo(ctx) {
  if (!ctx.get('llm')) return null
  const route = defaultSelection(ctx)
  return route ? { ...route, label: route.model } : null
}

/**
 * 流式调模型。onText 收到增量；没有模型时抛错，由路由转成可读提示。
 */
export async function callModel(ctx, { system, messages, maxTokens = 2400, signal, onText, light = false, sessionId = PLUGIN_SESSION_ID }) {
  const info = modelInfo(ctx)
  if (!info) throw new Error('当前没有可用模型：先在 DSH 里选好默认模型')
  const llm = ctx.get('llm')
  const call = await llm.prepareCall(
    { provider: info.provider, model: info.model, maxTokens },
    signal,
    (controls, model) => {
      const effort = light ? model.reasoning?.efforts?.[0]?.id : undefined
      return { ...controls, ...(effort === undefined ? {} : { reasoningEffort: effort }) }
    },
  )
  const payload = messages.map((message) => ({
    role: message.role,
    content: [{ type: 'text', text: String(message.content || '') }],
    ...(message.role === 'user' ? { source: { kind: 'raincoat-kb-desk' } } : {}),
  }))
  let text = ''
  for await (const chunk of call.stream({ ...call.config, system, messages: payload, sessionId, signal })) {
    if (chunk.type === 'text-delta') {
      text += chunk.text
      onText?.(chunk.text)
    } else if (chunk.type === 'finish' && ['error', 'aborted'].includes(chunk.reason?.kind)) {
      throw new Error(chunk.reason.failure?.message || '模型调用失败')
    }
  }
  return { text, model: info.label }
}

/** 让模型只输出 JSON：先剥代码块，解析失败时取第一个平衡的 {...} / [...]。 */
export function parseJsonLoose(text) {
  const raw = String(text || '').trim()
  const fenced = /```(?:json)?\s*([\s\S]*?)```/i.exec(raw)
  const candidates = [fenced?.[1], raw]
  for (const candidate of candidates) {
    if (!candidate) continue
    const trimmed = candidate.trim()
    const direct = tryParse(trimmed)
    if (direct !== undefined) return direct
    const start = trimmed.search(/[[{]/)
    if (start < 0) continue
    const sliced = balanceFrom(trimmed, start)
    const parsed = sliced ? tryParse(sliced) : undefined
    if (parsed !== undefined) return parsed
  }
  return null
}

function tryParse(text) {
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function balanceFrom(text, start) {
  const open = text[start]
  const close = open === '{' ? '}' : ']'
  let depth = 0
  let inString = false
  let escaped = false
  for (let i = start; i < text.length; i += 1) {
    const char = text[i]
    if (escaped) {
      escaped = false
      continue
    }
    if (char === '\\') {
      escaped = true
      continue
    }
    if (char === '"') inString = !inString
    if (inString) continue
    if (char === open) depth += 1
    if (char === close) {
      depth -= 1
      if (depth === 0) return text.slice(start, i + 1)
    }
  }
  return null
}

export const LEARN_SYSTEM = `你是用户的学习教练，服务对象是一个熟练的产品/技术从业者，读得快、讨厌被喂结论。

规则：
1. 只基于【文章】和【用户已知内容】作答；文章没写、你也不确定的地方直接说「文章没写」，不要补脑。
2. 每次回答控制在 250 字以内，先给一句判断，再给两三条支撑，能引用原文就带一句原文短句。
3. 默认反问一次：把问题往「所以对他来说意味着什么」推一步，除非用户已经说清要什么。
4. 用户说「沉淀」时，输出结构化的学习卡片：一句话结论 / 三层结构 / 与已有认知的冲突或补充 / 可执行动作。
5. 中文输出。不要用「首先其次最后」这类套话。`

export function learnUserPrompt({ article, related, history, message }) {
  const paragraphs = (article.paragraphs || []).join('\n')
  const relatedText = (related || [])
    .map((item, index) => `[${index + 1}] ${item.title}（${item.path}）：${item.excerpt}`)
    .join('\n')
  const historyText = (history || [])
    .slice(-8)
    .map((turn) => `${turn.role === 'user' ? '用户' : '你'}：${String(turn.content || '').slice(0, 600)}`)
    .join('\n')
  return [
    `【文章】${article.title}（${article.url}）`,
    paragraphs.slice(0, 12000),
    '',
    relatedText ? `【用户知识库里可能相关的页】\n${relatedText}` : '',
    '',
    historyText ? `【对话】\n${historyText}` : '',
    '',
    `【这次的问题】${message}`,
  ]
    .filter(Boolean)
    .join('\n')
}

export const TOPIC_SYSTEM = `你是用户的内容策划，只有一个任务：把知识库里最近读到的东西变成能写的选题。

规则：
1. 从【素材】里找真正的张力：反常识、被忽略的代价、正在发生的位移、可复用的方法。
2. 公众号选题偏「论证 + 案例」，小红书选题偏「一个具体做法/一个亲测结论」。
3. 不许编造素材里没有的事实、数字、公司名；引用素材时写明来自哪一篇。
4. 只输出 JSON 数组，不要任何解释文字。每个对象字段：
   platform("公众号"|"小红书"), title(不超过 24 字), hook(一句话钩子，不超过 40 字), angle(为什么现在写，30 字内), outline(3-5 条，每条一句话), sources(素材标题数组)
5. 一共 6 条：3 条公众号、3 条小红书。`

export function topicsUserPrompt({ docs, days }) {
  const material = docs
    .map((doc, index) => `[${index + 1}] ${doc.title}（${doc.space || doc.type || '未分类'}，${doc.path}）\n${doc.excerpt}`)
    .join('\n\n')
  return `【素材】最近 ${days} 天知识库里更新/摄入的内容：\n\n${material}\n\n请输出选题 JSON 数组。`
}
