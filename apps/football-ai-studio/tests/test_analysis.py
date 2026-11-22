import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.core import Store, now
from backend.analysis import register_routes, windows, validate_events, analyze, continuous_bounds, same_play, merge_play


def test_continuous_candidate_keeps_context_without_erasing_distinct_plays():
    assert continuous_bounds(15,17,22) == (13,20)
    assert continuous_bounds(.5,24,25) == (0,25)
    first = {'event_type':'dribble','start_s':10,'end_s':13}
    same = {'event_type':'dribble','start_s':11,'end_s':13.5}
    next_play = {'event_type':'dribble','start_s':12.5,'end_s':16}
    assert same_play(first,same)
    assert not same_play(first,next_play)
    overlapping_other = {'event_type':'tackle','start_s':10.2,'end_s':13.2,'event_confidence':.6}
    assert same_play(first,overlapping_other)
    merged=merge_play({**first,'event_confidence':.8},overlapping_other)
    assert (merged['start_s'],merged['end_s'],merged['event_type']) == (10,13.2,'dribble')


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv('FAS_AI_ENABLED', raising=False)
    store = Store(tmp_path / 'data', tmp_path / 'media')
    with store.connect() as c:
        c.execute('INSERT INTO sessions(id,name,date,created_at) VALUES(?,?,?,?)', ('s','test','2026-10-14',now()))
    media = store.root / 'test.mp4'
    media.write_bytes(b'video fixture')
    mid = store.register('s', media, media.name, 'iphone')['media_id']
    with store.connect() as c:
        c.execute('UPDATE media SET duration=25 WHERE id=?', (mid,))
        c.execute("UPDATE jobs SET status='succeeded' WHERE media_id=?",(mid,))
    app = FastAPI()
    register_routes(app, store)
    ref=store.data/'derived'/'test-ref.jpg'
    ref.write_bytes(b'fixture')
    with store.connect() as c:
        c.execute('INSERT INTO target_references VALUES(?,?,?,?,?,?,?,?)',('ref','s',mid,0,'[0,0,0.2,0.2]','测试目标',str(ref),now()))
    return store, TestClient(app), mid


