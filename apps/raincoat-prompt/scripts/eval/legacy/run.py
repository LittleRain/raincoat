#!/usr/bin/env python3
"""Dependency-free fixed-material evaluation. No automatic semantic scoring."""
import argparse
import concurrent.futures
import fnmatch
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import re
import platform
import subprocess
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / 'Sources/PromptCore/Resources/prompt-rules.json'
SCENES = dict(zip(['调研', '数据分析', '开发', '写方案', '写报告'], ['research', 'dataAnalysis', 'development', 'plan', 'report']))
SCENES['通用']='general'
TARGETS = {'bitto': ('bitto', 'deepseek-v4.1-flash'), 'workbuddy': ('workBuddy', 'kimi-k2.5'), 'gpt': ('codex', 'gpt-6.1-sol')}
COMPARISONS = [('B','A','通用改写收益'), ('C','B','场景收益'), ('D','C','Agent 适配收益'), ('E','D','模型规则收益'), ('C','A','A→C 总收益')]
COMPARISONS += [('Cprime','C',"候选 C' 相对场景基线"), ('Cprime','A',"候选 C' 总收益")]
COMPARISONS += [('Cdoubleprime','Cprime',"候选 C'' 相对 C'"), ('Cdoubleprime','A',"候选 C'' 总收益"), ('Cdoubleprime','C',"候选 C'' 相对场景基线")]
COMPARISONS += [('E','Cdoubleprime',"模型规则收益（冻结 C'' 基底）")]
TERMINAL = {'succeeded', 'completed', 'failed', 'cancelled', 'interrupted', 'timed_out'}

def model_key(label): return ''.join(c for c in (label or '').lower() if c.isalnum() or c=='.')
def eligible(run): return run['status']=='completed' and (not run.get('observed_model') or model_key(run['observed_model'])==model_key(run['model']))
def now(): return datetime.now(timezone.utc).isoformat()
def digest(data): return hashlib.sha256(data).hexdigest()
def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []
def append(path, data):
    with path.open('a') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())
