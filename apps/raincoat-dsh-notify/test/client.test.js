import assert from 'node:assert/strict';
import test from 'node:test';

// 模拟浏览器里的 `__ModuleLoader__`，加载客户端 bundle 并取出注册项。
let registration;
globalThis.window = {
  __ModuleLoader__: {
    load(entry) {
      registration = entry;
    },
  },
  focus() {},
};

await import('../client.js');

test('客户端 bundle 用包名注册并导出 apply/inject', () => {
  assert.ok(registration);
  assert.equal(registration.id, '@local/dsh-notify');
  const exported = registration.factory(() => {});
  assert.equal(typeof exported.apply, 'function');
  assert.deepEqual(exported.inject, ['uiWorkspace']);
});

test('轮询到会话后调用 openSession，并能在卸载时停止', async () => {
  const exported = registration.factory(() => {});
  const opened = [];
  const cleanups = [];
  const ctx = {
    uiWorkspace: { openSession: (id) => opened.push(id) },
    effect: (fn) => {
      cleanups.push(fn());
    },
  };

  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return { ok: true, json: async () => ({ sessionId: calls === 1 ? 'session-1' : null }) };
  };

  try {
    exported.apply(ctx, { pollIntervalMs: 60 });
    await new Promise((resolve) => setTimeout(resolve, 250));
    assert.deepEqual(opened, ['session-1']);
    assert.ok(calls >= 2);

    cleanups[0]();
    const seen = calls;
    await new Promise((resolve) => setTimeout(resolve, 150));
    assert.equal(calls, seen, '卸载后不应继续轮询');
  } finally {
    // 断言失败也要停掉轮询，否则定时器会让测试进程不退出。
    try {
      cleanups[0]?.();
    } catch {}
    globalThis.fetch = originalFetch;
  }
});
