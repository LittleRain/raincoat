from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('analyze_video', SCRIPTS / 'analyze_video.py')
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)


class WorkflowTests(unittest.TestCase):
    def test_separate_activity_groups_stay_separate_after_padding(self):
        activity = [0] * 2 + [0.8] * 7 + [0] * 5 + [0.8] * 7 + [0] * 3
        ranges = analyzer.active_ranges(activity, 2, 3, len(activity), 3)
        self.assertEqual(ranges, [(0.0, 12.0), (12.0, 24)])

    def test_review_keeps_original_source_for_chatcut_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clips = root / 'clips.json'
            clips.write_text(json.dumps({'source':'/absolute/原片.MOV','duration':20,
                                         'candidates':[{'id':'rally-001','start':2,'end':10,'score':75,
                                                        'reasons':['活动候选'],'completeness_confidence':.5,'signals':{}}]}))
            page = root / 'review.html'
            subprocess.run([sys.executable,str(SCRIPTS / 'generate_review_html.py'),str(clips),
                            '--out',str(page),'--video-src','source.mov','--mode','person',
                            '--target-description','白衣黄裤'],check=True,capture_output=True)
            html = page.read_text()
            self.assertIn('"source": "/absolute/原片.MOV"', html)
            self.assertIn('"preview_source": "source.mov"', html)
            self.assertIn('"initial_mode": "person"', html)
            self.assertIn('"target_description": "白衣黄裤"', html)
            self.assertIn('ChatCut 交接清单', html)
            script = html.split('<script>',1)[1].split('</script>',1)[0]
            js = root / 'page.js'
            js.write_text(script)
            subprocess.run(['node','--check',str(js)],check=True,capture_output=True)

    def test_render_uses_exact_bounds_and_checks_selected_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'testsrc=size=320x180:rate=30:duration=4', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=4', '-c:v', 'libx264', '-pix_fmt',
                            'yuv420p', '-c:a', 'aac', str(source)], check=True)
            edits = root / 'edits.json'
            payload = {'source': str(source), 'confirmed': True, 'mode': 'person',
                       'target_description': '白衣黄裤', 'target_count': 2,
                       'clips': [{'id': 'a', 'keep': True, 'start': 0.3, 'end': 1.6, 'target_confirmed': True},
                                 {'id': 'b', 'keep': True, 'start': 2.2, 'end': 3.5, 'target_confirmed': True}]}
            edits.write_text(json.dumps(payload))
            output = root / 'highlights.mp4'
            command = [sys.executable, str(SCRIPTS / 'render_highlights.py'), str(edits), '--out', str(output)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            duration = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                             '-of', 'default=nw=1:nk=1', str(output)], check=True,
                                            capture_output=True, text=True).stdout)
            self.assertAlmostEqual(duration, 2.6, delta=0.08)
            payload['target_count'] = 3
            edits.write_text(json.dumps(payload))
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == '__main__':
    unittest.main()
