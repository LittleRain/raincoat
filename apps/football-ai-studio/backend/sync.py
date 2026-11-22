"""Human-established source/session clock mappings and reversible camera grouping."""
import json
from uuid import uuid4
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, AliasChoices
from .analysis import media_for
from .core import now


def init_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS sync_mappings (
       id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
       media_id TEXT NOT NULL REFERENCES media(id), offset_s REAL NOT NULL,
       drift_ratio REAL NOT NULL, confidence REAL, method TEXT NOT NULL,
       verification_status TEXT NOT NULL, anchor_pairs TEXT NOT NULL,
       updated_at TEXT NOT NULL, UNIQUE(session_id,media_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS event_groups (
       id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
       match_confidence REAL, status TEXT NOT NULL, review_event_ids TEXT NOT NULL,
       created_at TEXT NOT NULL, description TEXT NOT NULL DEFAULT '')''')


class Anchor(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    source_time: float=Field(ge=0)
    session_time: float=Field(ge=-1e7,le=1e7)


class MappingInput(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    media_id: str
    offset_s: float=Field(default=0,ge=-1e7,le=1e7)
    drift_ratio: float=Field(default=1,ge=.9,le=1.1)
    anchors: list[Anchor]=Field(default_factory=list,max_length=20)
    anchor_pairs: list[tuple[float,float]]=Field(default_factory=list,max_length=20)
    verification_status: str='manual'


class MappingsInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mappings: list[MappingInput]=Field(max_length=200)


class GroupInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    review_event_ids: list[str]=Field(min_length=2,max_length=8,validation_alias=AliasChoices('event_ids','review_event_ids'))
    description: str=Field(default='',max_length=1000)


def register_routes(app,store):
    with store.connect() as conn:
        init_schema(conn)

    def require_session(sid):
        if not store.session(sid):
            raise HTTPException(404,'场次不存在')

    def mappings(sid):
        require_session(sid)
        rows=store.rows('SELECT * FROM sync_mappings WHERE session_id=? ORDER BY updated_at',(sid,))
        for row in rows:
            row['anchors']=json.loads(row.pop('anchor_pairs'))
        return rows

    app.get('/api/sessions/{sid}/sync-mappings')(mappings)

    @app.get('/api/sessions/{sid}/sync')
    def sync_get(sid: str):
        result=mappings(sid)
        for row in result:
            row['anchor_pairs']=[[a['source_time'],a['session_time']] for a in row['anchors']]
        return {'mappings':result}

    @app.put('/api/sessions/{sid}/sync')
    def sync_put(sid: str,body: MappingsInput):
        require_session(sid)
        if len({m.media_id for m in body.mappings})!=len(body.mappings):
            raise HTTPException(422,'同一素材不能重复同步映射')
        prepared=[prepare_mapping(sid,m) for m in body.mappings]
        with store.connect() as conn:
            for item in prepared:
                write_mapping(conn,item)
        return sync_get(sid)

    def prepare_mapping(sid,body):
        require_session(sid)
        media=media_for(store,body.media_id,sid)
        if body.verification_status!='manual':
            raise HTTPException(422,'此接口仅支持人工同步')
        if body.anchors and body.anchor_pairs:
            raise HTTPException(422,'请只提供一种锚点格式')
        if any(a<0 or abs(b)>1e7 for a,b in body.anchor_pairs):
            raise HTTPException(422,'无效同步锚点范围')
        anchors=body.anchors or [Anchor(source_time=a,session_time=b) for a,b in body.anchor_pairs]
        offset,drift=body.offset_s,body.drift_ratio
        if anchors:
            if not media['duration'] or any(a.source_time>media['duration'] for a in anchors):
                raise HTTPException(422,'同步锚点超出素材范围')
            xs=[a.source_time for a in anchors]
            ys=[a.session_time for a in anchors]
            if len(xs)==1:
                drift=1
                offset=ys[0]-xs[0]
            else:
                if len(set(xs))!=len(xs):
                    raise HTTPException(422,'源视频锚点不能重复')
                xmean,ymean=sum(xs)/len(xs),sum(ys)/len(ys)
                drift=sum((x-xmean)*(y-ymean) for x,y in zip(xs,ys))/sum((x-xmean)**2 for x in xs)
                offset=ymean-drift*xmean
                if not .9<=drift<=1.1:
                    raise HTTPException(422,'锚点时钟比例超出 0.9–1.1，请核对配对')
                if max(abs(offset+x*drift-y) for x,y in zip(xs,ys))>1:
                    raise HTTPException(422,'锚点拟合误差超过 1 秒，请检查配对')
        return (uuid4().hex,sid,body.media_id,offset,drift,None,'manual_anchors' if anchors else 'manual_offset',
                'manual',json.dumps([a.model_dump() for a in anchors]),now())

    def write_mapping(conn,item):
        conn.execute('''INSERT INTO sync_mappings VALUES(?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(session_id,media_id) DO UPDATE SET offset_s=excluded.offset_s,
              drift_ratio=excluded.drift_ratio,method=excluded.method,verification_status=excluded.verification_status,
              anchor_pairs=excluded.anchor_pairs,updated_at=excluded.updated_at''',item)

    @app.put('/api/sessions/{sid}/sync-mappings')
    def save_mapping(sid: str,body: MappingInput):
        prepared=prepare_mapping(sid,body)
        with store.connect() as conn:
            write_mapping(conn,prepared)
        return next(row for row in mappings(sid) if row['media_id']==body.media_id)

    def groups(sid):
        require_session(sid)
        rows=store.rows('SELECT * FROM event_groups WHERE session_id=? ORDER BY created_at',(sid,))
        for row in rows:
            row['review_event_ids']=json.loads(row['review_event_ids'])
            row['event_ids']=row['review_event_ids']
        return rows

    app.get('/api/sessions/{sid}/event-groups')(groups)

    @app.post('/api/sessions/{sid}/event-groups',status_code=201)
    def add_group(sid: str,body: GroupInput):
        require_session(sid)
        ids=body.review_event_ids
        if len(set(ids))!=len(ids):
            raise HTTPException(422,'机位关联不能重复引用同一事件')
        marks=','.join('?' for _ in ids)
        rows=store.rows('SELECT id,session_id,media_id FROM review_events WHERE id IN ('+marks+')',ids)
        if len(rows)!=len(ids) or any(row['session_id']!=sid for row in rows):
            raise HTTPException(404,'审核事件不存在或不属于本场次')
        if len({r['media_id'] for r in rows})!=len(ids):
            raise HTTPException(422,'机位关联须来自不同素材')
        # Stable explicit sets are idempotent, and undo only removes this association.
        for row in groups(sid):
            if set(row['review_event_ids'])==set(ids):
                return row
        gid=uuid4().hex
        with store.connect() as conn:
            conn.execute('INSERT INTO event_groups(id,session_id,match_confidence,status,review_event_ids,created_at,description) VALUES(?,?,?,?,?,?,?)',(gid,sid,None,'manual',json.dumps(ids),now(),body.description))
        return next(row for row in groups(sid) if row['id']==gid)

    @app.delete('/api/event-groups/{gid}')
    def delete_group(gid: str):
        rows=store.rows('SELECT session_id FROM event_groups WHERE id=?',(gid,))
        if not rows:
            raise HTTPException(404,'机位关联不存在')
        require_session(rows[0]['session_id'])
        with store.connect() as conn:
            conn.execute('DELETE FROM event_groups WHERE id=?',(gid,))
        return {'deleted':True}
