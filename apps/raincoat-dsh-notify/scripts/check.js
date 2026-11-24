#!/usr/bin/env node
/**
 * 环境自检：平台、前台应用识别、通知后端、DSH_HOME 与历史文件位置。
 *
 *   node scripts/check.js
 */

import { existsSync } from 'node:fs';
import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { findTerminalNotifier, frontmostAppName } from '../lib/macos.js';

const home = process.env.DSH_HOME || join(homedir(), '.dsh');
const historyFile = join(home, 'notify', 'history.jsonl');
const tokenFile = join(home, 'notify', 'token');
const originFile = join(home, 'notify', 'origin');
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const terminalNotifier = findTerminalNotifier({ root });

console.log(`平台:        ${process.platform}${process.platform === 'darwin' ? '' : '（非 macOS：只有 Webhook 可用）'}`);
console.log(`DSH_HOME:    ${home}`);
console.log(`通知后端:    ${terminalNotifier.length > 0 ? 'terminal-notifier（点击可唤起 DSH）' : 'osascript（点击不会唤起应用）'}`);
if (terminalNotifier.length > 0) console.log(`  可执行文件: ${terminalNotifier}`);

try {
  const front = await frontmostAppName();
  console.log(`前台应用:    ${front || '（无法识别）'}`);
  console.log(`前台判定:    ${front === 'DeepSeek Harness' ? '现在 DSH 在前台 → 默认会跳过通知' : '现在不是 DSH 前台 → 完成时会通知'}`);
} catch (error) {
  console.log(`前台应用:    读取失败（${error.message}）；通知会按后台处理`);
}

console.log(`历史文件:    ${historyFile}${existsSync(historyFile) ? '' : '（还没有记录）'}`);

/**
 * 探一次“点击投递”这条路：不带 session 的 POST 期望 400。
 *
 * 400 = 请求已经进入 handler（准入放行，只是缺 session）；
 * 401 = 卡在 WebServer 准入层（路由没声明 auth: routeAuth，点击只会唤起窗口）；
 * 403 = 令牌对不上（App 重启后命令读的是新令牌，一般不会出现）。
 */
function readTrimmed(file) {
  try {
    return readFileSync(file, 'utf8').trim();
  } catch {
    return '';
  }
}

const origin = readTrimmed(originFile);
const token = readTrimmed(tokenFile);
console.log(`点击路由:    ${origin || '（还没有 origin 文件：App 启动后插件会写）'}`);

if (origin.length > 0 && token.length > 0) {
  try {
    const response = await fetch(`${origin}/dsh-notify/open`, {
      method: 'POST',
      headers: { 'x-dsh-notify-token': token },
    });
    if (response.status === 400) {
      console.log('准入探测:    ✅ 已放行（POST /dsh-notify/open 进入 handler，返回 400 缺 session）');
    } else if (response.status === 401) {
      console.log('准入探测:    ❌ 401 准入拦截 —— 点击只会唤起窗口，不会切会话');
      console.log('             检查这次加载的插件是否带 auth: routeAuth（老版本没有这行），或仍从旧目录加载');
    } else if (response.status === 403) {
      console.log('准入探测:    ❌ 403 令牌不匹配 —— 重新加载插件后令牌会刷新，重跑本脚本');
    } else {
      console.log(`准入探测:    ⚠️  意外状态 ${response.status}`);
    }
  } catch (error) {
    console.log(`准入探测:    ❌ 连不上 ${origin}（${error.message}）；App 可能已退出或换了端口`);
  }
} else {
  console.log('准入探测:    跳过（缺 origin 或 token 文件）');
}
