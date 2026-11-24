import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeConfig } from '../lib/config.js';
import { messagesFor } from '../lib/messages.js';
import { createNotifier } from '../lib/notifier.js';
import {
  assistantMessage,
  emit,
  goalChange,
  jobSettled,
  makeSession,
  sessionTitle,
  turnEnd,
  turnStart,
} from './helpers.js';

/** 造一个时钟可控的决策器。 */
function setup(overrides = {}) {
  const clock = { now: 1_000 };
  const config = normalizeConfig({ minDurationMs: 0, ...overrides });
  const notifier = createNotifier({ config, messages: messagesFor('zh'), now: () => clock.now });
  return { clock, config, notifier };
}

test('完成一轮：标题、副标题、助手回复摘要都对', () => {
  const { clock, notifier } = setup();
  const session = makeSession({ cwd: '/tmp/my-app' });

  assert.equal(emit(notifier, session, turnStart(1)), null);
  clock.now += 12_000;
  assert.equal(emit(notifier, session, assistantMessage(1, '修好了 **登录** 逻辑。')), null);

  const notification = emit(notifier, session, turnEnd(1));
  assert.ok(notification);
  assert.equal(notification.kind, 'turn');
  assert.equal(notification.title, '✅ 任务完成');
  assert.equal(notification.subtitle, 'my-app');
  assert.equal(notification.body, '修好了 登录 逻辑。');
  assert.equal(notification.durationMs, 12_000);
  assert.equal(notification.sessionId, 'session-test');
});

test('短任务被最短时长过滤', () => {
  const { clock, notifier } = setup({ minDurationMs: 6_000 });
  const session = makeSession();
  emit(notifier, session, turnStart(1));
  clock.now += 1_000;
  assert.equal(emit(notifier, session, turnEnd(1)), null);
});

test('子 Agent 的轮次不通知', () => {
  const { clock, notifier } = setup();
  const session = makeSession({ origin: 'subagent' });
  emit(notifier, session, turnStart(1));
  clock.now += 60_000;
  assert.equal(emit(notifier, session, turnEnd(1)), null);
});

test('默认不通知 aborted / max-tokens，配置后可通知', () => {
  const { clock, notifier } = setup();
  const session = makeSession();
  emit(notifier, session, turnStart(1));
  clock.now += 30_000;
  assert.equal(emit(notifier, session, turnEnd(1, { kind: 'aborted' })), null);

  const second = setup({ onTurns: ['max-tokens'] });
  const s2 = makeSession({ id: 's2' });
  emit(second.notifier, s2, turnStart(1));
  second.clock.now += 30_000;
  assert.equal(emit(second.notifier, s2, turnEnd(1, { kind: 'max-tokens' }))?.title, '📏 输出达到上限');
});

test('出错时正文带上错误信息', () => {
  const { clock, notifier } = setup();
  const session = makeSession();
  emit(notifier, session, turnStart(1));
  clock.now += 30_000;
  const notification = emit(
    notifier,
    session,
    turnEnd(1, { kind: 'error', error: { message: '模型请求超时', code: 'TIMEOUT' } }),
  );
  assert.equal(notification.title, '⚠️ 任务出错');
  assert.equal(notification.body, '模型请求超时');
});

test('目标进行中不按轮通知，目标完成时只通知一次', () => {
  const { clock, notifier } = setup();
  const session = makeSession();

  emit(notifier, session, goalChange({ phase: 'active', objective: '把通知插件装好' }));
  emit(notifier, session, turnStart(1));
  clock.now += 60_000;
  assert.equal(emit(notifier, session, turnEnd(1)), null, '目标进行中应静默');

  const goalDone = emit(notifier, session, goalChange({ phase: 'complete', objective: '把通知插件装好' }));
  assert.equal(goalDone.title, '🎯 目标完成');
  assert.equal(goalDone.body, '把通知插件装好');

  // 目标完成后同一轮还会收到 turn/end，不应再补一条"任务完成"。
  assert.equal(emit(notifier, session, turnEnd(2)), null);
});

test('目标受阻时通知受阻原因', () => {
  const { notifier } = setup();
  const session = makeSession();
  const notification = emit(
    notifier,
    session,
    goalChange({ phase: 'blocked', objective: '迁移数据库', blockedReason: { code: 'db-locked', message: '数据库被占用' } }),
  );
  assert.equal(notification.title, '🚧 目标受阻');
  assert.equal(notification.body, '目标受阻：数据库被占用');
});

test('恢复会话时从日志折叠出进行中的目标', () => {
  const { clock, notifier } = setup();
  const session = makeSession({
    log: [
      sessionTitle('旧会话'),
      goalChange({ phase: 'active', objective: '继续修复' }),
      turnStart(3),
    ],
  });
  clock.now += 60_000;
  assert.equal(emit(notifier, session, turnEnd(3)), null);
});

test('会话标题事件会更新副标题', () => {
  const { clock, notifier } = setup();
  const session = makeSession();
  emit(notifier, session, sessionTitle('重构通知模块'));
  emit(notifier, session, turnStart(1));
  clock.now += 20_000;
  const notification = emit(notifier, session, turnEnd(1));
  assert.equal(notification.subtitle, '重构通知模块');
});

test('关闭摘要时正文回落到兜底文案', () => {
  const { clock, notifier } = setup({ includePreview: false });
  const session = makeSession();
  emit(notifier, session, turnStart(1));
  clock.now += 20_000;
  emit(notifier, session, assistantMessage(1, '很长的回复'));
  const notification = emit(notifier, session, turnEnd(1));
  assert.equal(notification.body, '回到 DeepSeek Harness 查看完整结果');
});

test('后台任务通知默认关闭，开启后按最短时长过滤', () => {
  const { notifier } = setup();
  assert.equal(emit(notifier, makeSession(), jobSettled({ startedAt: Date.now() })), null);

  const enabled = setup({ notifyJobs: true, jobMinDurationMs: 10_000 });
  const session = makeSession();
  assert.equal(emit(enabled.notifier, session, jobSettled({ startedAt: enabled.clock.now - 1_000 })), null);
  const notification = emit(
    enabled.notifier,
    session,
    jobSettled({ startedAt: enabled.clock.now - 60_000, status: 'completed' }),
  );
  assert.equal(notification.title, '🧰 后台任务结束');
  assert.match(notification.body, /npm test/u);
});

test('未知事件与空参数不会出错', () => {
  const { notifier } = setup();
  const session = makeSession();
  assert.equal(notifier.handle(session, { type: 'todo/write', data: {} }), null);
  assert.equal(notifier.handle(null, turnEnd(1)), null);
  assert.equal(notifier.handle(session, null), null);
});
