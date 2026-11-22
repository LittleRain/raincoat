#!/usr/bin/env python3
"""Reuse recorded answers; keep anonymous packets separate from private provenance."""
import argparse,copy,fnmatch,json,os,time,fcntl
from collections import defaultdict
from pathlib import Path
import run as ev
from judge import build_prompt,parse_output,validate_output,aggregate
JUDGES={'bitto':'deepseek-v4.1-flash','workbuddy':'kimi-k2.5'}
KEYS={'schema_version','id','pair_id','judge','requested_model','observed_model','mode','order','status','output','raw_response','error','duration_seconds','tokens','provenance'}

def validate_record(r,packet=None):
    if set(r)!=KEYS or r['schema_version']!=1 or r['judge'] not in JUDGES or r['mode'] not in ('pair','critical') or type(r['order']) is not int or r['order'] not in (0,1) or r['status'] not in ('completed','failed'):raise ValueError('Judge record schema mismatch')
    if not all(isinstance(r[k],str) and r[k] for k in ('id','pair_id','requested_model')) or not isinstance(r['raw_response'],str) or not isinstance(r['provenance'],dict):raise ValueError('Judge record field types')
    if r['observed_model'] is not None and not isinstance(r['observed_model'],str):raise ValueError('Invalid model field')
    if r['id']!=cid(r['pair_id'],r['judge'],r['order'],r['mode']):raise ValueError('Judge record identity differs')
    if r['duration_seconds'] is not None and (type(r['duration_seconds']) not in (int,float) or r['duration_seconds']<0):raise ValueError('Invalid duration')
    if r['status']=='completed':
        if r['error'] is not None:raise ValueError('Completed judge has error')
        validate_output(r['output'],r['mode'],packet)
    elif r['output'] is not None or r['error'] is None:raise ValueError('Failed judge needs error and null output')
    return r

def pair_identity(source,base,new,n,b):
    return ev.digest(json.dumps([str(source.resolve()),base,new,n['id'],n['model'],ev.digest(n['answer'].encode()),ev.digest(b['answer'].encode())],ensure_ascii=False).encode())[:24]

def prepare(out,source,base,new,only='*'):
    out=out.resolve();source=source.resolve()
    data=json.loads((source/'plan.json').read_text());runs={r['id']:r for r in ev.lines(source/'runs.jsonl')};mapping=json.loads((out/'private-mapping.json').read_text()) if (out/'private-mapping.json').exists() else {};selected=[]
    for n in runs.values():
        if n['version']!=new or n['status']!='completed' or not any(fnmatch.fnmatchcase(n['id'],p) or fnmatch.fnmatchcase(n['case'],p) for p in only.split(',')):continue
        oldid=n['id'].replace('--'+new+'--','--'+base+'--');b=runs.get(oldid)
        if not b or b['status']!='completed' or not n['answer'].strip() or not b['answer'].strip():continue
        if any(n.get(k)!=b.get(k) for k in ['case','target','model','repeat','scene','split']):raise ValueError('Pair metadata mismatch')
        pid=pair_identity(source,base,new,n,b);case=next(c for c in data['cases'] if c['id']==n['case'])
        entry=dict(source=str(source.resolve()),base=base,new=new,case=n['case'],target=n['target'],model=n['model'],repeat=n['repeat'],scene=n['scene'],split=n['split'],base_id=b['id'],new_id=n['id'],base_answer_sha256=ev.digest(b['answer'].encode()),new_answer_sha256=ev.digest(n['answer'].encode()))
        if pid in mapping and mapping[pid]!=entry:raise ValueError('Existing mapping changed')
        mapping[pid]=entry;selected.append(pid)
        for order in (0,1):
            a,z=(b,n) if order==0 else (n,b)
            packet=dict(pair_id=pid,task=case['input'],materials=case['materials'],core_checks=case['core_checks'],bonus_check=case['bonus_check'],critical_errors=case['critical_errors'],responses=dict(A=a['answer'],B=z['answer']))
            path=out/'blind-review'/f'{pid}-{order}.json'
            if path.exists() and json.loads(path.read_text())!=packet:raise ValueError('Existing anonymous packet changed')
            ev.write(path,packet)
    ev.write(out/'private-mapping.json',mapping)
    return sorted(selected)

def cid(pid,judge,order,mode):return ev.digest(f'{pid}|{judge}|{order}|{mode}'.encode())[:24]

