import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from run import CATALOG
from validate_rules import validate
from judge_release import dataset_gate

class HarnessGateTests(unittest.TestCase):
    def test_registered_harness_net_gate_can_pass_with_a_loss(self):
        rows=[dict(status='completed',winner=x,consistent=True) for x in ['new','new','base','tie']]
        self.assertTrue(all(dataset_gate(rows,4,1,0.75).values()))
        rows[0]['winner']='tie'
        self.assertFalse(dataset_gate(rows,4,1,0.75)['win_margin'])

    def test_only_explicit_harness_protocol_dispatches_to_blind_gate(self):
        c=json.loads(CATALOG.read_text());rule=next(r for r in c['rules'] if r['id']=='bitto-readonly')
        rule['enabled']=True;rule['evidence']=[dict(protocol='stage8-harness-blind-v1')]
        with patch('harness_release.validate_enabled') as check:
            validate(c);check.assert_called_once_with(rule,Path(CATALOG).resolve().parents[3])

    def test_model_rule_cannot_bypass_its_gate_with_harness_protocol_marker(self):
        c=json.loads(CATALOG.read_text());rule=next(r for r in c['rules'] if r['kind']=='model')
        rule['enabled']=True;rule['evidence']=[dict(protocol='stage8-harness-blind-v1')]
        with patch('harness_release.validate_enabled') as check:
            with self.assertRaises((KeyError,AssertionError)):validate(c)
            check.assert_not_called()

if __name__=='__main__':unittest.main()
