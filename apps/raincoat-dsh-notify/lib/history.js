/**
 * 通知历史：把最近若干条"发了什么 / 为什么没发"落到本地，
 * 用来排查"我明明没看到通知"到底是没触发、被前台过滤，还是发送失败。
 *
 * 默认文件是 `$DSH_HOME/notify/history.jsonl`，只保留最近 N 条。
 *
 * @module dsh-notify/history
 */

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';

/**
 * 创建历史记录器。写入串行化，避免并发通知互相覆盖。
 *
 * @param options - `file`（空串表示关闭）、`size`（保留条数）、`now`。
 * @returns `record(entry)`：永不抛出。
 */
export function createHistory({ file = '', size = 20, now = () => Date.now() } = {}) {
  let queue = Promise.resolve();

  return {
    /**
     * 追加一条记录。
     *
     * @param entry - 通知结果摘要。
     * @returns 写完后 resolve；任何失败都被吞掉。
     */
    record(entry) {
      if (typeof file !== 'string' || file.length === 0 || size <= 0) return Promise.resolve();
      queue = queue
        .then(async () => {
          const line = JSON.stringify({ at: new Date(now()).toISOString(), ...entry });
          await mkdir(dirname(file), { recursive: true, mode: 0o700 });
          let lines = [];
          try {
            lines = (await readFile(file, 'utf8')).split('\n').filter((item) => item.trim().length > 0);
          } catch {
            lines = [];
          }
          lines.push(line);
          await writeFile(file, `${lines.slice(-size).join('\n')}\n`, { mode: 0o600 });
        })
        .catch(() => {});
      return queue;
    },
  };
}
