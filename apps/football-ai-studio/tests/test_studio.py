import json
import subprocess
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.core import Store
from backend.worker import Worker


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'data', tmp_path / 'approved')


@pytest.fixture
def video(store):
    path = store.root / 'fixture.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=25',
                    '-f', 'lavfi', '-i', 'sine=frequency=440', '-t', '2', '-c:v', 'libx264', '-threads', '1', '-c:a', 'aac', str(path)], check=True)
    return path


def session(client):
    response = client.post('/api/sessions', json={'name': '足球训练', 'date': '2026-10-14'})
    assert response.status_code == 201
    return response.json()['id']


def wait_job(store, jid, status='succeeded', timeout=25):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        row = store.rows('SELECT * FROM jobs WHERE id=?', (jid,))[0]
        if row['status'] == status:
            return row
        if row['status'] == 'failed' and status != 'failed':
            pytest.fail(row['error'])
        time.sleep(.1)
    pytest.fail(f'timeout: {row}')


def test_crud_health_and_persistence(store):
    with TestClient(create_app(store, False)) as client:
        assert client.get('/api/health').json()['analysis_available'] is False
        sid = session(client)
        assert client.patch('/api/sessions/'+sid, json={'name':'改名','date':'2026-10-15'}).json()['name']=='改名'
        assert client.get('/api/sessions').json()[0]['id']==sid
        assert client.post('/api/sessions', json={'name':' ','date':'bad'}).status_code==422
    reopened = Store(store.data, store.root)
    with TestClient(create_app(reopened, False)) as client:
        assert client.get('/api/sessions/'+sid).json()['name']=='改名'
        assert client.delete('/api/sessions/'+sid).status_code==200
        assert client.get('/api/sessions/'+sid).status_code==404
        assert client.get('/api/sessions').json()==[]


def test_real_ffmpeg_upload_and_playback(store, video):
    with TestClient(create_app(store)) as client:
        sid=session(client)
        result=client.post(f'/api/sessions/{sid}/upload',params={'filename':'iphone.mp4','source':'iphone'},content=video.read_bytes())
        assert result.status_code==201
        item=result.json()
        job=wait_job(store,item['job_id'])
        assert job['progress']==100 and job['attempts']==1
        media=client.get('/api/sessions/'+sid).json()['media'][0]
        assert media['width']==640 and media['height']==360
        assert 1.9<=media['duration']<=2.1 and media['fps']==25
        proxy=client.get(f"/api/media/{item['media_id']}/proxy")
        assert proxy.status_code==200 and proxy.headers['content-type']=='video/mp4'
        ranged=client.get(f"/api/media/{item['media_id']}/proxy",headers={'Range':'bytes=0-99'})
        assert ranged.status_code==206 and len(ranged.content)==100
        assert client.get(f"/api/media/{item['media_id']}/thumbnail").content[:2]==b'\xff\xd8'
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-of','json','-show_streams',media['proxy_path']]))
        stream=next(s for s in info['streams'] if s['codec_type']=='video')
        assert stream['codec_name']=='h264' and stream['height']<=720
        assert client.get(f"/api/media/{item['media_id']}/original").status_code==422
    with TestClient(create_app(Store(store.data,store.root),False)) as client:
        assert client.get('/api/sessions/'+sid).json()['media'][0]['status']=='succeeded'


def test_register_folder_boundaries_and_duplicates(store, video):
    with TestClient(create_app(store,False)) as client:
        sid=session(client)
        endpoint=f'/api/sessions/{sid}/register'
        assert client.post(endpoint,json={'path':str(store.data)}).status_code==400
        outside=store.data/'outside.mp4'; outside.write_bytes(b'bad')
        (store.root/'escape.mp4').symlink_to(outside)
        assert client.post(endpoint,json={'path':str(store.root/'escape.mp4')}).status_code==400
        assert client.post(endpoint,json={'path':str(store.root)}).status_code==400
        (store.root/'escape.mp4').unlink()
        response=client.post(endpoint,json={'path':str(store.root),'source':'gopro'})
        assert len(response.json()['imported'])==1
        assert client.post(endpoint,json={'path':str(video)}).json()['skipped']==1
        assert client.get('/api/sessions/'+sid).json()['media'][0]['managed']==0
        client.delete('/api/sessions/'+sid)
        assert video.exists()


def test_cancel_retry_failure_and_recovery(store, video):
    with TestClient(create_app(store,False)) as client:
        sid=session(client)
        item=client.post(f'/api/sessions/{sid}/register',json={'path':str(video)}).json()['imported'][0]
        jid=item['job_id']
        assert client.post('/api/jobs/'+jid+'/retry').status_code==409
        assert client.post('/api/jobs/'+jid+'/cancel').json()['status']=='cancelled'
        assert client.post('/api/jobs/'+jid+'/retry').json()['status']=='queued'
        with store.connect() as conn:
            conn.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,))
    with TestClient(create_app(store)):
        assert wait_job(store,jid)['status']=='succeeded'
    broken=store.root/'broken.mov'; broken.write_bytes(b'not a video')
    with TestClient(create_app(store)) as client:
        bad=client.post(f'/api/sessions/{sid}/register',json={'path':str(broken)}).json()['imported'][0]
        assert wait_job(store,bad['job_id'],'failed')['error']
        broken.write_bytes(video.read_bytes())
        client.post('/api/jobs/'+bad['job_id']+'/retry')
        assert wait_job(store,bad['job_id'])['attempts']==2


