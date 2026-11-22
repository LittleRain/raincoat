"""Unit fixtures below test the adapter, never enter evaluation runs or scores."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('runner',Path(__file__).with_name('run.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class RunnerTests(unittest.TestCase):
    def test_local_succeeded_is_valid_and_tokens_are_not_estimated(self):
        raw=dict(stdout=json.dumps(dict(status='succeeded',text='unit-test response',model='m',message_usage=[dict(output_tokens=7)])),returncode=0,stderr='')
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,'execute',return_value=raw):
            result=r.local_call(dict(target='bitto',model='m'),Path(tmp),5)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['tokens'],[dict(output_tokens=7)])
    def test_failed_or_empty_backend_never_becomes_a_valid_answer(self):
        for state in [dict(status='failed',text='partial',error='connection lost'),dict(status='succeeded',text='')]:
            raw=dict(stdout=json.dumps(state),returncode=0,stderr='')
            with tempfile.TemporaryDirectory() as tmp, patch.object(r,'execute',return_value=raw):
                result=r.local_call(dict(target='workbuddy',model='m'),Path(tmp),5)
            self.assertEqual(result['status'],'failed');self.assertIsNotNone(result['error'])
    def test_codex_nonzero_and_partial_final_never_pass(self):
        raw=dict(returncode=1,stdout='{"type":"turn.failed","error":{"message":"stream lost"}}',stderr='original stderr')
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,'execute',return_value=raw):
            (Path(tmp)/'answer.txt').write_text('partial unit-test answer')
            result=r.codex_call(dict(model='m',prompt='unit fixture'),Path(tmp),5)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['error']['process']['stderr'],'original stderr')
    def test_blind_packet_has_no_execution_labels_and_only_complete_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            case=dict(id='c',input='task',materials=['material'],checks=['1','2','3','4'],critical_errors=['error'])
            base=dict(case='c',target='secret-target',model='secret-model',repeat=1,status='completed')
            runs=[dict(base,id='raw-A',version='A',answer='first'),dict(base,id='raw-C',version='C',answer='second'),dict(base,id='raw-B',version='B',answer='partial',status='failed')]
            m=r.review_materials(out,dict(seed=1,cases=[case]),runs)
            self.assertEqual(len(m),1)
            packet=json.loads(next((out/'blind-review').glob('*.json')).read_text())
            self.assertEqual(set(packet),{'pair_id','task','materials','checks','critical_errors','responses'})
            self.assertNotIn('secret',json.dumps(packet))
            first=next((out/'blind-review').glob('*.json')).read_text()
            r.review_materials(out,dict(seed=1,cases=[case]),runs)
            self.assertEqual(first,next((out/'blind-review').glob('*.json')).read_text())
    def test_unscored_and_duplicate_reviews_rejected(self):
        review=dict(pair_id='x',status='pending')
        with self.assertRaises(AssertionError):r.validate_reviews([review],dict(x={}))
        self.assertGreater(r.score_key(dict(core=[True]*3,bonus=False,critical_errors=[])),r.score_key(dict(core=[True]*3,bonus=True,critical_errors=['invented fact'])))
    def test_model_fallback_is_excluded_from_quality_pairs(self):
        self.assertFalse(r.eligible(dict(status='completed',model='requested',observed_model='different')))
        self.assertTrue(r.eligible(dict(status='completed',model='kimi-k2.5',observed_model='Kimi K2.5')))
        self.assertTrue(r.eligible(dict(status='completed',model='requested',observed_model=None)))

    def test_local_submit_and_wait_share_one_deadline(self):
        start=dict(stdout=json.dumps(dict(job_id='j',status='running')),returncode=0,stderr='')
        end=dict(stdout=json.dumps(dict(job_id='j',status='succeeded',text='unit fixture')),returncode=0,stderr='')
        with tempfile.TemporaryDirectory() as tmp, patch.object(r,'execute',side_effect=[start,end]) as call, patch.object(r.time,'monotonic',side_effect=[0,0,7,8]):
            result=r.local_call(dict(target='bitto',model='m'),Path(tmp),10)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(call.call_args_list[0].args[1],10)
        self.assertEqual(call.call_args_list[1].args[1],2)

    def test_case_filters_and_repeat_selection(self):
        fixture=dict(cases=[dict(id='r1',scene='调研',split='development'),dict(id='d1',scene='开发',split='holdout')],extended_pilot=['r1'])
        self.assertEqual(len(r.select_cases(fixture,'r*,holdout')),2)
        self.assertEqual(r.select_cases(fixture,'extended_pilot')[0]['id'],'r1')

class IncrementalRunnerTests(unittest.TestCase):
    def make_run(self, version='A', repeat=1):
        return dict(id=f'case--bitto--{version}--{repeat}', case='case', scene='调研',
                    split='development', target='bitto', model='unit-model', version=version,
                    repeat=repeat, prompt=f'unit task {version}', model_rule=None)

    def make_plan(self, runs):
        case = dict(id='case', input='unit task', materials=['unit material'],
                    checks=['one', 'two', 'three', 'bonus'], critical_errors=['invented fact'])
        return dict(seed=1, runs=runs, cases=[case], fixture_sha256='unit',
                    rules_sha256='unit', composer_sha256='unit')

    def complete(self, run, out, timeout):
        return {**run, 'status': 'completed', 'answer': 'unit response', 'tokens': None,
                'error': None, 'observed_model': 'unit-model', 'duration_seconds': 0.01}

    def invoke(self, out, requested, max_calls=60):
        from types import SimpleNamespace
        args = SimpleNamespace(out=out, targets='bitto', dry_run=False,
                               timeout=1, max_calls=max_calls)
        with patch.object(r, 'plan', return_value=requested), patch.object(r, 'run_one', side_effect=self.complete) as call:
            result = r.run_matrix(args)
        return result, call

    def test_completed_id_is_reused_without_another_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            requested = self.make_plan([self.make_run()])
            result, first = self.invoke(out, requested)
            original = (out / 'runs.jsonl').read_bytes()
            result, second = self.invoke(out, requested)
            self.assertEqual(first.call_count, 1)
            self.assertEqual(second.call_count, 0)
            self.assertEqual(result, 0)
            self.assertEqual((out / 'runs.jsonl').read_bytes(), original)
            self.assertEqual(len(r.lines(out / 'attempts.jsonl')), 1)

    def test_new_version_preserves_failure_and_uses_only_new_call_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            original = self.make_plan([self.make_run('A'), self.make_run('C')])
            r.write(out / 'plan.json', original)
            r.append(out / 'runs.jsonl', self.complete(original['runs'][0], out, 1))
            failed = {**original['runs'][1], 'status': 'failed', 'answer': '',
                      'error': 'original backend failure', 'duration_seconds': 1}
            r.append(out / 'runs.jsonl', failed)
            result, call = self.invoke(out, self.make_plan([self.make_run('A'), self.make_run('B'), self.make_run('C')]), max_calls=1)
            self.assertEqual(result, 0)
            self.assertEqual([entry.args[0]['version'] for entry in call.call_args_list], ['B'])
            records = r.lines(out / 'runs.jsonl')
            self.assertEqual(len(records), 3)
            self.assertEqual(records[1], failed)
            self.assertEqual(json.loads((out / 'plan.initial.json').read_text()), original)

    def test_repeat_two_submits_only_missing_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first = [self.make_run('A'), self.make_run('C')]
            self.invoke(out, self.make_plan(first))
            requested = self.make_plan(first + [self.make_run('A', 2), self.make_run('C', 2)])
            result, call = self.invoke(out, requested)
            self.assertEqual(result, 0)
            self.assertEqual([entry.args[0]['repeat'] for entry in call.call_args_list], [2, 2])
            self.assertEqual(len(r.lines(out / 'runs.jsonl')), 4)

    def test_attempt_without_result_is_not_submitted_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run = self.make_run()
            r.append(out / 'attempts.jsonl', dict(id=run['id'], target='bitto'))
            result, call = self.invoke(out, self.make_plan([run]))
            self.assertEqual(result, 0)
            self.assertEqual(call.call_count, 0)

    def test_changed_prompt_does_not_overwrite_existing_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            requested = self.make_plan([self.make_run()])
            self.invoke(out, requested)
            original = (out / 'runs.jsonl').read_bytes()
            changed = self.make_run()
            changed['prompt'] = 'changed unit task'
            with self.assertRaisesRegex(ValueError, 'different prompt'):
                self.invoke(out, self.make_plan([changed]))
            self.assertEqual((out / 'runs.jsonl').read_bytes(), original)

    def test_new_pair_keeps_existing_review_mapping_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first = [self.make_run('A'), self.make_run('C')]
            self.invoke(out, self.make_plan(first))
            before = json.loads((out / 'private-mapping.json').read_text())
            self.invoke(out, self.make_plan([self.make_run('B')]))
            after = json.loads((out / 'private-mapping.json').read_text())
            for pair_id, mapping in before.items():
                self.assertEqual(after[pair_id], mapping)
            self.assertEqual(len(after), 3)

class EvidenceTests(unittest.TestCase):
    def test_frozen_scene_model_evidence_requires_exact_single_rule_delta(self):
        import copy
        from validate_rules import validate
        catalog=json.loads(r.CATALOG.read_text())
        for entry in catalog['rules']:entry['enabled']=False
        rule=next(x for x in catalog['rules'] if x['id']=='kimi-format-discipline')
        rule['enabled']=True
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'unit-evidence';out.mkdir()
            mapping={};evidence=[]
            for repeat in (1,2):
                pid=str(repeat)*16;new=f'unit-E-{repeat}';old=f'unit-base-{repeat}'
                mapping[pid]=dict(newer='E',older='Cdoubleprime',sides=dict(A=new,B=old))
                evidence.append(dict(run_dir='unit-evidence',pair_id=pid,run_ids=[new,old]))
                base=dict(target='workbuddy',scene='开发',model='kimi-k2.5',observed_model='kimi-k2.5',case='unit-case',repeat=repeat,status='completed',split='holdout')
                r.append(out/'runs.jsonl',dict(base,id=new,version='E',model_rule=rule['id'],model_base_version='Cdoubleprime',prompt='unit task\n\n'+rule['instruction']))
                r.append(out/'runs.jsonl',dict(base,id=old,version='Cdoubleprime',model_rule=None,prompt='unit task'))
                scores=dict(A=dict(core=[True]*3,bonus=True,critical_errors=[],evidence='unit-only fixture'),B=dict(core=[False]*3,bonus=False,critical_errors=[],evidence='unit-only fixture'))
                r.append(out/'reviews.jsonl',dict(pair_id=pid,status='completed',reviewer='unit test',reviewed_at='2026-11-18T00:00:00Z',scores=scores))
            rule['evidence']=evidence
            r.write(out/'plan.json',dict(catalog=copy.deepcopy(catalog),candidate_catalog=json.loads((r.ROOT/'docs/candidates/scene-v0.2.1.json').read_text())))
            r.write(out/'private-mapping.json',mapping)
            validate(catalog,root)
            entries=r.lines(out/'runs.jsonl')
            entries[0]['observed_model']='Kimi K2.5'
            (out/'runs.jsonl').write_text('')
            for entry in entries:r.append(out/'runs.jsonl',entry)
            with self.assertRaisesRegex(AssertionError,'canonical requested label'):validate(catalog,root)
            entries[0]['observed_model']='kimi-k2.5'
            entries[0]['prompt']+=' extra harness instruction'
            (out/'runs.jsonl').write_text('')
            for entry in entries:r.append(out/'runs.jsonl',entry)
            with self.assertRaisesRegex(AssertionError,'more than one rule'):validate(catalog,root)

    def test_enabled_rule_requires_runs_and_reviews_not_a_prose_claim(self):
        import copy
        from validate_rules import validate
        catalog=json.loads(r.CATALOG.read_text())
        validate(catalog)
        bad=copy.deepcopy(catalog);bad['rules'][0]['enabled']=True
        with self.assertRaises(AssertionError):validate(bad)
        bad['rules'][0]['evidence']=['someone says it works']
        with self.assertRaises((TypeError,KeyError)):validate(bad)

    def test_duplicate_evidence_and_unknown_models_cannot_release_rules(self):
        import copy
        from validate_rules import validate
        catalog=json.loads(r.CATALOG.read_text())
        rule=next(x for x in catalog['rules'] if x['id']=='deepseek-check')
        rule['enabled']=True
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'unit-evidence';out.mkdir()
            pid='a'*16
            rule['evidence']=[dict(run_dir='unit-evidence',pair_id=pid)]*2
            r.write(out/'plan.json',dict(catalog=copy.deepcopy(catalog)))
            r.write(out/'private-mapping.json',{pid:dict(newer='E',older='D',sides=dict(A='new',B='old'))})
            base=dict(target='bitto',scene='数据分析',model='deepseek-v4.1-flash',observed_model='deepseek-v4.1-flash',case='c',repeat=1,status='completed',split='holdout')
            r.append(out/'runs.jsonl',dict(base,id='new',version='E',model_rule=rule['id'],prompt='task\n\n'+rule['instruction']))
            r.append(out/'runs.jsonl',dict(base,id='old',version='D',model_rule=None,prompt='task'))
            scores=dict(A=dict(core=[True]*3,bonus=True,critical_errors=[],evidence='unit rationale'),B=dict(core=[False]*3,bonus=False,critical_errors=[],evidence='unit rationale'))
            r.append(out/'reviews.jsonl',dict(pair_id=pid,status='completed',reviewer='unit test',reviewed_at='2026-11-17T00:00:00Z',scores=scores))
            with self.assertRaisesRegex(AssertionError,'Duplicate evidence pair'):validate(catalog,root)
            entries=r.lines(out/'runs.jsonl');entries[0]['observed_model']=None
            (out/'runs.jsonl').write_text('')
            for entry in entries:r.append(out/'runs.jsonl',entry)
            with self.assertRaisesRegex(AssertionError,'Unknown observed model'):validate(catalog,root)

    def test_report_counts_actual_scores_and_uncovered_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            case=dict(id='c',input='task',materials=['unit fixture'],checks=['1','2','3','4'],critical_errors=['bad fact'])
            base=dict(case='c',scene='调研',target='bitto',model='unit-model',repeat=1,status='completed',duration_seconds=1,split='development')
            runs=[dict(base,id='unit-A',version='A',answer='first'),dict(base,id='unit-C',version='C',answer='second')]
            plan=dict(seed=1,cases=[case],runs=runs,fixture_sha256='unit',rules_sha256='unit',composer_sha256='unit')
            r.write(out/'plan.json',plan)
            for run in runs:r.append(out/'runs.jsonl',run)
            mapping=r.review_materials(out,plan,runs);pid,m=next(iter(mapping.items()))
            new=next(s for s,rid in m['sides'].items() if rid=='unit-C')
            scores={s:dict(core=[True]*3 if s==new else [True,False,False],bonus=False,critical_errors=[],evidence='unit fixture rationale') for s in ['A','B']}
            r.append(out/'reviews.jsonl',dict(pair_id=pid,status='completed',reviewer='unit test',reviewed_at='2026-11-17T00:00:00Z',scores=scores))
            r.report(out)
            report=(out/'report.md').read_text()
            self.assertIn('| A→C 总收益 (C/A) | 1 | 0 | 0 | 1/1 |',report)
            self.assertIn('| 场景收益 (C/B) | 0 | 0 | 0 | 0/0 | 未覆盖 |',report)

if __name__=='__main__':unittest.main()
