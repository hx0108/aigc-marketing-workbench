import unittest
import httpx
from marketing_worker.http_providers import DeepSeek, MiniMaxHailuoFast, MiniMaxImage, MiniMaxVideo, QwenTTS, ExternalUnknown, ProviderRejected


class AdapterTests(unittest.TestCase):
    def test_hailuo_fast_private_frame_and_fixed_price(self):
        import base64
        from decimal import Decimal
        from io import BytesIO
        import json
        from PIL import Image
        from app.pricing import HAILUO_FAST_MODEL, HAILUO_FAST_PRICE_VERSION, dynamic_bound, creation_reservation_floor
        from marketing_worker.results import await_video

        image = BytesIO()
        Image.new('RGB',(400,600)).save(image,format='PNG')
        inline = 'data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()
        inputs = [{'type':'text','text':'Product in daylight'},{'type':'image_url','image_url':{'url':inline}}]
        requests = []
        def handler(request):
            requests.append(request)
            base = {'base_resp':{'status_code':0}}
            if request.method == 'POST':return httpx.Response(200,json={**base,'task_id':'123'})
            if request.url.path == '/v1/query/video_generation':
                return httpx.Response(200,json={**base,'task_id':'123','status':'Success','file_id':'456'})
            return httpx.Response(200,json={**base,'file':{'file_id':'456','purpose':'video_generation','download_url':'https://cdn.hailuoai.com/result.mp4'}})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            adapter=MiniMaxHailuoFast('key','https://api.minimax.cn',HAILUO_FAST_MODEL,client)
            submitted=adapter.submit(inputs,3)
            self.assertEqual(await_video(adapter,submitted['id'],lambda *_:None,lambda:False),'https://cdn.hailuoai.com/result.mp4')
            with self.assertRaises(ValueError):adapter.submit(inputs,6.1)
            with self.assertRaises(ValueError):adapter.submit([inputs[0],{'type':'image_url','image_url':{'url':'https://private.invalid/frame.png'}}],6)
        self.assertEqual([(r.method,r.url.path) for r in requests],[('POST','/v1/video_generation'),
            ('GET','/v1/query/video_generation'),('GET','/v1/files/retrieve')])
        self.assertEqual(requests[1].url.params['task_id'],'123')
        self.assertEqual(requests[2].url.params['file_id'],'456')
        self.assertEqual(json.loads(requests[0].content),{'model':HAILUO_FAST_MODEL,'prompt':'Product in daylight',
            'first_frame_image':inline,'resolution':'768P','duration':6,'prompt_optimizer':False})
        auth={'price_version':HAILUO_FAST_PRICE_VERSION,'providers':{'video':HAILUO_FAST_MODEL},
            'provider_parameters':{'video':adapter.parameters},'bounds':{'dynamic':'1.35','text':'0.01','product_image':'0.10','tts':'0.02'}}
        self.assertEqual(dynamic_bound(auth,3),Decimal('1.35'))
        self.assertEqual(creation_reservation_floor(auth,6,2),Decimal('2.95'))
        with self.assertRaises(ValueError):dynamic_bound({**auth,'price_version':'wrong'},3)
    def test_effective_parameters_cannot_disagree_with_wire(self):
        import json
        bodies=[]
        client=httpx.Client(transport=httpx.MockTransport(lambda request:(bodies.append(json.loads(request.content)) or httpx.Response(200,json={}))))
        DeepSeek('key','https://example.test','test',client,parameters={'max_tokens':512}).submit([{'content':'JSON'}])
        self.assertEqual(bodies[-1]['max_tokens'],512)
        for adapter,parameters in [(DeepSeek,{'thinking':{'type':'enabled'}}),(DeepSeek,{'max_tokens':True}),(DeepSeek,{'max_input_bytes':0}),(MiniMaxVideo,{'resolution':'2K'}),(MiniMaxImage,{'n':2}),(MiniMaxImage,{'unknown':1})]:
            with self.subTest(parameters=parameters),self.assertRaises(ValueError):adapter('key','https://example.test',{MiniMaxVideo:'MiniMax-H3',MiniMaxImage:'image-01'}.get(adapter,'test'),client,parameters=parameters)
    def test_explicit_cost_controls(self):
        import json
        bodies=[]
        client=httpx.Client(transport=httpx.MockTransport(lambda request:(bodies.append(json.loads(request.content)) or httpx.Response(200,json={}))))
        DeepSeek('key','https://example.test','test',client).submit([{'role':'user','content':'JSON'}])
        self.assertEqual(bodies[-1]['thinking'],{'type':'disabled'})
        with self.assertRaises(ValueError):DeepSeek('key','https://example.test','test',client).submit([{'content':'x'*20000}])

    def test_minimax_single_image_and_first_frame_video(self):
        import json
        requests = []
        def handler(request):
            requests.append(request)
            if request.url.path == '/v1/image_generation':
                return httpx.Response(200, json={'base_resp': {'status_code': 0}, 'data': {'image_base64': ['dGVzdA==']}})
            if request.method == 'POST':
                return httpx.Response(200, json={'task_id': '123'})
            return httpx.Response(200, json={'task': {'id': '123', 'model': 'MiniMax-H3', 'status': 'succeeded', 'content': {'url': 'https://cdn.hailuoai.com/test.mp4'}}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            image = MiniMaxImage('key', 'https://api.minimax.cn', 'image-01', client)
            video = MiniMaxVideo('key', 'https://api.minimax.cn', 'MiniMax-H3', client)
            self.assertEqual(image.submit('scene')['data']['image_base64'], ['dGVzdA=='])
            content = [{'type': 'text', 'text': 'scene'}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,dGVzdA=='}}]
            self.assertEqual(video.submit(content, 2.5)['id'], '123')
            self.assertEqual(video.query('123')['content']['video_url'], 'https://cdn.hailuoai.com/test.mp4')
            with self.assertRaises(ValueError):
                video.submit(content, 15.1)
        self.assertEqual([r.url.path for r in requests], ['/v1/image_generation', '/v2/video_generation', '/v2/query/video_generation/123'])
        self.assertTrue(all(r.headers['Authorization'] == 'Bearer key' for r in requests))
        image_body, video_body = (json.loads(r.content) for r in requests[:2])
        self.assertEqual((image_body['n'], image_body['response_format']), (1, 'base64'))
        self.assertEqual((video_body['duration'], video_body['resolution'], video_body['ratio']), (4, '768P', 'adaptive'))
        self.assertEqual(video_body['content'][1]['role'], 'first_frame')

    def test_minimax_rejects_application_error_on_http_success(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'base_resp': {'status_code': 1008}}))) as client:
            image = MiniMaxImage('key', 'https://api.minimax.cn', 'image-01', client)
            with self.assertRaises(ProviderRejected) as error:
                image.submit('scene')
            self.assertEqual(error.exception.provider_code, '1008')

    def test_each_provider_serializes_authenticated_request(self):
        for provider, args, suffix in [(DeepSeek, ([{'role': 'user', 'content': 'JSON'}],), '/chat/completions'), (QwenTTS, ('商品介绍',), '/services/aigc/multimodal-generation/generation')]:
            requests = []
            def handler(request):
                requests.append(request)
                return httpx.Response(200, json={'id': 'test'})
            adapter = provider('test-key', 'https://example.test', 'explicit-model', httpx.Client(transport=httpx.MockTransport(handler)))
            self.assertEqual(adapter.submit(*args), {'id': 'test'})
            self.assertEqual(requests[0].url.path, suffix)
            self.assertEqual(requests[0].headers['authorization'], 'Bearer test-key')

    def test_timeout_is_unknown_without_retry(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout('timeout')
        adapter = QwenTTS('key', 'https://example.test', 'model', httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(ExternalUnknown):
            adapter.submit('hello')
        self.assertEqual(len(calls), 1)

    def test_tts_limit_before_http(self):
        adapter = QwenTTS('key', 'https://example.test', 'model')
        with self.assertRaises(ValueError):
            adapter.submit('a' * 601)
