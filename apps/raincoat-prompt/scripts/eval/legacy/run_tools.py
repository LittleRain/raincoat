#!/usr/bin/env python3
"""Frozen real-workspace evaluation. No literal-only instruction or inline answers."""
import argparse,fcntl,json,os,shutil,time
from pathlib import Path
import run as ev
from tools_eval import validate_fixture,validate_candidate,snapshot,check,compare,PROTOCOL,IDS

def prompt(task,workspace,files):
    return task+'\n\n这是工具面开发任务。工作区绝对路径：'+str(workspace)+'。文件：'+', '.join(files)+'''。
请真实读取工作区核对文档与实现；允许文件读取工具和只读命令，不联网、不写入或修改任何文件。缺失脚本不可宣称执行成功。不要把文档的描述当运行记录。
最终提交JSON对象（可在作答前真实使用工具），字段为finding、evidence_id、citations、commands、limitations。
finding从equal_valid/equal_expired/owner_required/token_only/phase_only/started_flag_public/fen_to_yuan/yuan_direct/unknown中选择实际结论。evidence_id填写代码实际EVIDENCE_ID值，未读到则null。citations列出代码证据标签行和决定行为的实现行，每项{path:相对路径,line:真实行号,quote:逐字原文}。无法访问时citations为空，不猜内容。
commands列每条相关检查命令及status（not_run/succeeded/failed），未执行的给expected_output类型，不编实际值。无需执行验证脚本。limitations如实说明不能访问或尚未执行的部分。'''

def prepare(out,binary,candidate_path):
    fixture=json.loads((ev.ROOT/'docs/eval-cases-tools.json').read_text());validate_fixture(fixture)
    catalog=json.loads(ev.CATALOG.read_text());candidate=json.loads(candidate_path.read_text());validate_candidate(candidate,catalog)
    runs=[]
    for case in fixture['cases']:
        for target,(swift,model) in ev.TARGETS.items():
            if target=='gpt':continue
            rid='bitto-workspace-read' if target=='bitto' else 'workbuddy-no-tools';rule=next(r for r in candidate['rules'] if r['id']==rid)
            for version in ['C','D']:
                ident=f'{case["id"]}--{target}--{version}--1';opaque=ev.digest(ident.encode())[:24];directory=out/'raw'/opaque;workspace=directory/'workspace'
                cmd=[str(binary),'--eval-compose','C',swift,'development',model] if version=='C' else [str(binary),'--candidate-harness-compose',str(candidate_path),swift,'development',model,rid]
                composed=ev.execute(cmd,15,ev.ROOT,case['input']);assert composed['returncode']==0 and composed['stdout'].strip(),composed
                if version=='D':
                    control=ev.execute([str(binary),'--eval-compose','C',swift,'development',model],15,ev.ROOT,case['input'])
                    assert composed['stdout'].strip().replace('\n\n'+rule['instruction'],'',1)==control['stdout'].strip()
                text=prompt(composed['stdout'].strip(),workspace,case['files'])
                assert case['expected']['evidence_id'] not in text,'Ground truth leaked into answer prompt'
                runs.append(dict(id=ident,case=case['id'],scene='开发',split=case['split'],target=target,model=model,repeat=1,version=version,harness_rule=rid if version=='D' else None,prompt=text,workspace=str(workspace),raw_path=str(Path('raw')/opaque/'raw.json')))
    return dict(protocol=PROTOCOL,created_at=ev.now(),cases=fixture['cases'],metrics=fixture['metrics'],runs=runs,catalog=catalog,harness_catalog=candidate,fixture_sha256=ev.digest((ev.ROOT/'docs/eval-cases-tools.json').read_bytes()),candidate_sha256=ev.digest(candidate_path.read_bytes()),composer_sha256=ev.digest(binary.read_bytes()))

