"""Opt-in frame analysis. No images leave this machine unless explicitly enabled."""
import asyncio
import base64
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .core import now
from .minimax import request_payload, parse_response, video_content

PROMPT_VERSION = 'football-continuous-6'
PROMPT = '''Review these football video frames at the supplied absolute source timestamps.
Return only JSON {"events": [{"start_s": number, "end_s": number,
"event_type": "goal|shot|dribble|tackle|other", "event_confidence": number,
"identity_confidence": number, "evidence": string, "identity_evidence": string,
"description": string, "uncertainty": string}]}.
A goal requires visible ball entering the goal, shot requires shooting toward goal,
dribble includes a visible attempt to evade a defender with the ball, even if the
defender ultimately wins it. Describe the attempt and outcome in ONE sequence.
tackle requires change in control.
Ordinary running is not a highlight. Never invent an event or infer a goal from celebration.
Return continuous, reviewable sequences: include the approach or ball reception,
the full drill repetition or live-play involvement, and the end of that play.
Use event_type other for a visible training drill worth preserving even without a
goal, shot, dribble, or tackle. Keep source timestamps and do not return isolated
one-frame action points. Return ONE event per continuous play or drill repetition,
even if it contains a dribble, challenge and change of possession. Choose the
single most representative event_type and mention secondary actions in description.
Do not split the same play into multiple overlapping events or repeat it with
different labels. Merge adjacent moments when the same players and ball remain in
one uninterrupted play. Start a new event only after a visible reset, break, or
distinct new drill repetition. For overlapping windows, report the same play once
using its full visible extent inside this window, not a separate event per frame.
Confidence values are uncalibrated ranking hints. Target identity must remain uncertain
if small, occluded or similarly dressed. Use references only as tentative visual evidence.
Return empty events when evidence is insufficient. Event and identity evidence are separate.
Write evidence, identity_evidence, description and uncertainty in Simplified Chinese.
'''


def config(provider_override=None):
    enabled = os.getenv('FAS_AI_ENABLED', '').lower() == 'true'
    default_provider = os.getenv('FAS_AI_PROVIDER','openai-compatible').strip().lower()
    provider = provider_override or default_provider
    mini = provider=='minimax'
    if mini:
        legacy = (default_provider=='minimax'
                  and os.getenv('FAS_AI_MODEL','MiniMax-M3')=='MiniMax-M3'
                  and os.getenv('FAS_AI_BASE_URL','https://api.minimax.io/v1').rstrip('/')=='https://api.minimax.io/v1')
        input_mode = (os.getenv('FAS_MINIMAX_INPUT_MODE') or (os.getenv('FAS_AI_INPUT_MODE') if legacy else None) or 'frames').strip().lower()
        base = (os.getenv('FAS_MINIMAX_BASE_URL') or (os.getenv('FAS_AI_BASE_URL') if legacy else None) or 'https://api.minimax.io/v1').rstrip('/')
        model = os.getenv('FAS_MINIMAX_MODEL') or (os.getenv('FAS_AI_MODEL') if legacy else None) or 'MiniMax-M3'
        key = os.getenv('MINIMAX_API_KEY','') or (os.getenv('FAS_AI_API_KEY','') if legacy else '')
    else:
        input_mode = os.getenv('FAS_AI_INPUT_MODE', 'frames').strip().lower()
        base = os.getenv('FAS_AI_BASE_URL', '').rstrip('/')
        model = os.getenv('FAS_AI_MODEL', '')
        key = os.getenv('FAS_AI_API_KEY', '')
    try:
        parsed = urlsplit(base)
        valid_url = (parsed.scheme == 'https' or (parsed.scheme == 'http' and parsed.hostname in {'localhost','127.0.0.1','::1'})) and bool(parsed.hostname) and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
    except ValueError:
        valid_url = False
    if not valid_url:
        base = ''
    valid_model=not mini or model=='MiniMax-M3'
    return {'enabled': enabled, 'configured': bool(base and model and key and valid_model and (input_mode == 'frames' or mini and input_mode == 'video')),
            'base_url': base, 'model': model, 'key': key, 'provider':provider,
            'input_mode':input_mode,
            'trial_max_duration_s':None,'trial_max_calls':500}


def analysis_config():
    profiles = [config('minimax'),config('openai-compatible')]
    return {'enabled': any(c['enabled'] for c in profiles),
            'configured': any(c['configured'] for c in profiles),
            'available': any(c['enabled'] and c['configured'] for c in profiles)}


