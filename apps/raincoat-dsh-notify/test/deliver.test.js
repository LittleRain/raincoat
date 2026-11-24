import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeConfig } from '../lib/config.js';
import { createDeliverer } from '../lib/deliver.js';

const notification = {
  kind: 'turn',
  title: '✅ 任务完成',
  subtitle: '修复登录',
  body: '已经改好了',
  reason: 'completed',
  sessionId: 'session-1',
  cwd: '/tmp/app',
  durationMs: 9000,
  at: '2026-10-22T06:00:00.000Z',
};

/** 收集告警的假 logger。 */
function collector() {
  const warnings = [];
  const infos = [];
  return {
    warnings,
    infos,
    logger: {
      warn: (message) => warnings.push(String(message)),
      info: (message) => infos.push(String(message)),
    },
  };
}

/** 记录调用的假 exec。 */
function recordingExec({ frontName = 'DeepSeek Harness' } = {}) {
  const calls = [];
  const exec = async (command, args) => {
    calls.push([command, args]);
    if (command === 'lsappinfo' && args[0] === 'front') return { stdout: 'ASN:0x0-0x1:' };
    if (command === 'lsappinfo') return { stdout: `"LSDisplayName"="${frontName}"` };
    return { stdout: '' };
  };
  return { calls, exec };
}

test('DSH 在前台时直接跳过，不弹通知', async () => {
  const { warnings, logger } = collector();
  const { calls, exec } = recordingExec({ frontName: 'DeepSeek Harness' });
  const deliver = createDeliverer({ config: normalizeConfig({}), deps: { platform: 'darwin', exec }, logger });

  const outcome = await deliver(notification);
  assert.deepEqual(outcome, { skipped: true, native: false, webhook: false });
  assert.equal(calls.filter(([command]) => command === 'osascript').length, 0);
  assert.equal(warnings.length, 0);
});

test('DSH 在后台时弹系统通知', async () => {
  const { logger } = collector();
  const { calls, exec } = recordingExec({ frontName: '企业微信' });
  const deliver = createDeliverer({ config: normalizeConfig({}), deps: { platform: 'darwin', exec }, logger });

  const outcome = await deliver(notification);
  assert.deepEqual(outcome, { skipped: false, native: true, webhook: false });
  assert.equal(calls.filter(([command]) => command === 'osascript').length, 1);
});

test('关闭 onlyWhenBackground 后不再探前台', async () => {
  const { logger } = collector();
  const { calls, exec } = recordingExec();
  const deliver = createDeliverer({
    config: normalizeConfig({ onlyWhenBackground: false }),
    deps: { platform: 'darwin', exec },
    logger,
  });

  const outcome = await deliver(notification);
  assert.equal(outcome.native, true);
  assert.equal(calls.filter(([command]) => command === 'lsappinfo').length, 0);
});

test('Webhook 与系统通知并行投递', async () => {
  const { logger } = collector();
  const { exec } = recordingExec({ frontName: 'Safari' });
  const posted = [];
  const deliver = createDeliverer({
    config: normalizeConfig({ webhook: { enabled: true, url: 'https://example.com/hook' } }),
    deps: {
      platform: 'darwin',
      exec,
      fetch: async (url, init) => {
        posted.push({ url, init });
        return { ok: true, status: 200 };
      },
    },
    logger,
  });

  const outcome = await deliver(notification);
  assert.deepEqual(outcome, { skipped: false, native: true, webhook: true });
  assert.equal(posted.length, 1);
  assert.equal(JSON.parse(posted[0].init.body).title, '✅ 任务完成');
});

test('前台判定失败时按后台处理，不打断通知', async () => {
  const { warnings, logger } = collector();
  const deliver = createDeliverer({
    config: normalizeConfig({}),
    deps: {
      platform: 'darwin',
      frontmostAppName: async () => {
        throw new Error('lsappinfo missing');
      },
      exec: async () => ({ stdout: '' }),
    },
    logger,
  });

  const outcome = await deliver(notification);
  assert.equal(outcome.native, true);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /无法判断前台应用/u);
});

test('非 macOS 只记录一次"仅 Webhook 可用"', async () => {
  const { warnings, logger } = collector();
  const deliver = createDeliverer({ config: normalizeConfig({}), deps: { platform: 'linux', exec: async () => ({}) }, logger });

  await deliver(notification);
  await deliver(notification);
  assert.equal(warnings.filter((message) => /暂不支持系统通知/u.test(message)).length, 1);
});

test('投递失败只告警，不抛出', async () => {
  const { warnings, logger } = collector();
  const deliver = createDeliverer({
    config: normalizeConfig({ onlyWhenBackground: false }),
    deps: {
      platform: 'darwin',
      exec: async () => {
        throw new Error('osascript failed');
      },
    },
    logger,
  });

  const outcome = await deliver(notification);
  assert.equal(outcome.native, false);
  assert.ok(warnings.some((message) => /投递失败/u.test(message)));
});

