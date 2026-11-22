#!/usr/bin/env python3
"""Deterministic tool-surface gate: harness rules must change observable behaviour, not wording."""
import json
import re
from pathlib import Path
import run as ev

PROTOCOL = 'tools-v1-deterministic'
FAKE = re.compile(
    r'(\$Region:|\bRegion:|Function Call|subagent|<Agent>|\bGrep with|\bRead with|\bGlob with|'
    r'tool_call|"subagent_type"|"path":\s*"/)'
)
CONTENT = re.compile(r'缺少|请粘贴|需要提供|核对')


def usable(record):
    """A usable answer states the missing material or gives a checkable next step."""
    if record.get('status') != 'succeeded':
        return False
    text = record.get('text') or ''
    return len(text) >= 300 and not FAKE.search(text) and bool(CONTENT.search(text))


def evaluate(rule, evidence, root=ev.ROOT):
    assert evidence['protocol'] == PROTOCOL, 'Wrong tool gate protocol'
    out = (root / evidence['run_dir']).resolve()
    assert out.is_relative_to(root.resolve()), 'Evidence must stay within application'
    data = json.loads((out / 'runs.json').read_text())
    cases = json.loads((root / 'docs/eval-cases-tools.json').read_text())['cases']
    case_ids = {c['id'] for c in cases}
    dev_ids=set(evidence['cases']);hold_ids=set(evidence.get('holdout_cases',[]))
    assert dev_ids|hold_ids==case_ids and not dev_ids&hold_ids, 'Evidence must cover every frozen tool case exactly once'
    target = next(k for k,v in ev.TARGETS.items() if v[0]==rule['target'])
    base_v, new_v = evidence['baseline_version'], evidence['treated_version']
    rows = [r for r in data['records'] if r.get('target') == target and r.get('id') in case_ids]
    base = {r['id']: r for r in rows if r['version'] == base_v}
    new = {r['id']: r for r in rows if r['version'] == new_v}
    assert set(base) == case_ids and set(new) == case_ids, 'Missing baseline or treated runs'
    detail, improved, regressed = [], 0, 0
    for case_id in sorted(case_ids):
        b, n = base[case_id], new[case_id]
        ok_b, ok_n = usable(b), usable(n)
        detail.append(dict(case=case_id, baseline_usable=ok_b, treated_usable=ok_n))
        improved += bool(ok_n and not ok_b)
        regressed += bool(ok_b and not ok_n)
    dev=[d for d in detail if d['case'] in dev_ids];hold=[d for d in detail if d['case'] in hold_ids]
    def count(rows,field):return sum(r[field] for r in rows)
    gate = dict(case_count=len(case_ids), improved=improved, regressed=regressed,
                baseline_usable=sum(d['baseline_usable'] for d in detail),
                treated_usable=sum(d['treated_usable'] for d in detail),
                development=dict(cases=len(dev),improved=count(dev,'treated_usable')-sum(1 for r in dev if r['treated_usable'] and r['baseline_usable']),
                                 regressed=sum(1 for r in dev if r['baseline_usable'] and not r['treated_usable'])),
                holdout=dict(cases=len(hold),improved=sum(1 for r in hold if r['treated_usable'] and not r['baseline_usable']),
                             regressed=sum(1 for r in hold if r['baseline_usable'] and not r['treated_usable'])))
    gate['passed'] = (gate['development']['improved']>=3 and gate['development']['regressed']==0
                      and gate['holdout']['cases']>=4 and gate['holdout']['improved']>=3 and gate['holdout']['regressed']==0)
    return dict(rule=rule['id'], protocol=PROTOCOL, cases=detail, **gate)


def validate_enabled(rule, root=ev.ROOT):
    evidence = rule['evidence']
    assert evidence and all(isinstance(e, dict) and e.get('protocol') == PROTOCOL for e in evidence)
    assert len(evidence) == 1, 'Tool-surface evidence must be a single frozen run directory'
    result = evaluate(rule, evidence[0], root)
    assert result['passed'], 'Deterministic tool gate failed'
    return result
