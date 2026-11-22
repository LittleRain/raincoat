#!/usr/bin/env python3
"""Independent experiment: no UI, database writes, job queue, or automatic retries."""
import argparse
import base64
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

BASE=Path(__file__).resolve().parents[1]
PRICE_SOURCE='https://platform.minimax.cn/docs/pricing/overview'
PROMPT='''你正在验证足球训练视频理解能力，而不是制作集锦。目标人物由用户指定：{target}。
只依据当前视频可见证据判断，不要把其他人物动作归给目标。不可用人脸推断身份。
逐段查看完整视频，识别进球goal、射门shot、带球突破dribble、抢断tackle。
普通跑动、接球、传球可记为other，但不要冒充高光。
进球需要看到球入门；射门需要看到踢球射向球门；突破需有带球绕过防守并推进；抢断需有可见球权转换。
看不清球或目标时输出uncertain；没有证据时events为空，不要为满足任务编造动作。
所有时间均为输入视频从0开始的秒数，时长{duration:.6f}秒，忽略编码尾部不足一帧的填充。
视频没有声音，不能使用哨声、庆祝声音等证据。用简体中文给出证据、描述和局限。
只输出JSON，不要代码围栏：
{{"target":{{"visible":true,"clothing_evidence":"可见服装特征或看不清","uncertainty":""}},
"observations":[{{"start_s":0,"end_s":1,"description":"所有可见的普通动作和上下文，非只列高光"}}],
"events":[{{"start_s":0,"end_s":1,"event_type":"goal|shot|dribble|tackle|other",
"event_confidence":0.0,"identity_confidence":0.0,"identity_status":"likely_target|other|uncertain",
"evidence":"球、脚、门、防守或球权变化的具体可见证据","identity_evidence":"如何对应红衣绿裤目标",
"description":"简短描述","uncertainty":"缺失证据、遮挡或时间误差"}}],
"limitations":["画面限制"]}}
不要输出人工确认状态。置信度仅作排序，不代表已校准概率。'''


def estimate_cny(usage):
    """Pay-as-you-go equivalent, never a claim about subscription cash charges."""
    p=usage.get('prompt_tokens');o=usage.get('completion_tokens')
    if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in (p,o)):
        return None
    cached=usage.get('prompt_tokens_details',{}).get('cached_tokens',0)
    cached=min(p,max(0,cached)) if isinstance(cached,int) else 0
    factor=2 if p>512000 else 1
    return round(((p-cached)*2.1+cached*.42+o*8.4)*factor/1e6,8)


def validate_result(result,duration):
    if not isinstance(result,dict) or not isinstance(result.get('events'),list):
        raise ValueError('响应缺少events数组')
    for e in result['events']:
        values=[e.get('start_s'),e.get('end_s'),e.get('event_confidence'),e.get('identity_confidence')]
        if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in values):
            raise ValueError('时间或置信度无效')
        a,b,ec,ic=values
        if not 0<=a<b<=duration or not 0<=ec<=1 or not 0<=ic<=1:
            raise ValueError('时间范围或置信度越界')
        if e.get('event_type') not in {'goal','shot','dribble','tackle','other'} or e.get('identity_status') not in {'likely_target','other','uncertain'}:
            raise ValueError('动作或身份枚举无效')
    return result


