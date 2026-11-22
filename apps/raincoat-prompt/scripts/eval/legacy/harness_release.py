#!/usr/bin/env python3
"""Preregistered blind D/C gate; legacy model-rule score gates are separate."""
import json,plistlib
from pathlib import Path
import run as ev
import run_judge as jr
from judge import critical_findings
from judge_release import metrics
from harness_candidates import validate_harness_candidate
PROTOCOL='stage8-harness-blind-v1'

def evaluate(rule,run_dir,judge_dir,protocol,root=ev.ROOT):
    assert protocol['id']==PROTOCOL
    assert protocol['minimum_net_wins']==1 and protocol['minimum_consistency']==0.75
    assert protocol['minimum_repeats']==2 and protocol['minimum_cases']==4
    prereg=(root/protocol['preregistration']).resolve();assert prereg.is_relative_to(root.resolve())
    assert ev.digest(prereg.read_bytes())==protocol['preregistration_sha256'],'Preregistration changed after protocol freeze'
    out=(root/run_dir).resolve();judged=(root/judge_dir).resolve()
    assert out.is_relative_to(root.resolve()) and judged.is_relative_to(root.resolve())
    plan=json.loads((out/'plan.json').read_text());candidate=plan['harness_catalog'];validate_harness_candidate(candidate,plan['catalog'])
    recorded=next(r for r in candidate['rules'] if r['id']==rule['id'])
    assert all(recorded.get(k)==v for k,v in rule.items() if k not in ('enabled','evidence')),'Rule differs from evaluated harness candidate'
    runs={r['id']:r for r in ev.lines(out/'runs.jsonl')};mapping=json.loads((judged/'private-mapping.json').read_text());rows=jr.report(judged);records=ev.lines(judged/'judges.jsonl');valid_pairs={}
    for n in runs.values():
        if n['version']!='D' or n['status']!='completed':continue
        b=runs.get(n['id'].replace('--D--','--C--'))
        if not b or b['status']!='completed':continue
        assert n['harness_rule']==rule['id'] and ev.TARGETS[n['target']][0]==rule['target']
        assert ev.SCENES[n['scene']]==rule['scene'] and all(n[k]==b[k] for k in ['case','target','model','repeat','scene','split'])
        assert n['observed_model']==b['observed_model']==n['model']
        assert n['prompt'].count(rule['instruction'])==1 and n['prompt'].replace('\n\n'+rule['instruction'],'',1)==b['prompt'],'Not a single harness-rule difference'
        pid=jr.pair_identity(out,'C','D',n,b);valid_pairs[pid]=(n,b)
    assert valid_pairs,'No completed D/C pairs'
    assert set(mapping)==set(valid_pairs),'Judge scope must include all available completed pairs, not selected wins'
    for pid,(n,b) in valid_pairs.items():
        case=next(c for c in plan['cases'] if c['id']==n['case']);m=mapping[pid]
        assert m['new_id']==n['id'] and m['base_id']==b['id'] and Path(m['source']).resolve()==out
        for order in (0,1):
            packet=json.loads((judged/'blind-review'/f'{pid}-{order}.json').read_text());a,z=(b,n) if order==0 else (n,b)
            assert packet==dict(pair_id=pid,task=case['input'],materials=case['materials'],core_checks=case['core_checks'],bonus_check=case['bonus_check'],critical_errors=case['critical_errors'],responses=dict(A=a['answer'],B=z['answer']))
        for r in [x for x in records if x['pair_id']==pid]:jr.validate_record(r,json.loads((judged/'blind-review'/f'{pid}-{r["order"]}.json').read_text()))
    newer=[n for n,b in valid_pairs.values()];coverage=dict(cases=len({n['case'] for n in newer})>=protocol['minimum_cases'],repeats=len({n['repeat'] for n in newer})>=protocol['minimum_repeats'],unseen_holdout=any(n['split']=='holdout' and n['case'] in protocol['unseen_holdout_ids'] for n in newer))
    judges={}
    for judge in jr.JUDGES:
        quality=[r for r in rows if r['mode']=='pair' and r['judge']==judge];s=metrics(quality);audit=[]
        for pid in sorted(valid_pairs):audit.append(dict(pair_id=pid,**critical_findings([r for r in records if r['pair_id']==pid and r['judge']==judge and r['mode']=='critical'])))
        model_ok=all(r['requested_model']==r['observed_model']==jr.JUDGES[judge] for r in records if r['judge']==judge and r['status']=='completed')
        gates=dict(complete=s['valid']==len(valid_pairs) and not s['incomplete'],net_positive=s['win']-s['loss']>=protocol['minimum_net_wins'],order_consistent=s['consistency']>=protocol['minimum_consistency'],no_new_critical=all(a['status']=='completed' and a['new_errors']==[] for a in audit),observed_judge_model=model_ok)
        judges[judge]=dict(**s,gates=gates,critical=audit,passed=all(gates.values()))
    return dict(rule=rule['id'],protocol=PROTOCOL,valid_pairs=len(valid_pairs),coverage=coverage,judges=judges,passed=all(coverage.values()) and all(j['passed'] for j in judges.values()))

