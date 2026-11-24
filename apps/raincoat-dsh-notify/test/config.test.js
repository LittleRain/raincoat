import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_CONFIG, normalizeConfig } from '../lib/config.js';

test('空配置落回默认值', () => {
  const config = normalizeConfig(undefined);
  assert.equal(config.enabled, true);
  assert.equal(config.onlyWhenBackground, true);
  assert.equal(config.minDurationMs, DEFAULT_CONFIG.minDurationMs);
  assert.deepEqual(config.onTurns, ['completed', 'error', 'blocked']);
  assert.deepEqual(config.frontmostApps, ['DeepSeek Harness']);
  assert.equal(config.webhook.enabled, false);
  assert.deepEqual(config.webhook.headers, {});
});

test('用户配置覆盖默认值，webhook 子项逐项合并', () => {
  const config = normalizeConfig({
    onlyWhenBackground: false,
    minDurationMs: 0,
    sound: '',
    webhook: { enabled: true, url: 'https://example.com/hook' },
  });
  assert.equal(config.onlyWhenBackground, false);
  assert.equal(config.minDurationMs, 0);
  assert.equal(config.sound, '');
  assert.equal(config.webhook.enabled, true);
  assert.equal(config.webhook.format, 'json');
  assert.equal(config.webhook.timeoutMs, 5000);
});

test('拼错字段会明确报错，而不是被默认值吞掉', () => {
  assert.throws(() => normalizeConfig({ onlyWhenBackgroud: false }), /不认识的字段 "onlyWhenBackgroud"/u);
  assert.throws(() => normalizeConfig({ webhook: { enabld: true } }), /webhook 不认识的字段 "enabld"/u);
});

test('非法取值会被拒绝', () => {
  assert.throws(() => normalizeConfig({ sound: 'Loud' }), /sound 只能是/u);
  assert.throws(() => normalizeConfig({ onTurns: ['done'] }), /onTurns 含未知取值/u);
  assert.throws(() => normalizeConfig({ locale: 'fr' }), /locale 只能是/u);
  assert.throws(() => normalizeConfig({ minDurationMs: -1 }), /minDurationMs 必须是/u);
  assert.throws(() => normalizeConfig({ previewChars: 5 }), /previewChars 必须是/u);
  assert.throws(() => normalizeConfig({ webhook: { enabled: true, url: '' } }), /webhook\.url 不能为空/u);
  assert.throws(() => normalizeConfig({ webhook: { enabled: true, url: 'ftp://x' } }), /http\(s\)/u);
});

test('数组字段去重并去空白', () => {
  const config = normalizeConfig({ frontmostApps: ['DeepSeek Harness', ' DeepSeek Harness ', 'DSH'] });
  assert.deepEqual(config.frontmostApps, ['DeepSeek Harness', 'DSH']);
});

test('通知后端与点击唤起字段', () => {
  assert.equal(normalizeConfig({}).backend, 'auto');
  assert.equal(normalizeConfig({}).clickToFocus, true);
  assert.equal(normalizeConfig({}).clickToOpenSession, true);
  assert.equal(normalizeConfig({ clickToOpenSession: false }).clickToOpenSession, false);
  assert.equal(normalizeConfig({}).activateBundleId, 'com.deepseek.dsh');
  assert.equal(normalizeConfig({ backend: 'terminal-notifier' }).backend, 'terminal-notifier');
  assert.equal(normalizeConfig({ clickToFocus: false, activateBundleId: '' }).clickToFocus, false);
  assert.throws(() => normalizeConfig({ backend: 'growl' }), /backend 只能是/u);
});
