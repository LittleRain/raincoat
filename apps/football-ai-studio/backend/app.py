import asyncio
import os
import shutil
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .core import BASE, EXTENSIONS, Store, now
from .worker import Worker


class SessionInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    date: date


class RegisterInput(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    source: Literal['gopro', 'iphone', 'other'] = 'gopro'


def create_app(store=None, run_worker=True):
    store = store or Store()
    worker = Worker(store)

    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            worker.start()
        yield
        if run_worker:
            worker.stop()

    app = FastAPI(title='Football AI Studio — P0', lifespan=lifespan)
    app.state.store, app.state.worker = store, worker

    @app.middleware('http')
    async def local_only(request, call_next):
        # Reject browser requests from unrelated websites and DNS rebinding.
        host = request.headers.get('host', '').split(':')[0]
        if host not in {'127.0.0.1', 'localhost', 'testserver'}:
            return JSONResponse({'detail': '仅允许本机访问'}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin not in {f'http://{request.headers.get("host")}', f'https://{request.headers.get("host")}'}:
            return JSONResponse({'detail': '拒绝跨站请求'}, status_code=403)
        return await call_next(request)

    def require_session(sid):
        session = store.session(sid)
        if not session:
            raise HTTPException(404, '场次不存在')
        return session

    def require_job(jid):
        rows = store.rows('SELECT j.* FROM jobs j JOIN media m ON m.id=j.media_id JOIN sessions s ON s.id=m.session_id WHERE j.id=? AND s.deleted=0', (jid,))
        if not rows:
            raise HTTPException(404, '任务不存在')
        return rows[0]

    @app.get('/api/health')
    def health():
        binaries = {key: bool(shutil.which(os.getenv(env, key))) for key, env in [('ffmpeg', 'FFMPEG_BIN'), ('ffprobe', 'FFPROBE_BIN')]}
        alive = bool(worker.thread and worker.thread.is_alive())
        return {'status': 'ok' if all(binaries.values()) and (alive or not run_worker) else 'degraded', 'phase': 'P0', 'analysis_available': False,
                **binaries, 'worker_alive': bool(worker.thread and worker.thread.is_alive()), 'media_root': str(store.root), 'schema_version': 1}

    @app.get('/api/sessions')
    def sessions():
        return store.rows('SELECT s.*, (SELECT count(*) FROM media WHERE session_id=s.id) AS media_count FROM sessions s WHERE deleted=0 ORDER BY created_at DESC')

    @app.post('/api/sessions', status_code=201)
    def create_session(body: SessionInput):
        if not body.name.strip():
            raise HTTPException(422, '场次名称不能为空')
        sid = uuid4().hex
        with store.connect() as conn:
            conn.execute('INSERT INTO sessions(id,name,date,created_at) VALUES(?,?,?,?)', (sid, body.name.strip(), str(body.date), now()))
        return require_session(sid)

    @app.get('/api/sessions/{sid}')
    def detail(sid: str):
        session = require_session(sid)
        session['media'] = store.rows('SELECT m.*,j.id AS job_id,j.status,j.stage,j.progress,j.error,j.attempts FROM media m JOIN jobs j ON j.media_id=m.id WHERE m.session_id=? ORDER BY m.created_at', (sid,))
        return session

    @app.patch('/api/sessions/{sid}')
    def edit_session(sid: str, body: SessionInput):
        require_session(sid)
        if not body.name.strip():
            raise HTTPException(422, '场次名称不能为空')
        with store.connect() as conn:
            conn.execute('UPDATE sessions SET name=?,date=? WHERE id=?', (body.name.strip(), str(body.date), sid))
        return require_session(sid)

    @app.delete('/api/sessions/{sid}')
    def delete_session(sid: str):
        require_session(sid)
        with store.connect() as conn:
            conn.execute('UPDATE sessions SET deleted=1 WHERE id=?', (sid,))
            conn.execute("UPDATE jobs SET cancel_requested=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END,updated_at=? WHERE media_id IN (SELECT id FROM media WHERE session_id=?)", (now(), sid))
        return {'deleted': True, 'original_files_preserved': True}

    @app.post('/api/sessions/{sid}/register', status_code=201)
    def register(sid: str, body: RegisterInput):
        require_session(sid)
        try:
            path = store.approved_path(body.path)
            # Folder import is deliberately one level, deterministic, capped.
            paths = sorted(path.iterdir()) if path.is_dir() else [path]
            eligible = [p for p in paths if p.suffix.lower() in EXTENSIONS]
            if not eligible:
                raise ValueError('没有支持的视频文件；目录注册只读取第一层')
            if len(eligible) > 200:
                raise ValueError('单次最多注册 200 个文件')
            checked = [store.approved_path(str(p)) for p in eligible]
            if any(not p.is_file() for p in checked):
                raise ValueError('视频路径必须是普通文件')
            results = []
            existing = {m['path'] for m in store.rows('SELECT path FROM media WHERE session_id=?', (sid,))}
            for p in checked:
                if str(p) not in existing:
                    results.append(store.register(sid, p, p.name, body.source))
                    existing.add(str(p))
            return {'imported': results, 'skipped': len(checked) - len(results)}
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/sessions/{sid}/upload', status_code=201)
    async def upload(sid: str, request: Request, filename: str, source: Literal['gopro', 'iphone', 'other'] = 'gopro'):
        require_session(sid)
        name = Path(filename).name
        if not name or len(name) > 240 or Path(name).suffix.lower() not in EXTENSIONS:
            raise HTTPException(400, '不支持的文件名或视频扩展名')
        limit = int(os.getenv('FAS_MAX_UPLOAD_BYTES', str(100 * 1024**3)))
        dest = store.data / 'uploads' / (uuid4().hex + Path(name).suffix.lower())
        partial = dest.with_suffix(dest.suffix + '.partial')
        size = 0
        try:
            with partial.open('wb') as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(413, '文件超过配置的上传大小限制')
                    await asyncio.to_thread(stream.write, chunk)
            if not size:
                raise HTTPException(400, '文件为空')
            partial.replace(dest)
            try:
                return store.register(sid, dest, name, source, managed=True)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
        except BaseException:
            partial.unlink(missing_ok=True)
            dest.unlink(missing_ok=True)
            raise

    @app.get('/api/jobs')
    def jobs():
        return store.rows('SELECT j.*,m.name,m.session_id FROM jobs j JOIN media m ON m.id=j.media_id JOIN sessions s ON s.id=m.session_id WHERE s.deleted=0 ORDER BY j.created_at DESC LIMIT 200')

    @app.post('/api/jobs/{jid}/cancel')
    def cancel(jid: str):
        job = require_job(jid)
        if job['status'] not in {'queued', 'running'}:
            raise HTTPException(409, '只能取消等待或运行中的任务')
        with store.connect() as conn:
            conn.execute("UPDATE jobs SET cancel_requested=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END,stage=CASE WHEN status='queued' THEN '已取消' ELSE '正在取消' END,updated_at=? WHERE id=? AND status IN ('queued','running')", (now(), jid))
        return require_job(jid)

    @app.post('/api/jobs/{jid}/retry')
    def retry(jid: str):
        job = require_job(jid)
        if job['status'] not in {'failed', 'cancelled'}:
            raise HTTPException(409, '只能重试失败或已取消的任务')
        with store.connect() as conn:
            conn.execute("UPDATE jobs SET status='queued',stage='等待重试',cancel_requested=0,progress=0,error=NULL,updated_at=? WHERE id=? AND status IN ('failed','cancelled')", (now(), jid))
        return require_job(jid)

    @app.get('/api/media/{mid}/{kind}')
    def asset(mid: str, kind: Literal['proxy', 'thumbnail']):
        rows = store.rows('SELECT m.* FROM media m JOIN sessions s ON s.id=m.session_id WHERE m.id=? AND s.deleted=0', (mid,))
        if not rows:
            raise HTTPException(404, '媒体不存在')
        value = rows[0][kind + '_path']
        if not value or not Path(value).is_file():
            raise HTTPException(404, '文件尚未生成')
        path = Path(value).resolve()
        if not path.is_relative_to(store.data / 'derived'):
            raise HTTPException(403, '无效资源路径')
        return FileResponse(path, media_type='video/mp4' if kind == 'proxy' else 'image/jpeg')

    dist = BASE / 'frontend/dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    return app
