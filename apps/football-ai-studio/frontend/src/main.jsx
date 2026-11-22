import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import ReviewStudio from './ReviewStudio';
import StoragePanel from './StoragePanel';
const statusLabels = {queued:'等待处理',running:'处理中',succeeded:'就绪',failed:'失败',cancelled:'已取消'};
const camera = {gopro:'GoPro', iphone:'iPhone', other:'其他相机'};
const today = () => new Date().toLocaleDateString('sv-SE');
async function api(path, options={}) {
  const response = await fetch('/api'+path, { ...options, headers: {'Content-Type':'application/json', ...options.headers} });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
  return body;
}
function App() {
  const [reviewDirty,setReviewDirty]=useState(false);
  const [sessions,setSessions]=useState([]), [selected,setSelected]=useState(null), [detail,setDetail]=useState(null);
  const [health,setHealth]=useState(null), [error,setError]=useState(''), [notice,setNotice]=useState('');
  const [name,setName]=useState(''), [date,setDate]=useState(today()), [sport,setSport]=useState('football'), [editing,setEditing]=useState(false);
  const [source,setSource]=useState('gopro'), [path,setPath]=useState(''), [busy,setBusy]=useState(false);
  const [upload,setUpload]=useState(null), [playing,setPlaying]=useState(null), [deleteOpen,setDeleteOpen]=useState(false);
  const input=useRef(), xhrRef=useRef(), selectionRef=useRef(null);
  selectionRef.current=selected;
  async function refresh() {
    const list=await api('/sessions'); setSessions(list);
    const id=selectionRef.current;
    if(id) { const d=await api('/sessions/'+id); if(selectionRef.current===id) setDetail(d); }
  }
  useEffect(()=>{api('/health').then(setHealth).catch(e=>setError(e.message));},[]);
  useEffect(()=>{setDetail(null); setPlaying(null); setEditing(false); setDeleteOpen(false);
    let live=true; const run=()=>refresh().catch(e=>{if(live)setError(e.message)});
    run(); const timer=setInterval(run,1500); return()=>{live=false;clearInterval(timer)};
  },[selected]);
  async function action(fn) { setBusy(true);setError('');setNotice('');try {await fn();await refresh();} catch(e){setError(e.message)} finally{setBusy(false)} }
  function choose(id) { if(upload||reviewDirty)return;setSelected(id); }
  async function save(e) { e.preventDefault(); await action(async()=>{
    const d=await api(editing?'/sessions/'+selected:'/sessions',{method:editing?'PATCH':'POST',body:JSON.stringify({name,date,sport})});
    setSelected(d.id);setEditing(false);setName('');setDate(today());setNotice('场次已保存');
  }); }
  async function uploadFiles(files) {
    if(!selected||!files.length)return;
    setBusy(true);setError('');let completed=0; const sid=selected;
    try { for(const file of files) {
      await new Promise((resolve,reject)=>{
        const xhr=new XMLHttpRequest();xhrRef.current=xhr;
        xhr.open('POST',`/api/sessions/${sid}/upload?filename=${encodeURIComponent(file.name)}&source=${source}`);
        xhr.setRequestHeader('Content-Type','application/octet-stream');
        xhr.upload.onprogress=e=>setUpload({name:file.name,percent:e.lengthComputable?Math.round(e.loaded/e.total*100):0});
        xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300){completed++;resolve()}else{try{reject(new Error(JSON.parse(xhr.responseText).detail))}catch{reject(new Error('上传失败'))}}};
        xhr.onerror=()=>reject(new Error('上传连接中断'));xhr.onabort=()=>reject(new Error('上传已取消'));
        setUpload({name:file.name,percent:0});xhr.send(file);
      });
    } setNotice(`已导入 ${completed} 个文件，正在后台预处理`); }
    catch(e){setError(`${e.message}（已导入 ${completed} 个文件）`)}
    finally{setUpload(null);xhrRef.current=null;setBusy(false);if(input.current)input.current.value='';await refresh();}
  }
  const media=detail?.media||[], ready=media.filter(m=>m.status==='succeeded').length;
  return <div className="app-shell">
    <aside><div className="brand"><span className="brand-icon">◈</span><div>SPORT<span>CUT STUDIO</span></div></div>
      <div className="phase-tag">本地运动剪辑工作台</div>
      <div className="nav-title">运动场次 <span>{sessions.length}</span></div>
      <button className="new-session" disabled={busy||reviewDirty} onClick={()=>{setSelected(null);setName('');setDate(today());setSport('football');}}>＋ 新建场次</button>
      <nav>{sessions.map(s=><button key={s.id} disabled={busy||reviewDirty} className={'session '+(selected===s.id?'active':'')} onClick={()=>choose(s.id)}><strong>{s.name}</strong><span>{s.sport==='badminton'?'羽毛球':'足球'} · {s.date} · {s.media_count} 个视频</span></button>)}</nav>
      <div className="privacy"><span className="dot"/> 原始视频保留在本机<p>AI 默认关闭 · 无自动发布</p></div>
    </aside>
    <main><header><div className="breadcrumb">工作空间 / {detail?.name||'新建场次'}</div><span className="connection"><span className={'dot '+(health?.status==='ok'?'':'warning')}/>{health?.status==='ok'?'本地服务已连接':'正在检查环境'}</span></header>
      <section className="intro"><div className="eyebrow">YOUR NEXT GREAT PLAY STARTS HERE</div><h1>{detail?.name||'把精彩，留在场上。'}</h1><p>{detail?`${detail.date} · 导入视频，确认连续片段，交给 ChatCut 完成剪辑。`:'先选择运动类型，再导入固定机位视频。'}</p></section>
      {error&&<div role="alert" className="message error">{error}<button onClick={()=>setError('')}>关闭</button></div>}
      {notice&&<div role="status" className="message">{notice}</div>}
      {health&&(!health.ffmpeg||!health.ffprobe)&&<div role="alert" className="message error">缺少 FFmpeg 或 ffprobe，请按 README 安装后重启。</div>}
      {(!selected||editing)&&<form className="panel session-form" onSubmit={save}><h2>{editing?'编辑场次':'新建场次'}</h2><div className="form-row"><label>运动类型<select value={sport} disabled={editing&&!!detail?.media?.length} onChange={e=>setSport(e.target.value)}><option value="football">足球</option><option value="badminton">羽毛球</option></select></label><label>场次名称<input required maxLength={120} value={name} onChange={e=>setName(e.target.value)} placeholder="例如：周六羽毛球或足球训练"/></label><label>活动日期<input required type="date" value={date} onChange={e=>setDate(e.target.value)}/></label></div><button className="primary" disabled={busy}>{editing?'保存修改':'创建场次'}</button>{editing&&<button type="button" onClick={()=>setEditing(false)}>取消</button>}</form>}
      {selected&&detail&&<>
        <div className="stats"><div><span>已导入视频</span><strong>{media.length.toString().padStart(2,'0')}</strong></div><div><span>可播放预览</span><strong>{ready.toString().padStart(2,'0')}</strong></div><div><span>工作流阶段</span><strong className="stat-text">审核与集锦导出</strong></div><div className="session-actions"><button disabled={busy} onClick={()=>{setEditing(true);setName(detail.name);setDate(detail.date);setSport(detail.sport);}}>编辑场次</button><button disabled={busy||reviewDirty} className="danger" onClick={()=>setDeleteOpen(true)}>删除场次</button></div></div>
        {deleteOpen&&<div className="message error">删除场次将隐藏记录并取消任务，保留原始文件。<button disabled={busy} onClick={()=>action(async()=>{await api('/sessions/'+selected,{method:'DELETE'});setSelected(null);setDeleteOpen(false);setNotice('场次已删除，原始文件保留');})}>确认删除</button><button onClick={()=>setDeleteOpen(false)}>返回</button></div>}
        <section className="panel import-panel"><div className="section-head"><h2>01 <span>导入原始视频</span></h2><span className="small-badge">本机处理</span></div><label className="source-label">相机来源<select value={source} disabled={busy} onChange={e=>setSource(e.target.value)}><option value="gopro">Action 6 / GoPro · 固定机位</option><option value="iphone">iPhone</option><option value="other">其他相机</option></select></label>
          <div className="import-grid"><div className="upload-zone" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy)uploadFiles([...e.dataTransfer.files])}}><div className="upload-icon">↥</div><h3>拖入视频，或选择文件</h3><p>MP4 / MOV / MKV / WEBM 等 · 支持多文件</p><input ref={input} aria-label="选择视频文件" type="file" multiple accept=".mp4,.mov,.m4v,.mkv,.avi,.webm" disabled={busy} onChange={e=>uploadFiles([...e.target.files])}/><small>分块上传至本机，不会把原视频加载到播放器</small></div>
          <form className="path-zone" onSubmit={e=>{e.preventDefault();action(async()=>{const r=await api('/sessions/'+selected+'/register',{method:'POST',body:JSON.stringify({path,source})});setNotice(`已注册 ${r.imported.length} 个视频，跳过 ${r.skipped} 个重复文件`);setPath('');})}}><h3>注册现有文件或目录</h3><p>直接引用原文件，无需复制。目录只读取第一层。</p><label>本地绝对路径<input required value={path} onChange={e=>setPath(e.target.value)} placeholder="/…/data/media/训练视频" disabled={busy}/></label><button disabled={busy}>注册视频</button><small>批准的媒体根目录：<code>{health?.media_root}</code></small></form></div>
          {upload&&<div className="upload-progress" role="status"><span>正在上传 {upload.name} · {upload.percent}%</span><progress max="100" value={upload.percent}/><button onClick={()=>xhrRef.current?.abort()}>取消上传</button></div>}
        </section>
        <section className="library"><div className="section-head"><h2>02 <span>视频素材</span></h2><span className="muted">任务状态每 1.5 秒刷新</span></div>
        {!media.length?<div className="empty"><span>▤</span><h3>等待第一段运动视频</h3><p>导入后会自动探测时长、生成代理视频和缩略图。</p></div>:<div className="media-grid">{media.map(m=><article className="media-card" key={m.id}>
          <div className="thumbnail">{m.status==='succeeded'?<><img alt={m.name+' 缩略图'} src={`/api/media/${m.id}/thumbnail`}/><button aria-label={'播放 '+m.name} className="play" onClick={()=>setPlaying(m)}>▶</button></>:<div className="placeholder">{m.status==='failed'?'!':'◈'}</div>}<span className="camera-badge">{camera[m.source]}</span></div>
          <div className="card-body"><h3 title={m.name}>{m.name}</h3><p className="meta">{m.duration?`${Math.floor(m.duration/60)}:${String(Math.round(m.duration%60)).padStart(2,'0')} · ${m.width}×${m.height} · ${m.fps?.toFixed(1)} fps`:'元数据等待探测'} · {m.managed?'上传副本':'本地引用'}</p><div className="job-line"><span className={'status '+m.status}>{statusLabels[m.status]}</span><span>{Math.round(m.progress)}%</span></div><progress value={m.progress} max="100"/><p className="stage">{m.stage} · 已尝试 {m.attempts} 次</p>{m.error&&<details><summary>查看错误</summary><pre>{m.error}</pre></details>}
          {['queued','running'].includes(m.status)&&<button disabled={busy} onClick={()=>action(()=>api('/jobs/'+m.job_id+'/cancel',{method:'POST'}))}>取消任务</button>}{['failed','cancelled'].includes(m.status)&&<button disabled={busy} onClick={()=>action(()=>api('/jobs/'+m.job_id+'/retry',{method:'POST'}))}>重试预处理</button>}</div></article>)}</div>}</section>
        <ReviewStudio key={selected} sessionId={selected} sport={detail.sport} media={media} onDirtyChange={setReviewDirty}/>
      </>}
      <StoragePanel/>
      <footer><span>工作流程：选择运动 → 导入视频 → 指定人物 → 审核连续片段 → 导出 ChatCut 交接清单</span><p>原片保存在本机。AI 分析需单独配置并明确启用；身份、动作和片段边界请人工复核。</p></footer>
    </main>{playing&&<div className="modal" role="dialog" aria-modal="true" aria-label="代理视频预览" onClick={()=>setPlaying(null)}><div onClick={e=>e.stopPropagation()}><div className="section-head"><h2>{playing.name}</h2><button onClick={()=>setPlaying(null)}>关闭预览</button></div><video controls autoPlay playsInline src={`/api/media/${playing.id}/proxy`}/><p>正在播放本地 720p 代理视频 · 原始素材仍保留在本机</p></div></div>}
  </div>
}
createRoot(document.getElementById('root')).render(<App/>);
