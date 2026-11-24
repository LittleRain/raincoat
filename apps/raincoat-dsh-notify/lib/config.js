/**
 * 插件配置：默认值 + 严格校验。
 *
 * `config` 在 patch 层是整段替换，所以这里做一次显式归一化：
 * 缺省项落回默认值，拼错的键直接报错，避免"配了但没生效"。
 *
 * @module dsh-notify/config
 */

/** `turn/end` 可能给出的结束原因。 */
export const TURN_REASONS = Object.freeze(['completed', 'error', 'blocked', 'aborted', 'max-tokens']);

/** 目标的生命周期阶段。 */
export const GOAL_PHASES = Object.freeze(['active', 'paused', 'blocked', 'complete']);

/** 支持的通知语言。 */
export const LOCALES = Object.freeze(['zh', 'en']);

/** macOS 系统提示音（/System/Library/Sounds 下的名字）。 */
export const MACOS_SOUNDS = Object.freeze([
  'Basso', 'Blow', 'Bottle', 'Frog', 'Funk', 'Glass', 'Hero',
  'Morse', 'Ping', 'Pop', 'Purr', 'Sosumi', 'Submarine', 'Tink',
]);

/** Webhook 请求体格式。 */
export const WEBHOOK_FORMATS = Object.freeze(['json', 'bark', 'ntfy', 'wecom', 'feishu']);

/** 系统通知的发送方式。 */
export const BACKENDS = Object.freeze(['auto', 'osascript', 'terminal-notifier']);

/** 默认配置。 */
export const DEFAULT_CONFIG = Object.freeze({
  /** 总开关。 */
  enabled: true,
  /** 只有当 DeepSeek Harness 不在前台时才通知，避免盯着看时被重复打扰。 */
  onlyWhenBackground: true,
  /** 判定"在前台"的 macOS 应用显示名（不区分大小写）。 */
  frontmostApps: Object.freeze(['DeepSeek Harness']),
  /** 短于一览而过的任务不通知（毫秒）。0 表示每轮都通知。 */
  minDurationMs: 6000,
  /** 哪些 turn 结束原因需要通知。 */
  onTurns: Object.freeze(['completed', 'error', 'blocked']),
  /** 目标进行中时，不按"每一轮"通知，只在目标完成/受阻时通知一次。 */
  suppressWhenGoalActive: true,
  /** 目标到达哪些阶段时通知。 */
  notifyOnGoal: Object.freeze(['complete', 'blocked']),
  /** 是否通知后台任务的结束（长命令、子任务）。 */
  notifyJobs: false,
  /** 后台任务至少运行多久才通知（毫秒）。 */
  jobMinDurationMs: 30000,
  /** 系统通知发送方式：auto 优先用 terminal-notifier（可点击唤起），不可用时回退 osascript。 */
  backend: 'auto',
  /** `terminal-notifier` 可执行文件路径；空字符串表示自动探测（插件内置 → PATH → 常见安装位置）。 */
  terminalNotifierPath: '',
  /** 点击通知时唤起哪个应用（bundle id）；空字符串表示点击不唤起。 */
  activateBundleId: 'com.deepseek.dsh',
  /** 让通知在通知中心显示成哪个应用（bundle id）；空字符串表示显示为 terminal-notifier。 */
  senderBundleId: '',
  /** 是否在点击通知时唤起应用。 */
  clickToFocus: true,
  /** 是否在点击通知时直接打开对应会话（需要客户端插件配合）。 */
  clickToOpenSession: true,
  /** macOS 提示音；空字符串表示静音。 */
  sound: 'Glass',
  /** 通知文案语言。 */
  locale: 'zh',
  /** 标题前缀，例如 `[DSH] `；默认不加。 */
  titlePrefix: '',
  /** 是否在正文里带上助手最后一段回复的摘要。 */
  includePreview: true,
  /** 预览正文的最大字符数。 */
  previewChars: 160,
  /** 通知历史保留条数；0 关闭历史文件。 */
  historySize: 20,
  /** 历史文件路径；空字符串表示默认的 `$DSH_HOME/notify/history.jsonl`。 */
  historyFile: '',
  /** 可选的远端推送。 */
  webhook: Object.freeze({
    enabled: false,
    url: '',
    format: 'json',
    timeoutMs: 5000,
    headers: Object.freeze({}),
  }),
});

const TOP_LEVEL_KEYS = Object.freeze(Object.keys(DEFAULT_CONFIG));
const WEBHOOK_KEYS = Object.freeze(Object.keys(DEFAULT_CONFIG.webhook));

/** 统一抛出带字段名的配置错误。 */
function fail(message) {
  throw new Error(`dsh-notify config: ${message}`);
}

/** 必须是布尔值。 */
function boolean(name, value) {
  if (typeof value !== 'boolean') fail(`${name} 必须是 true/false，收到 ${JSON.stringify(value)}`);
  return value;
}

/** 必须是非负整数，且落在给定区间内。 */
function integer(name, value, { min = 0, max = Number.MAX_SAFE_INTEGER } = {}) {
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    fail(`${name} 必须是 ${min}–${max} 之间的整数，收到 ${JSON.stringify(value)}`);
  }
  return value;
}

/** 必须是非空字符串。 */
function text(name, value, { allowEmpty = false } = {}) {
  if (typeof value !== 'string') fail(`${name} 必须是字符串，收到 ${JSON.stringify(value)}`);
  const trimmed = value.trim();
  if (!allowEmpty && trimmed.length === 0) fail(`${name} 不能为空`);
  return trimmed;
}

