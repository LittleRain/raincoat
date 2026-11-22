import React,{useEffect,useState} from 'react';
const size=n=>{if(!Number.isFinite(n))return '—';if(n<1024)return n+' B';if(n<1024**2)return (n/1024).toFixed(1)+' KB';if(n<1024**3)return (n/1024**2).toFixed(1)+' MB';return (n/1024**3).toFixed(2)+' GB';};
export default function StoragePanel(){
 const [storage,setStorage]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function request(method='GET'){const r=await fetch('/api/storage'+(method==='POST'?'/cleanup':''),{method,headers:{'Content-Type':'application/json'},...(method==='POST'?{body:'{}'}:{})});const b=await r.json();if(!r.ok)throw new Error(typeof b.detail==='string'?b.detail:JSON.stringify(b.detail));return b;}
 async function refresh(){try{setStorage(await request());setError('');}catch(e){setError('读取存储用量失败：'+e.message);}}
 useEffect(()=>{refresh();},[]);
 async function cleanup(){setBusy(true);setError('');setNotice('');try{const result=await request('POST');setNotice(`已清理 ${result.files??result.removed_files??0} 个分析帧缓存，释放 ${size(result.removed_bytes)}。`);setStorage(await request());}catch(e){setError('清理分析帧缓存失败：'+e.message);}finally{setBusy(false);}}
 return <section className="panel storage-panel"><div className="section-head"><h2>本地存储</h2><button disabled={busy} onClick={refresh}>刷新用量</button></div><div className="storage-grid">{[['originals_bytes','原片'],['derived_bytes','播放代理与缩略图'],['exports_bytes','成片'],['cache_bytes','分析缓存'],['database_bytes','数据库'],['total_bytes','总计']].map(([key,label])=><div key={key}><span>{label}</span><strong>{size(storage?.[key])}</strong></div>)}</div><p className="review-help">清理仅移除可重新生成的分析帧；保留分析结果与费用缓存、目标人物参考、原片和成片。有活动任务时，请等待完成或取消后再清理。</p><button disabled={busy} onClick={cleanup}>{busy?'正在清理…':'清理分析帧缓存'}</button>{notice&&<p role="status" className="message">{notice}</p>}{error&&<p role="alert" className="message error">{error}</p>}</section>;
}
