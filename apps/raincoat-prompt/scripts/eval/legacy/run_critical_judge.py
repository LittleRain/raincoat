#!/usr/bin/env python3
"""Batch existing anonymous packets for critical-error audits, never new answers."""
import argparse,json,time,os,fcntl
from pathlib import Path
import run as ev
import run_judge as jr
from judge import build_prompt,validate_output,critical_findings

def batch_output(text,packets):
    value=json.loads(text)
    if not isinstance(value,dict) or set(value)!={'items'} or not isinstance(value['items'],list):raise ValueError('Batch output requires only items array')
    byid={}
    for item in value['items']:
        if not isinstance(item,dict) or 'pair_id' not in item:raise ValueError('Missing anonymous pair id')
        pid=item['pair_id']
        if pid not in packets or pid in byid:raise ValueError('Unknown/duplicate batch pair')
        byid[pid]=validate_output({k:v for k,v in item.items() if k!='pair_id'},'critical',packets[pid])
    if set(byid)!=set(packets):raise ValueError('Missing batch judgement')
    return byid

def audit(out,pids,judges,batch_size,timeout,max_calls,dry_run=False):
    out=out.resolve();done={r['id'] for r in ev.lines(out/'judges.jsonl')};attempted={r['id'] for r in ev.lines(out/'attempts.jsonl')};pending=[]
    for judge in judges:
        missing=[p for p in sorted(pids) if any(jr.cid(p,judge,i,'critical') not in done for i in (0,1))]
        for start in range(0,len(missing),batch_size):
            batch=missing[start:start+batch_size]
            for order in (0,1):
                # No resubmission of an already-recorded or attempted batch.
                ids=[p for p in batch if jr.cid(p,judge,order,'critical') not in done]
                if not ids:continue
                bid=ev.digest(json.dumps([ids,judge,order]).encode())[:24]
                if bid not in attempted:pending.append((bid,ids,judge,order))
    if len(pending)+len(attempted)>max_calls:raise ValueError('Critical batch submission budget exceeded')
    ev.write(out/'batch-plan.json',dict(pending=[dict(id=b,pairs=ps,judge=j,order=o) for b,ps,j,o in pending],max_calls=max_calls,dry_run=dry_run))
    if dry_run:return len(pending)
    os.environ['LOCAL_AGENT_MCP_STATE_DIR']=str(out/'backend-state')
    for bid,ids,judge,order in pending:
        packets={p:json.loads((out/'blind-review'/f'{p}-{order}.json').read_text()) for p in ids}
        prompt='逐组独立核对下面匿名配对的原有关键错误，不跨组混淆，不新增判据。不使用工具。最终只输出一个JSON对象，恰好items数组，每项含pair_id、verdict、reason、critical_A、critical_B。保留所有pair_id，每个出现一次。每项格式按其指令；证据引用必须逐字来自对应回答。\n'
        for p,packet in packets.items():prompt+='\n匿名配对 '+p+'\n'+build_prompt(packet,'critical')+'\n'
        prompt+='\n将各组结果合为 {"items":[{"pair_id":"匿名id","verdict":"A|B|tie","reason":"简短说明","critical_A":[],"critical_B":[]}]}，不要围栏或说明。'
        directory=out/'raw'/bid;directory.mkdir(parents=True,exist_ok=True);(directory/'prompt.txt').write_text(prompt)
        ev.append(out/'attempts.jsonl',dict(id=bid,pairs=ids,judge=judge,order=order,created_at=ev.now()));start=time.monotonic()
        try:result=ev.local_call(dict(target=judge,model=jr.JUDGES[judge]),directory,timeout)
        except Exception as error:result=dict(status='failed',answer='',error=f'{type(error).__name__}: {error}',observed_model=None,tokens=None,raw={})
        ev.write(directory/'raw.json',result['raw']);parsed=None;error=result['error']
        if result['status']=='completed':
            try:
                if result['observed_model']!=jr.JUDGES[judge]:raise ValueError('Unexpected observed judge model')
                parsed=batch_output(result['answer'],packets)
            except (ValueError,TypeError,KeyError) as exc:error=dict(validation_error=str(exc),raw_response=result['answer'])
        for pid in ids:
            output=parsed[pid] if parsed else None
            row=dict(schema_version=1,id=jr.cid(pid,judge,order,'critical'),pair_id=pid,judge=judge,requested_model=jr.JUDGES[judge],observed_model=result.get('observed_model'),mode='critical',order=order,status='completed' if output else 'failed',output=output,raw_response=result['answer'],error=error,duration_seconds=round(time.monotonic()-start,3),tokens=result.get('tokens'),provenance=dict(kind='local_batch',batch_id=bid,raw_path=str(directory/'raw.json'),job_id=result.get('job_id'),created_at=ev.now(),usage_note='shared batch usage; count once per batch id'))
            jr.validate_record(row,packets[pid]);ev.append(out/'judges.jsonl',row)
        print(bid,'completed' if parsed else 'failed',len(ids),'pairs',flush=True)
    return len(pending)

def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--judges',default='bitto');p.add_argument('--base',default='A');p.add_argument('--new',default='Cdoubleprime');p.add_argument('--batch-size',type=int,default=4);p.add_argument('--timeout',type=int,default=180);p.add_argument('--max-calls',type=int,default=60);p.add_argument('--dry-run',action='store_true');a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
    if a.batch_size<1 or not set(a.judges.split(','))<=jr.JUDGES.keys():p.error('Invalid batch size/judges')
    with (a.out/'.judge.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);ids=[]
        for s in a.sources.split(','):ids+=jr.prepare(a.out,Path(s),a.base,a.new)
        print('New batch calls:',audit(a.out,sorted(set(ids)),a.judges.split(','),a.batch_size,a.timeout,a.max_calls,a.dry_run));jr.report(a.out)
        if not a.dry_run and any(r['status']=='failed' for r in ev.lines(a.out/'judges.jsonl')):return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
