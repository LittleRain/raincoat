/**
 * macOS 原生通知：`osascript display notification` + `afplay` 提示音，
 * 并用 `lsappinfo` 判断 DeepSeek Harness 是否在前台，避免"盯着看时还弹窗"。
 *
 * 不依赖 terminal-notifier 等外部工具。
 *
 * @module dsh-notify/macos
 */

import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { delimiter, join } from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const SOUND_ROOT = '/System/Library/Sounds';

/**
 * 生成 `osascript -e` 的脚本行。
 * 通知正文通过 argv 传入，因此不需要对引号、换行、反斜杠做转义。
 *
 * @param hasSubtitle - 是否显示副标题（会话标题）。
 * @returns 逐行传入 `-e` 的脚本文本。
 */
export function displayScript(hasSubtitle) {
  return hasSubtitle
    ? [
        'on run argv',
        'display notification (item 1 of argv) with title (item 2 of argv) subtitle (item 3 of argv)',
        'end run',
      ]
    : [
        'on run argv',
        'display notification (item 1 of argv) with title (item 2 of argv)',
        'end run',
      ];
}

/**
 * 拼出系统提示音文件路径。
 *
 * @param name - 声音名（已由配置层校验）。
 * @returns 绝对路径；空名字返回空串。
 */
export function soundPath(name) {
  return typeof name === 'string' && name.length > 0 ? `${SOUND_ROOT}/${name}.aiff` : '';
}

/**
 * 读取当前前台应用的显示名。
 *
 * @param exec - 可注入的 `execFile` promise 版本。
 * @param options - 超时时间。
 * @returns 显示名；无法判断时为空串。
 */
export async function frontmostAppName(exec = execFileAsync, { timeoutMs = 3000 } = {}) {
  const { stdout: front } = await exec('lsappinfo', ['front'], { timeout: timeoutMs });
  const asn = String(front).trim();
  if (asn.length === 0) return '';
  const { stdout: info } = await exec('lsappinfo', ['info', '-only', 'name', asn], { timeout: timeoutMs });
  const match = /"LSDisplayName"="([^"]*)"/u.exec(String(info));
  return match?.[1] ?? '';
}

/**
 * 前台应用是否属于"用户正看着 DSH"的名单。
 *
 * @param appName - 前台应用显示名。
 * @param names - 配置里的应用名列表。
 * @returns 命中时返回 true。
 */
export function isFrontmost(appName, names) {
  if (typeof appName !== 'string' || appName.trim().length === 0) return false;
  const target = appName.trim().toLowerCase();
  return names.some((name) => name.toLowerCase() === target);
}

/**
 * 找 terminal-notifier 可执行文件：显式配置 → 插件内置 → PATH → 常见安装位置。
 *
 * 内置版让"点击通知唤起 DSH"不依赖用户额外安装任何东西。
 *
 * @param options - `override` 配置值、`root` 插件目录、`env`、`exists`（测试注入）。
 * @returns 可执行文件绝对路径；找不到时为空串。
 */
export function findTerminalNotifier({ override = '', root = '', env = process.env, exists = existsSync } = {}) {
  const candidates = [];
  if (typeof override === 'string' && override.length > 0) candidates.push(override);
  if (typeof root === 'string' && root.length > 0) {
    candidates.push(join(root, 'bin', 'terminal-notifier.app', 'Contents', 'MacOS', 'terminal-notifier'));
  }
  for (const dir of String(env.PATH ?? '').split(delimiter)) {
    if (dir.length > 0) candidates.push(join(dir, 'terminal-notifier'));
  }
  candidates.push('/opt/homebrew/bin/terminal-notifier', '/usr/local/bin/terminal-notifier');
  return candidates.find((candidate) => typeof candidate === 'string' && candidate.length > 0 && exists(candidate)) ?? '';
}

/**
 * 生成 terminal-notifier 的参数。
 *
 * `-sender` 让通知在通知中心里显示成 DeepSeek Harness（带它的图标），
 * `-activate` 决定点击后激活哪个应用，`-group` 让同一会话的通知互相替换。
 *
 * @param notification - `{ title, subtitle, body }`。
 * @param options - `activate` / `sender` bundle id、`group`、`sound`。
 * @returns 传给可执行文件的参数数组。
 */
export function terminalNotifierArgs(notification, { activate = '', sender = '', group = '', sound = '', execute = '' } = {}) {
  const args = ['-title', String(notification.title ?? ''), '-message', String(notification.body ?? '')];
  const subtitle = typeof notification.subtitle === 'string' ? notification.subtitle : '';
  if (subtitle.length > 0) args.push('-subtitle', subtitle);
  if (sound.length > 0) args.push('-sound', sound);
  if (group.length > 0) args.push('-group', group);
  if (sender.length > 0) args.push('-sender', sender);
  if (activate.length > 0) args.push('-activate', activate);
  if (execute.length > 0) args.push('-execute', execute);
  return args;
}

/**
 * 用 terminal-notifier 发通知（支持点击唤起）。
 *
 * @param notification - 通知内容。
 * @param options - 可执行文件路径、可注入的 exec、bundle id、分组、提示音。
 */
export async function sendTerminalNotifier(notification, {
  bin,
  exec = execFileAsync,
  activate = '',
  sender = '',
  group = '',
  sound = '',
  execute = '',
  timeoutMs = 5000,
} = {}) {
  if (typeof bin !== 'string' || bin.length === 0) throw new Error('terminal-notifier 路径为空');
  await exec(bin, terminalNotifierArgs(notification, { activate, sender, group, sound, execute }), { timeout: timeoutMs });
}

/**
 * 弹出一条 macOS 通知（失败会抛出，由调用方记录日志）。
 *
 * @param notification - `{ title, subtitle, body }`。
 * @param options - 可注入的 exec、提示音名、超时。
 */
export async function sendMacNotification(notification, { exec = execFileAsync, sound = '', timeoutMs = 5000 } = {}) {
  const subtitle = typeof notification.subtitle === 'string' ? notification.subtitle : '';
  const args = [];
  for (const line of displayScript(subtitle.length > 0)) args.push('-e', line);
  // `--` 之后才是脚本运行参数：正文、标题、副标题。
  args.push('--', String(notification.body ?? ''), String(notification.title ?? ''));
  if (subtitle.length > 0) args.push(subtitle);

  const pending = [exec('osascript', args, { timeout: timeoutMs })];
  const path = soundPath(sound);
  if (path.length > 0) {
    // 提示音是点缀：失败不应影响通知本身。
    pending.push(exec('afplay', [path], { timeout: timeoutMs }).catch(() => {}));
  }
  await Promise.all(pending);
}
