import base64
import json
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.analysis import config, register_routes, _provider_call
from backend.core import Store, now


def test_minimax_profile_and_missing_key(monkeypatch):
    monkeypatch.setenv('FAS_AI_PROVIDER','minimax')
    for name in ('FAS_AI_BASE_URL','FAS_AI_MODEL','FAS_AI_API_KEY','MINIMAX_API_KEY','FAS_AI_INPUT_MODE'):
        monkeypatch.delenv(name,raising=False)
    c=config()
    assert c['model']=='MiniMax-M3'
    assert c['base_url']=='https://api.minimax.io/v1'
    assert c['input_mode']=='frames' and c['configured'] is False
    monkeypatch.setenv('MINIMAX_API_KEY','local-test-secret')
    assert config()['configured'] is True
    assert config()['key']=='local-test-secret'
    monkeypatch.setenv('FAS_AI_INPUT_MODE','video')
    assert config()['input_mode']=='video'


def test_minimax_native_request_and_reasoning_split(monkeypatch):
    from backend.minimax import request_payload
    c={'provider':'minimax','model':'MiniMax-M3'}
    payload=request_payload(c,[{'type':'text','text':'Return JSON'}])
    assert payload['reasoning_split'] is True
    assert payload['thinking']=={'type':'disabled'}
    assert payload['max_completion_tokens']==8192 and 'max_tokens' not in payload
    assert 'response_format' not in payload
    async def handler(request):
        assert json.loads(request.content)==payload
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'```json\n{"events": []}\n```','reasoning_content':'not events'}}], 'usage':{'total_tokens':12}})
    original=httpx.AsyncClient
    observed={}
    def client_factory(**kw):
        observed['read_timeout']=kw['timeout'].read
        return original(transport=httpx.MockTransport(handler),**kw)
    monkeypatch.setattr(httpx,'AsyncClient',client_factory)
    assert _provider_call({**c,'base_url':'https://example.invalid/v1','key':'x'},payload['messages'][0]['content'],'one')==({'events':[]},{'total_tokens':12})
    assert observed['read_timeout']==240


def test_gemini_scan_uses_low_reasoning_without_sampling_temperature():
    from backend.minimax import request_payload
    payload=request_payload({'provider':'openai-compatible','model':'gemini-3.8-flash',
                             'base_url':'https://generativelanguage.googleapis.com/v1beta/openai'},
                            [{'type':'text','text':'Return JSON'}])
    assert payload['reasoning_effort']=='low'
    assert payload['response_format']=={'type':'json_object'}
    assert 'temperature' not in payload


def test_gemini_503_explains_manual_retry_without_resending(monkeypatch):
    import backend.analysis as analysis
    attempts=[]
    def handler(request):
        attempts.append(request)
        return httpx.Response(503,json={'error':{'message':'private upstream detail'}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(RuntimeError,match='暂时不可用或繁忙.*等待几分钟.*不会自动重发') as exc:
        analysis._provider_call({'base_url':'https://generativelanguage.googleapis.com/v1beta/openai',
                                 'key':'x','model':'gemini-3.8-flash','provider':'openai-compatible'},
                                [{'type':'text','text':'Return JSON'}],'one')
    assert len(attempts)==1
    assert 'private upstream detail' not in str(exc.value)


def test_minimax_401_points_to_key_without_leaking_response(monkeypatch):
    attempts=[]
    def handler(request):
        attempts.append(request)
        return httpx.Response(401,json={'error':{'message':'private upstream detail'}})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(RuntimeError,match='MiniMax 拒绝了当前密钥.*MINIMAX_API_KEY.*未通过鉴权') as exc:
        _provider_call({'base_url':'https://api.minimax.io/v1','key':'x',
                        'model':'MiniMax-M3','provider':'minimax'},
                       [{'type':'text','text':'Return JSON'}],'one')
    assert len(attempts)==1
    assert 'private upstream detail' not in str(exc.value)


def test_local_clip_has_no_audio_and_maps_source_time(tmp_path):
    from backend.minimax import video_content
    source=tmp_path/'原片.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=1280x720:rate=24',
                    '-f','lavfi','-i','sine=frequency=440','-t','2','-c:v','libx264','-threads','1','-c:a','aac',str(source)],check=True)
    class LocalWorker:
        def run(self,command,jid,output): subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    content=video_content(LocalWorker(),source,.87,2,'scan','job',tmp_path)
    assert 'source_time = 0.87' in content[0]['text']
    part=content[1]['video_url']
    encoded=part['url'].split(',',1)[1]
    decoded=tmp_path/'decoded.mp4';decoded.write_bytes(base64.b64decode(encoded))
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(decoded)]))
    assert not any(s['codec_type']=='audio' for s in probe['streams'])
    v=probe['streams'][0]
    assert v['width']<=768 and v['height']<=768
    assert abs(float(probe['format']['duration'])-1.13)<.05
    assert part['fps']==2
    assert not list(tmp_path.glob('minimax-*.mp4'))