def enable(monkeypatch):
    monkeypatch.setenv('FAS_AI_ENABLED', 'true')
    monkeypatch.setenv('FAS_AI_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('FAS_AI_MODEL', 'vision-test')
    monkeypatch.setenv('FAS_AI_API_KEY', 'private-key')


def test_disabled_no_jobs_or_secrets(setup):
    store, client, mid = setup
    assert client.get('/api/analysis/config').json()['enabled'] is False
    assert client.post(f'/api/media/{mid}/analyses', json={}).status_code == 409
    assert store.rows("SELECT * FROM jobs WHERE type='analysis'") == []
    assert client.get('/api/sessions/s/candidates').json() == []


def test_scan_requires_saved_target(setup, monkeypatch):
    store, client, mid = setup
    enable(monkeypatch)
    with store.connect() as conn:
        conn.execute('DELETE FROM target_references WHERE session_id=?',('s',))
    response=client.post(f'/api/media/{mid}/analyses',json={'max_calls':6})
    assert response.status_code==409
    assert '保存目标人物' in response.json()['detail']


def test_delete_target_reference_updates_scan_gate(setup, monkeypatch):
    store, client, mid = setup
    enable(monkeypatch)
    assert client.delete('/api/sessions/s/target-references/missing').status_code == 404
    response=client.delete('/api/sessions/s/target-references/ref')
    assert response.status_code==200
    assert response.json()['remaining']==[]
    assert client.get('/api/sessions/s/target-references').json()==[]
    assert client.post(f'/api/media/{mid}/analyses',json={'max_calls':6}).status_code==409


def test_full_windows_and_validation():
    spans = windows(25, 12, 2)
    assert spans == [(0,12),(10,22),(20,25)]
    valid = validate_events({'events':[{'start_s':1,'end_s':3,'event_type':'goal','event_confidence':.8,'identity_confidence':.7,'identity_status':'confirmed_target','evidence':'ball enters goal','identity_evidence':'shirt','description':'goal'}]}, 0, 12)
    assert valid[0]['identity_status'] == 'uncertain'
    clipped=validate_events({'events':[{**valid[0],'start_s':-1,'end_s':30}]},0,12)
    assert (clipped[0]['start_s'],clipped[0]['end_s']) == (0,12)
    assert '已截取' in clipped[0]['uncertainty']
    assert validate_events({'events':[{**valid[0],'start_s':15,'end_s':20}]},0,12)==[]
    with pytest.raises(ValueError):
        validate_events({'events':[{**valid[0],'start_s':4,'end_s':3}]},0,12)


def test_idempotency_and_budget(setup, monkeypatch):
    store, client, mid = setup
    enable(monkeypatch)
    assert client.post(f'/api/media/{mid}/analyses', json={'max_calls':1}).status_code == 422
    body = {'request_key':'one', 'max_calls':12}
    first = client.post(f'/api/media/{mid}/analyses', json=body)
    assert first.status_code == 202, first.text
    again = client.post(f'/api/media/{mid}/analyses', json=body)
    assert again.json()['job_id'] == first.json()['job_id']
    assert 'private-key' not in client.get('/api/analysis/config').text
    assert len(store.rows("SELECT * FROM jobs WHERE type='analysis'")) == 1


def test_provider_choice_keeps_minimax_separate_from_gemini(setup, monkeypatch):
    from pathlib import Path
    import backend.analysis as analysis
    store, client, mid = setup
    enable(monkeypatch)
    monkeypatch.setenv('MINIMAX_API_KEY', 'minimax-secret')
    public = client.get('/api/analysis/config').json()
    assert public['profiles']['minimax']['available'] is True
    assert public['profiles']['minimax']['model'] == 'MiniMax-M3'
    assert public['profiles']['openai-compatible']['available'] is True
    assert 'minimax-secret' not in json.dumps(public)
    first = client.post(f'/api/media/{mid}/analyses', json={
        'provider':'minimax','request_key':'minimax-first','max_calls':6})
    assert first.status_code == 202, first.text
    frozen = json.loads(store.rows('SELECT config_json FROM analysis_runs WHERE id=?',
                                   (first.json()['id'],))[0]['config_json'])
    assert frozen['provider'] == 'minimax'
    assert frozen['model'] == 'MiniMax-M3'
    assert frozen['base_url'] == 'https://api.minimax.io/v1'
    calls=[]
    def provider(c,content,key,check=None):
        calls.append(c['provider'])
        return {'events':[]},{}
    monkeypatch.setattr(analysis,'_provider_call',provider)
    class OfflineWorker:
        def __init__(self): self.store=store
        def check(self,jid): pass
        def update(self,*args,**kwargs): pass
        def run(self,command,jid,output): Path(command[-1]).write_bytes(b'offline-jpeg')
    job=store.rows('SELECT * FROM jobs WHERE id=?',(first.json()['job_id'],))[0]
    analysis.analyze(OfflineWorker(),job)
    assert calls == ['minimax']*6
    assert len(store.rows('SELECT id FROM analysis_runs')) == 1
    assert client.post(f'/api/media/{mid}/analyses', json={
        'provider':'openai-compatible','request_key':'gemini-second','max_calls':6}).status_code == 202
    assert len(store.rows('SELECT id FROM analysis_runs')) == 2


def test_reference_validates_media_and_box(setup):
    _, client, mid = setup
    url='/api/sessions/s/target-references'
    assert client.post(url,json={'media_id':mid,'source_time':1,'box_normalized':[.8,.2,.5,.4]}).status_code == 422
    assert client.post(url,json={'media_id':'other','source_time':1,'box_normalized':[0,0,.5,.5]}).status_code == 404


def test_offline_worker_cache_and_no_identity_confirmation(setup, monkeypatch):
    from pathlib import Path
    import backend.analysis as analysis
    store, client, mid = setup
    enable(monkeypatch)
    calls=[]
    def provider(config, content, key, check=None):
        calls.append(key)
        return {'events':[{'start_s':1,'end_s':3,'event_type':'shot','event_confidence':.8,'identity_confidence':.95,
                           'evidence':'visible shot','identity_evidence':'similar shirt','description':'疑似射门','identity_status':'confirmed_target'}]}, {'total_tokens':123}
    monkeypatch.setattr(analysis,'_provider_call',provider)
    with store.connect() as c:
        c.execute('UPDATE media SET duration=4 WHERE id=?',(mid,))
    class OfflineWorker:
        def __init__(self):
            self.store=store
        def check(self,jid):
            pass
        def update(self,jid,**values):
            with store.connect() as c:
                c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),jid))
        def run(self,command,jid,output):
            Path(command[-1]).write_bytes(b'offline-jpeg')
    worker=OfflineWorker()
    for key in ('first','second'):
        result=client.post(f'/api/media/{mid}/analyses',json={'request_key':key}).json()
        job=store.rows('SELECT * FROM jobs WHERE id=?',(result['job_id'],))[0]
        analyze(worker,job)
    assert len(calls)==2  # scan + verify once; later run reuses both window responses
    candidates=client.get('/api/sessions/s/candidates').json()
    assert len(candidates)==1  # Only the latest successful run is shown.
    assert all(c['identity_status']=='uncertain' for c in candidates)
    assert all(c['identity_confidence']==.95 for c in candidates)
    assert store.rows('SELECT * FROM analysis_runs')[0]['coverage_json']!='[]'


