import assert from 'node:assert/strict';
import test from 'node:test';

import {
  displayScript,
  findTerminalNotifier,
  frontmostAppName,
  isFrontmost,
  sendMacNotification,
  sendTerminalNotifier,
  soundPath,
  terminalNotifierArgs,
} from '../lib/macos.js';

/** 记录调用的假 exec。 */
function fakeExec(responses = {}) {
  const calls = [];
  const exec = async (command, args) => {
    calls.push([command, args]);
    if (command === 'lsappinfo' && args[0] === 'front') return { stdout: 'ASN:0x0-0x1234:\n' };
    if (command === 'lsappinfo') return { stdout: responses.lsappinfo ?? '"LSDisplayName"="DeepSeek Harness"\n' };
    return { stdout: '' };
  };
  return { calls, exec };
}

test('有副标题与无副标题生成不同脚本', () => {
  assert.equal(displayScript(true).length, 3);
  assert.match(displayScript(true)[1], /subtitle \(item 3 of argv\)/u);
  assert.doesNotMatch(displayScript(false)[1], /subtitle/u);
});

test('提示音路径只由声音名拼出', () => {
  assert.equal(soundPath('Glass'), '/System/Library/Sounds/Glass.aiff');
  assert.equal(soundPath(''), '');
});

test('前台应用名解析', async () => {
  const { exec } = fakeExec();
  assert.equal(await frontmostAppName(exec), 'DeepSeek Harness');
});

test('前台判定不区分大小写', () => {
  assert.equal(isFrontmost('DeepSeek Harness', ['DeepSeek Harness']), true);
  assert.equal(isFrontmost('deepseek harness', ['DeepSeek Harness']), true);
  assert.equal(isFrontmost('企业微信', ['DeepSeek Harness']), false);
  assert.equal(isFrontmost('', ['DeepSeek Harness']), false);
});

test('通知正文经 argv 传入，不做字符串拼接', async () => {
  const { calls, exec } = fakeExec();
  await sendMacNotification(
    { title: '标题 "引号"', subtitle: '副标题', body: '第一行\n第二行 `代码`' },
    { exec, sound: 'Glass' },
  );

  const [command, args] = calls[0];
  assert.equal(command, 'osascript');
  const separator = args.indexOf('--');
  assert.ok(separator > 0, '参数里应有 -- 分隔符');
  assert.deepEqual(args.slice(separator + 1), ['第一行\n第二行 `代码`', '标题 "引号"', '副标题']);

  // 提示音独立调用 afplay，不阻塞通知本身。
  assert.equal(calls[1][0], 'afplay');
  assert.deepEqual(calls[1][1], ['/System/Library/Sounds/Glass.aiff']);
});

test('静音时不调用 afplay，没有副标题时用两参数脚本', async () => {
  const { calls, exec } = fakeExec();
  await sendMacNotification({ title: 'T', subtitle: '', body: 'B' }, { exec, sound: '' });
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0][1].slice(-2), ['B', 'T']);
});

test('terminal-notifier 探测：显式配置 > 内置 > PATH > 常见位置', () => {
  const bundled = '/plugin/bin/terminal-notifier.app/Contents/MacOS/terminal-notifier';

  assert.equal(
    findTerminalNotifier({ override: '/custom/tn', root: '/plugin', env: { PATH: '' }, exists: () => true }),
    '/custom/tn',
  );
  assert.equal(
    findTerminalNotifier({ override: '/missing', root: '/plugin', env: { PATH: '' }, exists: (p) => p === bundled }),
    bundled,
  );
  assert.equal(
    findTerminalNotifier({ root: '/plugin', env: { PATH: '/usr/bin:/opt/x/bin' }, exists: (p) => p === '/opt/x/bin/terminal-notifier' }),
    '/opt/x/bin/terminal-notifier',
  );
  assert.equal(
    findTerminalNotifier({ root: '/plugin', env: { PATH: '' }, exists: () => true }),
    bundled,
    '内置副本优先于系统安装',
  );
  assert.equal(
    findTerminalNotifier({ env: { PATH: '' }, exists: (p) => p === '/opt/homebrew/bin/terminal-notifier' }),
    '/opt/homebrew/bin/terminal-notifier',
  );
  assert.equal(findTerminalNotifier({ root: '/plugin', env: { PATH: '' }, exists: () => false }), '');
});

test('terminal-notifier 参数：可选字段缺省时不传', () => {
  const full = terminalNotifierArgs(
    { title: '标题', subtitle: '副标题', body: '正文' },
    { activate: 'com.deepseek.dsh', sender: 'com.deepseek.dsh', group: 'g-1', sound: 'Glass' },
  );
  assert.deepEqual(full, [
    '-title', '标题',
    '-message', '正文',
    '-subtitle', '副标题',
    '-sound', 'Glass',
    '-group', 'g-1',
    '-sender', 'com.deepseek.dsh',
    '-activate', 'com.deepseek.dsh',
  ]);

  assert.deepEqual(terminalNotifierArgs({ title: 'T', body: 'B' }, {}), ['-title', 'T', '-message', 'B']);

  const clickable = terminalNotifierArgs(
    { title: 'T', body: 'B' },
    { activate: 'com.deepseek.dsh', execute: '/usr/bin/curl -s x' },
  );
  assert.equal(clickable[clickable.indexOf('-execute') + 1], '/usr/bin/curl -s x');
  assert.equal(clickable.indexOf('-activate') < clickable.indexOf('-execute'), true);
});

test('terminal-notifier 调用可执行文件而不是拼 shell', async () => {
  const calls = [];
  const exec = async (bin, args) => {
    calls.push([bin, args]);
    return { stdout: '' };
  };
  await sendTerminalNotifier(
    { title: 'T', subtitle: '', body: 'B' },
    { bin: '/plugin/bin/tn', exec, activate: 'com.deepseek.dsh', sender: 'com.deepseek.dsh', group: 'g', sound: '' },
  );
  assert.equal(calls[0][0], '/plugin/bin/tn');
  assert.ok(calls[0][1].includes('-activate'));
  await assert.rejects(sendTerminalNotifier({ title: 'T' }, { bin: '', exec }), /路径为空/u);
});
