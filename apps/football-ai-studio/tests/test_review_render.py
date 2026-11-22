import json
import sqlite3
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Store, now


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / '训练数据', tmp_path / '原片')
    with TestClient(create_app(store, False)) as client:
        sid = client.post('/api/sessions', json={'name': '周末足球', 'date': '2026-10-14'}).json()['id']
        path = store.root / '中文无音轨.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=24',
                        '-t', '2', '-c:v', 'libx264', '-threads', '1', str(path)], check=True)
        item = store.register(sid, path, path.name, 'iphone')
        with store.connect() as conn:
            conn.execute('UPDATE media SET duration=2,width=320,height=240,fps=24 WHERE id=?', (item['media_id'],))
            conn.execute("UPDATE jobs SET status='succeeded',progress=100 WHERE id=?", (item['job_id'],))
        yield store, client, sid, item['media_id']


def event(client, sid, mid, **fields):
    payload = dict(media_id=mid, start_s=0, end_s=1, event_type='shot',
                   identity_status='confirmed_target', decision='keep', description='射门！{\\安全} 中文字幕',
                   effects={'speed': 1, 'caption': True})
    payload.update(fields)
    return client.post(f'/api/sessions/{sid}/review-events', json=payload)


def test_review_bounds_versions_timeline_and_snapshot(setup):
    store, c, sid, mid = setup
    assert event(c, sid, mid, end_s=3).status_code == 422
    assert event(c, sid, mid, start_s=1, end_s=1).status_code == 422
    a = event(c, sid, mid)
    assert a.status_code == 201, a.text
    a = a.json()
    b = event(c, sid, mid, start_s=1, end_s=2).json()
    assert c.patch('/api/review-events/'+a['id'], json={'version': a['version'], 'description': '已确认'}).status_code == 200
    assert c.patch('/api/review-events/'+a['id'], json={'version': a['version'], 'description': '过期'}).status_code == 409
    assert c.put(f'/api/sessions/{sid}/timeline', json={'event_ids': [b['id'], a['id']]}).status_code == 200
    assert [e['id'] for e in c.get(f'/api/sessions/{sid}/review-events').json()] == [b['id'], a['id']]
    body = {'event_ids': [b['id'], a['id']], 'title': '足球训练', 'request_key': 'one'}
    r = c.post(f'/api/sessions/{sid}/exports', json=body)
    assert r.status_code == 202, r.text
    export = r.json()
    assert c.post(f'/api/sessions/{sid}/exports', json=body).json()['id'] == export['id']
    latest = c.get(f'/api/sessions/{sid}/review-events').json()[1]
    c.patch('/api/review-events/'+a['id'], json={'version': latest['version'], 'description': '之后修改'})
    assert c.get('/api/exports/'+export['id']).json()['snapshot'][1]['description'] == '已确认'
    assert len(c.get('/api/sessions/'+sid).json()['media']) == 1
    assert Store(store.data, store.root).rows('SELECT count(*) AS n FROM review_events')[0]['n'] == 2


def test_chatcut_handoff_keeps_source_ranges_and_review_labels(setup):
    store, c, sid, mid = setup
    selected = event(c, sid, mid, start_s=.2, end_s=1.3, event_type='dribble',
                     segment_kind='match', highlight=True, description='接球后连续推进').json()
    event(c, sid, mid, start_s=1.3, end_s=1.8, identity_status='confirmed_other')
    response = c.get(f'/api/sessions/{sid}/chatcut-handoff')
    assert response.status_code == 200, response.text
    handoff = response.json()
    assert handoff['sources'] == [{'id':mid,'name':'中文无音轨.mp4','path':str(store.root / '中文无音轨.mp4')}]
    assert handoff['segments'] == [{'id':selected['id'],'source_id':mid,'start_s':.2,'end_s':1.3,
                                    'segment_kind':'match','highlight':True,'action':'dribble',
                                    'identity_status':'confirmed_target','note':'接球后连续推进'}]
    assert c.patch('/api/review-events/'+selected['id'],json={'version':selected['version'],'highlight':False}).json()['highlight'] is False