def init_schema(conn):
    schema = '''
    CREATE TABLE IF NOT EXISTS analysis_runs (
      id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id),
      session_id TEXT NOT NULL REFERENCES sessions(id), job_id TEXT NOT NULL REFERENCES jobs(id),
      request_key TEXT NOT NULL, config_json TEXT NOT NULL, estimate_json TEXT NOT NULL,
      coverage_json TEXT NOT NULL DEFAULT '[]', actual_usage_json TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL, UNIQUE(media_id,request_key));
    CREATE TABLE IF NOT EXISTS candidates (
      id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES analysis_runs(id),
      media_id TEXT NOT NULL REFERENCES media(id), session_id TEXT NOT NULL REFERENCES sessions(id),
      start_s REAL NOT NULL, end_s REAL NOT NULL, event_type TEXT NOT NULL,
      event_confidence REAL NOT NULL, identity_confidence REAL NOT NULL,
      identity_status TEXT NOT NULL DEFAULT 'uncertain', evidence TEXT NOT NULL,
      identity_evidence TEXT NOT NULL, suggested_description TEXT NOT NULL,
      uncertainty TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS target_references (
      id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
      media_id TEXT NOT NULL REFERENCES media(id), source_time REAL NOT NULL,
      box_normalized TEXT NOT NULL, clothing_notes TEXT NOT NULL,
      local_reference_path TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS analysis_requests (
      run_id TEXT NOT NULL REFERENCES analysis_runs(id), hash TEXT NOT NULL,
      created_at TEXT NOT NULL, PRIMARY KEY(run_id,hash));
    CREATE TABLE IF NOT EXISTS analysis_cache (
      hash TEXT PRIMARY KEY, state TEXT NOT NULL, response_json TEXT,
      usage_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
    '''
    for statement in schema.split(';'):
        if statement.strip():
            conn.execute(statement)
    fields = {r[1] for r in conn.execute('PRAGMA table_info(jobs)')}
    if 'payload_json' not in fields:
        conn.execute("ALTER TABLE jobs ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'")


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    provider: str | None = Field(default=None, pattern='^(minimax|openai-compatible)$')
    request_key: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=120)
    window_s: float = Field(default=12, ge=4, le=60)
    overlap_s: float = Field(default=2, ge=0, le=15)
    frames_per_window: int = Field(default=4, ge=2, le=12)
    max_calls: int = Field(default=100, ge=1, le=500)
    max_cost: float | None = Field(default=None, gt=0, le=1000)
    cost_per_call_upper_bound: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode='after')
    def overlap(self):
        if self.overlap_s >= self.window_s:
            raise ValueError('重叠必须小于窗口')
        if self.max_cost is not None and self.cost_per_call_upper_bound is None:
            raise ValueError('设置费用预算时须填写供应商单次调用费用上限')
        return self


class RetryUnknownInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm_possible_repeat_charge: bool


class ReferenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    media_id: str
    source_time: float = Field(ge=0)
    box_normalized: list[float] = Field(min_length=4, max_length=4)
    clothing_notes: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def box(self):
        x, y, w, h = self.box_normalized
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > 1 or y+h > 1:
            raise ValueError('人物框须为归一化 x,y,width,height，且位于画面内')
        return self


def windows(duration, length=12, overlap=2):
    if not math.isfinite(duration) or duration <= 0 or length <= overlap or overlap < 0:
        raise ValueError('无效扫描范围')
    result, start = [], 0
    while start < duration:
        end = min(duration, start + length)
        result.append((start, end))
        if end == duration:
            break
        start += length-overlap
    return result


