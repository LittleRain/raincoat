/**
 * 投递层：决定"现在该不该真的打扰用户"，再调用 macOS 通知 / Webhook。
 *
 * 所有外部依赖（exec、fetch、时钟、平台）都可注入，方便在测试里断言。
 *
 * @module dsh-notify/deliver
 */

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { frontmostAppName, isFrontmost, sendMacNotification, sendTerminalNotifier } from './macos.js';
import { postWebhook } from './webhook.js';

const execFileAsync = promisify(execFile);

/**
 * 创建一个投递器。
 *
 * @param options - `config`、可注入的 `deps`、`logger`。
 * @returns `deliver(notification)`：返回 `{ skipped, native, webhook }`，不抛异常。
 */
export function createDeliverer({ config, deps = {}, logger = console } = {}) {
  const platform = deps.platform ?? process.platform;
  const exec = deps.exec ?? execFileAsync;
  const fetchImpl = deps.fetch ?? globalThis.fetch;
  const terminalNotifier = typeof deps.terminalNotifierPath === 'string' ? deps.terminalNotifierPath : '';
  // osascript 的通知无法绑定点击动作；terminal-notifier 可用时优先它（点击唤起 DSH）。
  const useTerminalNotifier = config.backend !== 'osascript' && terminalNotifier.length > 0;
  let warnedUnsupported = false;
  let warnedMissingTerminalNotifier = false;

  /** 记录一条不会中断主流程的告警。 */
  function warn(message) {
    try {
      logger?.warn?.(message);
    } catch {
      // 日志本身失败不该影响通知流程。
    }
  }

  return async function deliver(notification) {
    const outcome = { skipped: false, native: false, webhook: false };
    try {
      await dispatch(notification, outcome);
    } finally {
      // 历史只用于事后排查，写入失败不影响通知本身。
      try {
        await deps.history?.record({
          kind: notification.kind,
          reason: notification.reason,
          title: notification.title,
          subtitle: notification.subtitle,
          sessionId: notification.sessionId,
          ...outcome,
        });
      } catch {
        // ignore
      }
    }
    return outcome;
  };

  /** 真正决定并执行投递。 */
  async function dispatch(notification, outcome) {
    // 前台判定：用户正看着 DSH 时跳过。判断失败按"不在前台"处理。
    if (config.onlyWhenBackground && platform === 'darwin') {
      try {
        const front = await (deps.frontmostAppName ? deps.frontmostAppName() : frontmostAppName(exec));
        if (isFrontmost(front, config.frontmostApps)) {
          outcome.skipped = true;
          return;
        }
      } catch (error) {
        warn(`[dsh-notify] 无法判断前台应用，按后台处理：${error?.message ?? error}`);
      }
    }

    const tasks = [];

    if (platform === 'darwin') {
      if (useTerminalNotifier) {
        tasks.push(
          sendTerminalNotifier(notification, {
            bin: terminalNotifier,
            exec,
            activate: config.clickToFocus ? config.activateBundleId : '',
            sender: config.senderBundleId,
            group: `dsh-notify:${notification.sessionId}`,
            sound: config.sound,
            execute: config.clickToOpenSession && typeof deps.openSessionCommand === 'function'
              ? deps.openSessionCommand(notification.sessionId)
              : '',
          }).then(() => {
            outcome.native = true;
          }),
        );
      } else {
        if (config.backend === 'terminal-notifier' && !warnedMissingTerminalNotifier) {
          warnedMissingTerminalNotifier = true;
          warn('[dsh-notify] 没找到 terminal-notifier，回退到 osascript（点击不会唤起 DSH）');
        }
        tasks.push(
          sendMacNotification(notification, { exec, sound: config.sound })
            .then(() => {
              outcome.native = true;
            }),
        );
      }
    } else if (!warnedUnsupported) {
      warnedUnsupported = true;
      warn(`[dsh-notify] ${platform} 暂不支持系统通知，仅 Webhook 可用`);
    }

    if (config.webhook.enabled) {
      tasks.push(
        postWebhook(notification, {
          url: config.webhook.url,
          format: config.webhook.format,
          headers: config.webhook.headers,
          timeoutMs: config.webhook.timeoutMs,
          fetchImpl,
        }).then(() => {
          outcome.webhook = true;
        }),
      );
    }

    const results = await Promise.allSettled(tasks);
    for (const result of results) {
      if (result.status === 'rejected') {
        warn(`[dsh-notify] 投递失败：${result.reason?.message ?? result.reason}`);
      }
    }
  }
}
