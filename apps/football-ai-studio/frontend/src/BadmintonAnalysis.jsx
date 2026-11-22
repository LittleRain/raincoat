import React, { useEffect, useRef, useState } from 'react';

export default function BadmintonAnalysis({ media, onCandidates }) {
  const ready = media.filter(item => item.status === 'succeeded');
  const [mediaId, setMediaId] = useState('');
  const [ignoreBefore, setIgnoreBefore] = useState(0);
  const [roi, setRoi] = useState('');
  const [runs, setRuns] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const requestKey = useRef(null);
  const seenSuccess = useRef(new Set());
  const current = ready.find(item => item.id === mediaId) || ready[0];
  useEffect(() => {
    if (!current) return;
    let active = true;
    const load = async () => {
      const response = await fetch(`/api/media/${current.id}/badminton-analyses`);
      if (!response.ok) throw new Error('候选任务读取失败');
      const rows = await response.json();
      if (active) {
        setRuns(rows);
        const fresh = rows.filter(row => row.status === 'succeeded' && !seenSuccess.current.has(row.id));
        fresh.forEach(row => seenSuccess.current.add(row.id));
        if (fresh.length) onCandidates();
      }
    };
    load().catch(err => active && setError(err.message));
    const timer = setInterval(() => load().catch(err => active && setError(err.message)), 3000);
    return () => { active = false; clearInterval(timer); };
  }, [current?.id]);
  async function scan() {
    setBusy(true); setError('');
    try {
      const court = roi.trim() ? roi.trim().split(/[\s,]+/).map(Number) : null;
      if (court && (court.length !== 4 || court.some(value => !Number.isFinite(value)))) throw new Error('球场范围请填 4 个 0–1 数值');
      requestKey.current ||= crypto.randomUUID();
      const response = await fetch(`/api/media/${current.id}/badminton-analyses`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_key: requestKey.current, ignore_before: Number(ignoreBefore), court_roi: court }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '分析失败');
      setRuns(rows => [{ id: data.id, status: 'queued', stage: '等待本地分析', progress: 0 }, ...rows]);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  async function changeJob(jobId, action) {
    setError('');
    try {
      const response = await fetch(`/api/jobs/${jobId}/${action}`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '任务操作失败');
      setRuns(rows => rows.map(row => row.job_id === jobId ? { ...row, status: data.status, stage: data.stage } : row));
    } catch (err) { setError(err.message); }
  }
  return <div className="review-analysis">
    <p className="review-help">本机分析固定球场画面运动量，自动提出待审活动片段；不会自动确认完整回合或认出指定球员。</p>
    <label>要分析的视频 <select value={current?.id || ''} onChange={event => { setMediaId(event.target.value); requestKey.current = null; }}>
      {ready.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <details className="analysis-advanced"><summary>高级设置 · 跳过开头与球场范围</summary><label>跳过开头（秒）<input type="number" min="0" step="1" value={ignoreBefore} onChange={event => { setIgnoreBefore(event.target.value); requestKey.current = null; }} /></label>
    <label>球场范围（可留空）<input value={roi} onChange={event => { setRoi(event.target.value); requestKey.current = null; }} placeholder="左 上 宽 高，例如 0.1 0.22 0.85 0.72" /></label><p className="review-help">留空时分析整个画面。四个数字表示画面宽高的比例。</p></details>
    <div className="review-controls"><button disabled={!current || busy || !Number.isFinite(Number(ignoreBefore)) || Number(ignoreBefore) < 0} onClick={scan}>{busy ? '提交中…' : '生成候选片段'}</button></div>
    {error && <p role="alert" className="message error">{error}</p>}
    {runs[0]&&<p className="review-help">最近一次分析：{runs[0].status} · {runs[0].stage} · {Math.round(runs[0].progress || 0)}% {runs[0].error || ''}
      {['queued','running'].includes(runs[0].status) && runs[0].job_id && <button onClick={() => changeJob(runs[0].job_id,'cancel')}>取消</button>}
      {['failed','cancelled'].includes(runs[0].status) && runs[0].job_id && <button onClick={() => changeJob(runs[0].job_id,'retry')}>重试</button>}
    </p>}
    {runs.length>1&&<details className="analysis-history"><summary>历史分析记录 · {runs.length-1} 次</summary>{runs.slice(1).map(run => <p key={run.id} className="review-help">{run.status} · {run.stage} · {Math.round(run.progress || 0)}% {run.error || ''}
      {['queued','running'].includes(run.status) && run.job_id && <button onClick={() => changeJob(run.job_id,'cancel')}>取消</button>}
      {['failed','cancelled'].includes(run.status) && run.job_id && <button onClick={() => changeJob(run.job_id,'retry')}>重试</button>}
    </p>)}</details>}
  </div>;
}
