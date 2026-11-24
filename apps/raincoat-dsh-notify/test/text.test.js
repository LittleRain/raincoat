import assert from 'node:assert/strict';
import test from 'node:test';

import {
  collapseWhitespace,
  lastAssistantPreview,
  sessionTitleFromLog,
  stripMarkdown,
  textFromContent,
  truncate,
} from '../lib/text.js';

test('stripMarkdown 去掉代码块、链接、标题和强调符号', () => {
  const source = [
    '## 已完成',
    '',
    '改好了 [`index.js`](https://example.com) 和 **通知逻辑**。',
    '',
    '```js',
    'const secret = 1;',
    '```',
    '',
    '- 第一条',
    '- 第二条',
  ].join('\n');
  assert.equal(stripMarkdown(source), '已完成 改好了 index.js 和 通知逻辑。 第一条 第二条');
});

test('truncate 按码点截断，不会切坏 emoji', () => {
  assert.equal(truncate('abcdef', 10), 'abcdef');
  assert.equal(truncate('abcdef', 4), 'abc…');
  assert.equal(Array.from(truncate('✅✅✅✅✅', 3)).length, 3);
  assert.equal(truncate('abc', 0), '');
});

test('textFromContent 只取 text 块', () => {
  assert.equal(
    textFromContent([
      { type: 'reasoning', text: '内部推理' },
      { type: 'text', text: '第一段' },
      { type: 'tool-call', name: 'bash' },
      { type: 'text', text: '第二段' },
    ]),
    '第一段\n第二段',
  );
  assert.equal(textFromContent(undefined), '');
  assert.equal(collapseWhitespace('  a\n\n b  '), 'a b');
});

test('lastAssistantPreview 只取指定轮次，跳过纯代码回复', () => {
  const log = [
    { type: 'assistant/message', data: { turn: 1, message: { content: [{ type: 'text', text: '上一轮的结论' }] } } },
    { type: 'assistant/message', data: { turn: 2, message: { content: [{ type: 'text', text: '```bash\nls\n```' }] } } },
    { type: 'assistant/message', data: { turn: 2, message: { content: [{ type: 'text', text: '**最终**结果在这里' }] } } },
  ];
  assert.equal(lastAssistantPreview(log, 2, { max: 60 }), '最终结果在这里');
  assert.equal(lastAssistantPreview(log, 3, { max: 60 }), '');
});

test('sessionTitleFromLog 优先标题事件，其次目录名', () => {
  assert.equal(sessionTitleFromLog([{ type: 'session/title', data: { title: '修复通知' } }], '/a/b', 'DSH'), '修复通知');
  assert.equal(sessionTitleFromLog([], '/Users/me/work/my-app/', 'DSH'), 'my-app');
  assert.equal(sessionTitleFromLog([], '', 'DSH'), 'DSH');
});
