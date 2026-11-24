/**
 * dsh-notify —— DeepSeek Harness 任务完成后推送系统通知。
 *
 * 触发点：
 * - 一轮对话结束（完成 / 出错 / 受阻），且时长达标、当前没有进行中的目标；
 * - 目标（goal）完成或受阻时，一次性通知；
 * - 可选：后台任务（job）结束。
 *
 * 默认只在 DeepSeek Harness 不在前台时通知，避免盯着屏幕还被弹窗。
 * 配置项见 README.md。
 *
 * @module @local/dsh-notify
 */

import { mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { normalizeConfig } from './lib/config.js';
import { createDeliverer } from './lib/deliver.js';
import { createHistory } from './lib/history.js';
import { handleNotifyRoute, routeAuth } from './lib/http.js';
import { findTerminalNotifier } from './lib/macos.js';
import { buildOpenCommand, createOpenRequestStore } from './lib/open-requests.js';
import { messagesFor } from './lib/messages.js';
import { createNotifier } from './lib/notifier.js';

/** 加载器身份。 */
export const name = 'dsh-notify';

/** 需要会话服务先就位：我们只订阅它发出的 `session/event`。 */
export const inject = ['sessions'];

/**
 * 挂载插件。
 *
 * @param ctx - cordis 上下文。
 * @param rawConfig - profile patch 里的 `config`（可为空，全部走默认值）。
 */
export function apply(ctx, rawConfig) {
  let config;
  try {
    config = normalizeConfig(rawConfig);
  } catch (error) {
    // 配置写错时宁可明确失败，也不要静默地"看起来装了但不生效"。
    ctx.logger.error(`[dsh-notify] 配置无效，插件未启用：${error.message}`);
    return;
  }

  if (!config.enabled) {
    ctx.logger.info('[dsh-notify] 已关闭（enabled: false）');
    return;
  }

  const notifier = createNotifier({ config, messages: messagesFor(config.locale) });
  const historyFile = config.historyFile
    || join(process.env.DSH_HOME || join(homedir(), '.dsh'), 'notify', 'history.jsonl');
  const history = createHistory({ file: historyFile, size: config.historySize });
  const terminalNotifierPath = findTerminalNotifier({
    override: config.terminalNotifierPath,
    root: dirname(fileURLToPath(import.meta.url)),
  });

  // 「点击通知 → 打开对应会话」：宿主侧写令牌与当前 origin、挂路由，点击命令只带会话 id。
  const notifyDir = dirname(historyFile);
  const tokenFile = join(notifyDir, 'token');
  const originFile = join(notifyDir, 'origin');
  const openRequests = createOpenRequestStore();
  let webServer = null;
  let origin = '';
  try {
    mkdirSync(notifyDir, { recursive: true, mode: 0o700 });
    writeFileSync(tokenFile, openRequests.token, { mode: 0o600 });
  } catch (error) {
    ctx.logger.warn(`[dsh-notify] 无法写入令牌文件，点击打开会话可能不可用：${error?.message ?? error}`);
  }

  /**
   * 当前实例的可访问根地址，并落盘给点击命令读取。
   *
   * Desktop 每次启动的端口是随机的，通知中心的旧通知必须在点击那一刻读文件，
   * 否则重启后点旧通知只会打到一个已经没人监听的端口。
   */
  const currentOrigin = () => {
    if (webServer === null) return '';
    if (origin.length > 0) return origin;
    try {
      origin = webServer.getOrigin();
    } catch {
      return '';
    }
    try {
      writeFileSync(originFile, `${origin}\n`, { mode: 0o600 });
    } catch (error) {
      ctx.logger.warn(`[dsh-notify] 无法写入 origin 文件，重启后点击旧通知可能失效：${error?.message ?? error}`);
    }
    return origin;
  };

  ctx.inject(['webServer'], (child) => {
    try {
      webServer = child.webServer;
      const disposer = webServer.register({
        kind: 'prefix',
        path: '/dsh-notify',
        // 点击命令是本机 curl，没有浏览器登录态；准入交给 handler 里的令牌校验。
        auth: routeAuth,
        handler: (req, res) => handleNotifyRoute({ req, res, store: openRequests, logger: ctx.logger }),
      });
      currentOrigin();
      child.effect(() => () => {
        webServer = null;
        origin = '';
        disposer();
      }, 'dsh-notify: open-session route');
    } catch (error) {
      webServer = null;
      ctx.logger.warn(`[dsh-notify] 注册 /dsh-notify 路由失败，点击只唤起窗口：${error?.message ?? error}`);
    }
  });

  /** 把某次通知的会话 id 变成点击时执行的命令；端口在监听后才可读，所以按需取。 */
  const openSessionCommand = (sessionId) => {
    if (currentOrigin().length === 0) return '';
    try {
      return buildOpenCommand({ originFile, tokenFile, sessionId });
    } catch {
      return '';
    }
  };

  const deliver = createDeliverer({
    config,
    logger: ctx.logger,
    deps: { history, terminalNotifierPath, openSessionCommand },
  });

  ctx.on('session/event', (session, event) => {
    let notification;
    try {
      notification = notifier.handle(session, event);
    } catch (error) {
      ctx.logger.warn(`[dsh-notify] 处理会话事件失败：${error?.message ?? error}`);
      return;
    }
    if (notification === null || notification === undefined) return;

    // 投递是异步的，且绝不能把异常抛回会话事件循环。
    deliver(notification)
      .then((outcome) => {
        if (outcome.native || outcome.webhook) {
          ctx.logger.info(`[dsh-notify] 已通知：${notification.title}｜${notification.subtitle}`);
        } else if (!outcome.skipped) {
          ctx.logger.warn(`[dsh-notify] 通知未送达：${notification.title}`);
        }
      })
      .catch((error) => {
        ctx.logger.warn(`[dsh-notify] 通知投递异常：${error?.message ?? error}`);
      });
  });

  const backend = terminalNotifierPath.length > 0 && config.backend !== 'osascript' ? 'terminal-notifier' : 'osascript';
  ctx.logger.info(
    `[dsh-notify] 已启用（locale=${config.locale}，后端=${backend}，仅后台=${config.onlyWhenBackground}，最短时长=${config.minDurationMs}ms）`,
  );
}
