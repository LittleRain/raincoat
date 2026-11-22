import sqlite3
import subprocess

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.badminton import analyze
from backend.core import Store
from backend.worker import Worker


def test_workbench_html_is_not_cached(tmp_path, monkeypatch):
    import backend.app as app_module
    dist = tmp_path/'frontend'/'dist'
    dist.mkdir(parents=True)
    (dist/'index.html').write_text('<html>workbench</html>')
    monkeypatch.setattr(app_module,'BASE',tmp_path)
    store = Store(tmp_path/'data',tmp_path/'media')
    with TestClient(create_app(store,False)) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert page.headers['cache-control'] == 'no-store'


def test_badminton_uses_shared_session_review_and_handoff(tmp_path):
    store = Store(tmp_path/'data',tmp_path/'media')
    video = store.root/'match.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                    'testsrc2=size=320x180:rate=12:duration=8','-c:v','libx264','-threads','1',str(video)],check=True)
    with TestClient(create_app(store,False)) as client:
        session = client.post('/api/sessions',json={'name':'周六双打','date':'2026-10-28','sport':'badminton'}).json()
        assert session['sport'] == 'badminton'
        item = store.register(session['id'],video,video.name,'gopro')
        mid = item['media_id']
        with store.connect() as conn:
            conn.execute('UPDATE media SET duration=8,width=320,height=180 WHERE id=?',(mid,))
            conn.execute("UPDATE jobs SET status='succeeded' WHERE id=?",(item['job_id'],))
        assert client.patch('/api/sessions/'+session['id'],json={'name':'周六双打','date':'2026-10-28','sport':'football'}).status_code == 422
        assert client.post(f'/api/media/{mid}/badminton-analyses',json={'ignore_before':0}).status_code == 409
        ref=store.data/'derived'/'test-ref.jpg';ref.write_bytes(b'fixture')
        with store.connect() as conn:
            conn.execute('INSERT INTO target_references VALUES(?,?,?,?,?,?,?,?)',('ref',session['id'],mid,0,'[0,0,0.2,0.2]','白衣黄裤',str(ref),'2026-10-28'))
        started = client.post(f'/api/media/{mid}/badminton-analyses',json={'ignore_before':0})
        assert started.status_code == 202, started.text
        assert client.post(f'/api/media/{mid}/analyses',json={}).status_code == 422
        job = store.rows('SELECT * FROM jobs WHERE id=?',(started.json()['job_id'],))[0]
        analyze(Worker(store),job)
        candidates = client.get(f"/api/sessions/{session['id']}/candidates").json()
        assert candidates and all(0 <= row['start_s'] < row['end_s'] <= 8 for row in candidates)
        first = candidates[0]
        reviewed = client.post(f"/api/sessions/{session['id']}/review-events",json={
            'media_id':mid,'candidate_id':first['id'],'start_s':first['start_s'],'end_s':first['end_s'],
            'event_type':'other','segment_kind':'rally','identity_status':'confirmed_target',
            'decision':'keep','highlight':True,'description':'目标球员连续对打'}).json()
        handoff = client.get(f"/api/sessions/{session['id']}/chatcut-handoff?mode=person&target_count=1")
        assert handoff.status_code == 200, handoff.text
        data = handoff.json()
        assert data['sport'] == 'badminton' and data['sources'][0]['path'] == str(video)
        assert data['segments'][0]['id'] == reviewed['id'] and data['segments'][0]['segment_kind'] == 'rally'
        assert client.get(f"/api/sessions/{session['id']}/chatcut-handoff?mode=person&target_count=2").status_code == 422
        second = client.post(f"/api/sessions/{session['id']}/review-events",json={
            'media_id':mid,'start_s':0,'end_s':3,'event_type':'other','segment_kind':'rally',
            'identity_status':'uncertain','decision':'keep','description':'普通活动回合'}).json()
        activity = client.get(f"/api/sessions/{session['id']}/chatcut-handoff?mode=activity&target_count=2")
        assert activity.status_code == 200, activity.text
        assert {row['id'] for row in activity.json()['segments']} == {reviewed['id'],second['id']}
        export = client.post(f"/api/sessions/{session['id']}/exports",json={
            'event_ids':[reviewed['id'],second['id']],'title':'活动集锦','mode':'activity'})
        assert export.status_code == 202, export.text


def test_existing_sessions_default_to_football(tmp_path):
    data = tmp_path/'legacy'
    data.mkdir()
    with sqlite3.connect(data/'studio.sqlite3') as conn:
        conn.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY,name TEXT,date TEXT,created_at TEXT,deleted INTEGER DEFAULT 0)')
        conn.execute('INSERT INTO sessions(id,name,date,created_at) VALUES(?,?,?,?)',('old','旧场次','2026-10-14','now'))
        conn.execute('PRAGMA user_version=2')
    store = Store(data,tmp_path/'media')
    assert store.session('old')['sport'] == 'football'