def validate_events(payload, start, end):
    if not isinstance(payload, dict) or not isinstance(payload.get('events'), list) or len(payload['events']) > 50:
        raise ValueError('模型响应须包含 events 数组（最多 50 条）')
    result = []
    for raw in payload['events']:
        if not isinstance(raw, dict):
            raise ValueError('无效候选结构')
        a, b = raw.get('start_s'), raw.get('end_s')
        if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in (a,b)) or a >= b:
            raise ValueError('候选时间无效')
        if b <= start or a >= end:
            continue  # Ignore a play entirely outside the supplied frames.
        clipped_a, clipped_b = max(a,start), min(b,end)
        kind = raw.get('event_type')
        if kind not in {'goal','shot','dribble','tackle','other'}:
            raise ValueError('无效事件类型')
        for field in ('event_confidence','identity_confidence'):
            v = raw.get(field)
            if not isinstance(v, (float,int)) or isinstance(v,bool) or not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError('无效置信度')
        for field in ('evidence','identity_evidence','description'):
            if not isinstance(raw.get(field), str) or len(raw[field]) > 2000:
                raise ValueError('无效证据或描述')
        uncertainty = raw.get('uncertainty','')
        if not isinstance(uncertainty,str) or len(uncertainty)>2000:
            raise ValueError('无效不确定性说明')
        if clipped_a != a or clipped_b != b:
            uncertainty = ('模型时间越过分析窗口，已截取窗口内可见部分。' + uncertainty).strip()
        result.append({**raw, 'start_s':clipped_a, 'end_s':clipped_b,
                       'identity_status':'uncertain', 'uncertainty':uncertainty})
    return result


def combine_window_candidates(proposed, verified):
    """Keep evidence from either pass so an initial miss cannot erase a candidate."""
    combined = []
    matched_scan = set()
    for event in verified:
        matches = [index for index, first in enumerate(proposed) if same_play(first,event)]
        matched_scan.update(matches)
        combined.append({**event, 'uncertainty': event['uncertainty'] if matches else
                         ('仅复核发现，初扫漏报。' + event['uncertainty']).strip()})
    for index, event in enumerate(proposed):
        if index not in matched_scan:
            combined.append({**event, 'uncertainty': ('仅初扫发现，复核未确认。' + event['uncertainty']).strip()})
    return combined


def continuous_bounds(start, end, duration, before=2.0, after=3.0):
    """Keep context around a proposed action so the reviewer sees the whole play."""
    return max(0.0, start-before), min(duration, end+after)


def same_play(first, second):
    overlap = max(0.0, min(first['end_s'],second['end_s'])-max(first['start_s'],second['start_s']))
    shorter = min(first['end_s']-first['start_s'],second['end_s']-second['start_s'])
    return shorter > 0 and overlap / shorter >= 0.6


def merge_play(first, second):
    """Keep one candidate for a continuous play seen in multiple passes or windows."""
    rank={'goal':5,'shot':4,'dribble':3,'tackle':2,'other':1}
    primary=max((first,second),key=lambda item:(rank[item['event_type']],item['event_confidence']))
    return {**primary,'start_s':min(first['start_s'],second['start_s']),
            'end_s':max(first['end_s'],second['end_s'])}


def media_for(store, mid, sid=None):
    rows = store.rows('SELECT m.* FROM media m JOIN sessions s ON s.id=m.session_id WHERE m.id=? AND s.deleted=0', (mid,))
    if not rows or (sid is not None and rows[0]['session_id'] != sid):
        raise HTTPException(404, '素材不存在或不属于本场次')
    return rows[0]


def source_path(store, media):
    path = Path(media['path']).resolve()
    allowed = (store.data / 'uploads' if media['managed'] else store.root).resolve()
    if not path.is_relative_to(allowed) or not path.is_file():
        raise ValueError('原片缺失或路径越界')
    return path


def frame_command(path, time_s, dest, box=None):
    filters = 'scale=768:768:force_original_aspect_ratio=decrease'
    if box:
        x,y,w,h = box
        filters = f'crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},' + filters
    return [os.getenv('FFMPEG_BIN','ffmpeg'),'-v','error','-nostdin','-y','-ss',str(time_s),'-i',str(path),'-frames:v','1','-vf',filters,'-threads','1','-q:v','5',str(dest)]


def local_frame(store, media, time_s, box=None):
    with store.cache_lock:
        duration = media['duration']
        if not duration or not math.isfinite(time_s) or not 0 <= time_s < duration:
            raise HTTPException(422,'抽帧时间超出视频范围')
        path = source_path(store,media)
        stat = path.stat()
        digest = hashlib.sha256(json.dumps([media['id'],time_s,box,stat.st_size,stat.st_mtime_ns]).encode()).hexdigest()
        folder=store.data/'derived'/media['id']/'frames'
        folder.mkdir(parents=True,exist_ok=True)
        dest=folder/(digest+'.jpg')
        if not dest.exists():
            tmp=folder/(digest+'.partial.jpg')
            try:
                subprocess.run(frame_command(path,time_s,tmp,box),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)
                if not tmp.exists() or tmp.stat().st_size>600_000:
                    raise RuntimeError('抽帧失败或帧超过大小限制')
                tmp.replace(dest)
            finally:
                tmp.unlink(missing_ok=True)
        return dest


