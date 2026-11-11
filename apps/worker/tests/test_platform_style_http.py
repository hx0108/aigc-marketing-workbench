import base64
import hashlib
import io
import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from marketing_worker import business
from marketing_worker.factory import build_providers
from marketing_worker.platform_style import STYLES, scene_owners


@pytest.mark.parametrize('platforms', [['douyin'], ['xiaohongshu'], ['douyin', 'xiaohongshu']])
def test_actual_provider_payloads_carry_selected_platform_direction(tmp_path, monkeypatch, platforms):
    calls=[]

    def transport(request):
        body=json.loads(request.content) if request.content else {}
        calls.append((request.url.path,body))
        if request.url.path.endswith('/chat/completions'):
            result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({p:{'title':p} for p in platforms})}}]}
        elif request.url.path.endswith('/image_generation'):
            buffer=io.BytesIO()
            Image.new('RGB',(120,180),['#eeeeee','#c3d9cd'][sum(path.endswith('/image_generation') for path,_ in calls)-1]).save(buffer,format='PNG')
            result={'data':{'image_base64':[base64.b64encode(buffer.getvalue()).decode()]},'base_resp':{'status_code':0}}
        elif request.method=='POST':
            result={'task_id':'123'}
        else:
            result={'task':{'id':'123','model':'MiniMax-H3','status':'succeeded','content':{'url':'https://assets.example/clip.mp4'}}}
        return httpx.Response(200,json=result)

    def asset(name, color):
        path=tmp_path/name
        Image.new('RGB',(60,100),color).save(path)
        return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

    sources={'product':asset('product.png','red'),'mask':asset('mask.png','white')}
    config={kind:{'base_url':'https://provider.example','model':model} for kind,model in {
        'text':'deepseek-chat','image':'image-01','video':'MiniMax-H3','tts':'qwen-tts',
    }.items()}
    monkeypatch.setattr(business,'normalize_minimax_clip',lambda clip,*args:clip)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        providers=build_providers(config,dict.fromkeys(['DEEPSEEK_API_KEY','MINIMAX_API_KEY','DASHSCOPE_API_KEY'],'fixture'),client)
        registry=business.handlers(providers,tmp_path,'C:/Windows/Fonts/msyh.ttc',{'assets.example'},sources,
            lambda *_:None,lambda:False,lambda item:'data:image/png;base64,'+base64.b64encode(Path(item['path']).read_bytes()).decode(),
            lambda *_:{'path':'fixture-clip'})
        request={'platforms':platforms,'duration_seconds':4,'facts':[{'id':'name','value':'白色无线耳机盒','validity':'active'},{'id':'appearance','value':'白色圆角盒，正面可见指示灯','validity':'active'}]}
        registry['text'](request,'text')
        owners=scene_owners(platforms)
        from marketing_worker.creative_direction import fallback_plan
        plans={p:{**fallback_plan(request['facts'],p),'palette':'blue_complement','surface':'wood'} for p in platforms}
        images={slot:registry['product_image']({'slot':slot,'request':request,'copy':{p:{'visual_plan':plans[p]} for p in platforms}},slot) for slot in owners}
        for platform in platforms:
            slot=next(slot for slot,owner in owners.items() if owner==platform)
            registry['dynamic']({'platform':platform,'shot':{'duration':4,'asset_slot':slot},'images':images},platform)
        registry['text']({'platforms':[platforms[-1]],'facts':[],'purpose':'copy_rewrite','instruction':'改写标题'},'rewrite')

    text_requests=[body for path,body in calls if path.endswith('/chat/completions')]
    assert all(len(json.dumps(body['messages'],ensure_ascii=False).encode('utf-8'))<=8192 for body in text_requests)
    initial,rewrite=[body['messages'][0]['content'] for body in text_requests]
    for platform in STYLES:
        assert (STYLES[platform]['copy'] in initial)==(platform in platforms)
        assert (STYLES[platform]['copy'] in rewrite)==(platform==platforms[-1])
    assert 'scene_allocation' not in rewrite
    prompts=[body['prompt'] for path,body in calls if path.endswith('/image_generation')]
    assert len(prompts)==2
    for index,(slot,owner) in enumerate(owners.items()):
        assert 'No product, text, logos or people' in prompts[index]
        assert 'muted blue accents' in prompts[index] and 'wood' in prompts[index]
        assert ('directional side light' if owner=='douyin' else 'diffused window light') in prompts[index]
        assert 'Background materials never describe or change the product' in prompts[index]
    videos=[body for path,body in calls if path=='/v2/video_generation']
    assert len(videos)==len(platforms)
    for platform,video in zip(platforms,videos):
        prompt=video['content'][0]['text']
        assert ('camera pushes in' if platform=='douyin' else 'camera drifts slowly') in prompt
        assert 'Keep the product stationary' in prompt
        assert len(prompt)<=2000
        assert video['content'][1]['role']=='first_frame'
    if len(platforms)==2:
        assert videos[0]['content'][1]['image_url']!=videos[1]['content'][1]['image_url']
