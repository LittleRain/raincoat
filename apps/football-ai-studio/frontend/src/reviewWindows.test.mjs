import assert from 'node:assert/strict';
import test from 'node:test';
import { reviewWindows } from './reviewWindows.js';

test('overlapping windows cover the full source and the known dribble interval', () => {
  const windows = reviewWindows(22.146667);
  assert.deepEqual(windows, [
    { start: 0, end: 10 },
    { start: 8, end: 18 },
    { start: 16, end: 22.146667 },
  ]);
  assert.ok(windows.some(window => window.start <= 15 && window.end >= 17));
  const long = reviewWindows(600);
  assert.equal(long.at(-1).end, 600);
  assert.ok(long.every((window, index) => index === 0 || window.start <= long[index - 1].end));
});
