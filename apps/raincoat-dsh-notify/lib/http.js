/**
 * 宿主侧 HTTP 路由：给点击命令投递「打开会话」，给前端插件取走请求。
 *
 * 只监听本机（DSH Web 服务器本身绑定 loopback）；写入需要令牌。
 *
 * @module dsh-notify/http
 */

const PREFIX = '/dsh-notify';

/**
 * 路由准入策略。
 *
 * `POST /open` 由通知被点击时的本机 curl 触发，它没有浏览器的登录 Cookie，
 * 落在 WebServer 默认的 `required` 上会被准入层直接 401（请求根本到不了 handler）。
 * 所以写接口声明为 `anonymous`，身份由 `x-dsh-notify-token` 兜住；
 * 前端轮询的 `GET /pending` 仍然要求真实登录态。
 *
 * @param request - WebServer 交给策略的请求事实（至少要 method）。
 * @returns `'anonymous'` 或 `'required'`。
 */
export function routeAuth(request) {
  return String(request?.method ?? '').toUpperCase() === 'POST' ? 'anonymous' : 'required';
}

/** 回一个 JSON 响应。 */
function json(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(payload),
    'cache-control': 'no-store',
  });
  res.end(payload);
}

/**
 * 处理 `/dsh-notify/*` 请求。
 *
 * @param options - `req` / `res`、`store`（createOpenRequestStore 的返回值）、`logger`。
 */
export function handleNotifyRoute({ req, res, store, logger }) {
  try {
    const url = new URL(req.url ?? '/', 'http://127.0.0.1');
    const path = url.pathname.startsWith(PREFIX) ? url.pathname.slice(PREFIX.length) || '/' : url.pathname;
    const method = (req.method ?? 'GET').toUpperCase();

    // 前端插件轮询：有请求就返回并清除。
    if (method === 'GET' && path === '/pending') {
      return json(res, 200, { sessionId: store.take() });
    }

    // 点击命令写入：需要令牌。
    if (method === 'POST' && path === '/open') {
      if (!store.verify(req.headers['x-dsh-notify-token'])) {
        return json(res, 403, { error: 'forbidden' });
      }
      const sessionId = url.searchParams.get('session') ?? '';
      if (!store.request(sessionId)) {
        return json(res, 400, { error: 'session is required' });
      }
      return json(res, 200, { ok: true });
    }

    return json(res, 404, { error: 'not found' });
  } catch (error) {
    logger?.warn?.(`[dsh-notify] 处理打开请求失败：${error?.message ?? error}`);
    return json(res, 500, { error: 'internal error' });
  }
}
