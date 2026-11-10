// 学习模式取文：抓 HTML、抽标题与正文段落。不解析 JS 渲染页，抓不到就明说。
const ENTITIES = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', ldquo: '“', rdquo: '”', lsquo: '‘', rsquo: '’',
  hellip: '…', mdash: '—', ndash: '–', middot: '·', times: '×', copy: '©',
}

export function decodeEntities(text) {
  return String(text)
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(parseInt(code, 16)))
    .replace(/&([a-z]+);/gi, (whole, name) => ENTITIES[name.toLowerCase()] ?? whole)
}

function pick(html, regexes) {
  for (const regex of regexes) {
    const hit = regex.exec(html)
    if (hit) return decodeEntities(hit[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim())
  }
  return null
}

function bestContainer(html) {
  const candidates = [
    /<div[^>]+id=["']js_content["'][^>]*>([\s\S]*?)<\/div>\s*<\/div>/i,
    /<article[^>]*>([\s\S]*?)<\/article>/i,
    /<div[^>]+class=["'][^"']*(?:article|post|content|rich_media)[^"']*["'][^>]*>([\s\S]*?)<\/div>/i,
    /<main[^>]*>([\s\S]*?)<\/main>/i,
  ]
  let best = null
  for (const regex of candidates) {
    const hit = regex.exec(html)
    if (!hit) continue
    if (!best || hit[1].length > best.length) best = hit[1]
  }
  return best || html
}

export function extractParagraphs(fragment) {
  const cleaned = String(fragment)
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
    .replace(/<svg[\s\S]*?<\/svg>/gi, ' ')
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, ' ')
    .replace(/<(nav|header|footer|aside|form)[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|section|li|h[1-6]|blockquote|tr|pre)>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
  const text = decodeEntities(cleaned)
  const seen = new Set()
  const paragraphs = []
  for (const rawLine of text.split('\n')) {
    const line = rawLine.replace(/[ \t\u00a0]+/g, ' ').trim()
    if (!line) continue
    if (line.length < 8) continue
    if (/^(分享|点赞|在看|收藏|阅读原文|广告|微信扫一扫|关注该公众号)/.test(line)) continue
    const key = line.slice(0, 40)
    if (seen.has(key)) continue
    seen.add(key)
    paragraphs.push(line)
  }
  return paragraphs
}

export async function fetchArticle(url) {
  let target
  try {
    target = new URL(url)
  } catch {
    throw Object.assign(new Error('这不是一个合法的链接'), { status: 400 })
  }
  if (!/^https?:$/.test(target.protocol)) throw Object.assign(new Error('只支持 http/https 链接'), { status: 400 })

  let res
  try {
    res = await fetch(target, {
      redirect: 'follow',
      headers: {
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
        accept: 'text/html,application/xhtml+xml',
      },
      signal: AbortSignal.timeout(15000),
    })
  } catch (error) {
    throw Object.assign(new Error(`抓取失败：${error?.message || error}`), { status: 502 })
  }
  if (!res.ok) throw Object.assign(new Error(`抓取失败：HTTP ${res.status}`), { status: 502 })
  const contentType = res.headers.get('content-type') || ''
  if (!/html|text\/plain/i.test(contentType)) {
    throw Object.assign(new Error(`这个链接不是网页（${contentType || '未知类型'}）`), { status: 415 })
  }
  const html = (await res.text()).slice(0, 4_000_000)

  const title = pick(html, [
    /<h1[^>]+id=["']activity-name["'][^>]*>([\s\S]*?)<\/h1>/i,
    /<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']/i,
    /<meta[^>]+name=["']twitter:title["'][^>]+content=["']([^"']+)["']/i,
    /<h1[^>]*>([\s\S]*?)<\/h1>/i,
    /<title[^>]*>([\s\S]*?)<\/title>/i,
  ])
  const site = pick(html, [
    /<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)["']/i,
    /<meta[^>]+name=["']application-name["'][^>]+content=["']([^"']+)["']/i,
  ]) || target.hostname
  const author = pick(html, [
    /<meta[^>]+name=["']author["'][^>]+content=["']([^"']+)["']/i,
    /<a[^>]+id=["']js_name["'][^>]*>([\s\S]*?)<\/a>/i,
  ])
  const publishedAt = pick(html, [
    /<meta[^>]+property=["']article:published_time["'][^>]+content=["']([^"']+)["']/i,
    /<em[^>]+id=["']publish_time["'][^>]*>([\s\S]*?)<\/em>/i,
  ])

  const paragraphs = extractParagraphs(bestContainer(html))
  const textLength = paragraphs.reduce((sum, line) => sum + line.length, 0)
  return {
    url: target.href,
    title: title || target.hostname,
    site,
    author: author || null,
    publishedAt: publishedAt || null,
    paragraphs,
    textLength,
    // 正文太短通常是登录墙或 JS 渲染页，界面要提示改开原文
    thin: textLength < 400,
  }
}
