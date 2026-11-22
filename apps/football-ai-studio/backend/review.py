"""Human review is the authoritative edit list, independent from analysis runs."""
import json
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .core import now

EventType = Literal['goal', 'shot', 'dribble', 'tackle', 'other']
Identity = Literal['confirmed_target', 'confirmed_other', 'uncertain']
Decision = Literal['pending', 'keep', 'discard']
SegmentKind = Literal['training', 'match', 'rally', 'unknown']


def init_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS review_events (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
        media_id TEXT NOT NULL REFERENCES media(id), candidate_id TEXT,
        start_s REAL NOT NULL, end_s REAL NOT NULL, event_type TEXT NOT NULL,
        identity_status TEXT NOT NULL, decision TEXT NOT NULL, description TEXT NOT NULL,
        effects_json TEXT NOT NULL, segment_kind TEXT NOT NULL DEFAULT 'unknown',
        highlight INTEGER NOT NULL DEFAULT 0, position INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    columns = {row[1] for row in conn.execute('PRAGMA table_info(review_events)')}
    if 'segment_kind' not in columns:
        conn.execute("ALTER TABLE review_events ADD COLUMN segment_kind TEXT NOT NULL DEFAULT 'unknown'")
    if 'highlight' not in columns:
        conn.execute('ALTER TABLE review_events ADD COLUMN highlight INTEGER NOT NULL DEFAULT 0')
    conn.execute('CREATE INDEX IF NOT EXISTS review_session ON review_events(session_id,position)')
    conn.execute('''CREATE TABLE IF NOT EXISTS exports (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
        job_id TEXT NOT NULL REFERENCES jobs(id), request_key TEXT,
        settings_json TEXT NOT NULL, snapshot_json TEXT NOT NULL,
        output_path TEXT, duration REAL, created_at TEXT NOT NULL,
        UNIQUE(session_id,request_key))''')


class Effects(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    speed: Literal[0.5, 1] = 1
    caption: bool = True
    focus_box: list[float] | None = Field(default=None, min_length=4, max_length=4)
    focus_start_s: float | None = Field(default=None, ge=0)
    focus_end_s: float | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def box(self):
        if self.focus_box is not None:
            x,y,w,h=self.focus_box
            if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1 and x+w <= 1.000001 and y+h <= 1.000001):
                raise ValueError('人物框选必须在归一化画面内')
        if (self.focus_start_s is None) != (self.focus_end_s is None):
            raise ValueError('人物提示需要完整的起止时间')
        if self.focus_start_s is not None and self.focus_start_s >= self.focus_end_s:
            raise ValueError('人物提示结束时间必须晚于开始时间')
        return self


class EventInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    media_id: str
    candidate_id: str | None = None
    start_s: float = Field(ge=0)
    end_s: float = Field(gt=0)
    event_type: EventType = 'other'
    identity_status: Identity = 'uncertain'
    decision: Decision = 'pending'
    description: str = Field(default='', max_length=500)
    segment_kind: SegmentKind = 'unknown'
    highlight: bool = False
    effects: Effects = Field(default_factory=Effects)


class EventPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    version: int = Field(ge=1)
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, gt=0)
    event_type: EventType | None = None
    identity_status: Identity | None = None
    decision: Decision | None = None
    description: str | None = Field(default=None, max_length=500)
    segment_kind: SegmentKind | None = None
    highlight: bool | None = None
    effects: Effects | None = None


class TimelineInput(BaseModel):
    event_ids: list[str] = Field(max_length=1000)


def session_or_404(store, sid):
    session=store.session(sid)
    if not session:
        raise HTTPException(404, '场次不存在')
    return session


def serialize(row):
    item=dict(row)
    item['effects']=json.loads(item.pop('effects_json'))
    item['highlight']=bool(item['highlight'])
    return item


def validate_event(conn, sid, body):
    media=conn.execute("SELECT m.*,j.status FROM media m JOIN jobs j ON j.media_id=m.id AND j.type='preprocess' WHERE m.id=? AND m.session_id=?", (body['media_id'],sid)).fetchone()
    if not media or media['status'] != 'succeeded' or not media['duration']:
        raise HTTPException(422, '请选择本场次已完成预处理的视频')
    if not (0 <= body['start_s'] < body['end_s'] <= media['duration']):
        raise HTTPException(422, '片段范围必须在视频时长内，结束时间应晚于开始时间')
    effects=Effects.model_validate(body['effects']).model_dump()
    if effects['focus_start_s'] is not None and not (body['start_s'] <= effects['focus_start_s'] < effects['focus_end_s'] <= body['end_s']):
        raise HTTPException(422, '人物提示时间必须位于片段内')
    return media