def test_ambiguous_network_failure_never_rebilled(setup,monkeypatch):
    from pathlib import Path
    import backend.analysis as analysis
    store,client,mid=setup
    enable(monkeypatch)
    count=[]
    def failure(*args):
        count.append(1)
        raise RuntimeError('timeout')
    monkeypatch.setattr(analysis,'_provider_call',failure)
    class OfflineWorker:
        def __init__(self): self.store=store
        def check(self,jid): pass
        def update(self,*args,**kwargs): pass
        def run(self,command,jid,output): Path(command[-1]).write_bytes(b'offline-jpeg')
    result=client.post(f'/api/media/{mid}/analyses',json={}).json()
    job=store.rows('SELECT * FROM jobs WHERE id=?',(result['job_id'],))[0]
    for _ in range(2):
        with pytest.raises(RuntimeError):
            analyze(OfflineWorker(),job)
    assert len(count)==1


def test_unknown_request_requires_explicit_replay(setup,monkeypatch):
    store,client,mid=setup
    enable(monkeypatch)
    created=client.post(f'/api/media/{mid}/analyses',json={'request_key':'initial'}).json()
    with store.connect() as conn:
        conn.execute("UPDATE jobs SET status='failed',error='请求结果未确认' WHERE id=?",(created['job_id'],))
        conn.execute("INSERT INTO analysis_cache(hash,state,created_at) VALUES('unknown-window','pending',?)",(now(),))
        conn.execute("INSERT INTO analysis_requests(run_id,hash,created_at) VALUES(?,?,?)",(created['id'],'unknown-window',now()))
    row=client.get(f'/api/media/{mid}/analyses').json()[0]
    assert row['unknown_count']==1
    url=f"/api/analysis-runs/{created['id']}/retry-unknown"
    assert client.post(url,json={'confirm_possible_repeat_charge':False}).status_code==422
    assert store.rows("SELECT state FROM analysis_cache WHERE hash='unknown-window'")
    retry=client.post(url,json={'confirm_possible_repeat_charge':True})
    assert retry.status_code==202,retry.text
    assert retry.json()['replayed_unknown_requests']==1
    assert retry.json()['id']!=created['id']
    assert store.rows("SELECT state FROM analysis_cache WHERE hash='unknown-window'")==[]
    assert client.post(url,json={'confirm_possible_repeat_charge':True}).status_code==409


def test_gemini_read_timeout_is_longer_and_explained(monkeypatch):
    import httpx
    import backend.analysis as analysis
    seen={}
    class TimedOutResponse:
        async def __aenter__(self):
            raise httpx.ReadTimeout('slow response')
        async def __aexit__(self,*args):
            pass
    class Client:
        def __init__(self,**kwargs):
            seen['read_timeout']=kwargs['timeout'].read
        async def __aenter__(self):
            return self
        async def __aexit__(self,*args):
            pass
        def stream(self,*args,**kwargs):
            return TimedOutResponse()
    monkeypatch.setattr(analysis.httpx,'AsyncClient',Client)
    with pytest.raises(RuntimeError,match='180 秒.*ReadTimeout'):
        analysis._provider_call({'base_url':'https://generativelanguage.googleapis.com/v1beta/openai','key':'x','model':'test','provider':'openai-compatible'},[],'key')
    assert seen['read_timeout']==180