/** 必须是字符串数组。 */
function stringList(name, value) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    fail(`${name} 必须是字符串数组，收到 ${JSON.stringify(value)}`);
  }
  return [...new Set(value.map((item) => item.trim()).filter(Boolean))];
}

/** 必须是"允许值"之一。 */
function oneOf(name, value, allowed) {
  if (!allowed.includes(value)) fail(`${name} 只能是 ${allowed.join(' / ')}，收到 ${JSON.stringify(value)}`);
  return value;
}

/** 必须是"允许值"组成的子集。 */
function subset(name, value, allowed) {
  const list = stringList(name, value);
  for (const item of list) {
    if (!allowed.includes(item)) fail(`${name} 含未知取值 "${item}"，可选：${allowed.join(' / ')}`);
  }
  return [...new Set(list)];
}

/** 校验 webhook 子配置。 */
function normalizeWebhook(input) {
  if (input === undefined) return { ...DEFAULT_CONFIG.webhook, headers: {} };
  if (input === null || typeof input !== 'object' || Array.isArray(input)) {
    fail(`webhook 必须是对象，收到 ${JSON.stringify(input)}`);
  }
  for (const key of Object.keys(input)) {
    if (!WEBHOOK_KEYS.includes(key)) fail(`webhook 不认识的字段 "${key}"（可用：${WEBHOOK_KEYS.join(', ')}）`);
  }
  const merged = { ...DEFAULT_CONFIG.webhook, ...input };
  const enabled = boolean('webhook.enabled', merged.enabled);
  const url = text('webhook.url', merged.url, { allowEmpty: !enabled });
  if (enabled && !/^https?:\/\//u.test(url)) fail('webhook.url 必须是 http(s) 地址');

  const headers = merged.headers ?? {};
  if (typeof headers !== 'object' || Array.isArray(headers)) {
    fail('webhook.headers 必须是字符串键值对象');
  }
  for (const [key, value] of Object.entries(headers)) {
    if (typeof value !== 'string') fail(`webhook.headers.${key} 必须是字符串`);
  }

  return {
    enabled,
    url,
    format: oneOf('webhook.format', merged.format, WEBHOOK_FORMATS),
    timeoutMs: integer('webhook.timeoutMs', merged.timeoutMs, { min: 200, max: 60000 }),
    headers: { ...headers },
  };
}

/**
 * 合并默认值并校验一份用户配置。
 *
 * @param input - patch 层传入的原始配置；undefined 表示全默认。
 * @returns 归一化后的配置对象。
 * @throws 当出现未知字段或类型错误时，附带具体字段名。
 */
export function normalizeConfig(input) {
  if (input === undefined || input === null) input = {};
  if (typeof input !== 'object' || Array.isArray(input)) {
    fail(`config 必须是一个对象，收到 ${JSON.stringify(input)}`);
  }
  for (const key of Object.keys(input)) {
    if (!TOP_LEVEL_KEYS.includes(key)) fail(`不认识的字段 "${key}"（可用：${TOP_LEVEL_KEYS.join(', ')}）`);
  }

  const merged = { ...DEFAULT_CONFIG, ...input };
  const sound = text('sound', merged.sound, { allowEmpty: true });
  if (sound !== '' && !MACOS_SOUNDS.includes(sound)) {
    fail(`sound 只能是空字符串或 ${MACOS_SOUNDS.join(' / ')} 之一，收到 ${JSON.stringify(sound)}`);
  }

  return {
    enabled: boolean('enabled', merged.enabled),
    onlyWhenBackground: boolean('onlyWhenBackground', merged.onlyWhenBackground),
    frontmostApps: stringList('frontmostApps', merged.frontmostApps),
    minDurationMs: integer('minDurationMs', merged.minDurationMs, { min: 0, max: 3600000 }),
    onTurns: subset('onTurns', merged.onTurns, TURN_REASONS),
    suppressWhenGoalActive: boolean('suppressWhenGoalActive', merged.suppressWhenGoalActive),
    notifyOnGoal: subset('notifyOnGoal', merged.notifyOnGoal, GOAL_PHASES),
    notifyJobs: boolean('notifyJobs', merged.notifyJobs),
    jobMinDurationMs: integer('jobMinDurationMs', merged.jobMinDurationMs, { min: 0, max: 3600000 }),
    backend: oneOf('backend', merged.backend, BACKENDS),
    terminalNotifierPath: text('terminalNotifierPath', merged.terminalNotifierPath, { allowEmpty: true }),
    activateBundleId: text('activateBundleId', merged.activateBundleId, { allowEmpty: true }),
    senderBundleId: text('senderBundleId', merged.senderBundleId, { allowEmpty: true }),
    clickToFocus: boolean('clickToFocus', merged.clickToFocus),
    clickToOpenSession: boolean('clickToOpenSession', merged.clickToOpenSession),
    sound,
    locale: oneOf('locale', merged.locale, LOCALES),
    titlePrefix: text('titlePrefix', merged.titlePrefix, { allowEmpty: true }),
    includePreview: boolean('includePreview', merged.includePreview),
    previewChars: integer('previewChars', merged.previewChars, { min: 20, max: 400 }),
    historySize: integer('historySize', merged.historySize, { min: 0, max: 200 }),
    historyFile: text('historyFile', merged.historyFile, { allowEmpty: true }),
    webhook: normalizeWebhook(input.webhook),
  };
}