def import_legacy(out,path,source,base,new):
    selected=prepare(out,source,base,new);mapping=json.loads((out/'private-mapping.json').read_text());bytag={mapping[p]['new_id']:p for p in selected};done={r['id']:r for r in ev.lines(out/'judges.jsonl')};raw=path.read_bytes();prefix=raw[:raw.rfind(b'\n')+1] if b'\n' in raw else b'';count=0
    dest=out/'legacy-snapshots'/f'{path.name}.{ev.digest(prefix)[:12]}'
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(prefix)
    for line_no,line in enumerate(prefix.splitlines(),1):
        old=json.loads(line);tag=old['tag']
        if tag not in bytag:raise ValueError('Legacy tag not in source pairs: '+tag)
        judge=old['judge'];pid=bytag[tag]
        if old.get('base',base)!=base or old.get('new',new)!=new:raise ValueError('Legacy comparison differs')
        orders=old.get('orders',[])
        if len(orders)!=2:
            ev.append(out/'legacy-errors.jsonl',dict(pair_id=pid,judge=judge,source=str(dest),line=line_no,error=old.get('error','missing orders')))
            continue # source error retained, never invent ties
        for order,o in enumerate(orders):
            if o['slot_order']!=(["A1","A2"] if order==0 else ["A2","A1"]):raise ValueError('Unknown legacy order')
            v=o.get('raw');text=o.get('reason','');ok=v in ('A','B','tie') and bool(text.strip());output=dict(verdict=v,reason=text) if ok else None
            if ok:
                expected=0 if v=='tie' else ((1 if v=='A' else 2) if order==0 else (2 if v=='A' else 1))
                if o['winner']!=expected:raise ValueError('Legacy order winner mapping corrupt')
            row=dict(schema_version=1,id=cid(pid,judge,order,'pair'),pair_id=pid,judge=judge,requested_model=old.get('model',JUDGES[judge]),observed_model=None,mode='pair',order=order,status='completed' if ok else 'failed',output=output,raw_response=text,error=None if ok else dict(legacy_error=old.get('error'),raw_verdict=v),duration_seconds=None,tokens=None,provenance=dict(kind='legacy_import',path=str(path),snapshot=str(dest),line=line_no,line_sha256=ev.digest(line),normalization='legacy stored verdict + original reason text; original may be truncated or contain extra JSON fields; not strict fresh-output validation',model_attestation='requested label only; original script did not retain backend state'))
            validate_record(row)
            if row['id'] in done:
                before=done[row['id']]
                if before['output']!=row['output'] or before['status']!=row['status']:raise ValueError('Conflicting duplicate legacy result')
                continue
            ev.append(out/'judges.jsonl',row);done[row['id']]=row;count+=1
    return count

def run_new(out,pids,judges,mode,timeout,max_calls,dry_run=False):
    out=out.resolve()
    done={r['id'] for r in ev.lines(out/'judges.jsonl')};attempted={r['id'] for r in ev.lines(out/'attempts.jsonl')};pending=[(p,j,i) for p in pids for j in judges for i in (0,1) if cid(p,j,i,mode) not in done|attempted]
    remaining=max_calls-len(attempted)
    if len(pending)>remaining:raise ValueError(f'Budget would exceed {max_calls} total new submissions in out: pending={len(pending)}, already={len(attempted)}')
    ev.write(out/'last-plan.json',dict(mode=mode,pairs=pids,judges=judges,pending=[dict(pair_id=p,judge=j,order=i) for p,j,i in pending],max_calls=max_calls,dry_run=dry_run))
    if dry_run:return len(pending)
    os.environ['LOCAL_AGENT_MCP_STATE_DIR']=str((out/'backend-state').resolve())
    for p,j,i in pending:
        ident=cid(p,j,i,mode);packet=json.loads((out/'blind-review'/f'{p}-{i}.json').read_text());directory=out/'raw'/ident;directory.mkdir(parents=True,exist_ok=True);prompt=build_prompt(packet,mode);(directory/'prompt.txt').write_text(prompt)
        ev.append(out/'attempts.jsonl',dict(id=ident,pair_id=p,judge=j,order=i,mode=mode,created_at=ev.now()));start=time.monotonic()
        try:result=ev.local_call(dict(target=j,model=JUDGES[j]),directory,timeout)
        except Exception as error:result=dict(status='failed',answer='',error=f'{type(error).__name__}: {error}',observed_model=None,tokens=None,raw={})
        ev.write(directory/'raw.json',result['raw']);output=None;error=result['error']
        if result['status']=='completed':
            try:
                if result['observed_model']!=JUDGES[j]:raise ValueError('Judge observed model differs from request')
                output=parse_output(result['answer'],mode,packet)
            except (ValueError,TypeError,KeyError) as exc:error=dict(validation_error=str(exc),raw_response=result['answer'])
        row=dict(schema_version=1,id=ident,pair_id=p,judge=j,requested_model=JUDGES[j],observed_model=result.get('observed_model'),mode=mode,order=i,status='completed' if output else 'failed',output=output,raw_response=result['answer'],error=error,duration_seconds=round(time.monotonic()-start,3),tokens=result.get('tokens'),provenance=dict(kind='local_call',raw_path=str(directory/'raw.json'),job_id=result.get('job_id'),created_at=ev.now()))
        validate_record(row,packet);ev.append(out/'judges.jsonl',row);print(ident,row['status'],flush=True)
    return len(pending)

