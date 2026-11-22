from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Store, now


def test_cache_cleanup_preserves_references_and_cost_cache(tmp_path):
    store=Store(tmp_path/'data')
    with TestClient(create_app(store,False)) as c:
        sid=c.post('/api/sessions',json={'name':'训练','date':'2026-10-14'}).json()['id']
        original=store.root/'source.mp4'; original.write_bytes(b'original')
        item=store.register(sid,original,'source.mp4','other')
        folder=store.data/'derived'/item['media_id']/'frames'; folder.mkdir(parents=True)
        reference=folder/'reference.jpg'; reference.write_bytes(b'reference')
        cached=folder/'unused.jpg'; cached.write_bytes(b'cache')
        with store.connect() as conn:
            conn.execute("UPDATE jobs SET status='succeeded' WHERE id=?",(item['job_id'],))
            conn.execute('INSERT INTO target_references VALUES(?,?,?,?,?,?,?,?)',('ref',sid,item['media_id'],0,'[0,0,1,1]','',str(reference),now()))
            conn.execute("INSERT INTO analysis_cache(hash,state,created_at) VALUES('charged','pending',?)",(now(),))
        assert c.get('/api/storage').json()['cache_bytes']==5
        result=c.post('/api/storage/cleanup').json()
        assert result['removed_files']==1 and result['removed_bytes']==5
        assert not cached.exists() and reference.exists() and original.exists()
        assert store.rows('SELECT hash FROM analysis_cache')[0]['hash']=='charged'
        with store.connect() as conn:
            conn.execute("UPDATE jobs SET status='running' WHERE id=?",(item['job_id'],))
        assert c.post('/api/storage/cleanup').status_code==409


def test_reference_creation_excludes_concurrent_cleanup(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from threading import Event
    import backend.analysis as analysis

    store=Store(tmp_path/'data')
    app=create_app(store,False)
    frame_ready,allow_insert,cleanup_started,cleanup_finished=(Event() for _ in range(4))
    with TestClient(app) as client:
        sid=client.post('/api/sessions',json={'name':'训练','date':'2026-10-14'}).json()['id']
        original=store.root/'source.mp4'; original.write_bytes(b'original')
        item=store.register(sid,original,'source.mp4','other')
        with store.connect() as conn:
            conn.execute('UPDATE media SET duration=2 WHERE id=?',(item['media_id'],))
            conn.execute("UPDATE jobs SET status='succeeded' WHERE id=?",(item['job_id'],))
        real_local_frame=analysis.local_frame

        def fake_ffmpeg(command, **kwargs):
            Path(command[-1]).write_bytes(b'jpeg')
        monkeypatch.setattr(analysis.subprocess,'run',fake_ffmpeg)

        def paused_frame(*args,**kwargs):
            path=real_local_frame(*args,**kwargs)
            frame_ready.set()
            assert allow_insert.wait(5)
            return path
        monkeypatch.setattr(analysis,'local_frame',paused_frame)

        def cleanup():
            cleanup_started.set()
            try:
                return client.post('/api/storage/cleanup')
            finally:
                cleanup_finished.set()

        with ThreadPoolExecutor(max_workers=2) as pool:
            reference=pool.submit(client.post,f'/api/sessions/{sid}/target-references',json={
                'media_id':item['media_id'],'source_time':0,'box_normalized':[0,0,1,1]})
            assert frame_ready.wait(5)
            cleaning=pool.submit(cleanup)
            assert cleanup_started.wait(5)
            try:
                assert not cleanup_finished.wait(.15)
            finally:
                allow_insert.set()
            response=reference.result(timeout=5)
            assert response.status_code==201,response.text
            assert 'local_reference_path' not in response.json()
            assert cleaning.result(timeout=5).status_code==200
        row=store.rows('SELECT local_reference_path FROM target_references')[0]
        assert Path(row['local_reference_path']).read_bytes()==b'jpeg'


def test_frame_response_survives_cache_cleanup(tmp_path,monkeypatch):
    from pathlib import Path
    import backend.analysis as analysis

    store=Store(tmp_path/'data')
    app=create_app(store,False)
    with store.connect() as conn:
        conn.execute('INSERT INTO sessions(id,name,date,created_at) VALUES(?,?,?,?)',('s','训练','2026-10-14',now()))
    original=store.root/'source.mp4';original.write_bytes(b'original')
    item=store.register('s',original,'source.mp4','other')
    with store.connect() as conn:
        conn.execute('UPDATE media SET duration=2 WHERE id=?',(item['media_id'],))
        conn.execute("UPDATE jobs SET status='succeeded' WHERE id=?",(item['job_id'],))
    def fake_ffmpeg(command,**kwargs):
        Path(command[-1]).write_bytes(b'jpeg-payload')
    monkeypatch.setattr(analysis.subprocess,'run',fake_ffmpeg)
    frame_route=next(r.endpoint for r in app.routes if getattr(r,'path','')=='/api/media/{mid}/frame')
    cleanup_route=next(r.endpoint for r in app.routes if getattr(r,'path','')=='/api/storage/cleanup')
    response=frame_route(item['media_id'],0)
    assert cleanup_route()['removed_files']==1
    # Sending the already constructed response no longer needs the deleted file.
    assert response.body==b'jpeg-payload'
    assert response.media_type=='image/jpeg'
