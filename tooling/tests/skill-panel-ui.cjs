/* 用真实 Chromium 把「需人工」那一档的界面走一遍。
 *
 * 只断言「页面上真发生过的事」和「页面真发出去的请求」；磁盘终态由外层 shell 核对 ——
 * 两边各管一段，免得同一个结论在页面和文件系统上各判一次、却互相遮盖。
 */
const {chromium} = require('playwright');
const os = require('os');
const path = require('path');

const SHOT = process.env.SHOT_DIR || os.tmpdir();
const shot = (name) => path.join(SHOT, name + '.png');

const ok = [], bad = [];
const chk = (cond, msg) => { (cond ? ok : bad).push(msg); };

(async () => {
  const url = process.argv[2];
  if (!url) { console.error('用法：node skill-panel-ui.cjs "<带 token 的地址>"'); process.exit(2); }
  const browser = await chromium.launch();
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));

  // 记下页面发出去的写请求，核对参数到点带上了什么
  const sent = [];
  page.on('request', r => {
    if (r.method() === 'POST' && r.url().includes('/api/action')) {
      try { sent.push(JSON.parse(r.postData() || '{}')); } catch (e) { /* ignore */ }
    }
  });

  await page.goto(url, {waitUntil: 'load'});
  await page.waitForSelector('#confList .conf', {timeout: 15000});

  // 按卡片名精确定位再点 —— document.querySelector 会抓到列表里第一个同类按钮，
  // 上一版就是这么把 beta-report 的「都先留着」当成 link-farm 点了。
  const clickIn = async (name, sel) => page.evaluate(([n, s]) => {
    const el = [...document.querySelectorAll('#confList .conf')]
      .find(c => (c.querySelector('.conf-h b') || {}).textContent === n);
    if (!el) throw new Error('找不到卡片：' + n);
    el.classList.add('open');
    const t = el.querySelector(s);
    if (!t) throw new Error('卡片 ' + n + ' 里找不到 ' + s);
    t.click();
    return true;
  }, [name, sel]);
  const cardOf = async (name) => {
    await page.evaluate((n) => {
      const el = [...document.querySelectorAll('#confList .conf')]
        .find(c => c.querySelector('.conf-h b') && c.querySelector('.conf-h b').textContent === n);
      if (el) el.classList.add('open');
    }, name);
  };

  // ---------- 1. 决策卡片：正文分叉那一组 ----------
  await cardOf('beta-report');
  const beta = page.locator('#confList .conf', {hasText: 'beta-report'}).first();
  const txt = await beta.innerText();
  chk(/需人工/.test(txt), '分叉组的卡片仍标着「需人工」');
  chk(/建议留这一份/.test(txt), '卡片给出了建议留哪一份');
  chk(/理由：/.test(txt), '建议带了人话理由');
  chk(/最近被动过/.test(txt), '候选里给出了「最近被动过」');
  chk(/在用/.test(txt), '候选里给出了「谁在用」');
  chk(/未标注版本|v\d/.test(txt), '候选里给出了版本号（没有就写未标注）');
  chk(/都先留着，别再提醒/.test(txt), '卡片有「都先留着」出口');
  chk(!/diff |差异对比|相似度|综合评分/.test(txt), '卡片没有 diff / 评分这类词');

  const radios = beta.locator('input[data-manual]');
  const nRadio = await radios.count();
  chk(nRadio >= 2, `分叉组给出了 ${nRadio} 个可选副本`);
  // 默认选中推荐那份
  const defaultChecked = await beta.locator('input[data-manual]:checked').inputValue();
  const recommended = await page.evaluate((n) => {
    const c = DOC.conflicts.find(x => x.name === n);
    return c.prescription.canonical;
  }, 'beta-report');
  chk(defaultChecked === recommended, '默认选中推荐的那一份');

  // 改选「另一份」，按钮文案要跟着变
  const values = await radios.evaluateAll(els => els.map(e => e.value));
  const other = values.find(v => v !== recommended);
  await page.evaluate((v) => {
    const el = [...document.querySelectorAll('#confList input[data-manual]')].find(e => e.value === v);
    el.click();
  }, other);
  await page.waitForTimeout(120);
  const label = await page.evaluate(() => {
    const el = [...document.querySelectorAll('#confList .conf')]
      .find(c => (c.querySelector('.conf-h b') || {}).textContent === 'beta-report');
    const b = el && el.querySelector('button[data-manual-go]');
    return b ? b.textContent.trim() : '';
  });
  chk(label === '按我选的这份为准', `改选之后按钮文案变成「按我选的这份为准」（实际：${label}）`);
  await cardOf('beta-report');
  await beta.scrollIntoViewIfNeeded();
  await beta.screenshot({path: shot('card-manual')});
  // 点单选框不该把卡片折回去（上一版整表重渲染就会）
  const stillOpen = await page.evaluate((n) => {
    const el = [...document.querySelectorAll('#confList .conf')]
      .find(c => (c.querySelector('.conf-h b') || {}).textContent === n);
    return !!el && el.classList.contains('open');
  }, 'beta-report');
  chk(stillOpen, '选正本之后卡片没有被折回去');

  // 点「按这份为准」→ 干跑面板 → 确认执行
  await clickIn('beta-report', 'button[data-manual-go]');
  await page.waitForSelector('#act.open', {timeout: 8000});
  await page.waitForFunction(() => /干跑预览|已拒绝/.test(document.querySelector('#aBody').innerText), {timeout: 8000});
  const dry = await page.locator('#aBody').innerText();
  chk(/干跑预览/.test(dry), '点下去先给干跑预览');
  chk(dry.includes(other.replace('/Users/', '~/')) || dry.includes(other), '干跑预览里点名了要换掉的那份');
  await page.locator('#act').screenshot({path: shot('card-manual-dry')});
  await page.click('#aGo');
  await page.waitForFunction(() => /已执行/.test(document.querySelector('#aMsg').innerText), {timeout: 8000});
  chk(sent.some(p => p.action === 'resolve-conflict' && p.apply === true
        && p.canonical_map && p.canonical_map['beta-report'] === other),
      '执行时带上了 canonical_map（选的是哪一份）');
  const afterApply = await page.locator('#aBody').innerText();
  chk(!/还没改动任何文件/.test(afterApply), '执行完不再写「还没改动任何文件」');
  chk(/撤销上次去重|搬走/.test(afterApply), '执行完指向了撤销入口');
  await page.click('#aClose');
  await page.waitForTimeout(1600);   // 等自动重扫

  // ---------- 2. 撤销 ----------
  await page.waitForSelector('#btnUndo', {timeout: 8000});
  const undoTitle = await page.getAttribute('#btnUndo', 'title');
  chk(/撤销/.test(undoTitle || ''), `撤销按钮的说明跟着状态走（${undoTitle}）`);
  await page.click('#btnUndo');
  await page.waitForSelector('#act.open', {timeout: 8000});
  await page.waitForFunction(() => /干跑预览|撤不了|没有可撤销/.test(document.querySelector('#aBody').innerText), {timeout: 8000});
  const undoDry = await page.locator('#aBody').innerText();
  chk(/干跑预览/.test(undoDry), '撤销也先给干跑预览');
  chk(/beta-report/.test(undoDry), '撤销预览点名了要还原的组');
  await page.locator('#act').screenshot({path: shot('card-undo-dry')});
  await page.click('#aGo');
  await page.waitForFunction(() => /已执行/.test(document.querySelector('#aMsg').innerText), {timeout: 8000});
  chk(sent.some(p => p.action === 'undo-resolve' && p.apply === true), '撤销请求真的发出去了');
  await page.click('#aClose');
  await page.waitForTimeout(1600);

  // ---------- 3. 断链那一组：只给一个按钮 ----------
  await cardOf('link-broken');
  const lb = page.locator('#confList .conf', {hasText: 'link-broken'}).first();
  const lbTxt = await lb.innerText();
  chk(/有一份坏了/.test(lbTxt), '断链组标出了「有一份坏了」');
  chk(/修好这条断链/.test(lbTxt), '断链组给的是单一动作');
  chk(!/radio|按我选/.test(lbTxt), '断链组没有让人做选择题');
  await clickIn('link-broken', 'button[data-repair]');
  await page.waitForSelector('#act.open', {timeout: 8000});
  await page.waitForFunction(() => /干跑预览|已拒绝/.test(document.querySelector('#aBody').innerText), {timeout: 8000});
  await page.click('#aGo');
  await page.waitForFunction(() => /已执行/.test(document.querySelector('#aMsg').innerText), {timeout: 8000});
  chk(sent.some(p => p.action === 'resolve-conflict' && p.apply === true
        && (!p.canonical_map || !Object.keys(p.canonical_map).length)),
      '断链修复没有传 canonical_map（人不用选）');
  await page.click('#aClose');
  await page.waitForTimeout(1600);

  // ---------- 4. 都先留着 ----------
  await clickIn('link-farm', 'button[data-manual-dismiss]');
  await page.waitForSelector('#act.open', {timeout: 8000});
  const dmTxt = await page.locator('#aBody').innerText();
  chk(/待处理/.test(dmTxt) && /恢复提醒/.test(dmTxt), '「都先留着」说明了它会怎么影响待处理');
  await page.click('#aGo');
  await page.waitForFunction(() => /已执行/.test(document.querySelector('#aMsg').innerText), {timeout: 8000});
  chk(sent.some(p => p.action === 'dismiss-conflict' && p.apply === true && p.ignore === true),
      '「都先留着」写的是 dismiss-conflict');
  await page.click('#aClose');
  await page.waitForTimeout(1800);

  // 重扫之后：待处理里不该再有它，「已确认先留着」里要有
  const stats = await page.evaluate(() => DOC.stats);
  chk(stats.ignored_conflicts >= 1, `重扫后统计里有「已确认」：${stats.ignored_conflicts}`);
  await page.click('#cfIgnored');
  await page.waitForTimeout(200);
  const ignoredNames = await page.evaluate(() =>
    [...document.querySelectorAll('#confList .conf')]
      .map(c => (c.querySelector('.conf-h b') || {}).textContent));
  chk(ignoredNames.length === 1 && ignoredNames[0] === 'link-farm',
      `「已确认先留着」里恰好只剩 link-farm（实际：${JSON.stringify(ignoredNames)}）`);
  // 卡片默认是折起来的，按钮文字不在 innerText 里 —— 直接查元素
  const nUndismiss = await page.locator('#confList button[data-undismiss]').count();
  chk(nUndismiss === 1, `已确认的组上给了「恢复提醒」（找到 ${nUndismiss} 个）`);
  await page.evaluate(() => {
    const el = [...document.querySelectorAll('#confList .conf')]
      .find(c => c.querySelector('.conf-h b') && c.querySelector('.conf-h b').textContent === 'link-farm');
    if (el) el.classList.add('open');
  });
  const ignoredNote = await page.evaluate(() => {
    const all = [...document.querySelectorAll('#confList .conf')];
    const dump = all.map(c => ({
      name: (c.querySelector('.conf-h b') || {}).textContent,
      hasBtn: !!c.querySelector('button[data-undismiss]'),
      hasNote: [...c.querySelectorAll('.note')].some(n => n.textContent.includes('已确认')),
      ignored: (DOC.conflicts.find(x => x.name === ((c.querySelector('.conf-h b') || {}).textContent)) || {}).ignored,
    }));
    const el = all.find(c => c.querySelector('.conf-h b') && c.querySelector('.conf-h b').textContent === 'link-farm');
    if (el) el.classList.add('open');
    const note = el ? [...el.querySelectorAll('.note')].find(n => n.textContent.includes('已确认「都先留着」')) : null;
    return {found: !!note, open: !!(el && el.classList.contains('open')), dump};
  });
  chk(ignoredNote.found && ignoredNote.open,
      `展开后说明了它为什么不再提醒 —— ${JSON.stringify(ignoredNote)}`);
  await page.locator('#confList .conf').first().screenshot({path: shot('card-ignored')});

  // 恢复提醒
  await clickIn('link-farm', 'button[data-undismiss]');
  await page.waitForSelector('#act.open', {timeout: 8000});
  await page.click('#aGo');
  await page.waitForFunction(() => /已执行/.test(document.querySelector('#aMsg').innerText), {timeout: 8000});
  chk(sent.some(p => p.action === 'dismiss-conflict' && p.ignore === false),
      '恢复提醒写的是 ignore=false');
  await page.click('#aClose');
  await page.waitForTimeout(1800);
  const after = await page.evaluate(() => DOC.stats.ignored_conflicts);
  chk(after === 0, `恢复之后不再有「已确认」（实际 ${after}）`);

  chk(errs.length === 0, `页面上没有 JS 报错${errs.length ? '：' + errs.join(' | ') : ''}`);

  console.log('\n通过：');
  ok.forEach(m => console.log('  ✅ ' + m));
  if (bad.length) {
    console.log('\n失败：');
    bad.forEach(m => console.log('  ❌ ' + m));
  }
  console.log(`\n${ok.length} 条通过，${bad.length} 条失败；截图在 ${SHOT}`);
  await browser.close();
  process.exit(bad.length ? 1 : 0);
})().catch(async (e) => {
  console.error('脚本异常：', e);
  process.exit(2);
});
