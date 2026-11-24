/**
 * 纯决策层：把 `session/event` 折成"要不要通知、通知什么"。
 *
 * 这里不做任何 I/O（不弹通知、不发 HTTP），因此可以用假的会话日志完整测试。
 * 真正的投递见 `index.js` / `lib/macos.js` / `lib/webhook.js`。
 *
 * @module dsh-notify/notifier
 */

import { lastAssistantPreview, sessionTitleFromLog, stripMarkdown, truncate } from './text.js';

/** 目标完成通知后，同一轮不再补发"任务完成"的窗口（毫秒）。 */
const GOAL_ECHO_WINDOW_MS = 20000;

/** 会话标题副标题的长度上限。 */
const SUBTITLE_MAX = 80;

/** 目标正文的长度上限。 */
const GOAL_BODY_MAX = 200;

/**
 * 把会话日志里最后一条 goal/change 折叠成当前目标。
 *
 * @param log - 会话事件日志。
 * @returns `{ phase, objective, blockedReason }`，没有目标时 undefined。
 */
function goalFromLog(log) {
  for (let index = log.length - 1; index >= 0; index -= 1) {
    const event = log[index];
    if (event?.type !== 'goal/change') continue;
    const goal = event.data?.goal;
    if (!goal || typeof goal.phase !== 'string') return undefined;
    return {
      phase: goal.phase,
      objective: typeof goal.objective === 'string' ? goal.objective : '',
      blockedReason: typeof goal.blockedReason?.message === 'string' ? goal.blockedReason.message : '',
    };
  }
  return undefined;
}

/**
 * 创建一个无副作用的决策器。
 *
 * @param options - `config`（已归一化）、`messages`（文案表）、`now`（时钟，测试可注入）。
 * @returns 带 `handle(session, event)` 的对象；返回通知意图或 null。
 */