def register_routes(app, store):
    with store.connect() as conn:
        init_schema(conn)

    def session(sid):
        if not store.session(sid):
            raise HTTPException(404,'场次不存在')

    @app.get('/api/analysis/config')
    def get_config():
        def public(c):
            label = ('MiniMax' if c['provider']=='minimax' else
                     'Gemini' if urlsplit(c['base_url']).hostname=='generativelanguage.googleapis.com' else 'OpenAI-compatible')
            return {'enabled':c['enabled'],'configured':c['configured'],'available':c['enabled'] and c['configured'],
                'provider':label,'model':c['model'],'base_url':c['base_url'],
                'input_mode':c['input_mode'],'trial_max_duration_s':c['trial_max_duration_s'],'trial_max_calls':c['trial_max_calls'],
                'missing':['API key'] if not c['key'] else ([] if c['configured'] else ['供应商地址或视频理解模型']),
                'data_sent':('最长边768像素的无声压缩短片和本场次目标参考裁图；不发送原始4K文件' if c['input_mode']=='video' else '分析窗口抽帧和本场次目标参考裁图；不发送原视频'),
                'prompt_version':PROMPT_VERSION,'confidence_calibrated':False}
        profiles={'minimax':public(config('minimax')),
                  'openai-compatible':public(config('openai-compatible'))}
        return {**public(config()),'available':any(p['available'] for p in profiles.values()),'profiles':profiles}

    @app.get('/api/media/{mid}/frame')
    def get_frame(mid: str, time_s: float=0):
        # Materialize the small frame while protected; response sending outlives the lock.
        with store.cache_lock:
            path=local_frame(store,media_for(store,mid),time_s)
            return Response(path.read_bytes(),media_type='image/jpeg')

    @app.get('/api/sessions/{sid}/target-references')
    def refs(sid: str):
        session(sid)
        rows=store.rows('SELECT id,session_id,media_id,source_time,box_normalized,clothing_notes,created_at FROM target_references WHERE session_id=? ORDER BY created_at',(sid,))
        for row in rows:
            row['box_normalized']=json.loads(row['box_normalized'])
        return rows

    @app.post('/api/sessions/{sid}/target-references',status_code=201)
    def add_ref(sid: str, body: ReferenceInput):
        # Always acquire the cache lock before opening a database transaction.
        with store.cache_lock:
            session(sid)
            media=media_for(store,body.media_id,sid)
            if len(store.rows('SELECT id FROM target_references WHERE session_id=?',(sid,))) >= 8:
                raise HTTPException(422,'每场次最多 8 张目标参考')
            path=local_frame(store,media,body.source_time,body.box_normalized)
            rid=uuid4().hex
            with store.connect() as conn:
                conn.execute('INSERT INTO target_references VALUES(?,?,?,?,?,?,?,?)',(rid,sid,body.media_id,body.source_time,json.dumps(body.box_normalized),body.clothing_notes,str(path),now()))
            return next(row for row in refs(sid) if row['id']==rid)

    @app.delete('/api/sessions/{sid}/target-references/{rid}')
    def delete_ref(sid: str, rid: str):
        session(sid)
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            active=conn.execute('''SELECT 1 FROM jobs j JOIN media m ON m.id=j.media_id
                WHERE m.session_id=? AND j.type IN ('analysis','badminton_analysis')
                AND j.status IN ('queued','running') LIMIT 1''',(sid,)).fetchone()
            if active:
                raise HTTPException(409,'本场次正在分析，请等待完成或取消后再删除目标参考')
            deleted=conn.execute('DELETE FROM target_references WHERE id=? AND session_id=?',(rid,sid))
            if not deleted.rowcount:
                raise HTTPException(404,'目标参考不存在')
        return {'remaining':refs(sid)}

    @app.get('/api/media/{mid}/analyses')
    def runs(mid: str):
        media=media_for(store,mid)
        if store.session(media['session_id'])['sport'] != 'football':
            raise HTTPException(422,'此素材不属于足球场次')
        rows=store.rows("""SELECT a.*,j.status,j.stage,j.progress,j.error,
            (SELECT COUNT(*) FROM analysis_requests r JOIN analysis_cache c ON c.hash=r.hash
             WHERE r.run_id=a.id AND c.state='pending') AS unknown_count
            FROM analysis_runs a JOIN jobs j ON j.id=a.job_id
            WHERE a.media_id=? AND j.type='analysis' ORDER BY a.created_at DESC""",(mid,))
        for row in rows:
            for k in ('config','estimate','coverage','actual_usage'):
                row[k]=json.loads(row.pop(k+'_json'))
        return rows

    @app.post('/api/media/{mid}/analyses',status_code=202)
    def start(mid: str, body: AnalysisInput):
        media=media_for(store,mid)
        if store.session(media['session_id'])['sport'] != 'football':
            raise HTTPException(422,'此素材不属于足球场次')
        if not store.rows('SELECT id FROM target_references WHERE session_id=? LIMIT 1',(media['session_id'],)):
            raise HTTPException(409,'请先为本场次保存目标人物，再生成候选片段')
        c=config(body.provider)
        if not c['enabled'] or not c['configured']:
            raise HTTPException(409,'未运行 AI 分析：请配置供应商并显式设置 FAS_AI_ENABLED=true')
        existing=store.rows('SELECT id,job_id FROM analysis_runs WHERE media_id=? AND request_key=?',(mid,body.request_key))
        if existing:
            return existing[0]
        completed=store.rows("SELECT id FROM jobs WHERE media_id=? AND type='preprocess' AND status='succeeded'",(mid,))
        if not media['duration'] or not completed:
            raise HTTPException(409,'请先完成素材预处理')
        spans=windows(media['duration'],body.window_s,body.overlap_s)
        # Reserve one scan and one review call for every window, including empty scans.
        estimate={'scan_calls':len(spans),'max_calls':body.max_calls,'input_mode':c['input_mode'],
                  'frame_count':len(spans)*body.frames_per_window if c['input_mode']=='frames' else None,
                  'video_seconds':sum(b-a for a,b in spans) if c['input_mode']=='video' else None,
                  'estimated_cost_upper_bound':body.max_calls*body.cost_per_call_upper_bound if body.cost_per_call_upper_bound else None}
        if len(spans)*2>body.max_calls:
            raise HTTPException(422,'调用预算不足以完整扫描并预留逐窗口验证，请提高 max_calls 或加大 window_s')
        if body.max_cost is not None and estimate['estimated_cost_upper_bound']>body.max_cost:
            raise HTTPException(422,'预计费用上限超过预算')
        rid,jid=uuid4().hex,uuid4().hex
        frozen={**body.model_dump(),'model':c['model'],'base_url':c['base_url'],'prompt_version':PROMPT_VERSION,
                'provider':c['provider'],'input_mode':c['input_mode'],'media_duration':media['duration']}
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing=conn.execute('SELECT id,job_id FROM analysis_runs WHERE media_id=? AND request_key=?',(mid,body.request_key)).fetchone()
            if existing:
                return dict(existing)
            conn.execute('INSERT INTO jobs(id,media_id,type,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',(jid,mid,'analysis',json.dumps({'run_id':rid}),now(),now()))
            conn.execute('INSERT INTO analysis_runs(id,media_id,session_id,job_id,request_key,config_json,estimate_json,created_at) VALUES(?,?,?,?,?,?,?,?)',(rid,mid,media['session_id'],jid,body.request_key,json.dumps(frozen),json.dumps(estimate),now()))
        return {'id':rid,'run_id':rid,'job_id':jid,'estimate':estimate}

    @app.post('/api/analysis-runs/{rid}/retry-unknown',status_code=202)
    def retry_unknown(rid: str, body: RetryUnknownInput):
        if not body.confirm_possible_repeat_charge:
            raise HTTPException(422,'请确认可能重复计费后再重新发送')
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute("""SELECT a.*,j.status FROM analysis_runs a
                JOIN jobs j ON j.id=a.job_id JOIN sessions s ON s.id=a.session_id
                WHERE a.id=? AND j.type='analysis' AND s.deleted=0""",(rid,)).fetchone()
            if not row:
                raise HTTPException(404,'分析任务不存在')
            if row['status']!='failed':
                raise HTTPException(409,'只能重新发送失败任务中的未确认请求')
            old=json.loads(row['config_json'])
            c=config(old.get('provider'))
            if not c['enabled'] or not c['configured']:
                raise HTTPException(409,'当前 AI 供应商尚未启用')
            if any(old.get(key)!=c[key] for key in ('provider','model','base_url','input_mode')) or old.get('prompt_version')!=PROMPT_VERSION:
                raise HTTPException(409,'供应商或分析配置已改变，请先恢复原配置')
            hashes=[item['hash'] for item in conn.execute("""SELECT r.hash FROM analysis_requests r
                JOIN analysis_cache c ON c.hash=r.hash WHERE r.run_id=? AND c.state='pending'""",(rid,))]
            if not hashes:
                raise HTTPException(409,'这次任务没有未确认请求')
            for hash_value in hashes:
                active=conn.execute("""SELECT 1 FROM analysis_requests r JOIN analysis_runs a ON a.id=r.run_id
                    JOIN jobs j ON j.id=a.job_id WHERE r.hash=? AND r.run_id!=?
                    AND j.status IN ('queued','running') LIMIT 1""",(hash_value,rid)).fetchone()
                if active:
                    raise HTTPException(409,'其他任务正在使用同一请求，请稍后再试')
            for hash_value in hashes:
                conn.execute("DELETE FROM analysis_cache WHERE hash=? AND state='pending'",(hash_value,))
            new_rid,new_jid,new_key=uuid4().hex,uuid4().hex,uuid4().hex
            old['request_key']=new_key
            stamp=now()
            conn.execute('INSERT INTO jobs(id,media_id,type,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                         (new_jid,row['media_id'],'analysis',json.dumps({'run_id':new_rid}),stamp,stamp))
            conn.execute('INSERT INTO analysis_runs(id,media_id,session_id,job_id,request_key,config_json,estimate_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
                         (new_rid,row['media_id'],row['session_id'],new_jid,new_key,json.dumps(old),row['estimate_json'],stamp))
            conn.execute("UPDATE jobs SET stage='未确认请求已显式重新发送',updated_at=? WHERE id=?",(stamp,row['job_id']))
        return {'id':new_rid,'run_id':new_rid,'job_id':new_jid,'replayed_unknown_requests':len(hashes)}

    @app.get('/api/sessions/{sid}/candidates')
    def candidates(sid: str, limit: int=200, offset: int=0):
        session(sid)
        if not 1<=limit<=500 or offset<0:
            raise HTTPException(422,'无效分页')
        return store.rows('''SELECT c.* FROM candidates c JOIN analysis_runs a ON a.id=c.run_id
            JOIN jobs j ON j.id=a.job_id WHERE c.session_id=? AND j.status='succeeded'
            AND a.id=(SELECT a2.id FROM analysis_runs a2 JOIN jobs j2 ON j2.id=a2.job_id
                WHERE a2.media_id=c.media_id AND j2.status='succeeded'
                ORDER BY a2.created_at DESC LIMIT 1)
            ORDER BY c.media_id,c.start_s,c.end_s LIMIT ? OFFSET ?''',(sid,limit,offset))


def _hash_source(worker, path, jid):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(4*1024*1024):
            worker.check(jid)
            digest.update(chunk)
    return digest.hexdigest()


def _provider_call(c, content, key, check=None):
    # Async transport allows worker cancellation to abort an in-flight request.
    # No automatic retry: a timeout can mean the provider charged the request.
    is_gemini = urlsplit(c['base_url']).hostname == 'generativelanguage.googleapis.com'
    read_timeout = 180 if is_gemini else 240 if c.get('provider')=='minimax' else 60
    async def send():
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10,read=read_timeout,write=60,pool=10),follow_redirects=False) as client:
            async with client.stream('POST',c['base_url']+'/chat/completions',
                    headers={'Authorization':'Bearer '+c['key'],'Idempotency-Key':key},
                    json=request_payload(c,content)) as response:
                if response.status_code>=400:
                    if response.status_code==401:
                        if c['provider']=='minimax':
                            raise RuntimeError('MiniMax 拒绝了当前密钥（HTTP 401）。请在本机 .env 更新 MINIMAX_API_KEY，确认使用与账号区域一致的密钥，然后重启工作台；本次请求未通过鉴权。')
                        raise RuntimeError('AI 供应商拒绝了当前密钥（HTTP 401）。请检查本机 .env 中该供应商的 API key，更新后重启工作台；本次请求未通过鉴权。')
                    if is_gemini and response.status_code==503:
                        raise RuntimeError('Gemini 服务暂时不可用或繁忙（HTTP 503）；请等待几分钟后再手动重试。请求结果未确认，系统不会自动重发')
                    raise RuntimeError(f'AI 供应商返回 HTTP {response.status_code}，未记录响应正文')
                data=bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data)>256_000:
                        raise RuntimeError('模型响应超过限制')
                return data

    async def cancellable():
        task=asyncio.create_task(send())
        try:
            while not task.done():
                if check:
                    check()
                await asyncio.wait({task},timeout=.25)
            if check:
                check()
            return await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task,return_exceptions=True)
    try:
        value=json.loads(asyncio.run(cancellable()))
        usage=value.get('usage',{})
        usage={k:v for k,v in usage.items() if k in {'prompt_tokens','completion_tokens','total_tokens'} and isinstance(v,(int,float))} if isinstance(usage,dict) else {}
        return parse_response(value),usage
    except httpx.TimeoutException as exc:
        raise RuntimeError(f'AI 响应超时（等待上限 {read_timeout} 秒，{type(exc).__name__}）；请求结果未确认，本窗口不会自动重发') from None
    except (httpx.HTTPError,KeyError,IndexError,TypeError,json.JSONDecodeError) as exc:
        raise RuntimeError(f'AI 请求失败或响应无效（{type(exc).__name__}）；请求结果未确认，本窗口不会自动重发') from None


