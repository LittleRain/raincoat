import assert from 'node:assert/strict';
import test from 'node:test';

import { handleNotifyRoute, routeAuth } from '../lib/http.js';
import { createOpenRequestStore } from '../lib/open-requests.js';

/** 假的 ServerResponse，记录状态码与响应体。 */
function fakeResponse() {
  const state = { status: 0, headers: {}, body: '' };
  return {
    state,
    writeHead(status, headers) {
      state.status = status;
      state.headers = headers;
    },
    end(body) {
      state.body = body ?? '';
    },
  };
}

/** 造一次路由调用并解析 JSON 响应。 */
function call(store, { method = 'GET', url = '/dsh-notify/pending', headers = {} } = {}) {
  const res = fakeResponse();
  handleNotifyRoute({ req: { method, url, headers }, res, store });
  return { status: res.state.status, body: res.state.body ? JSON.parse(res.state.body) : undefined };
}

test('待打开会话：GET 取走并清空', () => {
  const store = createOpenRequestStore();
  assert.deepEqual(call(store), { status: 200, body: { sessionId: null } });

  const token = store.token;
  assert.deepEqual(
    call(store, { method: 'POST', url: '/dsh-notify/open?session=session-1', headers: { 'x-dsh-notify-token': token } }),
    { status: 200, body: { ok: true } },
  );
  assert.deepEqual(call(store), { status: 200, body: { sessionId: 'session-1' } });
  assert.deepEqual(call(store), { status: 200, body: { sessionId: null } });
});

test('没有令牌或令牌错误时拒绝写入', () => {
  const store = createOpenRequestStore();
  assert.equal(call(store, { method: 'POST', url: '/dsh-notify/open?session=x' }).status, 403);
  assert.equal(
    call(store, { method: 'POST', url: '/dsh-notify/open?session=x', headers: { 'x-dsh-notify-token': 'bad' } }).status,
    403,
  );
  assert.equal(store.take(), null);
});

test('令牌正确但缺少 session 时返回 400', () => {
  const store = createOpenRequestStore();
  assert.equal(
    call(store, { method: 'POST', url: '/dsh-notify/open', headers: { 'x-dsh-notify-token': store.token } }).status,
    400,
  );
});

test('未知路径返回 404', () => {
  const store = createOpenRequestStore();
  assert.equal(call(store, { url: '/dsh-notify/nope' }).status, 404);
});

test('准入策略：点击写入走匿名，前端轮询要登录态', () => {
  // 点击命令是本机 curl，没有浏览器 Cookie；默认的 required 会让它在准入层就 401。
  assert.equal(routeAuth({ method: 'POST' }), 'anonymous');
  assert.equal(routeAuth({ method: 'post' }), 'anonymous');
  assert.equal(routeAuth({ method: 'GET' }), 'required');
  assert.equal(routeAuth({}), 'required');
  assert.equal(routeAuth(undefined), 'required');
});
