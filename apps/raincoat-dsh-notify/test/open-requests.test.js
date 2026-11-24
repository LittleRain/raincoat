import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

import { buildOpenCommand, createOpenRequestStore } from '../lib/open-requests.js';

const execFileAsync = promisify(execFile);

test('取走一次后清空', () => {
  const store = createOpenRequestStore();
  assert.equal(store.take(), null);
  assert.equal(store.request('session-1'), true);
  assert.equal(store.take(), 'session-1');
  assert.equal(store.take(), null);
});

test('超过有效期作废', () => {
  const clock = { now: 1_000 };
  const store = createOpenRequestStore({ now: () => clock.now, ttlMs: 5_000 });
  store.request('session-1');
  clock.now += 6_000;
  assert.equal(store.take(), null);
});

test('新请求覆盖旧请求，空 id 被拒绝', () => {
  const store = createOpenRequestStore();
  assert.equal(store.request(''), false);
  assert.equal(store.request('   '), false);
  store.request('session-1');
  store.request('session-2');
  assert.equal(store.take(), 'session-2');
});

test('令牌校验', () => {
  const store = createOpenRequestStore();
  assert.equal(store.verify(store.token), true);
  assert.equal(store.verify('nope'), false);
  assert.equal(store.verify(''), false);
  assert.equal(store.verify(undefined), false);
});

test('点击命令：令牌与 origin 走文件，URL 用双引号包住', () => {
  const command = buildOpenCommand({
    originFile: '/Users/me/.dsh/notify/origin',
    tokenFile: '/Users/me/.dsh/notify/token',
    sessionId: 'session-8a3f-4b2c',
  });
  assert.match(command, /^\/usr\/bin\/curl /u);
  assert.ok(command.includes(`/bin/cat '/Users/me/.dsh/notify/token'`));
  assert.ok(command.includes(`/bin/cat '/Users/me/.dsh/notify/origin'`));
  assert.ok(command.includes('/dsh-notify/open?session=session-8a3f-4b2c"'));
  // 端口不能在发通知时就写死：Desktop 每次启动的端口是随机的。
  assert.ok(!command.includes(':65246'));
});

test('点击命令：origin 在点击那一刻才展开', () => {
  const command = buildOpenCommand({
    originFile: '/tmp/origin',
    tokenFile: '/tmp/token',
    sessionId: 'session-1',
  });
  assert.ok(command.includes('"$(/bin/cat \'/tmp/origin\')/dsh-notify/open?session=session-1"'));
});

test('会话 id 含可疑字符时拒绝生成命令', () => {
  for (const sessionId of ["session-1'&x", 'a b', '../etc', '', undefined]) {
    assert.equal(
      buildOpenCommand({ originFile: '/tmp/origin', tokenFile: '/tmp/token', sessionId }),
      '',
      `应拒绝 ${String(sessionId)}`,
    );
  }
});

test('命令真的能被 sh 跑通：点一次就把会话 id 与令牌送到当前 origin', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'dsh-notify-cmd-'));
  const received = [];
  const server = createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
    });
    req.on('end', () => {
      received.push({ method: req.method, url: req.url, token: req.headers['x-dsh-notify-token'], body });
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end('{"ok":true}');
    });
  });

  try {
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const { port } = server.address();
    const originFile = join(dir, 'origin');
    const tokenFile = join(dir, 'token');
    // 带空格与单引号的目录名，顺便验证命令里的引号处理。
    writeFileSync(originFile, `http://127.0.0.1:${port}\n`);
    writeFileSync(tokenFile, "tok'en with space\n");

    const command = buildOpenCommand({ originFile, tokenFile, sessionId: 'session-8a3f-4b2c' });
    await execFileAsync('/bin/sh', ['-c', command]);

    assert.equal(received.length, 1);
    assert.equal(received[0].method, 'POST');
    assert.equal(received[0].url, '/dsh-notify/open?session=session-8a3f-4b2c');
    assert.equal(received[0].token, "tok'en with space");
  } finally {
    await new Promise((resolve) => server.close(resolve));
    rmSync(dir, { recursive: true, force: true });
  }
});
