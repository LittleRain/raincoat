import React,{useEffect,useRef,useState} from 'react';
export default function AnalysisTools({media,config,onCandidates,targetReady}){
 const [selected,setSelected]=useState(''),[providerChoice,setProviderChoice]=useState('minimax'),[calls,setCalls]=useState(6),[consent,setConsent]=useState(false),[runs,setRuns]=useState([]),[error,setError]=useState(''),[notice,setNotice]=useState(''),[confirmRepeat,setConfirmRepeat]=useState(false),[busy,setBusy]=useState(false);
 const key=useRef(null),active=useRef(selected);active.current=selected;
 const profiles=config?.profiles,profile=profiles?.[providerChoice]||config;
 const mini=profile?.provider==='MiniMax',maxCalls=profile?.trial_max_calls||500;
 const ready=media.filter(m=>m.status==='succeeded');
 const current=ready.find(m=>m.id===selected),windows=current?Math.max(1,Math.ceil((current.duration-12)/10)+1):0,supported=Boolean(current&&windows*2<=maxCalls);
 const lastSuccessIndex=runs.findIndex(run=>run.status==='succeeded');
 const currentRuns=lastSuccessIndex<0?runs:runs.slice(0,lastSuccessIndex+1);
 const sameProvider=run=>run.status==='failed'&&run.unknown_count>0&&run.config?.model===profile?.model&&run.config?.base_url===profile?.base_url&&run.config?.input_mode===profile?.input_mode;
 const recoverable=currentRuns.find(run=>sameProvider(run)&&run.config?.prompt_version===profile?.prompt_version);
 const previousVersionUnknown=currentRuns.some(run=>sameProvider(run)&&run.config?.prompt_version!==profile?.prompt_version);
 const otherProviderUnknown=currentRuns.some(run=>run.status==='failed'&&run.unknown_count>0&&!sameProvider(run));
 useEffect(()=>{if(profiles&&!profiles[providerChoice]?.available&&profiles['openai-compatible']?.available)setProviderChoice('openai-compatible');},[profiles,providerChoice]);
 useEffect(()=>{if(!selected&&ready.length)setSelected(ready[0].id);},[media,selected]);
 useEffect(()=>{setCalls(Math.min(maxCalls,Math.max(6,windows*2)));key.current=null;setConsent(false);},[providerChoice,selected,windows,maxCalls]);
 async function load(mid){const r=await fetch(`/api/media/${mid}/analyses`);if(!r.ok)throw new Error('分析任务读取失败');const b=await r.json();if(active.current===mid)setRuns(Array.isArray(b)?b:[]);}
 useEffect(()=>{setRuns([]);setConsent(false);setConfirmRepeat(false);setNotice('');key.current=null;if(!selected)return;load(selected).catch(e=>setError(e.message));const t=setInterval(()=>load(selected).catch(e=>setError(e.message)),3000);return()=>clearInterval(t);},[selected]);
 async function analyze(){setBusy(true);setError('');const mid=selected;try{key.current||=crypto.randomUUID();const r=await fetch(`/api/media/${mid}/analyses`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:profiles?providerChoice:undefined,request_key:key.current,window_s:12,overlap_s:2,frames_per_window:4,max_calls:calls})});const b=await r.json();if(!r.ok)throw new Error(typeof b.detail==='string'?b.detail:JSON.stringify(b.detail));await load(mid);}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function job(id,verb){try{const r=await fetch(`/api/jobs/${id}/${verb}`,{method:'POST'});const b=await r.json();if(!r.ok)throw new Error(typeof b.detail==='string'?b.detail:JSON.stringify(b.detail));await load(selected);}catch(e){setError(e.message);}}
 async function retryUnknown(run){
  if(!confirmRepeat)return;
  setBusy(true);setError('');setNotice('');
  try{
   const r=await fetch(`/api/analysis-runs/${run.id}/retry-unknown`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm_possible_repeat_charge:true})});
   const b=await r.json();if(!r.ok)throw new Error(typeof b.detail==='string'?b.detail:JSON.stringify(b.detail));
   setConfirmRepeat(false);setConsent(false);key.current=null;
   await load(selected);
   setNotice('已创建重新扫描任务。前次请求记录已保留，请在下方查看新任务进度。');
  }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 return <div className="review-analysis">
 {profiles&&<label>分析供应商<select value={providerChoice} disabled={busy} onChange={e=>{setProviderChoice(e.target.value);setConfirmRepeat(false);setNotice('');setError('');}}><option value="minimax" disabled={!profiles.minimax?.available}>MiniMax · 优先</option><option value="openai-compatible" disabled={!profiles['openai-compatible']?.available}>{profiles['openai-compatible']?.provider||'兼容接口'} · 备用</option></select></label>}
 <p className="review-help">{profile?.model?`供应商：${profile.provider} · 模型：${profile.model}。${profile.data_sent}`:'AI 默认关闭。请在本机配置供应商与密钥并明确启用，再刷新候选。'}</p>
 {mini&&<p className="review-help">MiniMax 优先扫描整段视频；每个窗口都做初扫和复核，已成功的窗口可在重试时复用。候选仍需人工确认。</p>}
 {profile?.model&&!profile.configured&&<p role="status" className="message">配置尚未完成：{profile.missing?.join('、')||'API key'}。请检查本机 apps/football-ai-studio/.env，重启服务后刷新。当前没有发送视频或产生调用费用。</p>}
 {profile?.configured&&!profile.enabled&&<p className="review-help">供应商已配置，AI 尚未启用。请在本机设置 FAS_AI_ENABLED=true 并重启。</p>}
 {(profile?.available||mini)&&<>
 <div className="review-fields"><label>要分析的视频<select value={selected} disabled={busy} onChange={e=>setSelected(e.target.value)}><option value="">选择素材…</option>{ready.map(m=><option key={m.id} value={m.id}>{m.name} · {m.duration.toFixed(1)} 秒</option>)}</select></label></div><details className="analysis-advanced"><summary>高级设置 · 调用上限与分析方式</summary><label>调用次数上限<input type="number" min="2" max={maxCalls} disabled={busy} value={calls} onChange={e=>{setCalls(Number(e.target.value));key.current=null;}}/></label>
 <p className="review-help">12 秒窗口，重叠 2 秒。{profile.input_mode==='video'?'发送无声压缩短片，初扫每秒2帧、复核每秒5帧。':'每窗口初扫4帧、复核8帧，帧旁标注原片时间。'}每窗都执行两轮，共需 {windows?windows*2:'—'} 次调用；费用按供应商实际计费。</p></details>
 {!supported&&current&&<p role="status" className="message">整段视频需要 {windows*2} 次调用，超过当前 {maxCalls} 次上限。请将原片分段导入后分别扫描。</p>}
 <label className="review-check"><input type="checkbox" disabled={!profile.available||busy} checked={consent} onChange={e=>setConsent(e.target.checked)}/>我同意将所选视频的{profile.input_mode==='video'?'无声压缩短片':'抽帧'}及本场次人物参考发送给 {profile.provider}</label>
 {!targetReady&&<p className="review-help">请先在上方保存目标人物参考，再分析本场视频。</p>}
 {(recoverable||previousVersionUnknown||otherProviderUnknown)&&<div className="review-export-job" role="status"><strong>上次扫描有未确认的 AI 请求</strong>{recoverable?.error?.includes('HTTP 503')&&<p>Gemini 返回 503，服务暂时不可用或繁忙。请等待几分钟后再手动重试，连续点击不会更快恢复。</p>}<p>{recoverable?'前次请求可能已计费。重新发送相同窗口可能产生重复费用；此次操作会创建新任务，保留旧记录。':previousVersionUnknown?'扫描请求已更新，旧任务不能直接重试。前次请求可能已计费；开始新扫描仍可能产生重复费用，旧记录会保留。':'这段视频在另一家供应商有未确认请求。切换供应商会重新发送抽帧，两家都可能计费。'}</p><label className="review-check"><input type="checkbox" checked={confirmRepeat} disabled={busy} onChange={e=>setConfirmRepeat(e.target.checked)}/>我已了解可能重复计费，同意重新发送</label>{recoverable&&<div className="review-controls"><button disabled={busy||!confirmRepeat} onClick={()=>retryUnknown(recoverable)}>确认可能重复计费并重新扫描</button></div>}</div>}
 <div className="review-controls"><button disabled={Boolean(recoverable)||((previousVersionUnknown||otherProviderUnknown)&&!confirmRepeat)||!targetReady||!profile.available||!supported||!consent||busy||!Number.isFinite(calls)||calls<2||calls>maxCalls||!Number.isInteger(calls)||calls<windows*2} onClick={analyze}>{currentRuns[0]?.status==='succeeded'?'重新生成候选':'生成候选片段'}</button></div></>}
 {error&&<p role="alert" className="message error">{error}</p>}
 {notice&&<p role="status" className="message">{notice}</p>}
 {currentRuns[0]&&<div className="review-export-job"><strong>最近一次分析 · {currentRuns[0].status==='succeeded'?'已完成':currentRuns[0].status==='running'?'进行中':currentRuns[0].status==='failed'?'失败':currentRuns[0].status}</strong><p>{currentRuns[0].stage} · {Math.round(currentRuns[0].progress||0)}%</p>{currentRuns[0].error&&<p>{currentRuns[0].error}</p>}{currentRuns[0].status==='succeeded'&&<p>候选会自动显示在下方，无需手动刷新。</p>}{['queued','running'].includes(currentRuns[0].status)&&<button onClick={()=>job(currentRuns[0].job_id,'cancel')}>取消分析</button>}</div>}
 {runs.length>1&&<details className="analysis-history"><summary>历史分析记录 · {runs.length-1} 次</summary>{runs.slice(1).map(run=><div className="review-export-job" key={run.id}><strong>{run.status==='failed'?'失败':run.status==='succeeded'?'已完成':run.status} · {run.config?.provider||'分析'}</strong><p>{run.stage}</p>{run.error&&<p>{run.error}</p>}</div>)}</details>}
 </div>;
}
