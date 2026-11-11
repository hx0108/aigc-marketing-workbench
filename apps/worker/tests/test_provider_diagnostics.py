import unittest
import httpx
from marketing_worker.http_providers import DeepSeek,ProviderRejected


class DiagnosticTests(unittest.TestCase):
    def test_failed_step_persists_actionable_code_without_response_body(self):
        from marketing_worker.pipeline import Pipeline
        saved=[]
        class Store:
            def read(self,*args):return None
            def canceled(self,*args):return False
            def write(self,*args):saved.append(args)
        class Services:
            def invoke(self,*args):raise ProviderRejected('redacted',403,'ModelNotOpen')
        with self.assertRaises(ProviderRejected):Pipeline(Store(),Services()).step('task','image/scene_1','product_image',{})
        self.assertEqual(saved[-1],('task','image/scene_1','failed',{'code':'provider_rejected','provider_status':403,'provider_code':'ModelNotOpen'}))

    def test_rejection_retains_safe_code_without_raw_response(self):
        for code,expected in [('ModelNotOpen','ModelNotOpen'),('https://private.example/token?secret=hidden',None)]:
            with self.subTest(code=code),httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(403,json={'error':{'code':code,'message':'private token and request contents'}}))) as client:
                provider=DeepSeek('test-key','https://example.com','test',client)
                with self.assertRaises(ProviderRejected) as caught:provider.submit([])
                self.assertEqual(caught.exception.status_code,403)
                self.assertEqual(caught.exception.provider_code,expected)
                self.assertNotIn('private',str(caught.exception))
