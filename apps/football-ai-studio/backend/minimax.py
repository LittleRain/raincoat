"""MiniMax M3: local, silent window clips, then text-only structured results."""
import base64
import json
import os
from uuid import uuid4
from urllib.parse import urlsplit

MAX_CLIP_BYTES = 16 * 1024**2


def request_payload(config, content):
    common={'model':config['model'],'messages':[{'role':'user','content':content}]}
    if config.get('provider')=='minimax':
        if config['model']!='MiniMax-M3':
            raise RuntimeError('当前 MiniMax 验证预设仅支持 MiniMax-M3 视频理解')
        return {**common,'temperature':1,'max_completion_tokens':8192,
                'thinking':{'type':'disabled'},'reasoning_split':True}
    if urlsplit(config.get('base_url','')).hostname == 'generativelanguage.googleapis.com':
        return {**common,'reasoning_effort':'low','max_tokens':2500,
                'response_format':{'type':'json_object'}}
    return {**common,'temperature':0,'max_tokens':2500,'response_format':{'type':'json_object'}}


def parse_response(value):
    status=value.get('base_resp',{}).get('status_code',0)
    if status:
        raise RuntimeError(f'MiniMax 返回业务错误码 {status}，请检查账号、余额或模型权限')
    choice=value['choices'][0]
    if choice.get('finish_reason')=='length':
        raise RuntimeError('模型输出达到长度上限，未将不完整结果保存为成功')
    text=choice['message']['content']
    if not isinstance(text,str) or not text.strip():
        raise RuntimeError('模型未返回分析正文，未保存为成功')
    text=text.strip()
    if text.startswith('```') and text.endswith('```'):
        text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
    return json.loads(text)


def video_content(worker, source, start, end, phase, jid, folder):
    clip=folder/f'minimax-{uuid4().hex}.mp4'
    output=clip.with_suffix('.log')
    fps=2 if phase=='scan' else 5
    try:
        worker.run([os.getenv('FFMPEG_BIN','ffmpeg'),'-hide_banner','-loglevel','error','-nostdin','-y',
                    '-threads','2','-ss',str(start),'-t',str(end-start),'-i',str(source),
                    '-map','0:v:0','-an','-map_metadata','-1',
                    # Preserve tail timing at 24fps; model-side sampling controls cost.
                    '-vf','scale=768:768:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,fps=24',
                    '-c:v','libx264','-preset','veryfast','-crf','26','-threads','2',
                    '-pix_fmt','yuv420p','-movflags','+faststart',str(clip)],jid,output)
        if not clip.is_file() or not 0<clip.stat().st_size<=MAX_CLIP_BYTES:
            raise RuntimeError('分析短片未生成或超过16MiB限制，未发送')
        data=base64.b64encode(clip.read_bytes()).decode('ascii')
        return [
            {'type':'text','text':f'The following silent video contains only source range [{start}, {end}] seconds. '
             f'Video local time begins at zero: source_time = {start} + video_local_time. '
             f'The encoder may pad less than one frame at the tail; ignore anything at or after source time {end}. '
             'Return ALL event start_s/end_s in absolute SOURCE seconds, not clip-relative seconds. '
             'No audio is supplied; do not invent speech or cheering evidence. '
             'Write evidence, identity_evidence, description and uncertainty in Simplified Chinese.'},
            {'type':'video_url','video_url':{'url':'data:video/mp4;base64,'+data,'detail':'default','fps':fps}},
        ]
    finally:
        clip.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        output.with_name(output.name+'.err').unlink(missing_ok=True)
