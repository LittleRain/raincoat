/**
 * 测试用的会话/事件工厂：只包含插件实际读取的字段。
 */

/** 造一个假会话。 */
export function makeSession({ id = 'session-test', cwd = '/tmp/workspace', origin, log = [] } = {}) {
  return {
    id,
    header: {
      cwd,
      ...(origin === undefined ? {} : { origin }),
    },
    log,
  };
}

/** 造 `turn/start` 事件。 */
export function turnStart(turn) {
  return { type: 'turn/start', data: { turn } };
}

/** 造 `assistant/message` 事件。 */
export function assistantMessage(turn, text, step = 1) {
  return {
    type: 'assistant/message',
    data: { turn, step, message: { role: 'assistant', content: [{ type: 'text', text }] } },
  };
}

/** 造 `turn/end` 事件。 */
export function turnEnd(turn, reason = { kind: 'completed' }) {
  return { type: 'turn/end', data: { turn, reason } };
}

/** 造 `session/title` 事件。 */
export function sessionTitle(title) {
  return { type: 'session/title', data: { title } };
}

/** 造 `goal/change` 事件。 */
export function goalChange(goal) {
  return { type: 'goal/change', data: { kind: 'goal/change', operation: 'edit', goal } };
}

/** 造 `job/settled` 事件。 */
export function jobSettled({ label = 'npm test', status = 'completed', startedAt } = {}) {
  return { type: 'job/settled', data: { jobId: 'job-1', label, status, startedAt } };
}

/**
 * 模拟真实会话：事件先落到日志，再通知决策器。
 * 真实环境里 `session/event` 只在事件已追加到 `session.log` 之后才发出。
 */
export function emit(notifier, session, event) {
  session.log.push(event);
  return notifier.handle(session, event);
}
