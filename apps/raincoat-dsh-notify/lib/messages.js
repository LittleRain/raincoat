/**
 * 通知文案。中英双语，避免把中文写死在逻辑里。
 *
 * @module dsh-notify/messages
 */

const ZH = Object.freeze({
  turnTitle: Object.freeze({
    completed: '✅ 任务完成',
    error: '⚠️ 任务出错',
    blocked: '⛔ 任务受阻',
    aborted: '⏹ 任务已停止',
    'max-tokens': '📏 输出达到上限',
  }),
  goalTitle: Object.freeze({
    complete: '🎯 目标完成',
    blocked: '🚧 目标受阻',
  }),
  jobTitle: '🧰 后台任务结束',
  doneBody: '回到 DeepSeek Harness 查看完整结果',
  errorBody: '任务执行出错，回到 DeepSeek Harness 查看详情',
  goalBody: '目标已完成',
  goalBlockedBody: (message) => `目标受阻：${message}`,
  jobBody: (label, status) => [label, status].filter(Boolean).join(' · ') || '后台任务已结束',
  sessionFallback: 'DeepSeek Harness',
});

const EN = Object.freeze({
  turnTitle: Object.freeze({
    completed: '✅ Task complete',
    error: '⚠️ Task failed',
    blocked: '⛔ Task blocked',
    aborted: '⏹ Task stopped',
    'max-tokens': '📏 Output limit reached',
  }),
  goalTitle: Object.freeze({
    complete: '🎯 Goal complete',
    blocked: '🚧 Goal blocked',
  }),
  jobTitle: '🧰 Background job finished',
  doneBody: 'Return to DeepSeek Harness for the full result',
  errorBody: 'The task failed — return to DeepSeek Harness for details',
  goalBody: 'Goal completed',
  goalBlockedBody: (message) => `Goal blocked: ${message}`,
  jobBody: (label, status) => [label, status].filter(Boolean).join(' · ') || 'Background job finished',
  sessionFallback: 'DeepSeek Harness',
});

const TABLE = Object.freeze({ zh: ZH, en: EN });

/**
 * 取某语言的文案表。
 *
 * @param locale - `zh` 或 `en`。
 * @returns 该语言的文案对象。
 */
export function messagesFor(locale) {
  return TABLE[locale] ?? ZH;
}
