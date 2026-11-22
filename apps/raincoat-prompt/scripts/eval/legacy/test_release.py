"""Patch rebuilds reuse approved evidence and cannot change the enabled rule set."""
import copy,json,plistlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run as ev
from validate_release import validate

class RebuildReleaseTests(unittest.TestCase):
    def fixture(self,root):
        baseline=dict(version='0.2.0',templates=[dict(scene='development',version='0.2.0',text='unchanged')],rules=[])
        ev.write(root/'docs/releases/0.2.0-catalog.json',baseline)
        rule=dict(id='workbuddy-no-tools',kind='harness',enabled=True,instruction='unchanged',evidence=[dict(protocol='tools-v1-deterministic')])
        previous=dict(baseline,version='0.2.1',rules=[rule]);ev.write(root/'prior-catalog.json',previous)
        (root/'proof.txt').write_text('original evidence\n')
        proof=ev.digest((root/'proof.txt').read_bytes())
        ev.write(root/'docs/releases/0.2.0-evaluation.json',dict(catalog_sha256=ev.digest((root/'docs/releases/0.2.0-catalog.json').read_bytes()),artifacts={'proof.txt':proof},datasets=[],critical_judges=['bitto'],evidence='.build/scene'))
        old=dict(version='0.2.1',protocol='tools-v1-deterministic',enabled_rules=['workbuddy-no-tools'],scene_base_catalog='docs/releases/0.2.0-catalog.json',catalog_sha256=ev.digest((root/'prior-catalog.json').read_bytes()),artifacts={'proof.txt':proof})
        ev.write(root/'docs/releases/0.2.1-evaluation.json',old)
        catalog=dict(previous,version='0.2.2');ev.write(root/'Sources/PromptCore/Resources/prompt-rules.json',catalog)
        manifest=copy.deepcopy(old);manifest.update(version='0.2.2',catalog_sha256=ev.digest((root/'Sources/PromptCore/Resources/prompt-rules.json').read_bytes()),change_class='rebuild-only',no_behavior_change=True,base_manifest='docs/releases/0.2.1-evaluation.json',base_manifest_sha256=ev.digest((root/'docs/releases/0.2.1-evaluation.json').read_bytes()),behavior_base_catalog='prior-catalog.json',behavior_base_catalog_sha256=old['catalog_sha256'])
        manifest['artifacts'].update({'docs/releases/0.2.1-evaluation.json':manifest['base_manifest_sha256'],'prior-catalog.json':old['catalog_sha256']})
        ev.write(root/'docs/releases/0.2.2-evaluation.json',manifest)
        (root/'assets').mkdir();(root/'assets/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleShortVersionString='0.2.2')))
        return catalog,manifest

    def test_022_unchanged_evidence_passes_and_enabled_manifest_mismatch_rejects(self):
        with tempfile.TemporaryDirectory() as tmp,patch('tools_release.validate_enabled') as tools,patch('judge_release.evaluate',return_value=dict(passed=True)):
            root=Path(tmp);catalog,manifest=self.fixture(root)
            validate(root);tools.assert_called_once_with(catalog['rules'][0],root)
            manifest['enabled_rules']=[];ev.write(root/'docs/releases/0.2.2-evaluation.json',manifest)
            with self.assertRaises(AssertionError):validate(root)

    def test_rebuild_cannot_change_rule_text_even_with_a_new_catalog_hash(self):
        with tempfile.TemporaryDirectory() as tmp,patch('tools_release.validate_enabled'),patch('judge_release.evaluate',return_value=dict(passed=True)):
            root=Path(tmp);catalog,manifest=self.fixture(root)
            catalog['rules'][0]['instruction']='changed behaviour';ev.write(root/'Sources/PromptCore/Resources/prompt-rules.json',catalog)
            manifest['catalog_sha256']=ev.digest((root/'Sources/PromptCore/Resources/prompt-rules.json').read_bytes());ev.write(root/'docs/releases/0.2.2-evaluation.json',manifest)
            with self.assertRaisesRegex(AssertionError,'behavior'):validate(root)

    def test_021_keeps_using_the_same_harness_validation_path(self):
        with tempfile.TemporaryDirectory() as tmp,patch('tools_release.validate_enabled') as tools,patch('judge_release.evaluate',return_value=dict(passed=True)):
            root=Path(tmp);self.fixture(root)
            (root/'assets/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleShortVersionString='0.2.1')))
            (root/'Sources/PromptCore/Resources/prompt-rules.json').write_bytes((root/'prior-catalog.json').read_bytes())
            validate(root);tools.assert_called_once()

if __name__=='__main__':unittest.main()
