"""Evaluation-only harness catalogs; published scene and model data stay fixed."""
from validate_rules import validate

def validate_harness_candidate(candidate,baseline):
    validate(candidate)
    assert candidate.get('candidate_status')=='unpublished'
    assert set(candidate)==set(baseline)|{'candidate_status'}
    assert all(candidate[k]==v for k,v in baseline.items() if k not in ('version','rules')),'Harness candidate changed scene/model context'
    original={r['id']:r for r in baseline['rules']}
    assert {r['id'] for r in candidate['rules']}==set(original)
    for rule in candidate['rules']:
        assert rule['enabled'] is False,'Evaluation harness catalog cannot release rules'
        old=original[rule['id']]
        if rule!=old:assert rule['kind']==old['kind']=='harness' and rule['target']==old['target'],'Only same-target harness candidates may change'