def evaluate(out):
    plan=json.loads((out/'plan.json').read_text());cases={c['id']:c for c in plan['cases']};checks=[];pairs=[];runs={r['id']:r for r in ev.lines(out/'runs.jsonl')}
    for r in runs.values():
        directory=out/Path(r['raw_path']).parent;raw=json.loads((directory/'raw.json').read_text());before=json.loads((directory/'before.json').read_text());after=json.loads((directory/'after.json').read_text())
        checks.append(check(r,cases[r['case']],raw,before,after))
    byid={c['run_id']:c for c in checks}
    for r in runs.values():
        if r['version']!='D':continue
        bid=r['id'].replace('--D--','--C--')
        if bid in byid:pairs.append(dict(case=r['case'],target=r['target'],rule=r['harness_rule'],base_id=bid,new_id=r['id'],**compare(byid[bid],byid[r['id']])))
    rules={}
    for rid in IDS:
        rs=[r for r in pairs if r['rule']==rid];w=sum(r['outcome']=='improved' for r in rs);l=sum(r['outcome']=='regression' for r in rs);complete=len(rs)==4 and all(r['status']=='completed' for r in rs)
        models=all(r.get('observed_model')==r['model'] for r in runs.values() if r['harness_rule']==rid or (r['version']=='C' and ev.TARGETS[r['target']][0]==IDS[rid][0]))
        rules[rid]=dict(improved=w,tie=sum(r['outcome']=='tie' for r in rs),regressed=l,complete=complete,observed_model_matches=models,passed=complete and models and w>=3 and l==0)
    result=dict(protocol=PROTOCOL,checks=checks,pairs=pairs,rules=rules);ev.write(out/'deterministic.json',result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ev.ROOT/'.build/evaluation/stage10/answers');p.add_argument('--composer',type=Path,default=ev.ROOT/'.build/debug/RaincoatPrompt');p.add_argument('--candidate-catalog',type=Path,default=ev.ROOT/'docs/candidates/harness-tools-v0.1.0.json');p.add_argument('--target',choices=['bitto','workbuddy']);p.add_argument('--timeout',type=int,default=240);p.add_argument('--dry-run',action='store_true');p.add_argument('--report-only',action='store_true');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    with (out/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.report_only:print(json.dumps(evaluate(out)['rules'],ensure_ascii=False));return
        plan=prepare(out,a.composer.resolve(),a.candidate_catalog.resolve())
        if (out/'plan.json').exists():
            old=json.loads((out/'plan.json').read_text());assert old['runs']==plan['runs'] and old['cases']==plan['cases'] and old['candidate_sha256']==plan['candidate_sha256'],'Tool plan changed; use a new output'
        else:ev.write(out/'plan.json',plan)
        done={r['id'] for r in ev.lines(out/'runs.jsonl')};attempted={r['id'] for r in ev.lines(out/'attempts.jsonl')}
        pending=[r for r in plan['runs'] if r['id'] not in done|attempted and (not a.target or r['target']==a.target)]
        assert len(attempted)+len(pending)<=16,'Answer budget exceeds16'
        print('Pending real answer calls:',len(pending),flush=True)
        if a.dry_run:return
        os.environ['LOCAL_AGENT_MCP_STATE_DIR']=str(out/'backend-state')
        for r in pending:
            directory=out/Path(r['raw_path']).parent;workspace=Path(r['workspace']);workspace.mkdir(parents=True)
            case=next(c for c in plan['cases'] if c['id']==r['case'])
            for name,body in case['files'].items():(workspace/name).write_text(body)
            (directory/'prompt.txt').write_text(r['prompt']);before=snapshot(workspace);ev.write(directory/'before.json',before)
            ev.append(out/'attempts.jsonl',dict(id=r['id'],created_at=ev.now()));start=time.monotonic()
            try:result=ev.local_call(r,directory,a.timeout)
            except Exception as error:result=dict(status='failed',answer='',error=str(error),observed_model=None,tokens=None,raw={})
            ev.write(directory/'raw.json',result.pop('raw'));ev.write(directory/'after.json',snapshot(workspace))
            row=dict(**r,**result,duration_seconds=round(time.monotonic()-start,3),finished_at=ev.now());ev.append(out/'runs.jsonl',row)
            print(row['id'],row['status'],row.get('tool_call_count'),flush=True)
        evaluate(out)

if __name__=='__main__':main()
