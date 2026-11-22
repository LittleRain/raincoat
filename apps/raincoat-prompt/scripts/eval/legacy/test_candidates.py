"""Release separation, candidate scope and X-provenance regression checks."""
import copy
from collections import Counter
import json
import tempfile
import unittest
from pathlib import Path
from run import ROOT, CATALOG, review_materials
from validate_rules import validate, validate_candidate

class CandidateTests(unittest.TestCase):
    def test_harness_candidate_cannot_change_scenes_models_or_target_identity(self):
        from harness_candidates import validate_harness_candidate
        baseline=json.loads(CATALOG.read_text())
        candidate=json.loads((ROOT/'docs/candidates/harness-v0.1.0.json').read_text())
        validate_harness_candidate(candidate,baseline)
        for kind in ('template','model','target'):
            bad=copy.deepcopy(candidate)
            if kind=='template':bad['templates'][0]['text']+=' unintended'
            elif kind=='model':next(r for r in bad['rules'] if r['kind']=='model')['instruction']+=' unintended'
            else:next(r for r in bad['rules'] if r['id']=='bitto-readonly')['target']='workBuddy'
            with self.assertRaises(AssertionError):validate_harness_candidate(bad,baseline)

    def setUp(self):
        self.baseline=json.loads(CATALOG.read_text())
        self.candidate=json.loads((ROOT/'docs/candidates/scene-v0.2.0.json').read_text())

    def test_external_evidence_never_enables_a_rule(self):
        validate(self.baseline)
        modified=copy.deepcopy(self.baseline)
        modified['external_candidates'][0]['enabled']=True
        with self.assertRaisesRegex(AssertionError,'External experience'):validate(modified)

    def test_candidate_only_changes_three_scene_texts(self):
        validate_candidate(self.candidate,self.baseline)
        modified=copy.deepcopy(self.candidate)
        next(t for t in modified['templates'] if t['scene']=='development')['text']+=' unwanted change'
        with self.assertRaises(AssertionError):validate_candidate(modified,self.baseline)

    def test_new_cases_keep_fixed_materials_and_do_not_enter_holdout(self):
        fixture=json.loads((ROOT/'docs/evaluation-cases.json').read_text())
        cases=[c for c in fixture['cases'] if c['id'].startswith('x0')]
        self.assertEqual(len(cases),7)
        # Stage 11 grew the bank to 60 to meet the >=10-per-scene coverage gate.
        counts=Counter(c['scene'] for c in fixture['cases'])
        self.assertGreaterEqual(len(fixture['cases']),60)
        self.assertTrue(all(counts[s]>=10 for s in ('调研','数据分析','开发','写方案','写报告')),counts)
        self.assertTrue(all(c['split']=='development' and c['materials'] and len(c['checks'])==4 for c in cases))

    def test_stage6_targeted_cases_have_fixed_checks_and_unseen_holdout_coverage(self):
        fixture=json.loads((ROOT/'docs/evaluation-cases.json').read_text())
        cases=[c for c in fixture['cases'] if c['id'].startswith('s6-')]
        self.assertEqual(len(cases),7)
        self.assertEqual(len([c for c in cases if c['scene']=='数据分析']),2)
        for scene in ('数据分析','开发','写报告','写方案'):
            self.assertTrue(any(c['scene']==scene and c['split']=='holdout' for c in cases))
        for c in cases:
            self.assertEqual(len(c['core_checks']),3)
            self.assertEqual(c['checks'],c['core_checks']+[c['bonus_check']])
            self.assertTrue(c['materials'] and c['critical_errors'])

    def test_stage4_only_adds_three_guards_without_replacing_parent_text(self):
        candidate=json.loads((ROOT/'docs/candidates/scene-v0.2.1.json').read_text())
        validate_candidate(candidate,self.baseline)
        modified=copy.deepcopy(candidate)
        modified['templates'][0]['text']='unrelated rewrite'
        with self.assertRaises(AssertionError):validate_candidate(modified,self.baseline)
        modified=copy.deepcopy(candidate);modified['candidate_guards']=[]
        with self.assertRaises(AssertionError):validate_candidate(modified,self.baseline)

    def test_candidate_pairs_are_anonymous_and_no_op_is_excluded(self):
        case=dict(id='c',input='task',materials=['fixed'],checks=['1','2','3','4'],critical_errors=['fabrication'])
        base=dict(case='c',target='bitto',model='m',repeat=1,status='completed')
        runs=[dict(base,id='a',version='A',answer='a',prompt='a'),dict(base,id='c',version='C',answer='c',prompt='c'),dict(base,id='cp',version='Cprime',answer='candidate',prompt='cp')]
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);mapping=review_materials(out,dict(seed=1,cases=[case]),runs)
            self.assertEqual(len(mapping),3)
            packet=json.loads(next((out/'blind-review').glob('*.json')).read_text())
            self.assertEqual(set(packet),{'pair_id','task','materials','checks','critical_errors','responses'})
            runs[-1]['prompt']='c'
            mapping=review_materials(out,dict(seed=1,cases=[case]),runs)
            self.assertEqual(len(mapping),2)
            self.assertNotIn(('Cprime','C'),[(m['newer'],m['older']) for m in mapping.values()])
