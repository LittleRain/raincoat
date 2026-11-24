/**
 * 可选的远端推送：把同一条通知投到 Webhook / Bark / ntfy / 企业微信机器人 / 飞书机器人。
 *
 * 只在配置开启时才会安装并使用；默认完全关闭，不产生任何网络请求。
 *
 * @module dsh-notify/webhook
 */

/** 标题 + 副标题 + 正文的纯文本版本。 */
export function notificationText(notification) {
  return [notification.title, notification.subtitle, notification.body]
    .filter((part) => typeof part === 'string' && part.trim().length > 0)
    .join('\n');
}

/** 对外发送的完整 JSON 载荷。 */
export function webhookPayload(notification) {
  return {
    source: 'dsh-notify',
    kind: notification.kind,
    title: notification.title,
    subtitle: notification.subtitle,
    body: notification.body,
    reason: notification.reason,
    sessionId: notification.sessionId,
    cwd: notification.cwd,
    durationMs: notification.durationMs ?? null,
    timestamp: notification.at,
  };
}

/**
 * 按目标平台生成请求体与请求头。
 *
 * @param format - `json` / `bark` / `ntfy` / `wecom` / `feishu`。
 * @param notification - 通知意图。
 * @returns `{ body, headers }`。
 */
export function buildWebhookRequest(format, notification) {
  switch (format) {
    case 'bark':
      return {
        body: JSON.stringify({
          title: notification.title,
          body: [notification.subtitle, notification.body].filter(Boolean).join('\n'),
          group: 'DeepSeek Harness',
          level: 'active',
        }),
        headers: { 'content-type': 'application/json; charset=utf-8' },
      };

    case 'ntfy':
      return {
        body: notificationText(notification),
        headers: {
          'content-type': 'text/plain; charset=utf-8',
          Title: notification.title,
          Tags: 'bell',
        },
      };

    case 'wecom':
      return {
        body: JSON.stringify({ msgtype: 'text', text: { content: notificationText(notification) } }),
        headers: { 'content-type': 'application/json; charset=utf-8' },
      };

    case 'feishu':
      return {
        body: JSON.stringify({ msg_type: 'text', content: { text: notificationText(notification) } }),
        headers: { 'content-type': 'application/json; charset=utf-8' },
      };

    case 'json':
    default:
      return {
        body: JSON.stringify(webhookPayload(notification)),
        headers: { 'content-type': 'application/json; charset=utf-8' },
      };
  }
}

/**
 * POST 一条通知。
 *
 * @param notification - 通知意图。
 * @param options - url、format、自定义 headers、超时、可注入的 fetch。
 * @returns `{ status }`；网络错误或非 2xx 时抛出。
 */
export async function postWebhook(notification, { url, format, headers = {}, timeoutMs = 5000, fetchImpl = globalThis.fetch } = {}) {
  if (typeof fetchImpl !== 'function') throw new Error('当前运行时没有可用的 fetch');
  if (typeof url !== 'string' || !/^https?:\/\//u.test(url)) throw new Error('webhook.url 不是有效的 http(s) 地址');

  const request = buildWebhookRequest(format, notification);
  const response = await fetchImpl(url, {
    method: 'POST',
    headers: { ...request.headers, ...headers },
    body: request.body,
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error(`webhook 返回 HTTP ${response.status}`);
  return { status: response.status };
}