def validate_enabled(rule,root=ev.ROOT):
    evidence=rule['evidence'];assert evidence and all(isinstance(e,dict) and e.get('protocol')==PROTOCOL for e in evidence)
    dirs={(e['run_dir'],e['judge_dir'],e['protocol_file']) for e in evidence};assert len(dirs)==1
    run_dir,judge_dir,protocol_file=next(iter(dirs));protocol=json.loads((root/protocol_file).read_text());result=evaluate(rule,run_dir,judge_dir,protocol,root)
    assert result['passed'],'Preregistered harness blind gate failed'
    mapping=json.loads((root/judge_dir/'private-mapping.json').read_text());assert {e['pair_id'] for e in evidence}==set(mapping) and len(evidence)==len(mapping),'Evidence omitted or duplicated a pair'
    for e in evidence:assert set(e['run_ids'])=={mapping[e['pair_id']]['new_id'],mapping[e['pair_id']]['base_id']}
    return result

def validate_release_manifest(catalog,root,manifest=None):
    """A patch release keeps the approved scene catalog and adds only approved harnesses."""
    app_version=plistlib.loads((root/'assets/Info.plist').read_bytes())['CFBundleShortVersionString']
    if manifest is None:manifest=json.loads((root/f'docs/releases/{app_version}-evaluation.json').read_text())
    assert manifest['version']==app_version==catalog['version'],'App, catalog and manifest versions differ'
    assert manifest['protocol'] in (PROTOCOL,'tools-v1-deterministic')
    assert ev.digest((root/'Sources/PromptCore/Resources/prompt-rules.json').read_bytes())==manifest['catalog_sha256']
    for name,value in manifest['artifacts'].items():
        path=(root/name).resolve();assert path.is_relative_to(root.resolve())
        assert path.exists() and ev.digest(path.read_bytes())==value,'Missing/changed harness release evidence: '+name
    if manifest.get('change_class')=='rebuild-only':
        assert manifest.get('no_behavior_change') is True
        parent_path=(root/manifest['base_manifest']).resolve();catalog_path=(root/manifest['behavior_base_catalog']).resolve()
        assert parent_path.is_relative_to(root.resolve()) and catalog_path.is_relative_to(root.resolve())
        assert ev.digest(parent_path.read_bytes())==manifest['base_manifest_sha256']
        parent=json.loads(parent_path.read_text());prior=json.loads(catalog_path.read_text())
        assert ev.digest(catalog_path.read_bytes())==parent['catalog_sha256']==manifest['behavior_base_catalog_sha256']
        assert parent['protocol']==manifest['protocol'] and parent['enabled_rules']==manifest['enabled_rules']
        assert parent['scene_base_catalog']==manifest['scene_base_catalog']
        assert all(manifest['artifacts'].get(k)==v for k,v in parent['artifacts'].items()),'Rebuild changed inherited evidence hashes'
        normalized=json.loads(json.dumps(catalog));normalized['version']=prior['version']
        assert normalized==prior,'Rebuild changed behavior catalog beyond version'
    baseline=json.loads((root/manifest['scene_base_catalog']).read_text())
    scene_manifest=json.loads((root/'docs/releases/0.2.0-evaluation.json').read_text())
    released={r['id'] for r in catalog['rules'] if r['enabled']}
    restored=json.loads(json.dumps(catalog));restored['version']=baseline['version']
    restored['rules']=[r for r in restored['rules'] if r['id'] not in released]
    assert restored==baseline,'Baseline snapshot must equal the approved 0.2.0 catalog'
    assert all(catalog[k]==v for k,v in baseline.items() if k not in ('version','rules')),'Harness release changed approved scene/model context'
    enabled={r['id'] for r in catalog['rules'] if r['enabled']}
    assert enabled==set(manifest['enabled_rules']) and enabled
    original={r['id']:r for r in baseline['rules']}
    assert {r['id'] for r in catalog['rules']}==set(original)|enabled,'Release added or dropped a rule outside approved harnesses'
    for rule in catalog['rules']:
        if rule['id'] in enabled:
            assert rule['kind']=='harness'
            import tools_release
            if all(isinstance(e,dict) and e.get('protocol')==tools_release.PROTOCOL for e in rule['evidence']):
                tools_release.validate_enabled(rule,root)
            else:validate_enabled(rule,root)
        else:
            assert rule['id'] in original,'Unapproved rule cannot ship disabled'
            assert rule==original[rule['id']],'Nonreleased rule changed'
    from judge_release import evaluate as scene_evaluate
    for name,value in scene_manifest['artifacts'].items():assert ev.digest((root/name).read_bytes())==value,'Original scene evidence changed'
    datasets=[dict(d,source=str(root/d['source'])) for d in scene_manifest['datasets']]
    assert scene_evaluate(root/scene_manifest['evidence'],datasets,tuple(scene_manifest['critical_judges']))['passed']
