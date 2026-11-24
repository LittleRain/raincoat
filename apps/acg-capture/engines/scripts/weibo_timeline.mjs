// 拉取微博账号时间线，输出 JSON（帖子正文 + 官图 URL）。
// 用法：ego-browser nodejs < scripts/weibo_timeline.mjs
//   注意：ego-browser 不继承父进程 env，指定 uid/页数要在包装脚本里 setenv 再 import 本文件
//   （brand_sweep.py 就是这么做的；手工写法见 README「最短路径」）。
// 结果：<workspace>/runtime/weibo_<uid>.json（可用 WEIBO_OUT 覆盖，目录不存在会自动建）
const fs = await import("node:fs/promises");
const path = await import("node:path");

const UID = process.env.WEIBO_UID || "7324393029"; // 万代南梦宫潮玩
const PAGES = Number(process.env.WEIBO_PAGES || 30);
const OUT = process.env.WEIBO_OUT || `/Users/raincai/Documents/GitHub/workspace/runtime/weibo_${UID}.json`;

const task = await taskSpace("weibo timeline " + UID);
const page = task.page("p1");
await page.goto("https://m.weibo.cn/u/" + UID, { timeout: 60000 });

const all = [];
for (let p = 1; p <= PAGES; p++) {
  const url = `https://m.weibo.cn/api/container/getIndex?type=uid&value=${UID}&containerid=107603${UID}&page=${p}`;
  let cards = [];
  try {
    cards = await page.evaluate(async (u) => {
      const r = await fetch(u, { credentials: "include" });
      const j = await r.json();
      return ((j.data && j.data.cards) || []).map((c) => {
        const mb = c.mblog;
        if (!mb) return null;
        return {
          mid: mb.mid,
          created: mb.created_at || "",
          text: (mb.text || "").replace(/<[^>]+>/g, ""),
          pics: (mb.pics || []).map((x) => (x.large && x.large.url) || "").filter(Boolean),
        };
      }).filter(Boolean);
    }, url);
  } catch (e) { cards = []; }
  if (!cards.length) break;
  all.push(...cards);
  await new Promise((r) => setTimeout(r, 500));
}

await fs.mkdir(path.dirname(OUT), { recursive: true });
await fs.writeFile(OUT, JSON.stringify(all, null, 1));
console.log(JSON.stringify({ uid: UID, posts: all.length, out: OUT }));
