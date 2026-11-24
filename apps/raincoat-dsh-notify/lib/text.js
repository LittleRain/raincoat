/**
 * 文本处理：把助手回复压成一条适合通知中心的短句。
 *
 * @module dsh-notify/text
 */

/** 合并空白、去掉首尾空白。 */
export function collapseWhitespace(input) {
  return typeof input === 'string' ? input.replace(/\s+/gu, ' ').trim() : '';
}

/**
 * 去掉 Markdown 里对通知正文无意义的部分，只留可读文字。
 * 代码块整体丢弃：通知里放代码只会变成噪音。
 */
export function stripMarkdown(input) {
  if (typeof input !== 'string' || input.length === 0) return '';
  let text = input;
  text = text.replace(/```[\s\S]*?```/gu, ' ');
  text = text.replace(/~~~[\s\S]*?~~~/gu, ' ');
  text = text.replace(/`([^`]*)`/gu, '$1');
  text = text.replace(/!\[[^\]]*\]\([^)]*\)/gu, ' ');
  text = text.replace(/\[([^\]]+)\]\([^)]*\)/gu, '$1');
  text = text.replace(/<[^>\n]{1,200}>/gu, ' ');
  text = text.replace(/^\s{0,3}(?:#{1,6}|>|[-*+]|\d+[.)])\s+/gmu, '');
  text = text.replace(/^\s*[-*_]{3,}\s*$/gmu, ' ');
  text = text.replace(/[*_~]{1,3}/gu, '');
  return collapseWhitespace(text);
}

/**
 * 按 Unicode 码点截断，超出时补省略号。
 *
 * @param input - 原文。
 * @param max - 最大码点数（含省略号）。
 * @returns 截断后的字符串。
 */
export function truncate(input, max) {
  const text = typeof input === 'string' ? input : '';
  if (!Number.isFinite(max) || max <= 0) return '';
  const points = Array.from(text);
  if (points.length <= max) return text;
  return `${points.slice(0, Math.max(1, max - 1)).join('').trimEnd()}…`;
}

/**
 * 从消息内容块中提取纯文本。
 *
 * @param content - `message.content` 块数组。
 * @returns 各 text 块以换行连接；没有文本时为空串。
 */
export function textFromContent(content) {
  if (!Array.isArray(content)) return '';
  return content
    .filter((block) => block && block.type === 'text' && typeof block.text === 'string')
    .map((block) => block.text)
    .join('\n');
}

/**
 * 找某轮对话里最后一条助手消息，并压成通知正文。
 *
 * @param log - 会话事件日志（`session.log`）。
 * @param turn - 只接受该轮的事件；undefined 表示不限轮次。
 * @param options - `max` 字符上限，`limit` 最多回看的日志条数。
 * @returns 适合通知的短文本，找不到时为空串。
 */
export function lastAssistantPreview(log, turn, { max = 160, limit = 400 } = {}) {
  if (!Array.isArray(log) || log.length === 0) return '';
  const floor = Math.max(0, log.length - limit);
  for (let index = log.length - 1; index >= floor; index -= 1) {
    const event = log[index];
    if (!event || event.type !== 'assistant/message') continue;
    if (turn !== undefined && event.data?.turn !== turn) continue;
    const text = stripMarkdown(textFromContent(event.data?.message?.content));
    if (text.length === 0) continue;
    return truncate(text, max);
  }
  return '';
}

/**
 * 取会话标题：优先 `session/title` 事件，其次工作目录名。
 *
 * @param log - 会话事件日志。
 * @param cwd - 会话工作目录。
 * @param fallback - 都没有时的兜底文案。
 * @returns 一行标题。
 */
export function sessionTitleFromLog(log, cwd, fallback) {
  if (Array.isArray(log)) {
    for (let index = log.length - 1; index >= 0; index -= 1) {
      const event = log[index];
      if (event?.type !== 'session/title') continue;
      const title = typeof event.data?.title === 'string' ? event.data.title.trim() : '';
      if (title.length > 0) return title;
    }
  }
  if (typeof cwd === 'string' && cwd.length > 0) {
    const base = cwd.replace(/[/\\]+$/u, '').split(/[/\\]/u).pop();
    if (base) return base;
  }
  return fallback;
}