def quota_snapshot(client,key):
    # Same official provider and region; no video or model invocation.
    try:
        r=client.get('https://api.minimaxi.com/v1/api/openplatform/coding_plan/remains',headers={'Authorization':'Bearer '+key})
        b=r.json()
        allow={'model_name','start_time','end_time','remains_time','current_interval_total_count',
               'current_interval_usage_count','weekly_total_count','weekly_usage_count','weekly_remains_time'}
        def scrub(value):
            if isinstance(value,list): return [scrub(x) for x in value if isinstance(x,dict)]
            if isinstance(value,dict):
                return {k:(scrub(v) if isinstance(v,(dict,list)) else v) for k,v in value.items()
                        if k in allow or k in {'model_remains','data','base_resp','status_code'}}
            return None
        return {'http_status':r.status_code,'snapshot':scrub(b)}
    except (httpx.HTTPError,ValueError):
        return {'available':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--label',required=True)
    parser.add_argument('--target',default='红色上衣、绿色裤子的小孩')
    parser.add_argument('--fps',type=float,choices=[1,2,5],default=2)
    parser.add_argument('--width',type=int,choices=[768,1280,1920],default=1280)
    parser.add_argument('--height',type=int,choices=[960],help='Video or frame height; overrides --width')
    parser.add_argument('--prompt-file',type=Path,help='Use the exact UTF-8 prompt from this file')
    parser.add_argument('--mode',choices=['video','frames'],default='video')
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--end',type=float)
    parser.add_argument('--thinking',choices=['disabled','adaptive'],default='disabled')
    parser.add_argument('--strict-labels',action='store_true')
    parser.add_argument('--encode-fps',type=int,choices=[2,5,24],default=24)
    parser.add_argument('--base-url',default='https://api.minimaxi.com/v1')
    args=parser.parse_args()
    if args.prompt_file and (args.strict_labels or args.start or args.end is not None):
        parser.error('原文提示词仅支持完整视频且不能追加规则')
    if args.base_url not in {'https://api.minimaxi.com/v1','https://api.minimax.cn/v1','https://api.minimax.io/v1'}:
        parser.error('只允许明确列出的MiniMax官方端点')
    if not args.label.replace('-','').replace('_','').isalnum(): parser.error('label须为字母数字或连字符')
    load_dotenv(BASE/'.env')
    key=os.getenv('MINIMAX_API_KEY') or os.getenv('FAS_AI_API_KEY')
    if not key: raise SystemExit('缺少本机密钥')
    source=args.input.resolve(strict=True)
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/'experiment.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result_path=args.out/f'{args.label}.json'
        if result_path.exists():
            print(json.dumps({'label':args.label,'existing_result':str(result_path),'no_new_request':True}));return
        ledger_path=args.out/'ledger.json'
        ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else []
        if any(x['label']==args.label for x in ledger): raise SystemExit('此标签已有请求记录；为避免未知请求重复费用，不重发')
        if len(ledger)>=6: raise SystemExit('实验已达6次请求上限')
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(source)]))
        duration=float(probe['format']['duration'])
        if not 0<duration<=30: raise SystemExit('首轮独立实验仅接受30秒以内视频')
        start=args.start;end=duration if args.end is None else args.end
        if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end<=duration:
            raise SystemExit('实验输入区间必须位于源视频时长内')
        prompt=args.prompt_file.read_text() if args.prompt_file else PROMPT.format(target=args.target,duration=duration)
        if start or end<duration:
            prompt=prompt.replace('逐段查看完整视频','逐段查看完整输入区间')
            prompt+=f'\n本次只提供源时间[{start},{end}]秒的局部区间。不要推断该区间以外事件，输出仍使用源视频时间，不能从0重新计时。'
        if args.mode=='frames':
            prompt+='\n输入是按时间顺序排列的图片序列，每张图前明确标有源视频时间。请使用这些秒数定位动作，不能把帧号除以24当时间；观察范围应覆盖最后一张图，不可只分析前几张。两个图片之间缺失动作须明确写为不确定。'
        if args.strict_labels:
            prompt+='''\n类别规则补充：本实验枚举dribble特指“带球突破”，不等于英语日常用法中的一般带球。必须有明显带球越过/摆脱防守并保持推进的可见证据才能标为dribble。只是带球、护球、跟随、并跑、对抗，或你自己认为“未明显摆脱”“是否突破不确定”，一律归other，不能把不确定突破当作正例。shot必须同时具备清楚出脚击球和朝球门方向的证据，朝远离球门方向踢/捅球不能标为shot。tackle必须同时说明此前谁控球、谁触球、之后谁取得球权；动作主体不是目标时必须标identity_status=other。不要为了输出高光把普通动作升级为高光。'''
        (args.out/f'{args.label}-prompt.txt').write_text(prompt)
        with source.open('rb') as stream:
            sha=hashlib.file_digest(stream,'sha256').hexdigest()
        prep=time.monotonic()
        with tempfile.TemporaryDirectory(prefix='football-independent-') as tmp:
            content=[{'type':'text','text':prompt}];sample_times=[];clip_size=0
            scale=f'scale=-2:{args.height}' if args.height else f'scale={args.width}:{args.width}:force_original_aspect_ratio=decrease:force_divisible_by=2'
            if args.mode=='video':
                clip=Path(tmp)/'silent.mp4'
                command=['ffmpeg','-v','error','-nostdin','-y','-threads','2','-ss',str(start),'-i',str(source),'-t',str(end-start),
                         '-map','0:v:0','-an','-map_metadata','-1','-vf',f'{scale},setsar=1,fps={args.encode_fps}',
                         '-c:v','libx264','-preset','veryfast','-crf','24','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(clip)]
                subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
                encoded_probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate','-of','json',str(clip)]))['streams'][0]
                clip_size=clip.stat().st_size
                # Base64 expands by 4/3; 44 MiB leaves room under the 64 MB request limit.
                if clip_size>44*1024**2: raise SystemExit('压缩视频超过44MiB，未发送')
                encoded=base64.b64encode(clip.read_bytes()).decode()
                content.append({'type':'video_url','video_url':{'url':'data:video/mp4;base64,'+encoded,'fps':args.fps,'detail':'default'}})
            else:
                sample_times=[round(start+i/args.fps,6) for i in range(math.floor((end-start-.1)*args.fps)+1)]
                for index,t in enumerate(sample_times):
                    frame=Path(tmp)/f'{index:04}.jpg'
                    subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-threads','2','-ss',str(t),'-i',str(source),
                                    '-frames:v','1','-vf',scale,
                                    '-threads','1','-q:v','5',str(frame)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
                    if index==0:
                        frame_probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(frame)]))['streams'][0]
                    size=frame.stat().st_size;clip_size+=size
                    if size>1024**2 or clip_size>24*1024**2: raise SystemExit('抽帧输入过大，未发送')
                    content.extend([{'type':'text','text':f'源视频时间 {t:.3f} 秒'},
                                    {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(frame.read_bytes()).decode(),'detail':'default'}}])
            payload={'model':'MiniMax-M3','messages':[{'role':'user','content':content}],
                     'temperature':1,'thinking':{'type':args.thinking},'reasoning_split':True,
                     'max_completion_tokens':12000 if args.thinking=='adaptive' else 6000,'service_tier':'standard'}
            dimensions=encoded_probe if args.mode=='video' else frame_probe
            record={'label':args.label,'state':'pending','created_at':datetime.now(timezone.utc).isoformat(),
                    'model':'MiniMax-M3','base_url':args.base_url,'source_sha256':sha,'duration':duration,
                    'video_bytes':clip_size,'sample_fps':args.fps,'long_side':max(dimensions['width'],dimensions['height']),
                    'encoded_video':encoded_probe if args.mode=='video' else None,
                    'frame_dimensions':frame_probe if args.mode=='frames' else None,
                    'input_mode':args.mode,'sample_times_s':sample_times,
                    'source_window_s':[start,end],
                    'thinking':args.thinking,'strict_labels':args.strict_labels,
                    'encode_fps':args.encode_fps,
                    'local_prepare_seconds':round(time.monotonic()-prep,3),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()}
            with httpx.Client(timeout=httpx.Timeout(180,connect=15),follow_redirects=False) as client:
                record['quota_before']=quota_snapshot(client,key)
                ledger.append(record);ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
                started=time.monotonic()
                try:
                    with client.stream('POST',args.base_url+'/chat/completions',headers={'Authorization':'Bearer '+key,'Idempotency-Key':sha+'-'+args.label},json=payload) as response:
                        data=bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data)>1024**2: raise RuntimeError('响应超过1MiB限制')
                    record['request_seconds']=round(time.monotonic()-started,3)
                    record['http_status']=response.status_code
                    body=json.loads(data)
                    record['business_code']=body.get('base_resp',{}).get('status_code')
                    record['usage']=body.get('usage',{})
                    record['request_id']=body.get('id')
                    record['paygo_equivalent_cny']=estimate_cny(record['usage'])
                    record['actual_cash_charge']=None
                    record['pricing_source']=PRICE_SOURCE
                    if response.status_code>=400 or record['business_code']:
                        record['state']='rejected'
                        # Never retain arbitrary error bodies which might echo request content.
                        err=body.get('error',{})
                        record['error_type']=err.get('type') if isinstance(err,dict) else None
                        message=err.get('message','') if isinstance(err,dict) else ''
                        record['error_message']=str(message).replace(key,'[REDACTED]')[:500]
                        raise RuntimeError('供应商拒绝请求，查看实验ledger中的HTTP状态和业务码')
                    (args.out/f'{args.label}-response.json').write_text(json.dumps(body,ensure_ascii=False,indent=2))
                    text=body['choices'][0]['message']['content'].strip()
                    if body['choices'][0].get('finish_reason')=='length': raise ValueError('输出被截断')
                    if text.startswith('```') and text.endswith('```'): text=text.split('\n',1)[1].rsplit('```',1)[0]
                    result=validate_result(json.loads(text),duration)
                    if any(e['start_s']<start or e['end_s']>end for e in result['events']):
                        raise ValueError('事件超出本次输入区间')
                    result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
                    record['state']='succeeded'
                except (httpx.HTTPError,ValueError,KeyError,IndexError,RuntimeError) as exc:
                    record['error_class']=type(exc).__name__
                    if record['state']=='pending': record['state']='unknown_or_invalid'
                finally:
                    record['quota_after']=quota_snapshot(client,key)
                    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
        print(json.dumps({k:v for k,v in record.items() if k not in {'quota_before','quota_after'}},ensure_ascii=False,indent=2))
        if result_path.exists(): print(result_path.read_text())
        if record['state']!='succeeded': raise SystemExit(1)


if __name__=='__main__':main()