def test_manual_sync_anchors_and_bounds(setup):
    from backend.sync import register_routes as sync_routes
    store,client,mid=setup
    sync_routes(client.app,store)
    url='/api/sessions/s/sync-mappings'
    response=client.put(url,json={'media_id':mid,'anchors':[{'source_time':0,'session_time':10},{'source_time':20,'session_time':30.02}]})
    assert response.status_code==200, response.text
    assert response.json()['offset_s']==pytest.approx(10)
    assert response.json()['drift_ratio']==pytest.approx(1.001)
    assert response.json()['method']=='manual_anchors'
    assert client.put(url,json={'media_id':mid,'anchors':[{'source_time':100,'session_time':10}]}).status_code==422
    assert len(client.get(url).json())==1


def test_sync_batch_is_atomic_and_reversible_group(setup):
    from backend.sync import register_routes as sync_routes
    from backend.review import register_routes as review_routes
    store,client,mid=setup
    sync_routes(client.app,store)
    review_routes(client.app,store)
    url='/api/sessions/s/sync'
    response=client.put(url,json={'mappings':[{'media_id':mid,'anchor_pairs':[[0,10],[20,30]],'verification_status':'manual'}]})
    assert response.status_code==200,response.text
    assert response.json()['mappings'][0]['offset_s']==10
    bad=client.put(url,json={'mappings':[{'media_id':mid,'offset_s':50},{'media_id':'wrong','offset_s':100}]})
    assert bad.status_code==404
    assert client.get(url).json()['mappings'][0]['offset_s']==10
    assert client.put(url,json={'mappings':[{'media_id':mid,'anchor_pairs':[[-1,10]]}]}).status_code==422
    second=store.register('s',store.root/'second.mp4','second.mp4','gopro')['media_id']
    with store.connect() as c:
        c.execute('UPDATE media SET duration=25 WHERE id=?',(second,))
    with store.connect() as c:
        c.execute("UPDATE jobs SET status='succeeded' WHERE type='preprocess'")
    ids=[]
    for asset in (mid,second):
        response=client.post('/api/sessions/s/review-events',json={'media_id':asset,'start_s':1,'end_s':3,'event_type':'shot'})
        assert response.status_code==201,response.text
        ids.append(response.json()['id'])
    response=client.post('/api/sessions/s/event-groups',json={'event_ids':ids,'description':'两机位同一射门'})
    assert response.status_code==201,response.text
    group=response.json()
    assert group['event_ids']==ids
    assert group['description']=='两机位同一射门'
    assert client.post('/api/sessions/s/event-groups',json={'event_ids':[ids[0],ids[0]]}).status_code==422
    assert client.delete('/api/event-groups/'+group['id']).status_code==200
    assert client.get('/api/sessions/s/event-groups').json()==[]
    assert len(client.get('/api/sessions/s/review-events').json())==2


def test_only_local_http_and_failed_preprocess_rejected(setup,monkeypatch):
    from backend.analysis import config
    store,client,mid=setup
    enable(monkeypatch)
    monkeypatch.setenv('FAS_AI_BASE_URL','http://remote.example/v1')
    assert config()['configured'] is False
    monkeypatch.setenv('FAS_AI_BASE_URL','http://127.0.0.1:1234/v1')
    assert config()['configured'] is True
    with store.connect() as c:
        c.execute("UPDATE jobs SET status='failed' WHERE media_id=?",(mid,))
    assert client.post(f'/api/media/{mid}/analyses',json={}).status_code==409


def test_provider_inflight_cancellation_is_bounded(monkeypatch):
    import asyncio
    import time
    import backend.analysis as analysis
    from backend.worker import Cancelled
    closed=[]
    class SlowClient:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): closed.append(True)
        def stream(self,*args,**kwargs): return SlowResponse()
    class SlowResponse:
        async def __aenter__(self):
            await asyncio.sleep(100)
        async def __aexit__(self,*args): pass
    monkeypatch.setattr(analysis.httpx,'AsyncClient',SlowClient)
    checks=[]
    def check():
        checks.append(1)
        if len(checks)>1: raise Cancelled()
    started=time.monotonic()
    with pytest.raises(Cancelled):
        analysis._provider_call({'base_url':'https://example.invalid/v1','key':'none','model':'test'},[],'key',check)
    assert time.monotonic()-started<2
    assert closed