test('每次决策都写入历史（含前台跳过与失败）', async () => {
  const { logger } = collector();
  const records = [];
  const { exec } = recordingExec({ frontName: 'DeepSeek Harness' });
  const deliver = createDeliverer({
    config: normalizeConfig({}),
    deps: { platform: 'darwin', exec, history: { record: async (entry) => records.push(entry) } },
    logger,
  });

  await deliver(notification);
  assert.equal(records.length, 1);
  assert.equal(records[0].skipped, true);
  assert.equal(records[0].native, false);
  assert.equal(records[0].title, '✅ 任务完成');
  assert.equal(records[0].sessionId, 'session-1');
});

test('优先用 terminal-notifier，并带上点击唤起参数', async () => {
  const { logger } = collector();
  const calls = [];
  const exec = async (bin, args) => {
    calls.push([bin, args]);
    if (bin === 'lsappinfo' && args[0] === 'front') return { stdout: 'ASN:1' };
    if (bin === 'lsappinfo') return { stdout: '"LSDisplayName"="Safari"' };
    return { stdout: '' };
  };
  const deliver = createDeliverer({
    config: normalizeConfig({}),
    deps: { platform: 'darwin', exec, terminalNotifierPath: '/plugin/bin/tn' },
    logger,
  });

  const outcome = await deliver(notification);
  assert.equal(outcome.native, true);
  const [bin, args] = calls.find(([bin]) => bin === '/plugin/bin/tn');
  assert.equal(bin, '/plugin/bin/tn');
  assert.ok(args.includes('-activate'));
  assert.equal(args[args.indexOf('-activate') + 1], 'com.deepseek.dsh');
  assert.equal(args[args.indexOf('-group') + 1], 'dsh-notify:session-1');
  assert.equal(calls.filter(([bin]) => bin === 'osascript').length, 0);
});

test('backend: osascript 时即使装了 terminal-notifier 也不用', async () => {
  const { logger } = collector();
  const calls = [];
  const exec = async (bin) => {
    calls.push([bin]);
    if (bin === 'lsappinfo') return { stdout: '"LSDisplayName"="Safari"' };
    return { stdout: '' };
  };
  const deliver = createDeliverer({
    config: normalizeConfig({ backend: 'osascript' }),
    deps: { platform: 'darwin', exec, terminalNotifierPath: '/plugin/bin/tn' },
    logger,
  });
  await deliver(notification);
  assert.equal(calls.filter(([bin]) => bin === 'osascript').length, 1);
  assert.equal(calls.filter(([bin]) => bin === '/plugin/bin/tn').length, 0);
});

test('backend: terminal-notifier 但没找到时告警并回退', async () => {
  const { warnings, logger } = collector();
  const exec = async () => ({ stdout: '"LSDisplayName"="Safari"' });
  const deliver = createDeliverer({
    config: normalizeConfig({ backend: 'terminal-notifier' }),
    deps: { platform: 'darwin', exec, terminalNotifierPath: '' },
    logger,
  });
  await deliver(notification);
  assert.ok(warnings.some((message) => /没找到 terminal-notifier/u.test(message)));
});

test('点击打开会话的命令通过 -execute 传给 terminal-notifier', async () => {
  const { logger } = collector();
  const calls = [];
  const exec = async (bin, args) => {
    calls.push([bin, args]);
    if (bin === 'lsappinfo') return { stdout: '"LSDisplayName"="Safari"' };
    return { stdout: '' };
  };
  const deliver = createDeliverer({
    config: normalizeConfig({}),
    deps: {
      platform: 'darwin',
      exec,
      terminalNotifierPath: '/plugin/bin/tn',
      openSessionCommand: (sessionId) => `/usr/bin/curl ... session=${sessionId}`,
    },
    logger,
  });

  await deliver(notification);
  const [, args] = calls.find(([bin]) => bin === '/plugin/bin/tn');
  assert.equal(args[args.indexOf('-execute') + 1], '/usr/bin/curl ... session=session-1');
});

test('关闭 clickToOpenSession 时不传 -execute', async () => {
  const { logger } = collector();
  const calls = [];
  const exec = async (bin, args) => {
    calls.push([bin, args]);
    if (bin === 'lsappinfo') return { stdout: '"LSDisplayName"="Safari"' };
    return { stdout: '' };
  };
  const deliver = createDeliverer({
    config: normalizeConfig({ clickToOpenSession: false }),
    deps: { platform: 'darwin', exec, terminalNotifierPath: '/plugin/bin/tn', openSessionCommand: () => 'should-not-run' },
    logger,
  });
  await deliver(notification);
  const [, args] = calls.find(([bin]) => bin === '/plugin/bin/tn');
  assert.equal(args.includes('-execute'), false);
});