def test_upload_validation_and_origin_security(store,monkeypatch):
    with TestClient(create_app(store,False)) as client:
        sid=session(client); url=f'/api/sessions/{sid}/upload'
        assert client.post(url,params={'filename':'x.txt'},content=b'x').status_code==400
        assert client.post(url,params={'filename':'x.mp4'},content=b'').status_code==400
        monkeypatch.setenv('FAS_MAX_UPLOAD_BYTES','3')
        assert client.post(url,params={'filename':'x.mp4'},content=b'1234').status_code==413
        assert list((store.data/'uploads').iterdir())==[]
        assert client.get('/api/health',headers={'Host':'attacker.example'}).status_code==403
        assert client.post('/api/sessions',headers={'Origin':'https://attacker.example'},json={'name':'x','date':'2026-10-14'}).status_code==403


def test_single_worker_lock(store):
    a,b=Worker(store),Worker(store)
    a.start()
    try:
        with pytest.raises(RuntimeError,match='已有 worker'):
            b.start()
    finally:
        a.stop()


def test_running_cancel_and_shutdown_requeue(store, video, monkeypatch):
    # A real sleeping subprocess verifies termination without a long fixture encode.
    from backend.worker import Cancelled
    import sys
    with TestClient(create_app(store,False)) as client:
        sid=session(client)
        item=client.post(f'/api/sessions/{sid}/register',json={'path':str(video)}).json()['imported'][0]
        jid=item['job_id']
        def slow(self,job):
            self.run([sys.executable,'-c','import time; time.sleep(30)'],job['id'],store.data/'slow.log')
        monkeypatch.setattr(Worker,'preprocess',slow)
        worker=Worker(store); worker.start()
        try:
            wait_job(store,jid,'running')
            client.post('/api/jobs/'+jid+'/cancel')
            wait_job(store,jid,'cancelled')
            client.post('/api/jobs/'+jid+'/retry')
            wait_job(store,jid,'running')
        finally:
            worker.stop()
        assert store.rows('SELECT status FROM jobs WHERE id=?',(jid,))[0]['status']=='queued'


def test_portrait_and_4k_preprocessing(store):
    fixtures=[]
    for name,size in [('portrait','360x640'),('4k','3840x2160')]:
        path=store.root/f'{name}.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'testsrc2=size={size}:rate=5',
                        '-t','1','-c:v','libx264','-preset','ultrafast','-threads','2',str(path)],check=True)
        fixtures.append(path)
    with TestClient(create_app(store)) as client:
        sid=session(client)
        for path in fixtures:
            result=client.post(f'/api/sessions/{sid}/register',json={'path':str(path)})
            jid=result.json()['imported'][0]['job_id'];wait_job(store,jid)
        media=client.get('/api/sessions/'+sid).json()['media']
        assert media[0]['height']>media[0]['width']
        assert media[1]['width']==3840
        for m in media:
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',m['proxy_path']]))
            s=next(x for x in probe['streams'] if x['codec_type']=='video')
            assert s['width']<=1280 and s['height']<=720
            assert abs(s['width']/s['height']-m['width']/m['height'])<.01


def test_supervisor_terminates_child_after_parent_crash(tmp_path):
    import os,signal,sys
    script=tmp_path/'owner.py'; pidfile=tmp_path/'child.pid'
    script.write_text('''import os,subprocess,sys,time
r,w=os.pipe()
child_code="import os,time; from pathlib import Path; Path(sys_path).write_text(str(os.getpid())); time.sleep(30)".replace("sys_path",repr(sys.argv[1]))
p=subprocess.Popen([sys.executable,"-m","backend.supervisor",str(r),sys.executable,"-c",child_code],pass_fds=(r,))
os.close(r)
time.sleep(30)
''')
    owner=subprocess.Popen([sys.executable,str(script),str(pidfile)])
    try:
        end=time.monotonic()+5
        while not pidfile.exists() and time.monotonic()<end:
            time.sleep(.05)
        assert pidfile.exists()
        pid=int(pidfile.read_text())
        owner.kill();owner.wait()
        end=time.monotonic()+5
        while time.monotonic()<end:
            try:
                os.kill(pid,0)
            except ProcessLookupError:
                break
            time.sleep(.05)
        else:
            pytest.fail('orphan child survived parent crash')
    finally:
        if owner.poll() is None:
            owner.kill();owner.wait()