def execute(cmd, timeout, cwd, stdin=None):
    try:
        p = subprocess.run(cmd, input=stdin, text=True, capture_output=True, cwd=cwd, timeout=timeout)
        return dict(command=cmd, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired as e:
        def txt(x): return x.decode(errors='replace') if isinstance(x, bytes) else (x or '')
        return dict(command=cmd, returncode=None, stdout=txt(e.stdout), stderr=txt(e.stderr), error=f'TimeoutExpired: {e}')
    except OSError as e:
        return dict(command=cmd, returncode=None, stdout='', stderr='', error=f'{type(e).__name__}: {e}')

def parse_local(raw):
    try: return json.loads(raw['stdout'])
    except (ValueError, KeyError): return {}

def local_call(run, directory, timeout):
    prompt = directory / 'prompt.txt'
    cwd = directory / 'workspace'; cwd.mkdir(exist_ok=True)
    cmd = ['local-agent','submit',run['target'],'--prompt-file',str(prompt),'--model',run['model'],
           '--cwd',str(cwd),'--title','Raincoat fixed-material evaluation','--timeout-seconds',str(timeout),'--wait-seconds','0']
    deadline = time.monotonic() + timeout
    raw = [execute(cmd, max(0.01, deadline-time.monotonic()), cwd)]
    state = parse_local(raw[-1]); job_id = state.get('job_id')
    while job_id and state.get('status') not in TERMINAL and time.monotonic() < deadline:
        remaining=deadline-time.monotonic()
        raw.append(execute(['local-agent','wait',job_id,'--timeout-seconds',str(min(25,remaining))], max(0.01,remaining), cwd))
        next_state = parse_local(raw[-1])
        if not next_state: break
        state = next_state
    # Full state avoids local-agent compact's 32000-character truncation. Preserve it in raw.json.
    full_path = state.get('result_path')
    if full_path and Path(full_path).is_file():
        try: state = json.loads(Path(full_path).read_text())
        except (OSError, ValueError): pass
    if job_id and state.get('status') not in TERMINAL:
        # Only cancellation acknowledgement gets a separate, bounded cleanup allowance.
        raw.append(execute(['local-agent','cancel',job_id], 2, cwd))
        state['runner_error'] = 'Backend did not finish before deadline / wait failed; cancellation attempted (see raw acknowledgement)'
    answer = state.get('text', '')
    success = state.get('status') in ('succeeded', 'completed') and bool(answer.strip()) and not state.get('text_truncated')
    return dict(status='completed' if success else 'failed', answer=answer,
                error=None if success else dict(backend_error=state.get('error'), backend_status=state.get('status'),
                    runner_error=state.get('runner_error'), raw_error=raw[-1]),
                observed_model=state.get('model'), model_evidence='local-agent state label (not provider attestation)',
                tokens=state.get('usage') or state.get('message_usage') or None,
                tool_call_count=len(state['tool_calls']) if 'tool_calls' in state else state.get('tool_call_count'),
                job_id=job_id, raw=dict(commands=raw, state=state))

def codex_call(run, directory, timeout):
    cwd = directory / 'workspace'; cwd.mkdir(exist_ok=True)
    answer_path = directory / 'answer.txt'
    cmd = ['codex','exec','--ephemeral','--json','--color','never','--skip-git-repo-check','--sandbox','read-only',
           '--model',run['model'],'--cd',str(cwd),'-o',str(answer_path),'-']
    raw = execute(cmd, timeout, cwd, run['prompt'])
    events = []
    for line in raw['stdout'].splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    answer = answer_path.read_text() if answer_path.exists() else ''
    completed = any(e.get('type') == 'turn.completed' for e in events)
    errors = [e for e in events if e.get('type') in ('error','turn.failed')]
    success = raw['returncode'] == 0 and completed and not errors and bool(answer.strip())
    return dict(status='completed' if success else 'failed', answer=answer,
                error=None if success else dict(events=errors, process=raw), observed_model=None,
                model_evidence='requested model only; codex JSON does not attest model',
                tokens=next((e.get('usage') for e in reversed(events) if e.get('usage')),None),
                tool_call_count=sum(e.get('item',{}).get('type') in ('command_execution','mcp_tool_call','web_search') for e in events),
                raw=raw)

def run_one(run, out, timeout):
    directory = out / 'raw' / run['id']; directory.mkdir(parents=True, exist_ok=True)
    (directory/'prompt.txt').write_text(run['prompt'])
    started = time.monotonic()
    try: result = (codex_call if run['target']=='gpt' else local_call)(run, directory, timeout)
    except Exception as e: result = dict(status='failed', answer='', error=f'{type(e).__name__}: {e}', tokens=None, raw={})
    write(directory/'raw.json',result.pop('raw'))
    return {**run, **result, 'finished_at':now(), 'duration_seconds':round(time.monotonic()-started,3), 'raw_path':str(directory.relative_to(out)/'raw.json')}

def select_cases(fixture, only):
    patterns = only.split(',')
    selected = fixture.get(only) if only in ('pilot','extended_pilot') else None
    cases = [c for c in fixture['cases'] if c['id'] in selected] if selected is not None else [c for c in fixture['cases'] if any(fnmatch.fnmatchcase(c['id'],p) or c['scene']==p or c['split']==p for p in patterns)]
    if only in ('pilot','extended_pilot') and selected is None: raise ValueError(f'Missing selection {only}')
    if not cases: raise ValueError(f'No cases match --only {only}')
    return cases

def plan(args):
    from validate_cases import main as validate_cases
    from validate_rules import validate
    validate_cases()
    validate(json.loads(CATALOG.read_text()))
    fixture = json.loads((ROOT/'docs/evaluation-cases.json').read_text())
    catalog = json.loads(CATALOG.read_text())
    harness_path=getattr(args,'harness_catalog',None)
    harness_catalog=None
    if harness_path:
        if not getattr(args,'rule',None) or 'D' not in args.versions.split(','):raise ValueError('Harness catalog requires D and explicit --rule')
        harness_path=Path(harness_path).resolve();harness_catalog=json.loads(harness_path.read_text())
        from harness_candidates import validate_harness_candidate
        validate_harness_candidate(harness_catalog,catalog)
    candidate_path = getattr(args, 'candidate_catalog', None)
    candidate = None
    candidate_versions = set(args.versions.split(',')) & {'Cprime','Cdoubleprime'}
    base_version=getattr(args,'base_version','D')
    if 'E' in args.versions.split(',') and base_version=='Cdoubleprime':candidate_versions.add('Cdoubleprime')
    if candidate_versions:
        if not candidate_path: raise ValueError('Candidate version requires --candidate-catalog (unpublished evaluation only)')
        candidate_path = Path(candidate_path).resolve()
        candidate = json.loads(candidate_path.read_text())
        from validate_rules import validate_candidate
        validate_candidate(candidate, catalog)
        expected={'Cprime':'0.2.0-candidate','Cdoubleprime':'0.2.1-candidate'}
        if any(candidate['version']!=expected[v] for v in candidate_versions):raise ValueError('Candidate version/catalog mismatch; evaluate each snapshot separately')
    cases = select_cases(fixture,args.only)
    binary = Path(args.composer).resolve()
    if not binary.is_file(): raise ValueError('Build composer first: bash scripts/build-app.sh')
    runs=[]
    for case in cases:
        for target in args.targets.split(','):
            swift_target, model = TARGETS[target]
            model = args.models.get(target,model)
            for repeat in range(1,args.repeat+1):
                for version in args.versions.split(','):
                    scene = getattr(args,'scene_override',None) or SCENES[case['scene']]
                    scene_title=next(k for k,v in SCENES.items() if v==scene)
                    # E always changes exactly one matching model rule, or is rejected before calls.
                    rule = next((r for r in catalog['rules'] if r['kind']=='model' and r['target']==swift_target and r['scene']==scene and r.get('model')==model and (not args.rule or r['id']==args.rule)),None) if version=='E' else None
                    if version=='E' and not rule: raise ValueError(f'E has no matching model rule: {case["id"]}/{target}/{model}')
                    harness_rule=next((r for r in harness_catalog['rules'] if r['id']==args.rule and r['kind']=='harness' and r['target']==swift_target and r['scene']==scene),None) if version=='D' and harness_catalog else None
                    if version=='D' and harness_catalog and not harness_rule:raise ValueError('Selected harness rule does not match case target/scene')
                    cmd=[str(binary),'--eval-compose',version,swift_target,scene,model]
                    if harness_rule:cmd=[str(binary),'--candidate-harness-compose',str(harness_path),swift_target,scene,model,harness_rule['id']]
                    if version in ('Cprime','Cdoubleprime'):cmd=[str(binary),'--candidate-compose',str(candidate_path),swift_target,scene,model]
                    if version=='E' and base_version=='Cdoubleprime':cmd=[str(binary),'--candidate-model-compose',str(candidate_path),swift_target,scene,model,rule['id']]
                    elif rule:cmd.append(rule['id'])
                    composed=execute(cmd,15,ROOT,case['input'])
                    if composed['returncode']!=0 or not composed['stdout'].strip(): raise ValueError(f'Composer failed: {composed}')
                    if rule and composed['stdout'].count(rule['instruction'])!=1:raise ValueError(f'Model rule did not apply exactly once: {rule["id"]}/{case["id"]}')
                    if harness_rule:
                        control=execute([str(binary),'--eval-compose','C',swift_target,scene,model],15,ROOT,case['input'])
                        if control['returncode']!=0 or composed['stdout'].count(harness_rule['instruction'])!=1 or composed['stdout'].strip().replace('\n\n'+harness_rule['instruction'],'',1)!=control['stdout'].strip():raise ValueError('D changed more than one harness rule or was a no-op')
                    if version=='E' and base_version=='Cdoubleprime':
                        control=execute([str(binary),'--candidate-compose',str(candidate_path),swift_target,scene,model],15,ROOT,case['input'])
                        if control['returncode']!=0 or composed['stdout'].strip().replace('\n\n'+rule['instruction'],'',1)!=control['stdout'].strip():raise ValueError('E changed more than one model rule from frozen Cdoubleprime')
                    prompt=fixture['common_instruction']+'\n\n'+composed['stdout'].strip()+'\n\n材料\n'+'\n'.join(case['materials'])
                    run=dict(id=f'{case["id"]}--{target}--{version}--{repeat}',case=case['id'],scene=scene_title,split=case['split'],version=version,target=target,model=model,repeat=repeat,prompt=prompt,model_rule=rule['id'] if rule else None)
                    if getattr(args,'scene_override',None):run['source_scene']=case['scene']
                    if version=='E':run['model_base_version']=base_version
                    if harness_rule:run['harness_rule']=harness_rule['id']
                    runs.append(run)
    random.Random(args.seed).shuffle(runs)
    source_hashes={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in sorted((ROOT/'Sources').rglob('*.swift'))}
    return dict(schema_version=1,created_at=now(),seed=args.seed,fixture_sha256=digest((ROOT/'docs/evaluation-cases.json').read_bytes()),rules_sha256=digest(CATALOG.read_bytes()),composer_sha256=digest(binary.read_bytes()),source_hashes=source_hashes,catalog=catalog,candidate_catalog=candidate,candidate_sha256=digest(candidate_path.read_bytes()) if candidate else None,harness_catalog=harness_catalog,harness_catalog_sha256=digest(harness_path.read_bytes()) if harness_catalog else None,runner_sha256=digest(Path(__file__).read_bytes()),environment=dict(platform=platform.platform(),local_agent=execute(['local-agent','--version'],10,ROOT),codex=execute(['codex','--version'],10,ROOT)),runs=runs,cases=cases)

def review_materials(out, plan_data, runs):
    grouped={}
    for r in runs:
        if eligible(r): grouped.setdefault((r['case'],r['target'],r['model'],r['repeat']),{})[r['version']]=r
    private={}; pending=[]; blind=out/'blind-review';blind.mkdir(exist_ok=True)
    for key, versions in sorted(grouped.items()):
        for newer,older,_ in COMPARISONS:
            if newer not in versions or older not in versions: continue
            if versions[newer].get('prompt') is not None and versions[newer]['prompt']==versions[older].get('prompt'): continue
            pair_id=digest(('|'.join(map(str,key))+newer+older+str(plan_data['seed'])).encode())[:16]
            pair=[versions[newer],versions[older]]
            random.Random(pair_id).shuffle(pair)
            case=next(c for c in plan_data['cases'] if c['id']==key[0])
            # No prompt, target, model, version, run id or mapping in reviewer directory.
            packet=dict(pair_id=pair_id,task=case['input'],materials=case['materials'],checks=case['checks'],critical_errors=case['critical_errors'],responses={side:r['answer'] for side,r in zip(['A','B'],pair)})
            write(blind/(pair_id+'.json'),packet)
            private[pair_id]=dict(sides={side:r['id'] for side,r in zip(['A','B'],pair)},newer=newer,older=older,case=key[0],target=key[1],repeat=key[3])
            pending.append(dict(pair_id=pair_id,reviewer='',reviewed_at=None,status='pending',scores={side:dict(core=[None]*3,bonus=None,critical_errors=[],evidence='') for side in ['A','B']}))
    write(out/'private-mapping.json',private)
    write(out/'review-template.json',pending)
    return private

def validate_reviews(reviews, mapping):
    seen=set()
    for review in reviews:
        assert set(review)=={'pair_id','reviewer','reviewed_at','status','scores'}
        pid=review['pair_id'];assert re.fullmatch('[a-f0-9]{16}',pid), 'Invalid pair ID'
        assert pid in mapping and pid not in seen, f'Unknown/duplicate pair {pid}';seen.add(pid)
        assert review.get('status')=='completed' and isinstance(review.get('reviewer'),str) and review['reviewer'].strip() and review.get('reviewed_at'), 'Incomplete reviewer metadata'
        assert datetime.fromisoformat(review['reviewed_at'].replace('Z','+00:00')).utcoffset() is not None, 'reviewed_at requires timezone'
        assert set(review['scores'])=={'A','B'}
        for score in review['scores'].values():
            assert set(score)=={'core','bonus','critical_errors','evidence'}
            assert len(score['core'])==3 and all(type(v) is bool for v in score['core']), 'core needs 3 booleans'
            assert type(score['bonus']) is bool and isinstance(score['critical_errors'],list) and all(isinstance(x,str) and x.strip() for x in score['critical_errors'])
            assert isinstance(score['evidence'],str) and score['evidence'].strip(), 'Scoring needs evidence'

def score_key(score): return (-int(bool(score['critical_errors'])), sum(score['core']), int(score['bonus']))
def report(out):
    p=json.loads((out/'plan.json').read_text());runs=lines(out/'runs.jsonl')
    mapping=review_materials(out,p,runs)
    reviews=lines(out/'reviews.jsonl');validate_reviews(reviews,mapping)
    byid={r['id']:r for r in runs}; outcomes={};critical=[]
    for review in reviews:
        m=mapping[review['pair_id']]; scores=review['scores']
        side_new=next(s for s,rid in m['sides'].items() if byid[rid]['version']==m['newer'])
        diff=(score_key(scores[side_new])>score_key(scores['B' if side_new=='A' else 'A']))-(score_key(scores[side_new])<score_key(scores['B' if side_new=='A' else 'A']))
        outcomes[review['pair_id']]=diff
        for side,score in scores.items():
            if score['critical_errors']:critical.append(f'{m["sides"][side]}: {"；".join(score["critical_errors"])}')
    success=sum(r['status']=='completed' for r in runs)
    note=json.loads((out/'execution-note.json').read_text()) if (out/'execution-note.json').exists() else None
    text=['# 扩展评测报告','',f'计划 {len(p["runs"])} 次；已记录 {len(runs)} 次，成功 {success}，失败 {len(runs)-success}。匿名可评 {len(mapping)} 对；已评分 {len(reviews)} 对。',
          '', '固定合成材料、独立新会话、单次默认运行。不同环境使用不同模型，不能据此拆分模型与 harness 的因果贡献。未评分不计平局；调用失败不计质量败。',
          '', '| 对照 | 胜 | 平 | 负 | 已评分/有效配对 | 状态 |','| --- | ---: | ---: | ---: | --- | --- |']
    for n,o,label in COMPARISONS:
        ids=[pid for pid,m in mapping.items() if m['newer']==n and m['older']==o];vals=[outcomes[i] for i in ids if i in outcomes]
        text.append(f'| {label} ({n}/{o}) | {vals.count(1)} | {vals.count(0)} | {vals.count(-1)} | {len(vals)}/{len(ids)} | '+('未覆盖' if not ids else ('待评分' if len(vals)<len(ids) else '已评分，仍需复次与保留题'))+' |')
    if note:text += ['', '**未执行原因：** '+note['reason']]
    text += ['', '## 逐题运行与配对','', '| 题目 | 场景 | 环境/请求模型 | 版本/状态/秒/可见型号 | 配对结果 |','| --- | --- | --- | --- | --- |']
    groups={}
    for r in runs:groups.setdefault((r['case'],r['scene'],r['target'],r['model'],r['repeat']),[]).append(r)
    for k,rs in sorted(groups.items()):
        pair_results=[]
        for pid,m in mapping.items():
            if m['case']==k[0] and m['target']==k[2] and m['repeat']==k[4]:pair_results.append(f'{m["newer"]}/{m["older"]}: '+({1:'胜',0:'平',-1:'负'}[outcomes[pid]] if pid in outcomes else '待评分'))
        text.append(f'| {k[0]} (r{k[4]}) | {k[1]} | {k[2]}/{k[3]} | '+', '.join(f'{r["version"]}/{r["status"]}/{r["duration_seconds"]}/{r.get("observed_model") or "未知"}' for r in sorted(rs,key=lambda r:r['version']))+' | '+'；'.join(pair_results)+' |')
    text += ['', '## 覆盖缺口','']
    text.append(f'- 计划中尚未得到运行记录 {len(p["runs"])-len(runs)} 次；无操作（两版提示词完全相同）的配对不进入评分。')
    for scene in SCENES:
        rs=[r for r in runs if r['scene']==scene and r['status']=='completed'];text.append(f'- {scene}：{len(set(r["case"] for r in rs))} 题，{len(set(r["target"] for r in rs))} 环境，{len(rs)} 份有效回答。')
    mismatches=[r['id'] for r in runs if r['status']=='completed' and not eligible(r)]
    text.append(f'- 可见型号与请求型号冲突而排除的回答 {len(mismatches)} 份：'+('、'.join(mismatches) or '无')+'。型号未知仍可评整体交付，但不能发布模型规则。')
    text += [f'- 保留题成功运行 {sum(r["status"]=="completed" and r["split"]=="holdout" for r in runs)} 次；未列入计划的题目与目标均未覆盖。',
             '- 固定材料不验证真实联网、SQL、工作区检索或代码落地；开发题仅验证补丁建议与验收推理。',
             '- token 缺失保留 null；后端标签不代表供应商签名型号；没有价格数据，不估造费用。',
             '- 通用、场景、Agent、模型的独立收益只由各自相邻版本配对支持；A/C 不能单独证明场景收益。',
             '', '## 关键失败与运行错误','']
    text += ['- '+s for s in critical] or ['- 已评分答案未记录关键错误。' if reviews else '- 答案关键错误尚待评分。']
    error_groups={}
    for r in runs:
        if r['status']=='failed':
            error=r['error']
            raw_error=error.get('raw_error') or error.get('process') or {} if isinstance(error,dict) else {}
            message=raw_error.get('stderr') or raw_error.get('error') or str(error)
            error_groups[message]=error_groups.get(message,0)+1
    for error,count in error_groups.items():text += [f'\n{count} 次相同运行错误（原文）：', '```text',error.rstrip(),'```']
    if any(r['status']=='failed' for r in runs):text += ['', '每次失败的原始命令与完整错误见 runs.jsonl 及 raw/<运行ID>/raw.json；运行ID为 `<题号>--<环境>--<版本>--<repeat>`。']
    text += ['', '## 可追溯性','',f'- 题库 SHA256：`{p["fixture_sha256"]}`',f'- 规则 SHA256：`{p["rules_sha256"]}`',f'- 生成器 SHA256：`{p["composer_sha256"]}`', '- plan.json 固化完整提示词和源码哈希；attempts.jsonl 记录调用预约，runs.jsonl 保存原始回答，raw/ 保存后端原始输出。', '- blind-review/ 仅含匿名材料。private-mapping.json、runs.jsonl、plan.json 不交给盲评者。reviews.jsonl 不存在时，报告只呈现运行覆盖。','']
    if p.get('invocations'):text += ['- 增量运行的独立提示词、生成器与运行器快照保存在invocations/，原始计划保存在plan.initial.json。','']
    if CATALOG.exists() and digest(CATALOG.read_bytes())!=p['rules_sha256']:text += ['- 当前规则文件与本轮快照不同；本轮证据仅对应计划中的规则哈希。','']
    (out/'report.md').write_text('\n'.join(text))
    print(out/'report.md')


def prepare_increment(out, requested, invocation_id):
    """Merge compatible plans and identify IDs that have never been submitted."""
    plan_path = out / 'plan.json'
    previous = json.loads(plan_path.read_text()) if plan_path.exists() else None
    if previous and previous['seed'] != requested['seed']:
        raise ValueError('Existing output uses a different seed; keep --seed unchanged')

    merged = dict(previous or requested)
    planned = {run['id']: run for run in merged['runs']}
    cases = {case['id']: case for case in merged['cases']}
    for case in requested['cases']:
        if case['id'] in cases and cases[case['id']] != case:
            raise ValueError(f'Case materials or scoring changed: {case["id"]}')
        cases[case['id']] = case
    for run in requested['runs']:
        existing = planned.get(run['id'])
        if existing:
            for field in ('prompt', 'model', 'scene', 'split', 'model_rule', 'model_base_version', 'source_scene', 'harness_rule'):
                if existing.get(field) != run.get(field):
                    raise ValueError(f'Existing run {run["id"]} has a different {field}; use another --out')
        else:
            planned[run['id']] = run

    records = lines(out / 'runs.jsonl')
    recorded = {run['id']: run for run in records}
    if len(recorded) != len(records):
        raise ValueError('Duplicate IDs in runs.jsonl; inspect the existing records')
    attempted = {attempt['id'] for attempt in lines(out / 'attempts.jsonl')}
    pending = []
    skipped = dict(completed=0, failed=0, unfinished=0)
    for run in requested['runs']:
        existing = recorded.get(run['id'])
        if existing:
            for field in ('prompt', 'model'):
                if existing.get(field) != run.get(field):
                    raise ValueError(f'Recorded run {run["id"]} has a different {field}')
            category = 'completed' if existing['status'] == 'completed' else 'failed'
            skipped[category] += 1
        elif run['id'] in attempted:
            skipped['unfinished'] += 1
        else:
            pending_run = {**run, 'invocation_id': invocation_id}
            pending.append(pending_run)
            planned[run['id']] = pending_run
    merged['runs'] = list(planned.values())
    merged['cases'] = list(cases.values())
    merged['updated_at'] = now()
    merged['invocations'] = [*merged.get('invocations', []), f'invocations/{invocation_id}.json']
    return merged, pending, skipped, previous


def run_matrix(args):
    requested = plan(args)
    invocation_id = uuid.uuid4().hex
    merged, pending, skipped, previous = prepare_increment(args.out, requested, invocation_id)
    invocation = {**requested, 'pending_ids': [run['id'] for run in pending],
                  'skipped': skipped, 'dry_run': args.dry_run, 'max_new_calls': args.max_calls}
    invocation_path = args.out / 'invocations' / f'{invocation_id}.json'
    write(invocation_path, invocation)
    print(f'New calls: {len(pending)}; reused completed: {skipped["completed"]}; '
          f'existing failures: {skipped["failed"]}; unfinished attempts: {skipped["unfinished"]}', flush=True)
    if args.dry_run:
        if previous is None:
            write(args.out / 'plan.json', requested)
        print(f'Dry run plan: {invocation_path}')
        return 0

    initial = args.out / 'plan.initial.json'
    if previous is not None and not initial.exists():
        write(initial, previous)
    temporary = args.out / 'plan.json.tmp'
    write(temporary, merged)
    temporary.replace(args.out / 'plan.json')
    note = args.out / 'execution-note.json'
    if len(pending) > args.max_calls:
        write(note, dict(reason=f'新增计划 {len(pending)} 次超过提交上限 {args.max_calls}，本次未调用后端。'))
        report(args.out)
        return 1
    note.unlink(missing_ok=True)

    queues = {target: iter([run for run in pending if run['target'] == target])
              for target in args.targets.split(',')}
    failed = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(queues)) as pool:
        futures = {}
        def schedule(target):
            run = next(queues[target], None)
            if run is None:
                return
            append(args.out / 'attempts.jsonl', dict(id=run['id'], target=target,
                   invocation_id=invocation_id, started_at=now()))
            futures[pool.submit(run_one, run, args.out, args.timeout)] = target
        for target in queues:
            schedule(target)
        while futures:
            done, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                target = futures.pop(future)
                result = future.result()
                append(args.out / 'runs.jsonl', result)
                failed |= result['status'] == 'failed'
                print(f'{result["id"]}: {result["status"]} ({result["duration_seconds"]}s)', flush=True)
                report(args.out)
                schedule(target)
    report(args.out)
    return int(failed)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only',default='extended_pilot',help='pilot / extended_pilot / comma-separated case globs, scenes or splits')
    parser.add_argument('--targets',default='bitto,workbuddy')
    parser.add_argument('--versions',default='A,C')
    parser.add_argument('--repeat',type=int,default=1)
    parser.add_argument('--seed',type=int,default=20261117)
    parser.add_argument('--model',action='append',default=[],help='target=model override')
    parser.add_argument('--rule',help='one candidate model rule ID for E, or harness rule for explicit harness catalog D')
    parser.add_argument('--harness-catalog',type=Path,help='unpublished harness catalog for D; preserves published scenes and default composer behavior')
    parser.add_argument('--composer',default=str(ROOT/'dist/Raincoat Prompt.app/Contents/MacOS/RaincoatPrompt'))
    parser.add_argument('--candidate-catalog',type=Path,help='unpublished scene catalog used only by version Cprime')
    parser.add_argument('--base-version',choices=['D','Cdoubleprime'],default='D',help='E baseline; Cdoubleprime adds exactly one model rule without harness candidates')
    parser.add_argument('--scene-override',choices=list(SCENES.values()),help='explicit scene selection for both versions; records original case scene separately')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--report-only',action='store_true')
    parser.add_argument('--timeout',type=int,default=180)
    parser.add_argument('--max-calls',type=int,default=60)
    args=parser.parse_args();args.out=args.out.resolve()
    if args.report_only: report(args.out);return
    if not 1<=args.repeat or not 1<=args.max_calls<=60 or not 1<=args.timeout<=3600:parser.error('repeat >=1, max-calls 1..60, timeout 1..3600')
    if not set(args.targets.split(','))<=TARGETS.keys() or not set(args.versions.split(','))<=set('ABCDE')|{'Cprime','Cdoubleprime'}:parser.error('Unknown target/version')
    if len(set(args.targets.split(',')))!=len(args.targets.split(',')) or len(set(args.versions.split(',')))!=len(args.versions.split(',')):parser.error('Duplicate targets/versions')
    args.models=dict(s.split('=',1) for s in args.model)
    if not args.models.keys()<=TARGETS.keys():parser.error('Unknown model override target')
    os.environ['PATH']='/Users/raincai/.nvm/versions/node/v24.14.0/bin:'+os.environ['PATH']
    args.out.mkdir(parents=True,exist_ok=True)
    os.environ['LOCAL_AGENT_MCP_STATE_DIR']=str(args.out/'backend-state')
    with (args.out / '.runner.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another evaluation is using this --out directory')
        return run_matrix(args)

if __name__=='__main__':raise SystemExit(main())
