#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, html
from pathlib import Path

PAGE='''<!doctype html><meta charset="utf-8"><title>Rain Badminton Cut review</title>
<style>body{font:15px system-ui;max-width:1100px;margin:24px auto;padding:0 16px;background:#f6f7f9}article{background:white;padding:14px;margin:12px 0;border-radius:10px}video{width:100%;max-height:420px;background:#111}input{width:90px}button{padding:8px 14px;margin:5px}</style>
<h1>Rain Badminton Cut</h1><p id="summary"></p><p id="status">请检查候选片段，确认保留范围后生成合集。</p><div id="clips"></div><button onclick="download()">导出 edits.json</button><button onclick="renderHighlights()">确认并生成合集</button>
<script>const data=__DATA__;const source=data.source;const state={source,plan:'standard',output:{resolution:'original',video_bitrate_kbps:null},weights:{},confirmed:false,clips:[]};
for(const [k,v] of Object.entries(data.candidates[0]?.signals||{}))state.weights[k]=v?1:1;
state.clips=data.candidates.map(x=>({id:x.id,keep:true,start:x.start,end:x.end}));
document.querySelector('#summary').textContent=`候选 ${data.candidates.length} 段｜原视频 ${data.duration.toFixed(1)} 秒｜请确认时间范围后导出`;
const root=document.querySelector('#clips');data.candidates.forEach((x,i)=>{const a=document.createElement('article');a.innerHTML=`<h3>${x.id}　评分 ${x.score}</h3><p>${x.reasons.join('；')}｜完整性 ${x.completeness_confidence}</p><video controls preload="metadata" src="${source.replaceAll('\\\\','/')}" data-start="${x.start}" data-end="${x.end}"></video><label><input type="checkbox" checked data-i="${i}" onchange="state.clips[${i}].keep=this.checked"> 保留</label> 起 <input value="${x.start}" data-s="${i}"> 止 <input value="${x.end}" data-e="${i}">`;const v=a.querySelector('video');v.addEventListener('loadedmetadata',()=>{v.currentTime=Number(v.dataset.start)});v.addEventListener('timeupdate',()=>{if(v.currentTime>=Number(v.dataset.end))v.pause()});root.append(a)});
document.addEventListener('change',e=>{if(e.target.dataset.s)state.clips[e.target.dataset.s].start=Number(e.target.value);if(e.target.dataset.e)state.clips[e.target.dataset.e].end=Number(e.target.value)});
function confirmed(){return {...state,confirmed:true}}
function download(){const b=new Blob([JSON.stringify(confirmed(),null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='edits.json';a.click()}
async function renderHighlights(){const status=document.querySelector('#status');status.textContent='正在生成合集…';try{const r=await fetch('/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(confirmed())}),body=await r.json();if(!r.ok)throw new Error(body.error||'渲染失败');status.textContent=`完成：${body.output}`}catch(error){status.textContent=`无法直接渲染：${error.message}。若此页面是直接打开的，请先导出 edits.json，再运行 render_highlights.py。`}}</script>'''

def main():
 ap=argparse.ArgumentParser();ap.add_argument('clips',type=Path);ap.add_argument('--out',type=Path,default=Path('review.html'));ap.add_argument('--video-src');a=ap.parse_args();data=json.loads(a.clips.read_text(encoding='utf-8'))
 if a.video_src: data['source']=a.video_src
 a.out.write_text(PAGE.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/')),encoding='utf-8');print(f'Wrote {a.out}')
if __name__=='__main__':main()
