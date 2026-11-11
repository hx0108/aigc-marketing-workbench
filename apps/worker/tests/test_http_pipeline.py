import base64
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import httpx
from PIL import Image
from marketing_worker.business import handlers
from marketing_worker.factory import build_providers
from marketing_worker.pipeline import Pipeline
from test_pipeline import Store


class HTTPPipelineTest(unittest.TestCase):
    def test_synthetic_http_to_real_media(self):
        self.run_media_case(['douyin'])

    def test_dual_platform_same_sku_to_real_media(self):
        self.run_media_case(['douyin','xiaohongshu'])

    def run_media_case(self,platforms):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def asset(name,size,color):
                path=root/name; Image.new('RGB',size,color).save(path)
                return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            source={'product':asset('product.png',(80,160),'red'),'mask':asset('mask.png',(80,160),'white'),'white_background':asset('white.png',(400,600),'white')}
            backgrounds=[asset('studio.png',(500,700),'blue'),asset('tabletop.png',(500,700),'beige')]
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=160x240:r=25:d=2','-c:v','libx264',str(root/'clip.mp4')],capture_output=True,check=True)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=2',str(root/'voice.wav')],capture_output=True,check=True)
            copy={'douyin':{'title':'Synthetic','body':'Synthetic','narration':'Synthetic','poster_title':'Synthetic','shots':[{'duration':2,'narration':'Synthetic','fact_refs':['f1']}]}}
            if len(platforms)==2:
                copy['xiaohongshu']={'title':'Desktop note','body':'Check the appearance before choosing','narration':'On a tabletop',
                    'poster_title':'Tabletop details','shots':[{'duration':2,'narration':'On a tabletop','fact_refs':['f1']}]}
            calls=[]
            submitted_frames=[]
            def http(request):
                calls.append(request.url.path)
                path=request.url.path
                if path.endswith('/chat/completions'): result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(copy)}}]}
                elif path.endswith('/v1/image_generation'):
                    background=backgrounds[calls.count(path)-1]
                    encoded=base64.b64encode(Path(background['path']).read_bytes()).decode('ascii')
                    result={'data':{'image_base64':[encoded]},'base_resp':{'status_code':0}}
                elif path.endswith('/generation'): result={'output':{'audio':{'url':'https://assets.example/voice.wav'}}}
                elif request.method=='POST':
                    submitted_frames.append(json.loads(request.content)['content'][1]['image_url']['url'])
                    result={'task_id':'123'}
                else: result={'task':{'id':'123','model':'MiniMax-H3','status':'succeeded','content':{'url':'https://assets.example/clip.mp4'}}}
                return httpx.Response(200,json=result)
            config={kind:{'base_url':'https://provider.example','model':{'image':'image-01','video':'MiniMax-H3'}.get(kind,'test')} for kind in ['text','image','video','tts']}
            providers=build_providers(config,{key:'fake' for key in ['DEEPSEEK_API_KEY','MINIMAX_API_KEY','DASHSCOPE_API_KEY']},httpx.Client(transport=httpx.MockTransport(http)))
            def fetch(url,destination,hosts,kind):
                data=(root/url.rsplit('/',1)[1]).read_bytes()
                with Path(destination).open('xb') as out:out.write(data)
                return {'path':str(destination),'sha256':hashlib.sha256(data).hexdigest()}
            def publish(item):
                return 'data:image/png;base64,'+base64.b64encode(Path(item['path']).read_bytes()).decode('ascii')
            registry=handlers(providers,root,'C:/Windows/Fonts/msyh.ttc',{'assets.example'},source,lambda *args:None,lambda:False,publish,fetch)
            class Services:
                def invoke(self,kind,payload,intent):
                    try:return registry[kind](payload,intent)
                    except subprocess.CalledProcessError as error:
                        raise AssertionError(error.stderr.decode(errors='replace')) from error
            result=Pipeline(Store(),Services()).execute('test',{'platforms':platforms,'duration_seconds':2,'facts':[{'id':'f1','validity':'active'}]})
            self.assertEqual(set(result['images']),{'white','scene_1','scene_2'})
            self.assertEqual(set(result['platforms']),set(platforms))
            for platform,branches in result['platforms'].items():
                for kind,branch in branches.items():
                    self.assertEqual(branch['state'],'awaiting_review',branch)
                    self.assertTrue(Path(branch['result']['path']).is_file(),(platform,kind))
            if len(platforms)==2:
                self.assertEqual(submitted_frames,[publish(result['images'][slot]) for slot in ('scene_1','scene_2')])
                self.assertNotEqual(*submitted_frames)
                self.assertNotEqual(*(result['platforms'][p]['poster']['result']['sha256'] for p in platforms))
            self.assertEqual(calls.count('/v1/image_generation'),2)
