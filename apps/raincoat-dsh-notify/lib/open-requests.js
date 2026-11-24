/**
 * 「点击通知 → 打开对应会话」的宿主侧状态与命令拼装。
 *
 * 链路：通知被点击 → terminal-notifier 执行 `-execute` 命令 → 本机 POST
 * `/dsh-notify/open?session=<id>` → 客户端插件轮询 `/dsh-notify/pending`
 * 拿到会话 id 后调用 `uiWorkspace.openSession()`。
 *
 * @module dsh-notify/open-requests
 */

import { randomBytes, timingSafeEqual } from 'node:crypto';

/** 用户从点通知到前端取走请求的窗口期（毫秒）。 */
const DEFAULT_TTL_MS = 60_000;

/** 会话 id 的实际字符集；超出就直接放弃生成命令，避免把任意文本送进 shell。 */
const SAFE_SESSION_ID = /^[A-Za-z0-9._:-]{1,200}$/u;

/** 用单引号包住一段 shell 参数。 */
function shellQuote(value) {
  return `'${String(value).replace(/'/gu, `'\\''`)}'`;
}

/**
 * 建一个「待打开会话」的槽位：新请求覆盖旧请求，读取即清除，超时作废。
 *
 * @param options - 时钟与有效期，测试可注入。
 * @returns 带 `token` / `request` / `take` / `verify` 的对象。
 */
export function createOpenRequestStore({ now = () => Date.now(), ttlMs = DEFAULT_TTL_MS } = {}) {
  let pending = null;
  const token = randomBytes(16).toString('hex');

  return {
    token,

    /**
     * 记下要打开的会话。
     *
     * @param sessionId - 会话 id。
     * @returns 是否接受。
     */
    request(sessionId) {
      if (typeof sessionId !== 'string' || sessionId.trim().length === 0) return false;
      pending = { sessionId: sessionId.trim(), at: now() };
      return true;
    },

    /**
     * 取走待打开的会话（只返回一次）。
     *
     * @returns 会话 id，或 null。
     */
    take() {
      if (pending === null) return null;
      const { sessionId, at } = pending;
      pending = null;
      return now() - at <= ttlMs ? sessionId : null;
    },

    /**
     * 校验点击命令带来的令牌。
     *
     * @param candidate - 请求头里的令牌。
     * @returns 是否匹配。
     */
    verify(candidate) {
      if (typeof candidate !== 'string' || candidate.length !== token.length) return false;
      return timingSafeEqual(Buffer.from(candidate), Buffer.from(token));
    },
  };
}

/**
 * 拼出 terminal-notifier 点击时执行的 shell 命令。
 *
 * 令牌和当前 origin 都在点击那一刻从文件读取，而不是写死进命令：
 * - 令牌每次加载都会重新生成，写死会让「重启后点旧通知」校验失败；
 * - Desktop 每次启动的端口是随机的，写死端口会让旧通知指向一个已经没人监听的地址。
 *
 * 会话 id 只允许安全字符，并再经过一次 URL 编码。
 *
 * @param options - `originFile`（如 `~/.dsh/notify/origin`）、`tokenFile`、`sessionId`。
 * @returns 可直接交给 `-execute` 的命令字符串。
 */
export function buildOpenCommand({ originFile, tokenFile, sessionId }) {
  if (typeof sessionId !== 'string' || !SAFE_SESSION_ID.test(sessionId)) return '';
  const origin = `$(/bin/cat ${shellQuote(originFile)})`;
  const url = `${origin}/dsh-notify/open?session=${encodeURIComponent(sessionId)}`;
  return `/usr/bin/curl -s -o /dev/null -X POST -H "x-dsh-notify-token: $(/bin/cat ${shellQuote(tokenFile)})" "${url}"`;
}
