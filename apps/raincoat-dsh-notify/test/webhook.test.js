import assert from 'node:assert/strict';
import test from 'node:test';

import { buildWebhookRequest, notificationText, postWebhook, webhookPayload } from '../lib/webhook.js';

const notification = {
  kind: 'turn',
  title: '✅ 任务完成',
  subtitle: '修复登录',
  body: '已经改好了',
  reason: 'completed',
  sessionId: 'session-1',
  cwd: '/tmp/app',
  durationMs: 12345,
  at: '2026-10-22T06:00:00.000Z',
};

test('notificationText 拼出标题/副标题/正文', () => {
  assert.equal(notificationText(notification), '✅ 任务完成\n修复登录\n已经改好了');
  assert.equal(notificationText({ title: 'T' }), 'T');
});

test('json 载荷包含会话、原因、耗时', () => {
  const payload = webhookPayload(notification);
  assert.equal(payload.source, 'dsh-notify');
  assert.equal(payload.sessionId, 'session-1');
  assert.equal(payload.durationMs, 12345);
  assert.equal(payload.cwd, '/tmp/app');
});

test('各平台请求体格式', () => {
  const json = buildWebhookRequest('json', notification);
  assert.match(json.headers['content-type'], /application\/json/u);
  assert.equal(JSON.parse(json.body).title, '✅ 任务完成');

  const bark = buildWebhookRequest('bark', notification);
  assert.deepEqual(Object.keys(JSON.parse(bark.body)).sort(), ['body', 'group', 'level', 'title']);
  assert.equal(JSON.parse(bark.body).body, '修复登录\n已经改好了');

  const ntfy = buildWebhookRequest('ntfy', notification);
  assert.equal(ntfy.headers.Title, '✅ 任务完成');
  assert.match(ntfy.body, /已经改好了/u);

  const wecom = buildWebhookRequest('wecom', notification);
  assert.equal(JSON.parse(wecom.body).msgtype, 'text');

  const feishu = buildWebhookRequest('feishu', notification);
  assert.equal(JSON.parse(feishu.body).msg_type, 'text');
});

test('postWebhook 使用配置的格式、请求头与超时', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return { ok: true, status: 204 };
  };

  const result = await postWebhook(notification, {
    url: 'https://example.com/hook',
    format: 'json',
    headers: { authorization: 'Bearer token' },
    timeoutMs: 2000,
    fetchImpl,
  });

  assert.deepEqual(result, { status: 204 });
  assert.equal(calls[0].url, 'https://example.com/hook');
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.headers.authorization, 'Bearer token');
  assert.ok(calls[0].init.signal instanceof AbortSignal);
});

test('非 2xx 与非法地址都会抛出', async () => {
  await assert.rejects(
    postWebhook(notification, {
      url: 'https://example.com/hook',
      format: 'json',
      fetchImpl: async () => ({ ok: false, status: 500 }),
    }),
    /HTTP 500/u,
  );

  await assert.rejects(
    postWebhook(notification, { url: 'not-a-url', format: 'json', fetchImpl: async () => ({ ok: true }) }),
    /http\(s\)/u,
  );
});
