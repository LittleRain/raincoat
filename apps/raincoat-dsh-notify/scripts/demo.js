#!/usr/bin/env node
/**
 * 手动发一条和真实通知同形的内容，用来确认通知链路是否打通。
 *
 *   node scripts/demo.js              # 走插件实际使用的后端
 *   node scripts/demo.js --sound Ping
 *   node scripts/demo.js --osascript  # 强制用 osascript（点击不会唤起应用）
 */

import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { MACOS_SOUNDS } from '../lib/config.js';
import { findTerminalNotifier, sendMacNotification, sendTerminalNotifier } from '../lib/macos.js';

const args = process.argv.slice(2);
const soundIndex = args.indexOf('--sound');
const sound = soundIndex >= 0 ? args[soundIndex + 1] : 'Glass';
if (sound && !MACOS_SOUNDS.includes(sound)) {
  console.error(`未知的提示音 "${sound}"，可选：${MACOS_SOUNDS.join(' / ')}`);
  process.exit(1);
}

const notification = {
  title: '✅ 任务完成',
  subtitle: 'dsh-notify 自检',
  body: '看到这条通知，说明通知链路已经打通。点击它应当唤起 DeepSeek Harness。',
};

const forceOsascript = args.includes('--osascript');
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const terminalNotifier = forceOsascript ? '' : findTerminalNotifier({ root });

if (terminalNotifier.length > 0) {
  await sendTerminalNotifier(notification, {
    bin: terminalNotifier,
    activate: 'com.deepseek.dsh',
    group: 'dsh-notify-demo',
    sound,
  });
  console.log(`已用 terminal-notifier 发送（${terminalNotifier}）。点击通知应唤起 DeepSeek Harness。`);
} else {
  await sendMacNotification(notification, { sound });
  console.log(
    `已用 osascript 发送（提示音：${sound || '静音'}）。点击不会唤起应用；`
      + '若系统设置里没允许 DeepSeek Harness 通知，请先允许。',
  );
}