def test_existing_v2_review_table_gets_new_labels(tmp_path):
    store = Store(tmp_path / 'data', tmp_path / 'media')
    with store.connect() as conn:
        conn.execute('DROP TABLE review_events')
        conn.execute('''CREATE TABLE review_events (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, media_id TEXT NOT NULL,
            candidate_id TEXT, start_s REAL NOT NULL, end_s REAL NOT NULL,
            event_type TEXT NOT NULL, identity_status TEXT NOT NULL,
            decision TEXT NOT NULL, description TEXT NOT NULL, effects_json TEXT NOT NULL,
            position INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
    with TestClient(create_app(store, False)):
        pass
    columns = {row['name'] for row in store.rows('PRAGMA table_info(review_events)')}
    assert {'segment_kind','highlight'} <= columns


def test_export_rejects_cross_session_unconfirmed_and_deleted(setup):
    _, c, sid, mid = setup
    a = event(c, sid, mid, identity_status='uncertain').json()
    url = f'/api/sessions/{sid}/exports'
    assert c.post(url, json={'event_ids': [a['id']]}).status_code == 422
    assert c.post(url, json={'event_ids': [a['id']], 'allow_uncertain': True}).status_code == 202
    other = c.post('/api/sessions', json={'name': '另场', 'date': '2026-10-14'}).json()['id']
    assert c.post(f'/api/sessions/{other}/exports', json={'event_ids': [a['id']]}).status_code == 422
    assert event(c, other, mid).status_code == 422
    c.delete('/api/sessions/'+sid)
    assert c.get(f'/api/sessions/{sid}/review-events').status_code == 404


@pytest.mark.parametrize('orientation', ['landscape', 'portrait'])
def test_real_export_silent_chinese_caption_and_slow_motion(setup, orientation):
    store, c, sid, mid = setup
    a = event(c, sid, mid, end_s=.5, effects={'speed': .5, 'caption': True}).json()
    b = event(c, sid, mid, start_s=1, end_s=1.5, effects={'speed': 1, 'caption': False}).json()
    r = c.post(f'/api/sessions/{sid}/exports', json={'event_ids': [a['id'], b['id']], 'title': '训练集锦', 'orientation': orientation})
    assert r.status_code == 202, r.text
    item = r.json()
    from backend.worker import Worker
    worker = Worker(store)
    worker.start()
    try:
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            state = c.get('/api/exports/'+item['id']).json()
            if state['status'] in {'failed', 'succeeded'}:
                break
            time.sleep(.1)
        assert state['status'] == 'succeeded', state
        result = c.get('/api/exports/'+item['id']+'/download')
        assert result.status_code == 200 and result.headers['content-type'] == 'video/mp4'
        assert c.get('/api/exports/'+item['id']+'/download', headers={'Range': 'bytes=0-99'}).status_code == 206
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', state['output_path']]))
        v = next(s for s in probe['streams'] if s['codec_type']=='video')
        assert (v['width'], v['height']) == ((1920,1080) if orientation=='landscape' else (1080,1920))
        assert v['codec_name']=='h264'
        assert next(s for s in probe['streams'] if s['codec_type']=='audio')['codec_name']=='aac'
        assert abs(float(probe['format']['duration'])-3) < .15  # 1.5s title + 1s slow + .5s
    finally:
        worker.stop()


def test_v1_migration_keeps_original_data_and_creates_backup(tmp_path):
    from backend.core import BASE
    data=tmp_path/'data'; data.mkdir()
    db=data/'studio.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.executescript((BASE/'backend/schema.sql').read_text())
        conn.execute('INSERT INTO sessions(id,name,date,created_at) VALUES(?,?,?,?)', ('old','保留场次','2026-10-14',now()))
    store=Store(data)
    assert store.session('old')['name']=='保留场次'
    assert store.rows('PRAGMA user_version')[0]['user_version'] == 2
    backups=list((data/'backups').glob('*.sqlite3'))
    assert backups
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute('SELECT name FROM sessions').fetchone()[0]=='保留场次'


def test_mixed_audio_rotated_source_and_cancelled_export_retry(setup):
    store,c,sid,mid=setup
    source=store.root/'有声音.mp4'
    rotated=store.root/'旋转视频.mov'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=25',
                    '-f','lavfi','-i','sine=frequency=880:sample_rate=44100','-t','2',
                    '-c:v','libx264','-threads','1','-c:a','aac',str(source)],check=True)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-c','copy','-metadata:s:v:0','rotate=90',str(rotated)],check=True)
    item=store.register(sid,rotated,rotated.name,'iphone')
    with store.connect() as conn:
        conn.execute('UPDATE media SET duration=2,width=640,height=360,fps=25 WHERE id=?',(item['media_id'],))
        conn.execute("UPDATE jobs SET status='succeeded' WHERE id=?",(item['job_id'],))
    a=event(c,sid,mid,start_s=.2,end_s=.7,effects={'speed':1,'caption':False}).json()
    b=event(c,sid,item['media_id'],start_s=.5,end_s=1,effects={'speed':.5,'caption':True,'focus_box':[.1,.1,.2,.3],'focus_start_s':.5,'focus_end_s':1}).json()
    item=c.post(f'/api/sessions/{sid}/exports',json={'event_ids':[a['id'],b['id']],'title':''}).json()
    assert c.post('/api/jobs/'+item['job_id']+'/cancel').json()['status']=='cancelled'
    assert c.get('/api/exports/'+item['id']+'/download').status_code==409
    assert c.post('/api/jobs/'+item['job_id']+'/retry').json()['status']=='queued'
    from backend.worker import Worker
    worker=Worker(store); worker.start()
    try:
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            state=c.get('/api/exports/'+item['id']).json()
            if state['status'] in {'failed','succeeded'}: break
            time.sleep(.1)
        assert state['status']=='succeeded',state
        assert abs(state['duration']-1.5)<.15
        # Decode the real concatenated output, including both sides of the seam.
        subprocess.run(['ffmpeg','-v','error','-i',state['output_path'],'-f','null','-'],check=True)
        assert rotated.exists() and source.exists()
    finally:
        worker.stop()