def test_minimax_long_video_uses_explicit_call_budget(tmp_path,monkeypatch):
    monkeypatch.setenv('FAS_AI_PROVIDER','minimax')
    monkeypatch.setenv('FAS_AI_ENABLED','true')
    monkeypatch.setenv('FAS_AI_API_KEY','local-test-secret')
    monkeypatch.delenv('FAS_AI_BASE_URL',raising=False)
    monkeypatch.delenv('FAS_AI_MODEL',raising=False)
    store=Store(tmp_path/'data')
    with store.connect() as conn:
        conn.execute('INSERT INTO sessions(id,name,date,created_at) VALUES(?,?,?,?)',('s','test','2026-10-14',now()))
    mid=store.register('s',store.root/'source.mov','source.mov','gopro')['media_id']
    with store.connect() as conn:
        conn.execute('UPDATE media SET duration=22.14 WHERE id=?',(mid,))
        conn.execute("UPDATE jobs SET status='succeeded' WHERE media_id=?",(mid,))
    app=FastAPI();register_routes(app,store)
    ref=store.data/'derived'/'test-ref.jpg';ref.write_bytes(b'fixture')
    with store.connect() as conn:
        conn.execute('INSERT INTO target_references VALUES(?,?,?,?,?,?,?,?)',('ref','s',mid,0,'[0,0,0.2,0.2]','测试目标',str(ref),now()))
    with TestClient(app) as c:
        public=c.get('/api/analysis/config').json()
        assert public['provider']=='MiniMax' and public['input_mode']=='frames'
        assert public['trial_max_duration_s'] is None and public['trial_max_calls']==500
        assert 'local-test-secret' not in json.dumps(public)
        response=c.post(f'/api/media/{mid}/analyses',json={'max_calls':100})
        assert response.status_code==202,response.text
        assert response.json()['estimate']['max_calls']==100
        with store.connect() as conn: conn.execute('UPDATE media SET duration=600 WHERE id=?',(mid,))
        assert c.post(f'/api/media/{mid}/analyses',json={'provider':'minimax','max_calls':100}).status_code==422
        long_run=c.post(f'/api/media/{mid}/analyses',json={'provider':'minimax','max_calls':120})
        assert long_run.status_code==202,long_run.text
        assert long_run.json()['estimate']['scan_calls']==60
        assert long_run.json()['estimate']['max_calls']==120


def test_native_worker_cache_keeps_human_review(tmp_path,monkeypatch):
    import time
    import backend.analysis as analysis
    from backend.app import create_app
    from backend.worker import Worker
    monkeypatch.setenv('FAS_AI_PROVIDER','minimax')
    monkeypatch.setenv('FAS_AI_INPUT_MODE','video')
    monkeypatch.setenv('FAS_AI_ENABLED','true')
    monkeypatch.setenv('FAS_AI_API_KEY','offline-only')
    monkeypatch.delenv('FAS_AI_MODEL',raising=False)
    monkeypatch.delenv('FAS_AI_BASE_URL',raising=False)
    store=Store(tmp_path/'data')
    source=store.root/'fixture.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=24',
                    '-t','2','-c:v','libx264','-threads','1',str(source)],check=True)
    calls=[]
    def provider(cfg,content,key,check=None):
        calls.append(content)
        assert any(x['type']=='video_url' for x in content)
        return {'events':[{'start_s':.25,'end_s':.75,'event_type':'other',
               'event_confidence':.4,'identity_confidence':.1,'evidence':'offline test pattern',
               'identity_evidence':'none','description':'离线契约测试'}]}, {'total_tokens':20}
    monkeypatch.setattr(analysis,'_provider_call',provider)
    with TestClient(create_app(store,False)) as c:
        sid=c.post('/api/sessions',json={'name':'离线测试','date':'2026-10-14'}).json()['id']
        item=store.register(sid,source,source.name,'other');mid=item['media_id']
        with store.connect() as conn:
            conn.execute('UPDATE media SET duration=2 WHERE id=?',(mid,))
            conn.execute("UPDATE jobs SET status='succeeded' WHERE id=?",(item['job_id'],))
        ref=store.data/'derived'/'test-ref.jpg';ref.write_bytes(b'fixture')
        with store.connect() as conn:
            conn.execute('INSERT INTO target_references VALUES(?,?,?,?,?,?,?,?)',('ref',sid,mid,0,'[0,0,0.2,0.2]','测试目标',str(ref),now()))
        human=c.post(f'/api/sessions/{sid}/review-events',json={'media_id':mid,'start_s':0,'end_s':1,'description':'人工结果保持','decision':'keep','identity_status':'confirmed_target'}).json()
        worker=Worker(store);worker.start()
        try:
            for key in ('first','second'):
                response=c.post(f'/api/media/{mid}/analyses',json={'request_key':key,'max_calls':6})
                assert response.status_code==202,response.text
                job=response.json()['job_id'];deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    state=store.rows('SELECT * FROM jobs WHERE id=?',(job,))[0]
                    if state['status'] in {'succeeded','failed'}: break
                    time.sleep(.05)
                assert state['status']=='succeeded',state
            assert len(calls)==2  # scan + verify only; second run uses the same cache
            assert c.get(f'/api/sessions/{sid}/review-events').json()==[human]
            assert all(e['identity_status']=='uncertain' for e in c.get(f'/api/sessions/{sid}/candidates').json())
        finally:
            worker.stop()
