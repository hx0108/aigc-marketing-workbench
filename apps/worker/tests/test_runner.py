import unittest
from unittest.mock import patch
from marketing_worker.runner import run_once,HANDLERS
from marketing_worker.http_providers import ExternalUnknown
class Repository:
    def __init__(self):self.finished=None
    def claim(self,owner):return {'id':'task','fencing_token':1,'kind':'test','payload':{}}
    def canceled(self,*args):return False
    def heartbeat(self,*args):return True
    def _finish(self,task,token,state,result):self.finished=(state,result)
    def fail(self,task,token,code):self.finished=('failed',code)
    def complete(self,task,token,result):self.finished=('succeeded',result)
class RunnerTests(unittest.TestCase):
    def test_provider_unknown_is_not_a_definite_failure(self):
        repo=Repository()
        def uncertain():raise ExternalUnknown('network response lost')
        with patch.dict(HANDLERS,{'test':uncertain}):self.assertTrue(run_once(repo,'owner'))
        self.assertEqual(repo.finished[0],'external_unknown')
        self.assertEqual(repo.finished[1],{'code':'external_unknown'})
    def test_partial_results_remain_partial(self):
        repo=Repository()
        with patch.dict(HANDLERS,{'test':lambda:{'status':'partial','assets':['completed']}}):run_once(repo,'owner')
        self.assertEqual(repo.finished[0],'partial')
        self.assertEqual(repo.finished[1]['assets'],['completed'])
