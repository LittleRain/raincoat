"""Snapshot-based, single-worker rendering. User text never enters filter syntax."""
import hashlib
import json
import math
import os
import shutil
import unicodedata
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .core import now
from .review import session_or_404, serialize, validate_event


class ExportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_ids: list[str] = Field(min_length=1, max_length=200)
    title: str = Field(default='训练精彩集锦', max_length=100)
    orientation: Literal['landscape', 'portrait'] = 'landscape'
    allow_uncertain: bool = False
    mode: Literal['person','activity'] = 'person'
    request_key: str | None = Field(default=None, min_length=1, max_length=128)


def export_detail(store, eid):
    rows=store.rows('''SELECT e.*,j.status,j.progress,j.stage,j.error,j.attempts FROM exports e
        JOIN jobs j ON j.id=e.job_id JOIN sessions s ON s.id=e.session_id WHERE e.id=? AND s.deleted=0''',(eid,))
    if not rows:
        raise HTTPException(404,'导出不存在')
    item=rows[0]
    item['settings']=json.loads(item.pop('settings_json'))
    item['snapshot']=json.loads(item.pop('snapshot_json'))
    return item


def register_routes(app, store):
    @app.get('/api/sessions/{sid}/exports')
    def exports(sid: str):
        session_or_404(store,sid)
        return [export_detail(store,r['id']) for r in store.rows('SELECT id FROM exports WHERE session_id=? ORDER BY created_at DESC',(sid,))]

    @app.post('/api/sessions/{sid}/exports', status_code=202)
    def enqueue(sid: str, body: ExportInput):
        session = session_or_404(store,sid)
        if len(body.event_ids)!=len(set(body.event_ids)):
            raise HTTPException(422,'不能重复加入同一片段')
        settings={'title':body.title.strip(),'orientation':body.orientation,'allow_uncertain':body.allow_uncertain,'mode':body.mode,
                  'fps':30,'width':1920 if body.orientation=='landscape' else 1080,
                  'height':1080 if body.orientation=='landscape' else 1920,'version':1,'audio':'original_atempo_or_silence',
                  'title_duration':1.5 if body.title.strip() else 0}
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if body.request_key:
                existing=conn.execute('SELECT * FROM exports WHERE session_id=? AND request_key=?',(sid,body.request_key)).fetchone()
                if existing:
                    old_ids=[x['id'] for x in json.loads(existing['snapshot_json'])]
                    if old_ids!=body.event_ids or json.loads(existing['settings_json'])!=settings:
                        raise HTTPException(409,'此提交标识已用于不同导出，请重新提交')
                    return export_detail(store,existing['id'])
            snapshot=[]
            for eid in body.event_ids:
                row=conn.execute('SELECT * FROM review_events WHERE id=? AND session_id=?',(eid,sid)).fetchone()
                if not row:
                    raise HTTPException(422,'所选片段不属于此场次')
                event=serialize(row)
                activity = session['sport']=='badminton' and body.mode=='activity'
                if event['decision']!='keep' or not (activity or event['identity_status']=='confirmed_target' or
                                                    session['sport']=='football' and body.allow_uncertain and event['identity_status']=='uncertain'):
                    raise HTTPException(422,'只能导出已保留且身份确认的片段；身份不确定需显式启用')
                media=validate_event(conn,sid,event)
                event['media_name']=media['name']
                # Paths are server-resolved from IDs, not client-controlled fields.
                event['original_path']=media['path']
                event['managed']=media['managed']
                snapshot.append(event)
            total=settings['title_duration']+sum((e['end_s']-e['start_s'])/e['effects']['speed'] for e in snapshot)
            if total>3600:
                raise HTTPException(422,'单次集锦最多一小时，请缩短选片范围')
            eid,jid,stamp=uuid4().hex,uuid4().hex,now()
            conn.execute('INSERT INTO jobs(id,media_id,type,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                         (jid,snapshot[0]['media_id'],'render',json.dumps({'export_id':eid}),stamp,stamp))
            conn.execute('INSERT INTO exports(id,session_id,job_id,request_key,settings_json,snapshot_json,created_at) VALUES(?,?,?,?,?,?,?)',
                         (eid,sid,jid,body.request_key,json.dumps(settings,ensure_ascii=False),json.dumps(snapshot,ensure_ascii=False),stamp))
        return export_detail(store,eid)

    @app.get('/api/exports/{eid}')
    def detail(eid: str):
        return export_detail(store,eid)

    @app.get('/api/exports/{eid}/download')
    def download(eid: str):
        item=export_detail(store,eid)
        path=Path(item['output_path'] or '').resolve()
        if item['status']!='succeeded' or not path.is_relative_to(store.data/'exports') or not path.is_file():
            raise HTTPException(409,'成片尚未生成成功')
        sport = session_or_404(store,item['session_id'])['sport']
        return FileResponse(path,media_type='video/mp4',filename=f'{sport}-{eid[:8]}.mp4')


def font_path():
    candidates=[os.getenv('FAS_FONT_PATH',''),'/System/Library/Fonts/STHeiti Light.ttc',
                '/System/Library/Fonts/PingFang.ttc','/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
                '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
    for path in candidates:
        if path and Path(path).is_file():
            return path
    raise RuntimeError('未找到支持中文的字体，请设置 FAS_FONT_PATH 为本地字体路径')


def caption_image(text, dest, width, height, title=False):
    from PIL import Image, ImageDraw, ImageFont
    text=unicodedata.normalize('NFC',text)
    text=''.join(c for c in text if not unicodedata.category(c).startswith('C') or c=='\n')
    size=64 if title else (42 if width>height else 38)
    font=ImageFont.truetype(font_path(),size)
    image=Image.new('RGBA',(width,height),(15,27,21,255) if title else (0,0,0,0))
    draw=ImageDraw.Draw(image)
    lines=[]
    for paragraph in text.splitlines() or ['']:
        line=''
        for ch in paragraph:
            if draw.textlength(line+ch,font=font)>width-160 and line:
                lines.append(line); line=''
            line+=ch
        lines.append(line)
    # Keep all reviewed text readable: reject overlong overlays rather than truncate.
    line_height=size+16
    if len(lines)*line_height>height*.65:
        raise RuntimeError('字幕行数过多，请缩短片段描述后重新导出')
    y=(height-len(lines)*line_height)//2 if title else height-90-len(lines)*line_height
    if not title:
        draw.rounded_rectangle((50,y-20,width-50,y+len(lines)*line_height+12),radius=14,fill=(0,0,0,190))
    for line in lines:
        draw.text(((width-draw.textlength(line,font=font))/2,y),line,font=font,fill=(246,250,240,255),stroke_width=1)
        y+=line_height
    image.save(dest)


def render(worker, job):
    store,jid=worker.store,job['id']
    payload=json.loads(job['payload_json'])
    item=export_detail(store,payload['export_id'])
    eid=item['id']; settings=item['settings']; snapshot=item['snapshot']
    folder=store.data/'exports'/eid
    folder.mkdir(parents=True,exist_ok=True)
    # Retry cannot reuse partials from an interrupted attempt.
    work=folder/'work'
    shutil.rmtree(work,ignore_errors=True); work.mkdir()
    completed=False
    try:
        width,height=settings['width'],settings['height']
        ffmpeg=os.getenv('FFMPEG_BIN','ffmpeg'); ffprobe=os.getenv('FFPROBE_BIN','ffprobe')
        encoding=['-c:v','libx264','-preset','veryfast','-crf','21','-threads','2','-pix_fmt','yuv420p',
                  '-r','30','-video_track_timescale','90000','-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-movflags','+faststart']
        base=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-y','-filter_complex_threads','1']
        files=[]; durations=[]
        if settings['title_duration']:
            worker.update(jid,stage='生成片头',progress=1)
            image=work/'title.png'; caption_image(settings['title'],image,width,height,True)
            target=work/'0000.mp4'
            worker.run(base+['-loop','1','-i',str(image),'-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
                             '-t',str(settings['title_duration']),'-map','0:v','-map','1:a',*encoding,str(target)],jid,work/'title.log')
            files.append(target); durations.append(settings['title_duration'])
        total=settings['title_duration']+sum((e['end_s']-e['start_s'])/e['effects']['speed'] for e in snapshot)
        processed=sum(durations)
        for index,event in enumerate(snapshot,1):
            worker.check(jid)
            path=Path(event['original_path']).resolve()
            allowed=store.data/'uploads' if event['managed'] else store.root
            if not path.is_relative_to(allowed) or not path.is_file():
                raise RuntimeError('导出所需原文件缺失或已越界，请恢复原片后重试')
            worker.update(jid,stage=f'渲染片段 {index}/{len(snapshot)}',progress=5+processed/total*85)
            probe=work/f'probe-{index}.json'
            worker.run([ffprobe,'-v','error','-show_streams','-of','json',str(path)],jid,probe)
            streams=json.loads(probe.read_text())['streams']
            audio=any(s['codec_type']=='audio' for s in streams)
            speed=event['effects']['speed']; length=event['end_s']-event['start_s']; out_length=length/speed
            command=base+['-threads','2','-ss',str(event['start_s']),'-t',str(length),'-i',str(path)]
            filters=[f'[0:v:0]setpts=(PTS-STARTPTS)/{speed},scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x0f1b15,setsar=1,fps=30[v0]']
            label='v0'; image_index=1
            effects=event['effects']
            if effects.get('focus_box'):
                # Coordinates refer to displayed source orientation, before padding.
                v=next(s for s in streams if s['codec_type']=='video')
                rotation=next((float(s.get('rotation',0)) for s in v.get('side_data_list',[]) if 'rotation' in s),0)
                sw,sh=v['width'],v['height']
                if abs(rotation)%180==90: sw,sh=sh,sw
                ratio=min(width/sw,height/sh); dw,dh=sw*ratio,sh*ratio
                x,y,w,h=effects['focus_box']
                # A static outline is deliberately short and never presented as tracking.
                begin=max(0,((effects.get('focus_start_s') if effects.get('focus_start_s') is not None else event['start_s'])-event['start_s'])/speed)
                end=min(out_length,((effects.get('focus_end_s') if effects.get('focus_end_s') is not None else min(event['start_s']+1,event['end_s']))-event['start_s'])/speed)
                filters.append(f"[{label}]drawbox=x={(width-dw)/2+x*dw}:y={(height-dh)/2+y*dh}:w={w*dw}:h={h*dh}:color=0xb8ef91:t=5:enable='between(t,{begin},{end})'[vf]")
                label='vf'
            if effects.get('caption',True) and event['description'].strip():
                image=work/f'caption-{index}.png'
                text=event['description']
                if event['identity_status']=='uncertain':
                    text='身份未确认 · '+text
                caption_image(text,image,width,height)
                command+=['-loop','1','-i',str(image)]
                filters.append(f'[{label}][{image_index}:v]overlay=0:0:shortest=1[vout]')
                label='vout'; image_index+=1
            if audio:
                filters.append(f'[0:a:0]asetpts=PTS-STARTPTS,atempo={speed},aresample=48000,apad,atrim=duration={out_length}[aout]')
                audio_label='[aout]'
            else:
                command+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
                audio_label=f'{image_index}:a:0'
            target=work/f'{index:04}.mp4'; progress=work/f'progress-{index}.txt'
            command+=['-filter_complex',';'.join(filters),'-map',f'[{label}]','-map',audio_label,'-t',str(out_length),*encoding,'-progress',str(progress),str(target)]
            # Overall progress is monotonic across clips, based on FFmpeg media time.
            worker.run(command,jid,work/f'clip-{index}.log',progress,out_length,
                       progress_start=5+processed/total*85,progress_span=out_length/total*85)
            files.append(target); durations.append(out_length); processed+=out_length
        worker.update(jid,stage='拼接集锦',progress=92)
        manifest=work/'concat.txt'
        # Paths are fixed numeric filenames generated above; no user string enters concat syntax.
        manifest.write_text(''.join(f"file '{p.name}'\n" for p in files))
        partial=folder/'output.partial.mp4'
        worker.run(base+['-f','concat','-safe','1','-i',str(manifest),'-map','0:v:0','-map','0:a:0',
                         '-c','copy','-movflags','+faststart',str(partial)],jid,work/'concat.log')
        worker.update(jid,stage='校验成片',progress=97)
        probe=work/'output.json'
        worker.run([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(partial)],jid,probe)
        info=json.loads(probe.read_text()); streams=info['streams']
        v=next((s for s in streams if s['codec_type']=='video'),{})
        a=next((s for s in streams if s['codec_type']=='audio'),{})
        duration=float(info.get('format',{}).get('duration',0))
        if v.get('codec_name')!='h264' or a.get('codec_name')!='aac' or (v.get('width'),v.get('height'))!=(width,height) or not math.isfinite(duration) or abs(duration-total)>max(.4,total*.02):
            raise RuntimeError('成片格式或时长校验失败，未发布输出文件')
        worker.check(jid)
        output=folder/'output.mp4'; partial.replace(output)
        with store.connect() as conn:
            # Cancellation after the last poll must not publish a successful job.
            conn.execute('BEGIN IMMEDIATE')
            current=conn.execute('SELECT cancel_requested FROM jobs WHERE id=?',(jid,)).fetchone()
            if current['cancel_requested']:
                from .worker import Cancelled
                raise Cancelled()
            conn.execute('UPDATE exports SET output_path=?,duration=? WHERE id=?',(str(output),duration,eid))
            conn.execute("UPDATE jobs SET status='succeeded',stage='集锦已完成',progress=100,error=NULL,updated_at=? WHERE id=?",(now(),jid))
        completed=True
    finally:
        shutil.rmtree(work,ignore_errors=True)
        (folder/'output.partial.mp4').unlink(missing_ok=True)
        if not completed:
            # A completed but cancelled file is not downloadable, and takes no orphan space.
            (folder/'output.mp4').unlink(missing_ok=True)
