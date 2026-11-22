import React, { useEffect, useMemo, useState } from 'react';
import { reviewWindows } from './reviewWindows';

export default function ReviewCoverage({ sessionId, media, sport='football', onSelect }) {
  const [mediaId, setMediaId] = useState('');
  const [page, setPage] = useState(0);
  const [checked, setChecked] = useState({});
  const ready = media.filter(item => item.status === 'succeeded');
  const current = ready.find(item => item.id === mediaId) || ready[0];
  const windows = useMemo(() => reviewWindows(current?.duration), [current?.duration]);
  const key = current ? `${sport}-review:${sessionId}:${current.id}` : '';
  useEffect(() => { setMediaId(''); setPage(0); }, [sessionId]);
  useEffect(() => {
    if (!key) return;
    try { setChecked(JSON.parse(localStorage.getItem(key) || '{}')); }
    catch { setChecked({}); }
  }, [key]);
  if (!current) return null;
  const pages = Math.max(1, Math.ceil(windows.length / 12));
  const shown = windows.slice(page * 12, (page + 1) * 12);
  function mark(start, value) {
    const next = { ...checked, [start]: value };
    setChecked(next);
    try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* browser storage may be unavailable */ }
  }
  return <details className="review-coverage"><summary>全片兜底复核 · {windows.length} 个时间窗</summary>
    <p className="review-help">每 8 秒开始一个候选窗，前后窗重叠 2 秒。这里覆盖完整原片，方便找回漏掉的动作或回合；缩略图和人物身份仍需人工确认。已看标记仅保存在当前浏览器。</p>
    <label>原素材 <select value={current.id} onChange={event => { setMediaId(event.target.value); setPage(0); }}>
      {ready.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <div className="review-coverage-nav"><button disabled={page === 0} onClick={() => setPage(page - 1)}>上一页</button><span>{page + 1} / {pages}</span><button disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>下一页</button></div>
    <div className="review-coverage-grid">{shown.map(window => <article key={window.start}>
      <img loading="lazy" alt={`${window.start} 秒画面`} src={`/api/media/${current.id}/frame?time_s=${Math.min(current.duration - 0.01, (window.start + window.end) / 2)}`} />
      <strong>{window.start.toFixed(0)}–{window.end.toFixed(1)} 秒</strong>
      <div><button onClick={() => { onSelect(current, window); document.querySelector('.review-editor')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>打开并复核</button><label><input type="checkbox" checked={!!checked[window.start]} onChange={event => mark(window.start, event.target.checked)} />已看</label></div>
    </article>)}</div>
  </details>;
}