def test_persisted_call_budget_and_cancel_before_publish(setup,monkeypatch):
    import backend.analysis as analysis
    from backend.worker import Cancelled
    from pathlib import Path
    store,client,mid=setup
    enable(monkeypatch)
    with store.connect() as c:
        c.execute('UPDATE media SET duration=4 WHERE id=?',(mid,))
    first=client.post(f'/api/media/{mid}/analyses',json={'max_calls':2}).json()
    jid=first['job_id']
    rid=first['run_id']
    with store.connect() as c:
        for key in ('paid-1','paid-2'):
            c.execute('INSERT INTO analysis_requests VALUES(?,?,?)',(rid,key,now()))
    class OfflineWorker:
        def __init__(self): self.store=store
        def check(self,jid): pass
        def update(self,*args,**kwargs): pass
        def run(self,command,jid,output): Path(command[-1]).write_bytes(b'offline-jpeg')
    def forbidden(*args): pytest.fail('budget must stop before provider I/O')
    monkeypatch.setattr(analysis,'_provider_call',forbidden)
    job=store.rows('SELECT * FROM jobs WHERE id=?',(jid,))[0]
    with pytest.raises(RuntimeError,match='此前尝试'):
        analyze(OfflineWorker(),job)
    # A late cancellation after the last network result is checked atomically at publication.
    second=client.post(f'/api/media/{mid}/analyses',json={}).json()
    jid=second['job_id']
    def cancel_provider(*args):
        with store.connect() as c:
            c.execute('UPDATE jobs SET cancel_requested=1 WHERE id=?',(jid,))
        return {'events':[]},{}
    monkeypatch.setattr(analysis,'_provider_call',cancel_provider)
    job=store.rows('SELECT * FROM jobs WHERE id=?',(jid,))[0]
    with pytest.raises(Cancelled):
        analyze(OfflineWorker(),job)
    assert store.rows('SELECT status FROM jobs WHERE id=?',(jid,))[0]['status']!='succeeded'
    assert client.get('/api/sessions/s/candidates').json()==[]
def test_union_keeps_events_found_in_only_one_pass():
    from backend.analysis import combine_window_candidates

    first = {'start_s': 15, 'end_s': 17, 'event_type': 'dribble', 'uncertainty': ''}
    second = {'start_s': 20, 'end_s': 21, 'event_type': 'shot', 'uncertainty': ''}
    combined = combine_window_candidates([first], [second])
    assert {event['event_type'] for event in combined} == {'dribble', 'shot'}
    assert all('漏报' in event['uncertainty'] or '未确认' in event['uncertainty'] for event in combined)


def test_two_labels_for_one_play_are_one_candidate():
    from backend.analysis import combine_window_candidates
    first={'start_s':1,'end_s':10,'event_type':'dribble','uncertainty':''}
    verified={'start_s':1.5,'end_s':10.5,'event_type':'tackle','uncertainty':''}
    assert combine_window_candidates([first],[verified]) == [verified]


def test_empty_first_pass_still_runs_review_and_keeps_candidate(setup, monkeypatch):
    from pathlib import Path
    import backend.analysis as analysis

    store, client, mid = setup
    enable(monkeypatch)
    with store.connect() as conn:
        conn.execute('UPDATE media SET duration=4 WHERE id=?', (mid,))
    calls = []

    def provider(config, content, key, check=None):
        calls.append(key)
        if len(calls) == 1:
            return {'events': []}, {'total_tokens': 10}
        return {'events': [{'start_s': 1, 'end_s': 2, 'event_type': 'dribble',
                            'event_confidence': .5, 'identity_confidence': .4,
                            'evidence': 'visible attempt', 'identity_evidence': 'red shirt',
                            'description': '疑似尝试过人'}]}, {'total_tokens': 20}

    class OfflineWorker:
        def __init__(self): self.store = store
        def check(self, jid): pass
        def update(self, jid, **values): pass
        def run(self, command, jid, output): Path(command[-1]).write_bytes(b'offline-jpeg')

    monkeypatch.setattr(analysis, '_provider_call', provider)
    result = client.post(f'/api/media/{mid}/analyses', json={'max_calls': 2}).json()
    job = store.rows('SELECT * FROM jobs WHERE id=?', (result['job_id'],))[0]
    analysis.analyze(OfflineWorker(), job)
    candidates = client.get('/api/sessions/s/candidates').json()
    assert len(calls) == 2
    assert len(candidates) == 1
    assert candidates[0]['event_type'] == 'dribble'
    assert '初扫漏报' in candidates[0]['uncertainty']
    assert candidates[0]['identity_status'] == 'uncertain'

