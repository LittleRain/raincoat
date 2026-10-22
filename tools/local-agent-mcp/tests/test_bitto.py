from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bitto
class BittoEventsTests(unittest.TestCase):
    def event(self,kind,**payload):return {'type':bitto.PREFIX+kind,'payload':payload}
    def test_intermediate_message_is_not_task_completion(self):
        s={'status':'submitted','model':'test','tool_calls':[],'message_usage':[]}
        bitto.consume_event(s,self.event('SessionAccepted',runId='current'))
        bitto.consume_event(s,self.event('SessionChatMessageEnded',runId='current',contents=[{'text':{'text':'still working'}}],meta={'stopReason':'STOP_REASON_TOOL_USE'}))
        self.assertEqual(s['status'],'running')
        bitto.consume_event(s,self.event('SessionRunEnded',runId='other',stopReason='STOP_REASON_STOP'))
        self.assertEqual(s['status'],'running')
        bitto.consume_event(s,self.event('SessionRunEnded',runId='current',stopReason='STOP_REASON_STOP'))
        self.assertEqual(s['status'],'succeeded')
    def test_normal_end_turn_wins_cancel_race(self):
        state={'status':'running','model':'test','cancel_sent':True,'run_id':'current'}
        bitto.consume_event(state,self.event('SessionRunEnded',stopReason='STOP_REASON_END_TURN'))
        self.assertEqual(state['status'],'succeeded')
if __name__=='__main__':unittest.main()