def analyze(worker, job):
    store,jid=worker.store,job['id']
    rid=json.loads(job['payload_json'])['run_id']
    run=store.rows('SELECT * FROM analysis_runs WHERE id=?',(rid,))[0]
    cfg=json.loads(run['config_json'])
    c=config(cfg.get('provider'))
    if not c['enabled'] or not c['configured']:
        raise RuntimeError('AI 分析未显式启用或未配置')
    if any(cfg[k]!=c[k] for k in ('model','base_url')) or cfg['prompt_version']!=PROMPT_VERSION:
        raise RuntimeError('模型配置已变更，请新建分析任务')
    if cfg.get('provider','openai-compatible')!=c['provider'] or cfg.get('input_mode','frames')!=c['input_mode']:
        raise RuntimeError('分析供应商或发送范围已变更，请新建任务')
    media=media_for(store,job['media_id'])
    path=source_path(store,media)
    worker.update(jid,stage='计算本地内容校验和',progress=1)
    signature=_hash_source(worker,path,jid)
    refs=store.rows('SELECT * FROM target_references WHERE session_id=? ORDER BY id',(media['session_id'],))
    reference_content=[]
    for ref in refs:
        p=Path(ref['local_reference_path']).resolve()
        if not p.is_relative_to((store.data/'derived').resolve()) or not p.is_file() or p.stat().st_size>600_000:
            raise RuntimeError('本地参考图缺失或无效')
        reference_content.extend([{'type':'text','text':'Target reference, tentative only: '+ref['clothing_notes']},
                                  {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(p.read_bytes()).decode(),'detail':'low'}}])
    refs_hash=hashlib.sha256(json.dumps(reference_content,sort_keys=True).encode()).hexdigest()
    folder=store.data/'derived'/media['id']/'analysis'
    folder.mkdir(parents=True,exist_ok=True)
    spans=windows(media['duration'],cfg['window_s'],cfg['overlap_s'])
    usage=[]
    calls=0

    def request(a,b,phase):
        nonlocal calls
        key=hashlib.sha256(json.dumps([signature,{k:v for k,v in cfg.items() if k not in {'request_key','max_calls','max_cost','cost_per_call_upper_bound'}},refs_hash,a,b,phase],sort_keys=True).encode()).hexdigest()
        cached=store.rows('SELECT * FROM analysis_cache WHERE hash=?',(key,))
        if cached:
            if cached[0]['state']!='succeeded':
                raise RuntimeError('此窗口上次请求结果未确认；为避免重复费用已停止，请核对供应商账单后由管理员处理本地请求缓存')
            payload=json.loads(cached[0]['response_json'])
            usage.append({'cached':True,'usage':json.loads(cached[0]['usage_json'])})
            return validate_events(payload,a,b)
        if calls>=cfg['max_calls']:
            raise RuntimeError('已达到本次分析调用预算')
        content=[{'type':'text','text':PROMPT+f'\n{phase}. Window [{a},{b}] absolute seconds.'},*reference_content]
        count=cfg['frames_per_window'] if phase=='scan' else min(12,cfg['frames_per_window']*2)
        if cfg.get('input_mode')=='video':
            content+=video_content(worker,path,a,b,phase,jid,folder)
        for i in range(count if cfg.get('input_mode','frames')=='frames' else 0):
            worker.check(jid)
            t=a+(b-a)*(i+.5)/count
            frame=folder/f'{key}-{i}.jpg'
            output=folder/'frame.log'
            try:
                worker.run(frame_command(path,t,frame),jid,output)
                if not frame.exists() or frame.stat().st_size>600_000:
                    raise RuntimeError('分析帧过大或未生成')
                content.extend([{'type':'text','text':f'Source time {t:.4f} seconds'}, {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(frame.read_bytes()).decode(),'detail':'low'}}])
            finally:
                frame.unlink(missing_ok=True)
                output.unlink(missing_ok=True)
                Path(str(output)+'.err').unlink(missing_ok=True)
        worker.check(jid)
        # Persist before I/O. Ambiguous transport failure must never trigger a blind billable retry.
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            spent=conn.execute('SELECT count(*) FROM analysis_requests WHERE run_id=?',(rid,)).fetchone()[0]
            if spent>=cfg['max_calls']:
                raise RuntimeError('已达到本次分析调用预算（包含此前尝试）')
            conn.execute('INSERT INTO analysis_requests(run_id,hash,created_at) VALUES(?,?,?)',(rid,key,now()))
            conn.execute('INSERT INTO analysis_cache(hash,state,created_at) VALUES(?,?,?)',(key,'pending',now()))
        calls+=1
        payload,used=_provider_call(c,content,key,lambda: worker.check(jid))
        validated=validate_events(payload,a,b)
        with store.connect() as conn:
            conn.execute("UPDATE analysis_cache SET state='succeeded',response_json=?,usage_json=? WHERE hash=?",(json.dumps(payload),json.dumps(used),key))
        usage.append({'cached':False,'usage':used})
        worker.check(jid)
        return validated

    coverage=[]
    accepted=[]
    for index,(a,b) in enumerate(spans):
        worker.check(jid)
        worker.update(jid,stage=f'扫描源视频 {a:.1f}–{b:.1f} 秒',progress=5+90*index/len(spans))
        proposed=request(a,b,'scan')
        # Run the reserved second pass even when the first pass reports nothing.
        verified=request(a,b,'verify')
        for event in combine_window_candidates(proposed, verified):
            match=next((i for i,existing in enumerate(accepted) if same_play(existing,event)),None)
            if match is None:
                accepted.append(event)
            else:
                accepted[match]=merge_play(accepted[match],event)
        coverage.append({'start_s':a,'end_s':b,'scanned':True,'verified':True})
        with store.connect() as conn:
            conn.execute('UPDATE analysis_runs SET coverage_json=?,actual_usage_json=? WHERE id=?',(json.dumps(coverage),json.dumps(usage),rid))
    worker.check(jid)
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        state=conn.execute('SELECT j.cancel_requested,s.deleted FROM jobs j JOIN media m ON m.id=j.media_id JOIN sessions s ON s.id=m.session_id WHERE j.id=?',(jid,)).fetchone()
        if not state or state['cancel_requested'] or state['deleted']:
            from .worker import Cancelled
            raise Cancelled()
        worker.check(jid)
        # Same-run retry replaces only unpublished machine candidates; human reviews are separate.
        # IDs are deterministic, so successful retry never duplicates candidates.
        for event in accepted:
            cid=hashlib.sha256(json.dumps([rid,event['start_s'],event['end_s'],event['event_type']]).encode()).hexdigest()
            clip_start, clip_end = continuous_bounds(event['start_s'],event['end_s'],media['duration'])
            conn.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (cid,rid,media['id'],media['session_id'],clip_start,clip_end,event['event_type'],event['event_confidence'],event['identity_confidence'],'uncertain',event['evidence'],event['identity_evidence'],event['description'],event['uncertainty'],now()))
        conn.execute("UPDATE jobs SET status='succeeded',stage=?,progress=100,error=NULL,updated_at=? WHERE id=?",('AI 候选扫描完成，等待人工审核',now(),jid))