def register_routes(app, store):
    # Existing v2 databases also need the new review labels.
    with store.connect() as conn:
        init_schema(conn)

    @app.get('/api/sessions/{sid}/review-events')
    def events(sid: str):
        session_or_404(store,sid)
        return [serialize(r) for r in store.rows('SELECT * FROM review_events WHERE session_id=? ORDER BY position,created_at,id',(sid,))]

    @app.post('/api/sessions/{sid}/review-events', status_code=201)
    def create(sid: str, body: EventInput):
        session_or_404(store,sid)
        data=body.model_dump()
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            validate_event(conn,sid,data)
            if body.candidate_id:
                candidate=conn.execute('SELECT * FROM candidates WHERE id=? AND media_id=?',(body.candidate_id,body.media_id)).fetchone()
                if not candidate:
                    raise HTTPException(422,'候选不属于此视频')
                existing=conn.execute('SELECT * FROM review_events WHERE session_id=? AND candidate_id=?',(sid,body.candidate_id)).fetchone()
                if existing:
                    return serialize(existing)
            position=conn.execute('SELECT coalesce(max(position),-1)+1 FROM review_events WHERE session_id=?',(sid,)).fetchone()[0]
            eid,stamp=uuid4().hex,now()
            conn.execute('''INSERT INTO review_events(id,session_id,media_id,candidate_id,start_s,end_s,event_type,
                identity_status,decision,description,effects_json,segment_kind,highlight,position,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (eid,sid,body.media_id,body.candidate_id,body.start_s,body.end_s,body.event_type,body.identity_status,
                 body.decision,body.description,json.dumps(data['effects'],ensure_ascii=False),body.segment_kind,int(body.highlight),position,stamp,stamp))
            return serialize(conn.execute('SELECT * FROM review_events WHERE id=?',(eid,)).fetchone())

    @app.patch('/api/review-events/{eid}')
    def edit(eid: str, body: EventPatch):
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT e.* FROM review_events e JOIN sessions s ON s.id=e.session_id WHERE e.id=? AND s.deleted=0',(eid,)).fetchone()
            if not row:
                raise HTTPException(404,'片段不存在')
            if row['version'] != body.version:
                raise HTTPException(409,'片段已被修改，请重新载入后再保存')
            changes=body.model_dump(exclude_unset=True,exclude={'version'})
            if any(v is None for v in changes.values()):
                raise HTTPException(422,'编辑字段不能为空')
            data=serialize(row); data.update(changes)
            validate_event(conn,row['session_id'],data)
            conn.execute('''UPDATE review_events SET start_s=?,end_s=?,event_type=?,identity_status=?,decision=?,description=?,
                effects_json=?,segment_kind=?,highlight=?,version=version+1,updated_at=? WHERE id=?''',
                (data['start_s'],data['end_s'],data['event_type'],data['identity_status'],data['decision'],data['description'],
                 json.dumps(data['effects'],ensure_ascii=False),data['segment_kind'],int(data['highlight']),now(),eid))
            return serialize(conn.execute('SELECT * FROM review_events WHERE id=?',(eid,)).fetchone())

    @app.get('/api/sessions/{sid}/chatcut-handoff')
    def chatcut_handoff(sid: str, include_uncertain: bool = False, mode: Literal['activity','person'] = 'person', target_count: int | None = None):
        session = session_or_404(store,sid)
        from .analysis import source_path
        badminton_activity = session['sport'] == 'badminton' and mode == 'activity'
        approved = [row for row in events(sid) if row['decision'] == 'keep' and
                    (badminton_activity or row['identity_status'] == 'confirmed_target' or
                     session['sport'] == 'football' and include_uncertain and row['identity_status'] == 'uncertain')]
        if not approved:
            raise HTTPException(422, '没有已保留且人物已确认的片段')
        if target_count is not None and (target_count < 1 or len(approved) != target_count):
            raise HTTPException(422, '已保留片段数与设定数量不一致')
        media_ids = {row['media_id'] for row in approved}
        media = {row['id']: row for row in store.rows('SELECT * FROM media WHERE session_id=?',(sid,)) if row['id'] in media_ids}
        sources = []
        for mid in sorted(media_ids):
            item = media[mid]
            try:
                path = source_path(store,item)
            except ValueError as exc:
                raise HTTPException(409,str(exc)) from exc
            sources.append({'id':mid,'name':item['name'],'path':str(path)})
        references = store.rows('SELECT clothing_notes FROM target_references WHERE session_id=? ORDER BY created_at',(sid,))
        return {'schema_version':1,'sport':session['sport'],'session_id':sid,'session_name':session['name'],
                'mode':mode if session['sport']=='badminton' else 'person',
                'target_description':'；'.join(row['clothing_notes'] for row in references if row['clothing_notes']),
                'sources':sources,'segments':[{'id':row['id'],'source_id':row['media_id'],
                'start_s':row['start_s'],'end_s':row['end_s'],'segment_kind':row['segment_kind'],
                'highlight':row['highlight'],'action':row['event_type'],'identity_status':row['identity_status'],
                'note':row['description']} for row in approved]}

    @app.delete('/api/review-events/{eid}')
    def delete(eid: str, version: int):
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT e.* FROM review_events e JOIN sessions s ON s.id=e.session_id WHERE e.id=? AND s.deleted=0',(eid,)).fetchone()
            if not row:
                raise HTTPException(404,'片段不存在')
            if row['version'] != version:
                raise HTTPException(409,'片段已修改，请重新载入')
            conn.execute('DELETE FROM review_events WHERE id=?',(eid,))
        return {'deleted':True}

    @app.put('/api/sessions/{sid}/timeline')
    def timeline(sid: str, body: TimelineInput):
        session_or_404(store,sid)
        with store.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current={r[0] for r in conn.execute('SELECT id FROM review_events WHERE session_id=?',(sid,))}
            if len(body.event_ids)!=len(set(body.event_ids)) or set(body.event_ids)!=current:
                raise HTTPException(409,'片段列表已变化，请刷新后重新排序')
            for position,eid in enumerate(body.event_ids):
                conn.execute('UPDATE review_events SET position=?,updated_at=? WHERE id=?',(position,now(),eid))
        return events(sid)
