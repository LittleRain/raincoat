import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

import { createHistory } from '../lib/history.js';

test('历史文件只保留最近 N 条', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-notify-'));
  const file = join(dir, 'nested', 'history.jsonl');
  const history = createHistory({ file, size: 2, now: () => 1_700_000_000_000 });

  try {
    await history.record({ title: '第一条' });
    await history.record({ title: '第二条' });
    await history.record({ title: '第三条' });

    const lines = (await readFile(file, 'utf8')).split('\n').filter(Boolean);
    assert.equal(lines.length, 2);
    assert.deepEqual(lines.map((line) => JSON.parse(line).title), ['第二条', '第三条']);
    assert.match(JSON.parse(lines[1]).at, /^\d{4}-\d{2}-\d{2}T/u);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('size 为 0 或路径为空时不写文件', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'dsh-notify-'));
  const file = join(dir, 'history.jsonl');
  try {
    await createHistory({ file, size: 0 }).record({ title: '忽略' });
    await createHistory({ file: '', size: 5 }).record({ title: '忽略' });
    await assert.rejects(readFile(file, 'utf8'), /ENOENT/u);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('写失败被吞掉，不影响通知流程', async () => {
  const history = createHistory({ file: '/proc/definitely-not-writable/history.jsonl', size: 2 });
  await assert.doesNotReject(history.record({ title: 'x' }));
});
