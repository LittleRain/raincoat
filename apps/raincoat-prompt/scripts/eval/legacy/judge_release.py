#!/usr/bin/env python3
"""Check preregistered scene release gates from anonymous judge records."""
import json
from pathlib import Path
import run as ev
import run_judge as jr
from judge import critical_findings

PROTOCOL='stage7-two-order-v1'
def metrics(rows):
    good=[r for r in rows if r['status']=='completed'];v=[r['winner'] for r in good]
    return dict(win=v.count('new'),tie=v.count('tie'),loss=v.count('base'),valid=len(good),incomplete=len(rows)-len(good),consistent=sum(r['consistent'] for r in good),consistency=sum(r['consistent'] for r in good)/len(good) if good else 0)

def dataset_gate(rows,expected,minimum_margin,minimum_consistency):
    s=metrics(rows)
    return dict(complete=s['valid']==expected and not s['incomplete'],win_margin=s['win']-s['loss']>=minimum_margin,order_consistency=s['consistency']>=minimum_consistency)

def evaluate(out,datasets,critical_judges=('bitto',)):
    out=Path(out);mapping=json.loads((out/'private-mapping.json').read_text());records=ev.lines(out/'judges.jsonl')
    for r in records:
        packet=json.loads((out/'blind-review'/f'{r["pair_id"]}-{r["order"]}.json').read_text());jr.validate_record(r,packet)
    results=jr.report(out);quality={};required=set()
    for dataset in datasets:
        source=Path(dataset['source']).resolve();source_runs={r['id']:r for r in ev.lines(source/'runs.jsonl')};ids=set()
        for pid,m in mapping.items():
            if Path(m['source']).resolve()!=source or (m['base'],m['new'])!=('A','Cdoubleprime'):continue
            n,b=source_runs[m['new_id']],source_runs[m['base_id']]
            assert ev.digest(n['answer'].encode())==m['new_answer_sha256'] and ev.digest(b['answer'].encode())==m['base_answer_sha256'],'Original answer changed'
            assert all(n[k]==b[k] for k in ['case','target','model','repeat','scene','split'])
            fixture=json.loads((source/'plan.json').read_text());case=next(c for c in fixture['cases'] if c['id']==m['case'])
            for order in (0,1):
                packet=json.loads((out/'blind-review'/f'{pid}-{order}.json').read_text())
                first,second=(b,n) if order==0 else (n,b)
                assert packet==dict(pair_id=pid,task=case['input'],materials=case['materials'],core_checks=case['core_checks'],bonus_check=case['bonus_check'],critical_errors=case['critical_errors'],responses=dict(A=first['answer'],B=second['answer'])),'Anonymous packet differs from original task/rubric/answers'
            ids.add(pid)
        # Ensure no missing complete answer pair can be hidden by omitting a mapping entry.
        expected={jr.pair_identity(source,'A','Cdoubleprime',n,source_runs[n['id'].replace('--Cdoubleprime--','--A--')]) for n in source_runs.values() if n['version']=='Cdoubleprime' and n['status']=='completed' and n['id'].replace('--Cdoubleprime--','--A--') in source_runs and source_runs[n['id'].replace('--Cdoubleprime--','--A--')]['status']=='completed'}
        assert ids==expected and ids,'Dataset mapping does not cover all available complete pairs'
        required|=ids
        for judge in jr.JUDGES:
            rows=[r for r in results if r['pair_id'] in ids and r['judge']==judge and r['mode']=='pair'];g=dataset_gate(rows,len(ids),dataset['minimum_margin'],0.75)
            quality[dataset['name']+'/'+judge]=dict(**metrics(rows),gates=g,passed=all(g.values()))
    audits={}
    for judge in critical_judges:
        details=[]
        for pid in sorted(required):
            rows=[r for r in records if r['pair_id']==pid and r['judge']==judge and r['mode']=='critical'];finding=critical_findings(rows)
            details.append(dict(pair_id=pid,new_id=mapping[pid]['new_id'],**finding))
        passed=all(r['status']=='completed' and r['new_errors']==[] for r in details)
        audits[judge]=dict(pairs=len(details),passed=passed,details=details)
    return dict(protocol=PROTOCOL,quality=quality,critical_audits=audits,unique_answer_pairs=len(required),passed=all(v['passed'] for v in quality.values()) and all(v['passed'] for v in audits.values()))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    datasets=[dict(name='main',source=str(ev.ROOT/'.build/evaluation/round-03'),minimum_margin=1),dict(name='existing-holdout',source=str(ev.ROOT/'.build/evaluation/round-04-holdout'),minimum_margin=0)]
    value=evaluate(a.evidence,datasets);ev.write(a.out,value);print(json.dumps(value,ensure_ascii=False,indent=2));raise SystemExit(0 if value['passed'] else 1)
