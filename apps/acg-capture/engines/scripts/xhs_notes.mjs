// 抓小红书账号主页的作品卡片（标题 + 卡片可见文案），输出 JSON。
// 用法：ego-browser nodejs < 包装脚本（XHS_PROFILE / XHS_SCROLLS / XHS_OUT 由包装脚本注入，
//       ego-browser 不继承父进程 env）。
// 口径：小红书笔记详情页现在要 xsec_token，直开 /explore/<id> 会 404；
//       所以只抓主页卡片，正文长度有限——验收按「卡片文案命中」算，item 里标 evidence=xhs_card。
const fs = await import("node:fs/promises");
const path = await import("node:path");

const PROFILE = process.env.XHS_PROFILE || "";
const SCROLLS = Number(process.env.XHS_SCROLLS || 6);
const OUT = process.env.XHS_OUT || "";

if (!PROFILE || !OUT) {
  console.log(JSON.stringify({ ok: false, error: "missing_channel_config" }));
  process.exit(0);
}

const task = await taskSpace("xhs notes");
const page = task.page("p1");
await page.goto(PROFILE, { timeout: 60000 });
await new Promise((r) => setTimeout(r, 3000));

const seen = new Map();
const grab = async () => {
  let rows = [];
  try {
    rows = await page.evaluate(() => {
      const out = [];
      for (const a of document.querySelectorAll('a[href*="/explore/"]')) {
        const href = a.getAttribute("href") || "";
        const id = (href.match(/\/explore\/([0-9a-f]+)/) || [])[1] || "";
        if (!id) continue;
        // 只取这张卡自己的 section：往上找多级会把相邻卡片一起吞进来
        const card = a.closest("section") || a.parentElement || a;
        const text = (card.innerText || "").trim();
        out.push({ id, href, text: text.slice(0, 600) });
      }
      return out;
    });
  } catch (e) { rows = []; }
  for (const r of rows) if (!seen.has(r.id)) seen.set(r.id, r);
};

await grab();
for (let i = 0; i < SCROLLS; i += 1) {
  try {
    await page.evaluate(() => window.scrollBy(0, Math.round(window.innerHeight * 1.1)));
  } catch (e) { /* 滚动失败就停在当前屏 */ }
  await new Promise((r) => setTimeout(r, 1400));
  await grab();
}

const notes = [...seen.values()].map((n) => ({
  id: n.id,
  url: "https://www.xiaohongshu.com" + n.href.split("?")[0],
  text: n.text,
}));

await fs.mkdir(path.dirname(OUT), { recursive: true });
await fs.writeFile(OUT, JSON.stringify(notes, null, 1));
console.log(JSON.stringify({ url: PROFILE, notes: notes.length, out: OUT }));
