import unittest
from marketing_worker.results import text_result, await_video
from marketing_worker.http_providers import ExternalUnknown, ProviderRejected


class ResultTests(unittest.TestCase):
    def test_incomplete_text_rejected(self):
        with self.assertRaises(ProviderRejected):
            text_result({'choices':[{'finish_reason':'length','message':{'content':'{}'}}]})

    def test_poll_only_queries_existing_id(self):
        class Provider:
            def query(self, identifier):
                self.identifier=identifier
                return {'status':'succeeded','content':{'video_url':'https://example.test/video'}}
        provider=Provider(); states=[]
        result=await_video(provider,'task-1',lambda *args:states.append(args),lambda:False)
        self.assertEqual(result,'https://example.test/video')
        self.assertEqual(provider.identifier,'task-1')
        self.assertEqual(len(states),1)

    def test_cancel_keeps_remote_unknown(self):
        with self.assertRaises(ExternalUnknown):
            await_video(None,'task-1',None,lambda:True)

    def test_ambiguous_and_nonstandard_json_rejected(self):
        for content in ['{"title":"first","title":"second"}','{"duration":NaN}','{"duration":Infinity}','{"shots":[{"duration":1,"duration":2}]}']:
            with self.subTest(content=content):
                with self.assertRaises(ProviderRejected):
                    text_result({'choices':[{'finish_reason':'stop','message':{'content':content}}]})