export function createNotifier({ config, messages, now = () => Date.now() }) {
  const states = new WeakMap();

  /** 会话状态按对象身份存放在 WeakMap 里，会话被回收时自动清理。 */
  function stateFor(session) {
    let state = states.get(session);
    if (state !== undefined) return state;
    const log = Array.isArray(session.log) ? session.log : [];
    state = {
      turn: undefined,
      title: sessionTitleFromLog(log, session.header?.cwd, messages.sessionFallback),
      goal: goalFromLog(log),
      goalJustNotifiedAt: undefined,
    };
    states.set(session, state);
    return state;
  }

  /** 会话标题（副标题）。 */
  function subtitleOf(session, state) {
    return truncate(state.title || sessionTitleFromLog(session.log, session.header?.cwd, messages.sessionFallback), SUBTITLE_MAX);
  }

  /** 统一构造一条通知意图。 */
  function intent({ session, state, kind, title, body, reason, durationMs }) {
    return {
      id: `${session.id}:${now()}`,
      kind,
      title: `${config.titlePrefix}${title}`,
      subtitle: subtitleOf(session, state),
      body: truncate(body, 240),
      sessionId: session.id,
      cwd: session.header?.cwd ?? '',
      reason,
      durationMs,
      at: new Date(now()).toISOString(),
    };
  }

  /** 任务轮结束时是否有资格通知。 */
  function turnEnd(session, state, event) {
    const turn = event.data?.turn;
    const reason = event.data?.reason?.kind ?? 'completed';
    const startedAt = state.turn?.turn === turn ? state.turn.startedAt : undefined;
    state.turn = undefined;

    // 子 Agent 的每一轮不打扰用户；主 Agent 收尾时只报一次。
    if (session.header?.origin === 'subagent') return null;
    if (!config.onTurns.includes(reason)) return null;

    const durationMs = startedAt === undefined ? undefined : Math.max(0, now() - startedAt);
    if (durationMs !== undefined && durationMs < config.minDurationMs) return null;

    // 目标还在自动推进：中途每一轮都弹没有意义，等目标完成/受阻的统一通知。
    if (config.suppressWhenGoalActive && state.goal?.phase === 'active') return null;

    const justNotified = state.goalJustNotifiedAt;
    if (justNotified !== undefined && now() - justNotified < GOAL_ECHO_WINDOW_MS) {
      state.goalJustNotifiedAt = undefined;
      return null;
    }
    state.goalJustNotifiedAt = undefined;

    const preview = config.includePreview
      ? lastAssistantPreview(session.log, turn, { max: config.previewChars })
      : '';
    const errorMessage = typeof event.data?.reason?.error?.message === 'string'
      ? stripMarkdown(event.data.reason.error.message)
      : '';

    let body;
    if (reason === 'error') body = truncate(errorMessage, config.previewChars) || messages.errorBody;
    else body = preview || messages.doneBody;

    return intent({
      session,
      state,
      kind: 'turn',
      title: messages.turnTitle[reason] ?? messages.turnTitle.completed,
      body,
      reason,
      durationMs,
    });
  }

  /** 目标阶段变化：只在完成/受阻时通知，并进行中不打扰。 */
  function goalChange(session, state, event) {
    const goal = event.data?.goal;
    state.goal = goal && typeof goal.phase === 'string'
      ? {
          phase: goal.phase,
          objective: typeof goal.objective === 'string' ? goal.objective : '',
          blockedReason: typeof goal.blockedReason?.message === 'string' ? goal.blockedReason.message : '',
        }
      : undefined;

    if (state.goal === undefined) return null;
    if (!config.notifyOnGoal.includes(state.goal.phase)) return null;

    state.goalJustNotifiedAt = now();
    const objective = stripMarkdown(state.goal.objective);
    const blockedReason = stripMarkdown(state.goal.blockedReason);
    const body = state.goal.phase === 'blocked'
      ? messages.goalBlockedBody(truncate(blockedReason || objective, GOAL_BODY_MAX))
      : truncate(objective, GOAL_BODY_MAX) || messages.goalBody;

    return intent({
      session,
      state,
      kind: 'goal',
      title: messages.goalTitle[state.goal.phase],
      body,
      reason: `goal-${state.goal.phase}`,
      durationMs: undefined,
    });
  }

  /** 后台任务结束（默认关闭）。 */
  function jobSettled(session, state, event) {
    if (!config.notifyJobs) return null;
    const data = event.data ?? {};
    const startedAt = typeof data.startedAt === 'number' ? data.startedAt : undefined;
    const durationMs = startedAt === undefined ? undefined : Math.max(0, now() - startedAt);
    if (durationMs !== undefined && durationMs < config.jobMinDurationMs) return null;

    return intent({
      session,
      state,
      kind: 'job',
      title: messages.jobTitle,
      body: messages.jobBody(typeof data.label === 'string' ? data.label : '', typeof data.status === 'string' ? data.status : ''),
      reason: 'job-settled',
      durationMs,
    });
  }

  return {
    /**
     * 观察一个会话事件。
     *
     * @param session - 事件所属会话（Session 实例）。
     * @param event - 已提交的会话事件。
     * @returns 需要投递的通知意图，或 null。
     */
    handle(session, event) {
      if (!session || !event || typeof event.type !== 'string') return null;
      const state = stateFor(session);

      switch (event.type) {
        case 'turn/start':
          state.turn = { turn: event.data?.turn, startedAt: now() };
          state.goalJustNotifiedAt = undefined;
          return null;

        case 'session/title': {
          const title = typeof event.data?.title === 'string' ? event.data.title.trim() : '';
          if (title.length > 0) state.title = title;
          return null;
        }

        case 'turn/end':
          return turnEnd(session, state, event);

        case 'goal/change':
          return goalChange(session, state, event);

        case 'job/settled':
          return jobSettled(session, state, event);

        default:
          return null;
      }
    },
  };
}
