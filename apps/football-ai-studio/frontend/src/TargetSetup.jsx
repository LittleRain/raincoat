import React, { useEffect, useRef, useState } from 'react';

export default function TargetSetup({ sessionId, media, sport, onReady }) {
  const ready = media.filter(item => item.status === 'succeeded');
  const [mediaId, setMediaId] = useState('');
  const [time, setTime] = useState(0);
  const [frameTime, setFrameTime] = useState(0);
  const [shown, setShown] = useState(false);
  const [box, setBox] = useState(null);
  const origin = useRef(null);
  const [notes, setNotes] = useState('');
  const [references, setReferences] = useState([]);
  const [editing, setEditing] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState('');
  const current = ready.find(item => item.id === mediaId) || ready[0];
  useEffect(() => {
    let active = true;
    setReferences([]);
    fetch(`/api/sessions/${sessionId}/target-references`).then(response => response.json()).then(rows => {
      if (active) { setReferences(rows); setEditing(rows.length === 0); onReady(rows.length > 0); }
    }).catch(() => { if (active) setMessage('目标参考读取失败'); });
    return () => { active = false; };
  }, [sessionId, onReady]);
  function point(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    return [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))];
  }
  function move(event) {
    if (!origin.current) return;
    const end = point(event);
    setBox([Math.min(origin.current[0], end[0]), Math.min(origin.current[1], end[1]),
      Math.abs(origin.current[0] - end[0]), Math.abs(origin.current[1] - end[1])]);
  }
  async function save() {
    setMessage('');
    try {
      const response = await fetch(`/api/sessions/${sessionId}/target-references`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ media_id: current.id, source_time: frameTime, box_normalized: box, clothing_notes: notes.trim() }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || '保存失败');
      setReferences(rows => [...rows, result]);
      setBox(null); setShown(false); setEditing(false); setMessage('目标人物参考已保存，可以开始分析。'); onReady(true);
    } catch (error) { setMessage(error.message); }
  }
  async function remove(id) {
    setDeleting(true); setMessage('');
    try {
      const response = await fetch(`/api/sessions/${sessionId}/target-references/${id}`, { method: 'DELETE' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || '删除失败');
      setReferences(result.remaining);
      onReady(result.remaining.length > 0);
      if (!result.remaining.length) setEditing(true);
      setConfirmDelete(null);
      setMessage(result.remaining.length ? '目标参考已删除。' : '最后一张目标参考已删除，请重新指定人物后再生成候选。');
    } catch (error) { setMessage('删除目标参考失败：' + error.message); }
    finally { setDeleting(false); }
  }
  return <section className="review-target panel"><h3>03 指定目标人物</h3>
    <p className="review-help">先从清晰画面中框选{sport === 'badminton' ? '球员' : '孩子'}，填写本场衣着。可保存多张不同位置的参考图；远景、遮挡和同款衣着仍需要你逐段确认。</p>
    {references.length > 0 && <><p className="review-help">本场目标已保存 {references.length} 张参考图，进入页面无需重新圈选。</p><div className="target-reference-list">{references.map(row => <div key={row.id}><div className="target-reference-image"><img src={`/api/media/${row.media_id}/frame?time_s=${row.source_time}`} alt={row.clothing_notes || '已保存的目标参考'} />{row.box_normalized&&<i style={{left:`${row.box_normalized[0]*100}%`,top:`${row.box_normalized[1]*100}%`,width:`${row.box_normalized[2]*100}%`,height:`${row.box_normalized[3]*100}%`}} />}</div><span>{row.clothing_notes || '未填写衣着备注'} · {Number(row.source_time).toFixed(1)} 秒</span><div className="target-reference-actions">{confirmDelete === row.id ? <><button disabled={deleting} onClick={() => remove(row.id)}>确认删除</button><button disabled={deleting} onClick={() => setConfirmDelete(null)}>取消</button></> : <button disabled={deleting} onClick={() => setConfirmDelete(row.id)}>删除这张标记</button>}</div></div>)}</div><button onClick={() => setEditing(value => !value)}>{editing ? '收起圈选工具' : '补充目标参考'}</button></>}
    {editing && current && <><label>原素材 <select value={current.id} onChange={event => { setMediaId(event.target.value); setShown(false); setBox(null); }}>
      {ready.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <video controls preload="metadata" style={{ display: 'block', width: '100%', maxHeight: 380, margin: '12px 0' }} src={`/api/media/${current.id}/proxy`} onTimeUpdate={event => setTime(event.currentTarget.currentTime)} />
      <button onClick={() => { setFrameTime(time); setShown(true); setBox(null); }}>从当前画面取参考帧 · {time.toFixed(2)} 秒</button>
      {shown && <><div className="review-frame" onPointerDown={event => { event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); origin.current = point(event); setBox(null); }} onPointerMove={move} onPointerUp={event => { move(event); origin.current = null; }} onPointerCancel={() => { origin.current = null; }}>
        <img draggable="false" src={`/api/media/${current.id}/frame?time_s=${frameTime}`} alt="框选目标人物" />
        {box && <span style={{ left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${box[2] * 100}%`, height: `${box[3] * 100}%` }} />}
      </div><label>衣着与辨认备注 <input value={notes} maxLength={500} onChange={event => setNotes(event.target.value)} placeholder="例如红衣绿裤、球衣号码" /></label>
        <button disabled={!box || box[2] <= .005 || box[3] <= .005 || references.length >= 8} onClick={save}>保存目标人物</button></>}
    </>}
    {message && <p role="status" className="review-help">{message}</p>}
  </section>;
}
