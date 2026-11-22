"""Local fixed-camera badminton activity candidates for the shared workbench."""
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .core import now
from .analysis import media_for, source_path


class ScanInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    request_key: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=120)
    ignore_before: float = Field(default=0, ge=0)
    court_roi: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode='after')
    def valid_roi(self):
        if self.court_roi:
            x, y, w, h = self.court_roi
            if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > 1 or y+h > 1:
                raise ValueError('球场区域必须位于画面内')
        return self


def normalize(values):
    if not values:
        return []
    ordered = sorted(values)
    low = ordered[int((len(ordered)-1)*.10)]
    high = ordered[int((len(ordered)-1)*.90)]
    if high-low < 1e-9:
        return [0.0]*len(values)
    return [max(0.0,min(1.0,(v-low)/(high-low))) for v in values]


def candidate_ranges(activity, total, ignore_before):
    for index in range(min(len(activity),math.ceil(ignore_before))):
        activity[index] = 0.0
    if not activity or max(activity) <= 0:
        return fallback_ranges(total,ignore_before), True
    threshold = max(.25,sorted(activity)[int((len(activity)-1)*.60)])
    raw, start = [], None
    for second, value in enumerate(activity+[0.0]):
        if value >= threshold and start is None:
            start = second
        elif value < threshold and start is not None:
            if raw and start <= raw[-1][1]+1:
                raw[-1] = (raw[-1][0],float(second))
            else:
                raw.append((float(start),float(second)))
            start = None
    expanded = [[max(ignore_before,a-2),min(total,b+3)] for a,b in raw]
    for index in range(len(expanded)-1):
        if expanded[index][1] > expanded[index+1][0]:
            boundary = (raw[index][1]+raw[index+1][0])/2
            expanded[index][1] = boundary
            expanded[index+1][0] = boundary
    ranges = [(a,b) for a,b in expanded if b-a >= 3]
    return (ranges,False) if ranges else (fallback_ranges(total,ignore_before),True)


def fallback_ranges(total, ignore_before):
    result, start = [], ignore_before
    while start < total:
        end = min(total,start+30)
        if end-start >= 3:
            result.append((start,end))
        if end == total:
            break
        start += 24
    return result


def register_routes(app, store):
    @app.get('/api/media/{mid}/badminton-analyses')
    def runs(mid: str):
        media = media_for(store,mid)
        if store.session(media['session_id'])['sport'] != 'badminton':
            raise HTTPException(422,'此素材不属于羽毛球场次')
        rows = store.rows("SELECT a.*,j.status,j.stage,j.progress,j.error FROM analysis_runs a JOIN jobs j ON j.id=a.job_id WHERE a.media_id=? AND j.type='badminton_analysis' ORDER BY a.created_at DESC",(mid,))
        for row in rows:
            for key in ('config','estimate','coverage','actual_usage'):
                row[key] = json.loads(row.pop(key+'_json'))
        return rows

    @app.post('/api/media/{mid}/badminton-analyses',status_code=202)
    def start(mid: str, body: ScanInput):
        media = media_for(store,mid)
        if store.session(media['session_id'])['sport'] != 'badminton':
            raise HTTPException(422,'此素材不属于羽毛球场次')
        if not store.rows('SELECT id FROM target_references WHERE session_id=? LIMIT 1',(media['session_id'],)):
            raise HTTPException(409,'请先为本场次保存目标人物，再生成候选片段')
        if not media['duration'] or body.ignore_before >= media['duration']:
            raise HTTPException(422,'跳过开头时间必须小于原片时长')
        completed = store.rows("SELECT id FROM jobs WHERE media_id=? AND type='preprocess' AND status='succeeded'",(mid,))
        if not completed:
            raise HTTPException(409,'请先完成素材预处理')
        existing = store.rows('SELECT id,job_id FROM analysis_runs WHERE media_id=? AND request_key=?',(mid,body.request_key))
        if existing:
            return existing[0]
        rid,jid = uuid4().hex,uuid4().hex
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT INTO jobs(id,media_id,type,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                         (jid,mid,'badminton_analysis',json.dumps({'run_id':rid}),now(),now()))
            conn.execute('INSERT INTO analysis_runs(id,media_id,session_id,job_id,request_key,config_json,estimate_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
                         (rid,mid,media['session_id'],jid,body.request_key,json.dumps(body.model_dump()),json.dumps({'provider':'local-motion'}),now()))
        return {'id':rid,'run_id':rid,'job_id':jid}


def analyze(worker, job):
    store,jid = worker.store,job['id']
    rid = json.loads(job['payload_json'])['run_id']
    run = store.rows('SELECT * FROM analysis_runs WHERE id=?',(rid,))[0]
    cfg = json.loads(run['config_json'])
    media = media_for(store,job['media_id'])
    source = source_path(store,media)
    folder = store.data/'derived'/media['id']/'badminton'
    folder.mkdir(parents=True,exist_ok=True)
    roi = cfg['court_roi']
    crop = '' if not roi else f'crop=iw*{roi[2]}:ih*{roi[3]}:iw*{roi[0]}:ih*{roi[1]},'
    width = 160
    source_width = media['width']*(roi[2] if roi else 1)
    source_height = media['height']*(roi[3] if roi else 1)
    height = max(2,round(source_height*width/source_width/2)*2)
    raw = folder/f'{rid}.gray'
    log = folder/f'{rid}.log'
    worker.update(jid,stage='提取球场运动信号',progress=10)
    try:
        worker.run([os.getenv('FFMPEG_BIN','ffmpeg'),'-v','error','-nostdin','-y','-i',str(source),
                    '-vf',f'fps=1,{crop}scale={width}:{height}','-pix_fmt','gray','-f','rawvideo',str(raw)],jid,log)
        frame_size = width*height
        values, previous = [],None
        with raw.open('rb') as stream:
            while frame := stream.read(frame_size):
                worker.check(jid)
                if len(frame) != frame_size:
                    break
                sampled = frame[::8]
                values.append(0.0 if previous is None else sum(abs(a-b) for a,b in zip(sampled,previous))/(255*len(sampled)))
                previous = sampled
        total = media['duration']
        motion = normalize((values+[0.0]*math.ceil(total))[:math.ceil(total)])
        ranges,fallback = candidate_ranges(motion,total,cfg['ignore_before'])
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for index,(start,end) in enumerate(ranges):
                worker.check(jid)
                cid = hashlib.sha256(f'{rid}:{index}:{start}:{end}'.encode()).hexdigest()
                part = motion[int(start):max(int(start)+1,math.ceil(end))]
                confidence = 0.4 if fallback else 0.62
                evidence = '未检测到可靠活动边界，使用重叠时间窗' if fallback else '固定机位画面运动量提示的活跃范围；尚未确认完整回合或人物'
                conn.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             (cid,rid,media['id'],media['session_id'],start,end,'other',sum(part)/len(part) if part else 0,
                              confidence,'uncertain',evidence,'未自动识别球员','待确认回合边界','需人工确认发球和结束点',now()))
            conn.execute('UPDATE analysis_runs SET coverage_json=? WHERE id=?',(json.dumps([{'start_s':0,'end_s':total,'method':'local-motion'}]),rid))
            conn.execute("UPDATE jobs SET status='succeeded',stage='待复核活动候选已生成',progress=100,error=NULL,updated_at=? WHERE id=?",(now(),jid))
    finally:
        raw.unlink(missing_ok=True)
        log.unlink(missing_ok=True)
        Path(str(log)+'.err').unlink(missing_ok=True)
