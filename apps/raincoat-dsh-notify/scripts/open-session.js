#!/usr/bin/env node
/**
 * 模拟「点击通知」：向运行中的 DSH 投递一次打开会话请求。
 *
 * 用来单独验证客户端插件（轮询 → 切会话）是否生效，不依赖通知点击。
 *
 *   node scripts/open-session.js <sessionId>
 *
 * 会话 id 可以从 `~/.dsh/notify/history.jsonl` 最后一条里拿。
 */

import { readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const sessionId = process.argv[2];
if (!sessionId) {
  console.error('用法: node scripts/open-session.js <sessionId>');
  process.exit(1);
}

const home = process.env.DSH_HOME || join(homedir(), '.dsh');
const tokenFile = join(home, 'notify', 'token');
const originFile = join(home, 'notify', 'origin');

/** 优先用插件落盘的当前 origin（端口每次启动都会变），其次才是环境变量与老默认值。 */
function readOrigin() {
  if (process.env.DSH_WEB_URL) return process.env.DSH_WEB_URL;
  try {
    return readFileSync(originFile, 'utf8').trim();
  } catch {
    return 'http://127.0.0.1:65246';
  }
}

const webUrl = readOrigin();

let token;
try {
  token = readFileSync(tokenFile, 'utf8').trim();
} catch (error) {
  console.error(`读不到令牌文件 ${tokenFile}：${error.message}`);
  console.error('（插件启动时才会写它；先确认插件已加载并重启过 DeepSeek Harness）');
  process.exit(1);
}

const response = await fetch(`${webUrl}/dsh-notify/open?session=${encodeURIComponent(sessionId)}`, {
  method: 'POST',
  headers: { 'x-dsh-notify-token': token },
});

if (!response.ok) {
  console.error(`投递失败：HTTP ${response.status}`);
  process.exit(1);
}

console.log(`已投递打开会话请求：${sessionId}`);
console.log('如果客户端插件在工作，最多 1.2 秒内 DSH 会切到该会话。');
