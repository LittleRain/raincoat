import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import judge as j
import run_judge as r
import run as ev
from run_critical_judge import batch_output
from judge_release import dataset_gate
from harness_judge import run_batches

class JudgeTests(unittest.TestCase):
    def test_repair_normalizes_one_prefixed_id_but_rejects_ambiguous_ids(self):
        from repair_judge import parse_batch
        pid='a'*24;other='b'*24
        packet=dict(critical_errors=['promise'],responses=dict(A='base expected',B='new guaranteed'))
        item=dict(pair_id='匿名配对 <'+pid+'> (结果)',verdict='A',reason='promise',critical_flags=dict(A=[],B=[dict(criterion=0,quote='guaranteed')]))
        good,errors,normalizations=parse_batch(json.dumps(dict(items=[item])),{pid:packet})
        self.assertEqual(good[pid]['critical_B'][0]['criterion'],0)
        self.assertFalse(errors);self.assertEqual(normalizations[pid],item['pair_id'])
        good,errors,_=parse_batch(json.dumps(dict(items=[dict(item,pair_id=pid+' '+other)])),{pid:packet})
        self.assertFalse(good);self.assertIn(pid,errors)

    def test_repair_missing_fields_fail_only_the_affected_item(self):
        from repair_judge import parse_batch
        pids=['a'*24,'b'*24];packet=dict(critical_errors=['promise'],responses=dict(A='base',B='new'))
        item=dict(pair_id=pids[0],verdict='tie',reason='equal',critical_flags=dict(A=[],B=[]))
        bad=dict(pair_id=pids[1],verdict='tie',reason='missing flags')
        good,errors,_=parse_batch(json.dumps(dict(items=[item,bad])),dict.fromkeys(pids,packet))
        self.assertEqual(set(good),{pids[0]});self.assertIn(pids[1],errors)
        self.assertNotIn(pids[0],errors)

    def test_repair_duplicate_normalized_pair_is_not_selected_or_defaulted(self):
        from repair_judge import parse_batch
        pid='a'*24;packet=dict(critical_errors=['promise'],responses=dict(A='base',B='new'))
        item=dict(pair_id=pid,verdict='tie',reason='equal',critical_flags=dict(A=[],B=[]))
        good,errors,_=parse_batch(json.dumps(dict(items=[item,dict(item,pair_id='匿名配对 '+pid)])),{pid:packet})
        self.assertFalse(good);self.assertIn('Duplicate',errors[pid])
        with self.assertRaises(ValueError):parse_batch('```json\n{}\n```',{pid:packet})

    def test_repair_timeout_retries_once_and_keeps_first_failure_and_effective_success(self):
        from repair_judge import run_repairs
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out';out.mkdir();ids=r.prepare(out,source,'A','Cdoubleprime')
            response=json.dumps(dict(items=[dict(pair_id=ids[0],verdict='tie',reason='equal',critical_flags=dict(A=[],B=[]))]))
            ok=dict(status='completed',answer=response,observed_model='deepseek-v4.1-flash',tokens={},error=None,raw={},job_id='mock-ok')
            fail=dict(status='failed',answer='',observed_model='deepseek-v4.1-flash',tokens=None,error=dict(runner_error='Backend did not finish before deadline'),raw={},job_id='mock-fail')
            with patch.object(ev,'local_call',side_effect=[fail,ok,ok]) as call:
                self.assertEqual(run_repairs(out,ids,['bitto'],2,240,4,retries=1),3)
                self.assertEqual(run_repairs(out,ids,['bitto'],2,240,4,retries=1),0)
                self.assertEqual(call.call_count,3)
            attempts=ev.lines(out/'attempts.jsonl');self.assertEqual(len(attempts),3)
            self.assertEqual(attempts[1]['retry_of'],attempts[0]['id'])
            self.assertTrue(any(x['status']=='failed' for x in ev.lines(out/'attempt-records.jsonl')))
            self.assertTrue(all(x['status']=='completed' for x in ev.lines(out/'judges.jsonl')))
            self.assertEqual(r.report(out)[1]['status'],'completed')

    def test_repair_only_transient_failures_retry_and_never_more_than_once(self):
        from repair_judge import is_transient,run_repairs
        self.assertTrue(is_transient(dict(backend_error='HTTP 502 Bad Gateway')))
        self.assertFalse(is_transient(dict(validation_error='missing fields')))
        self.assertFalse(is_transient(dict(backend_error='permission denied')))
        self.assertFalse(is_transient(dict(backend_error='permission denied',raw_error=dict(command=['local-agent','wait','--timeout-seconds','25'],stderr='permission denied'))))
        self.assertFalse(is_transient(dict(raw_error=dict(stderr='Invalid --timeout-seconds argument; permission denied'))))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out';out.mkdir();ids=r.prepare(out,source,'A','Cdoubleprime')
            fail=dict(status='failed',answer='',observed_model=None,tokens=None,error='TimeoutExpired',raw={})
            with patch.object(ev,'local_call',return_value=fail) as call:
                run_repairs(out,ids,['bitto'],2,240,4,retries=1)
                run_repairs(out,ids,['bitto'],2,240,4,retries=1)
                self.assertEqual(call.call_count,4)
            self.assertEqual(len(ev.lines(out/'batch-results.jsonl')),4)
            self.assertTrue(all(x['status']=='incomplete' for x in r.report(out)))

    def test_repair_partial_success_is_retained_without_retrying_schema_failures(self):
        from repair_judge import run_repairs
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);runs=ev.lines(source/'runs.jsonl')
            for row in runs:ev.append(source/'runs.jsonl',dict(row,id=row['id'].removesuffix('--1')+'--2',repeat=2))
            out=root/'out';out.mkdir();ids=r.prepare(out,source,'A','Cdoubleprime')
            items=[dict(pair_id=ids[0],verdict='tie',reason='equal',critical_flags=dict(A=[],B=[])),dict(pair_id=ids[1],verdict='tie',reason='missing flags')]
            result=dict(status='completed',answer=json.dumps(dict(items=items)),observed_model='deepseek-v4.1-flash',tokens={},error=None,raw={})
            with patch.object(ev,'local_call',return_value=result) as call:
                run_repairs(out,ids,['bitto'],2,240,4,retries=1)
                run_repairs(out,ids,['bitto'],2,240,4,retries=1)
                self.assertEqual(call.call_count,2)
            rows=ev.lines(out/'judges.jsonl')
            self.assertTrue(all(x['status']=='completed' for x in rows if x['pair_id']==ids[0]))
            self.assertTrue(all(x['status']=='failed' for x in rows if x['pair_id']==ids[1]))
            self.assertTrue(all(x['status']=='partial' for x in ev.lines(out/'batch-results.jsonl')))

    def test_repair_import_preserves_all_prior_failures_and_never_replaces_success(self):
        from repair_judge import seed_existing
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);prior=root/'prior';prior.mkdir();ids=r.prepare(prior,source,'A','Cdoubleprime')
            ok=dict(status='completed',answer='{"verdict":"tie","reason":"equal"}',observed_model='deepseek-v4.1-flash',tokens={},error=None,raw={})
            fail=dict(status='failed',answer='',observed_model=None,tokens=None,error='TimeoutExpired',raw={})
            with patch.object(ev,'local_call',side_effect=[ok,fail]):r.run_new(prior,ids,['bitto'],'pair',1,2)
            out=root/'out';out.mkdir();r.prepare(out,source,'A','Cdoubleprime')
            self.assertEqual(seed_existing(out,prior),1);self.assertEqual(seed_existing(out,prior),0)
            self.assertEqual((out/'prior-judges.jsonl').read_bytes(),(prior/'judges.jsonl').read_bytes())
            self.assertEqual(ev.lines(out/'judges.jsonl'),[x for x in ev.lines(prior/'judges.jsonl') if x['status']=='completed'])

    def test_joint_batch_projects_two_valid_profiles_without_duplicate_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out';out.mkdir();ids=r.prepare(out,source,'A','Cdoubleprime')
            response=json.dumps(dict(items=[dict(pair_id=ids[0],verdict='tie',reason='unit equal',critical_A=[],critical_B=[])]))
            result=dict(status='completed',answer=response,observed_model='deepseek-v4.1-flash',tokens=dict(input=5,output=3),error=None,raw=dict(unit_fixture=True),job_id='unit')
            with patch.object(ev,'local_call',return_value=result) as call:
                self.assertEqual(run_batches(out,ids,['bitto'],4,1,2),2)
                self.assertEqual(run_batches(out,ids,['bitto'],4,1,2),0)
                self.assertEqual(call.call_count,2)
            self.assertEqual(len(ev.lines(out/'judges.jsonl')),4)
            self.assertEqual(len(ev.lines(out/'attempts.jsonl')),2)
            self.assertEqual({v['mode'] for v in ev.lines(out/'judges.jsonl')},{'pair','critical'})

    def test_scene_gate_uses_net_benefit_not_unregistered_zero_losses(self):
        rows=[dict(status='completed',winner=w,consistent=True) for w in ['new','new','base']]
        self.assertTrue(all(dataset_gate(rows,3,1,0.75).values()))
        self.assertFalse(dataset_gate(rows,4,1,0.75)['complete'])

    def fixture(self,root):
        source=root/'source';source.mkdir()
        case=dict(id='c',input='do task',materials=['fixed'],core_checks=['one','two','three'],bonus_check='bonus',critical_errors=['guarantee'])
        ev.write(source/'plan.json',dict(cases=[case]))
        base=dict(case='c',target='bitto',model='deepseek-v4.1-flash',repeat=1,scene='写方案',split='holdout',status='completed')
        for v,a in [('A','base answer'),('Cdoubleprime','new answer')]:ev.append(source/'runs.jsonl',dict(base,id=f'c--bitto--{v}--1',version=v,answer=a))
        return source

    def test_whole_output_schema_rejects_fences_extra_fields_and_parse_error(self):
        self.assertEqual(j.parse_output('{"verdict":"tie","reason":"equal"}')['verdict'],'tie')
        for s in ['```json\n{"verdict":"A","reason":"x"}\n```','{"verdict":"A","reason":"x","extra":1}','{"verdict":"parse_error","reason":"x"}']:
            with self.assertRaises(ValueError):j.parse_output(s)

    def test_two_orders_map_back_before_testing_consistency(self):
        rows=[dict(order=0,status='completed',output=dict(verdict='B',reason='new')),dict(order=1,status='completed',output=dict(verdict='A',reason='new'))]
        self.assertEqual(j.aggregate(rows),dict(status='completed',winner='new',consistent=True))
        rows[1]['output']['verdict']='B'
        self.assertEqual(j.aggregate(rows),dict(status='completed',winner='tie',consistent=False))
        rows[1]['status']='failed'
        self.assertEqual(j.aggregate(rows)['status'],'incomplete')
        with self.assertRaisesRegex(ValueError,'Duplicate'):j.aggregate([rows[0],rows[0]])

    def test_critical_findings_require_real_quote_and_agreement_not_verdict(self):
        packet=dict(critical_errors=['promise'],responses=dict(A='base says expected',B='new guarantees 6 weeks'))
        value=dict(verdict='tie',reason='not the deciding field',critical_A=[],critical_B=[dict(criterion=0,quote='guarantees 6 weeks')])
        j.validate_output(value,'critical',packet)
        bad=dict(value,critical_B=[dict(criterion=0,quote='invented')])
        with self.assertRaisesRegex(ValueError,'quote'):j.validate_output(bad,'critical',packet)
        rows=[dict(order=0,status='completed',output=value),dict(order=1,status='completed',output=dict(value,critical_A=value['critical_B'],critical_B=[]))]
        self.assertEqual(j.critical_findings(rows)['new_errors'],[0])
        rows[1]['output']['critical_A']=[]
        self.assertEqual(j.critical_findings(rows)['status'],'inconsistent')

    def test_packets_hide_identifiers_mapping_stays_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out';out.mkdir()
            ids=r.prepare(out,source,'A','Cdoubleprime')
            packet=json.loads((out/'blind-review'/f'{ids[0]}-0.json').read_text())
            self.assertEqual(set(packet),{'pair_id','task','materials','core_checks','bonus_check','critical_errors','responses'})
            self.assertNotIn('Cdoubleprime',json.dumps(packet))
            self.assertEqual(packet['responses'],dict(A='base answer',B='new answer'))
            flipped=json.loads((out/'blind-review'/f'{ids[0]}-1.json').read_text());self.assertEqual(flipped['responses']['A'],'new answer')
            self.assertTrue((out/'private-mapping.json').exists())

    def test_batch_audits_require_all_ids_and_verbatim_quotes(self):
        packet=dict(critical_errors=['promise'],responses=dict(A='base expected',B='new guaranteed'))
        item=dict(pair_id='opaque',verdict='A',reason='promise',critical_A=[],critical_B=[dict(criterion=0,quote='guaranteed')])
        self.assertEqual(batch_output(json.dumps(dict(items=[item])),{'opaque':packet})['opaque']['critical_B'][0]['criterion'],0)
        for items in [[],[item,item],[dict(item,pair_id='unknown')]]:
            with self.assertRaises(ValueError):batch_output(json.dumps(dict(items=items)),{'opaque':packet})

    def test_no_new_error_does_not_require_baseline_errors_to_agree(self):
        value=dict(verdict='tie',reason='no candidate errors',critical_A=[],critical_B=[])
        rows=[dict(order=0,status='completed',output=value),dict(order=1,status='completed',output=dict(value,critical_B=[dict(criterion=0,quote='base promise')]))]
        result=j.critical_findings(rows)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['new_errors'],[])
        self.assertFalse(result['base_agreement'])

    def test_relative_out_is_resolved_before_local_call_and_completed_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out';out.mkdir();ids=r.prepare(out,source,'A','Cdoubleprime')
            def fake(request,directory,timeout):
                self.assertTrue(directory.is_absolute());self.assertTrue((directory/'prompt.txt').exists())
                return dict(status='completed',answer='{"verdict":"tie","reason":"equal"}',observed_model='deepseek-v4.1-flash',tokens=dict(input=5,output=3),error=None,raw=dict(unit_fixture=True),job_id='unit')
            relative=Path(os.path.relpath(out,Path.cwd()))
            with patch.object(ev,'local_call',side_effect=fake) as call:
                self.assertEqual(r.run_new(relative,ids,['bitto'],'pair',1,2),2)
                self.assertEqual(r.run_new(relative,ids,['bitto'],'pair',1,2),0)
                self.assertEqual(call.call_count,2)
            results=r.report(out);valid=[x for x in results if x['status']=='completed'];self.assertEqual(len(valid),1)
            self.assertTrue(valid[0]['consistent'])

    def test_legacy_import_deduplicates_preserves_raw_and_does_not_attest_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out';out.mkdir();legacy=root/'legacy.jsonl'
            entry=dict(tag='c--bitto--Cdoubleprime--1',judge='bitto',model='deepseek-v4.1-flash',orders=[dict(slot_order=['A1','A2'],raw='B',winner=2,reason='{"verdict":"B","reason":"x","extra":1}'),dict(slot_order=['A2','A1'],raw='A',winner=2,reason='truncated raw reason')])
            legacy.write_text(json.dumps(entry)+'\n'+json.dumps(dict(entry))[:10])
            self.assertEqual(r.import_legacy(out,legacy,source,'A','Cdoubleprime'),2)
            self.assertEqual(r.import_legacy(out,legacy,source,'A','Cdoubleprime'),0)
            rows=ev.lines(out/'judges.jsonl');self.assertTrue(all(x['observed_model'] is None and x['tokens'] is None for x in rows));self.assertIn('extra',rows[0]['raw_response'])
            self.assertEqual(j.aggregate(rows)['winner'],'new')

    def test_failed_judgement_is_preserved_and_never_submitted_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.fixture(root);out=root/'out';out.mkdir();ids=r.prepare(out,source,'A','Cdoubleprime')
            fail=dict(status='failed',answer='',observed_model=None,tokens=None,error='unit backend error',raw={})
            with patch.object(ev,'local_call',return_value=fail) as call:
                r.run_new(out,ids,['bitto'],'pair',1,2);r.run_new(out,ids,['bitto'],'pair',1,2);self.assertEqual(call.call_count,2)
            self.assertTrue(all(x['status']=='failed' and x['output'] is None for x in ev.lines(out/'judges.jsonl')))
            self.assertTrue(all(x['status']=='incomplete' and x['winner'] is None for x in r.report(out)))

if __name__=='__main__':unittest.main()
