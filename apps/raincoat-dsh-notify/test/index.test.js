/**
 * 挂载层的回归测试：守住「点击通知能落到路由」这条链路的两个外部契约。
 *
 * 1. `/dsh-notify` 路由必须声明准入策略，否则 WebServer 默认的 `required`
 *    会把没有登录 Cookie 的点击 curl 直接 401 掉；
 * 2. 当前 origin 必须落盘，点击命令在点击那一刻才读它，
 *    这样 Desktop 重启换端口后，通知中心里的旧通知仍然打得通。
 */

import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { apply } from '../index.js';
import { routeAuth } from '../lib/http.js';

/** 记录注册信息的假 WebServer。 */
function fakeWebServer(origin = 'http://127.0.0.1:65246') {
  const routes = [];
  return {
    routes,
    register(route) {
      routes.push(route);
      return () => {};
    },
    getOrigin() {
      return origin;
    },
  };
}

/** 最小可用的 cordis 上下文：只实现 index.js 用到的几个面。 */
function fakeContext(webServer) {
  const handlers = [];
  return {
    handlers,
    logger: { info() {}, warn() {}, error() {} },
    on(event, handler) {
      handlers.push({ event, handler });
    },
    inject(_names, callback) {
      callback({
        webServer,
        effect() {
          return () => {};
        },
      });
    },
  };
}

test('路由声明准入策略，并把当前 origin 落盘', () => {
  const dir = mkdtempSync(join(tmpdir(), 'dsh-notify-'));
  const historyFile = join(dir, 'history.jsonl');
  const server = fakeWebServer();
  const ctx = fakeContext(server);

  try {
    apply(ctx, { historyFile });

    assert.equal(server.routes.length, 1);
    const [route] = server.routes;
    assert.equal(route.kind, 'prefix');
    assert.equal(route.path, '/dsh-notify');
    // 关键回归：没有 auth 时，点击命令的 POST 在准入层就 401 了。
    assert.equal(route.auth, routeAuth);
    assert.equal(route.auth({ method: 'POST' }), 'anonymous');
    assert.equal(route.auth({ method: 'GET' }), 'required');

    assert.equal(readFileSync(join(dir, 'origin'), 'utf8').trim(), 'http://127.0.0.1:65246');
    assert.match(readFileSync(join(dir, 'token'), 'utf8'), /^[0-9a-f]{32}$/u);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('端口未就绪时不写 origin，也不影响挂载', () => {
  const dir = mkdtempSync(join(tmpdir(), 'dsh-notify-'));
  const historyFile = join(dir, 'history.jsonl');
  const server = fakeWebServer();
  server.getOrigin = () => {
    throw new Error('not listening');
  };

  try {
    apply(fakeContext(server), { historyFile });
    assert.throws(() => readFileSync(join(dir, 'origin'), 'utf8'));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('配置无效时明确失败且不挂路由', () => {
  const dir = mkdtempSync(join(tmpdir(), 'dsh-notify-'));
  const server = fakeWebServer();
  try {
    apply(fakeContext(server), { historyFile: join(dir, 'history.jsonl'), unknownKey: true });
    assert.equal(server.routes.length, 0);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