def report(out):
    mapping=json.loads((out/'private-mapping.json').read_text());rows=ev.lines(out/'judges.jsonl');seen=set();groups={}
    for r in rows:
        validate_record(r);assert r['id'] not in seen;seen.add(r['id']);groups.setdefault((r['pair_id'],r['judge'],r['mode']),[]).append(r)
    for pid in mapping:
        for j in JUDGES:groups.setdefault((pid,j,'pair'),[])
        if any(p==pid and mode=='critical' for p,j,mode in groups):
            for j in JUDGES:groups.setdefault((pid,j,'critical'),[])
    results=[]
    for (p,j,mode),rr in sorted(groups.items()):results.append(dict(pair_id=p,judge=j,mode=mode,**mapping[p],**aggregate(rr)))
    ev.write(out/'results.json',results)
    grouped=defaultdict(list)
    for row in results:
        if row['mode']=='pair':grouped[(row['source'],row['new'],row['base'],row['judge'])].append(row)
    text=['# 匿名顺序盲评报告','','同向才计胜负；顺序不一致记平，缺失/失败不记平。两个tie是一致平。旧导入不冒充新增调用。','','| 来源/对照 | 评委 | 胜 | 平 | 负 | 顺序一致/完整 | 未完成 |','| --- | --- | ---: | ---: | ---: | --- | ---: |']
    for (source,new,base,j),rs in sorted(grouped.items()):
        valid=[r for r in rs if r['status']=='completed'];w=[r['winner'] for r in valid]
        text.append(f'| {Path(source).name}: {new}/{base} | {j} | {w.count("new")} | {w.count("tie")} | {w.count("base")} | {sum(r["consistent"] for r in valid)}/{len(valid)} | {len(rs)-len(valid)} |')
    (out/'report.md').write_text('\n'.join(text)+'\n')
    return results

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--base');p.add_argument('--new');p.add_argument('--out',type=Path,required=True);p.add_argument('--judges',default='bitto,workbuddy');p.add_argument('--mode',choices=['pair','critical'],default='pair');p.add_argument('--only',default='*');p.add_argument('--import-legacy',type=Path);p.add_argument('--report-only',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--timeout',type=int,default=180);p.add_argument('--max-calls',type=int,default=60);p.add_argument('--batch-size',type=int,default=1,help='>1 jointly judges quality and critical findings; count each batch once')
    p.add_argument('--repair-missing',action='store_true',help='Stage9 compact per-item channel; preserve successes and audit all attempts')
    p.add_argument('--reuse-judgments',type=Path,help='Seed only successful votes, snapshot all prior records')
    p.add_argument('--retry-transient',type=int,choices=[0,1],default=0)
    args=p.parse_args();args.out=args.out.resolve();args.out.mkdir(parents=True,exist_ok=True)
    if args.batch_size<1 or (args.batch_size>1 and args.mode!='pair'):p.error('Joint batching requires pair mode and positive batch size')
    if args.repair_missing and (args.batch_size!=2 or args.mode!='pair'):p.error('Repair channel requires pair mode and batch-size 2')
    if (args.reuse_judgments or args.retry_transient) and not args.repair_missing:p.error('Reuse/retry flags require explicit repair channel')
    with (args.out/'.judge.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not args.report_only:
            if not args.source or not args.base or not args.new:p.error('source/base/new required')
            if args.import_legacy:print('Imported orders:',import_legacy(args.out,args.import_legacy,args.source,args.base,args.new))
            else:
                js=args.judges.split(',')
                if not set(js)<=JUDGES.keys():p.error('Unknown judge')
                ids=prepare(args.out,args.source,args.base,args.new,args.only)
                if not ids:raise ValueError('No complete recorded answer pairs')
                if args.repair_missing:
                    from repair_judge import seed_existing,run_repairs
                    if args.reuse_judgments:print('Reused successful records:',seed_existing(args.out,args.reuse_judgments))
                    print('New submissions:',run_repairs(args.out,ids,js,args.batch_size,args.timeout,args.max_calls,args.dry_run,retries=args.retry_transient))
                elif args.batch_size>1:
                    from harness_judge import run_batches
                    print('New submissions:',run_batches(args.out,ids,js,args.batch_size,args.timeout,args.max_calls,args.dry_run))
                else:print('New submissions:',run_new(args.out,ids,js,args.mode,args.timeout,args.max_calls,args.dry_run))
        print('Pair aggregates:',len(report(args.out)))
        if not args.report_only and not args.dry_run and not args.import_legacy:
            modes=['pair','critical'] if args.repair_missing else [args.mode]
            wanted={cid(pid,j,i,m) for pid in ids for j in js for i in (0,1) for m in modes}
            if args.repair_missing and not wanted<={r['id'] for r in ev.lines(args.out/'judges.jsonl') if r['status']=='completed'}:return 1
            if any(r['id'] in wanted and r['status']=='failed' for r in ev.lines(args.out/'judges.jsonl')):return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
