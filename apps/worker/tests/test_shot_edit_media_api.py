import base64
import hashlib
import json
import math
import struct
import subprocess
import wave
from pathlib import Path
import httpx
from PIL import Image
from marketing_worker.business import handlers
from marketing_worker.factory import build_providers
from marketing_worker.pipeline import Pipeline


from types import SimpleNamespace
from app import db,sources,exporting
from app.db import Record
from app.execution import Task
from marketing_worker.persistence import StepStore
from marketing_worker.business import persist_result
from marketing_worker.edits import edit_handler
from marketing_worker.runner import run_once
from app.job_repository import JobRepository
from test_core import client
import io,zipfile


def test_two_shot_revision_and_export(client,tmp_path,monkeypatch):
    invocations=[]
    root=tmp_path
    def asset(name,size,color):
        path=root/name; Image.new('RGB',size,color).save(path)
        return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    source={'product':asset('product.png',(80,160),'red'),'mask':asset('mask.png',(80,160),'white'),'white_background':asset('white.png',(400,600),'white')}
    asset('background.png',(500,700),'blue')
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=160x240:r=25:d=2','-c:v','libx264',str(root/'clip.mp4')],capture_output=True,check=True)
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=4',str(root/'voice.wav')],capture_output=True,check=True)
    copy={'douyin':{'title':'Synthetic','body':'Synthetic','narration':'SyntheticSynthetic','poster_title':'Synthetic','shots':[{'duration':2,'narration':'Synthetic','fact_refs':['f1'],'asset_slot':'scene_1'}, {'duration':2,'narration':'Synthetic','fact_refs':['f1'],'asset_slot':'scene_2'}]}}
    calls=[]
    def http(request):
        calls.append(request.url.path)
        path=request.url.path
        if path.endswith('/chat/completions'): result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(copy)}}]}
        elif path.endswith('/v1/image_generation'): result={'data':{'image_base64':[base64.b64encode((root/'background.png').read_bytes()).decode('ascii')]},'base_resp':{'status_code':0}}
        elif path.endswith('/generation'): result={'output':{'audio':{'url':'https://assets.example/voice.wav'}}}
        elif request.method=='POST': result={'task_id':'123'}
        else: result={'task':{'id':'123','model':'MiniMax-H3','status':'succeeded','content':{'url':'https://assets.example/clip.mp4'}}}
        return httpx.Response(200,json=result)
    config={kind:{'base_url':'https://provider.example','model':{'image':'image-01','video':'MiniMax-H3'}.get(kind,'test')} for kind in ['text','image','video','tts']}
    providers=build_providers(config,{key:'fake' for key in ['DEEPSEEK_API_KEY','MINIMAX_API_KEY','DASHSCOPE_API_KEY']},httpx.Client(transport=httpx.MockTransport(http)))
    def fetch(url,destination,hosts,kind):
        data=(root/url.rsplit('/',1)[1]).read_bytes()
        with Path(destination).open('xb') as out:out.write(data)
        return {'path':str(destination),'sha256':hashlib.sha256(data).hexdigest()}
    registry=handlers(providers,root,'C:/Windows/Fonts/msyh.ttc',{'assets.example'},source,lambda *args:None,lambda:False,lambda asset:'data:image/png;base64,dGVzdA==',fetch)
    class Services:
        def invoke(self,kind,payload,intent):
            invocations.append((kind,payload))
            return registry[kind](payload,intent)

    service=Services();service.private_root=root
    monkeypatch.setattr(sources,'ROOT',root);monkeypatch.setattr(exporting,'ROOT',root)
    with db.Session.begin() as session:
        session.add(Record(id='sku',workspace='one',kind='sku',data={'name':'Synthetic'}))
        session.add(Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed','facts':{'f1':'Synthetic'}}))
        session.add(Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','profile_id':'profile','platforms':['douyin'],'duration_seconds':4}))
        session.add(Task(id='original',workspace='one',state='running',phase='creation_run',fencing_token=1,payload={}))
    job={'id':'original','workspace':'one','fencing_token':1,'payload':{'work_id':'work'}}
    result=Pipeline(StepStore(db.Session,'one',1),service).execute('original',{'platforms':['douyin'],'duration_seconds':4,'facts':[{'id':'f1','value':'Synthetic','validity':'active'}]})
    assert result['platforms']['douyin']['video']['state']=='awaiting_review'
    stored=persist_result(db.Session,job,result,root)
    with db.Session() as session:result_clip=session.get(Record,'original:douyin/dynamic/1').data['result']
    original_hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token']}
    music=io.BytesIO()
    with wave.open(music,'wb') as audio:
        audio.setparams((1,2,8000,0,'NONE','not compressed'))
        audio.writeframes(b''.join(struct.pack('<h',round(4096*math.sin(2*math.pi*660*i/8000))) for i in range(8000)))
    uploaded=client.post('/api/v1/skus/sku/sources',content=music.getvalue(),headers={**headers,
        'X-Rights-Confirmed':'true','X-Filename':'synthetic-music.wav','Content-Type':'audio/wav'})
    assert uploaded.status_code==201,uploaded.text
    music_id=uploaded.json()['id']
    edits=[('visual',{'shots':[{'index':0,'visual_description':'Synthetic studio','asset_slot':'white'}]},['dynamic','video_render']),
        ('repair-shot',None,['static_clip','video_render']),
        ('narration',{'shots':[{'index':1,'narration':'Updated synthetic'}]},['tts','video_render']),
        ('subtitle',{'subtitle_style':'dark_on_light'},['video_render']),
        ('music',{'music':music_id},['video_render'])]
    for identifier,draft,expected in edits:
        if identifier=='repair-shot':
            with db.Session.begin() as session:
                work=session.get(Record,'work')
                prior=session.get(Record,work.data['current_result'])
                parent=next(row for asset_id in prior.data['assets'] if (row:=session.get(Record,asset_id)).data['media_kind']=='product_image' and row.data['slot']=='white')
                parent_id=parent.id
                with Image.open(root/parent.data['object_key']) as image:dimensions=image.size
                for source_id,color in [('repair-green','lime'),('repair-mask','white')]:
                    item=asset(source_id+'.png',dimensions,color)
                    session.add(Record(id=source_id,workspace='one',kind='source',data={
                        'sku_id':'sku','type':'image','rights_confirmed':True,'object_key':source_id+'.png','sha256':item['sha256'],
                    }))
                old_clip=session.get(Record,'visual:douyin/dynamic/0').data['result']
                session.add(Record(id='original:douyin/static/0',workspace='one',kind='task_step',data={'state':'succeeded','result':old_clip}))
                revision=work.revision
            repair=client.post('/api/v1/assets/'+parent_id+'/repairs',json={
                'original_source_id':'repair-green','mask_source_id':'repair-mask',
            },headers={**headers,'Idempotency-Key':'media-repair'})
            assert repair.status_code==202,repair.text
            assert run_once(JobRepository(db.Session),'repair-test-owner')
            repair_id=repair.json()['task_id']+':asset'
            path='/api/v1/assets/'+repair_id
            assert client.post(path+'/reviews',json={'decision':'adopt'},headers=headers).status_code==201
            applied=client.post(path+'/apply-repair',json={'expected_revision':revision},headers=headers)
            assert applied.status_code==200,applied.text
            draft={'shots':[{'index':0,'repair_asset_id':repair_id}]}
        with db.Session.begin() as session:
            work=session.get(Record,'work');base_id=work.data['current_result'];base=session.get(Record,base_id).data
            revision=work.revision
            session.add(Task(id=identifier,workspace='one',state='running',phase='edit_run',fencing_token=1,payload={}))
        invocations.clear()
        edited={'id':identifier,'workspace':'one','fencing_token':1,'payload':{'work_id':'work','profile_id':'profile','base_result':base,'base_result_id':base_id,'base_draft_revision':revision,'draft':{'platform':'douyin',**draft}}}
        try:stored=edit_handler(SimpleNamespace(sessions=db.Session),edited,lambda job:service)
        except subprocess.CalledProcessError as error:
            raise AssertionError(error.stderr.decode(errors='replace')) from error
        assert [kind for kind,_ in invocations]==expected
        if identifier=='narration':
            assert invocations[0][1]['text']=='SyntheticUpdated synthetic'
            assert invocations[-1][1]['copy']['shots'][1]['narration']=='Updated synthetic'
        if identifier not in {'visual','repair-shot'}:
            assert invocations[-1][1]['clips'][0]['path']==changed_clip
        else:changed_clip=invocations[-1][1]['clips'][0]['path']
        assert invocations[-1][1]['clips'][1]==result_clip
        for path,digest in original_hashes.items():assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
        with db.Session() as session:
            assert session.get(Record,'work').data['current_result']==identifier+':result'
            assert session.get(Record,'work').revision==revision+1
            current=session.get(Record,stored['result_revision'])
            video=next(row.data for asset_id in current.data['assets']
                       if (row:=session.get(Record,asset_id)).data['media_kind']=='video' and row.data['slot']=='douyin')
            if identifier!='visual':
                assert video['repair_source_ids']==[repair_id]
                cover=next(row.data for asset_id in current.data['assets']
                           if (row:=session.get(Record,asset_id)).data['media_kind']=='cover' and row.data['slot']=='douyin')
                assert cover['repair_source_ids']==[repair_id]
        subtitles=subprocess.run(['ffmpeg','-v','error','-i',str(root/video['object_key']),'-map','0:s:0','-f','srt','-'],capture_output=True,check=True).stdout.decode('utf-8')
        assert '00:00:02,000 --> 00:00:04,000' in subtitles
        if identifier in {'narration','subtitle','music'}:assert 'Updated synthetic' in subtitles
    for asset_id in stored['assets']:
        response=client.post('/api/v1/assets/'+asset_id+'/reviews',json={'decision':'adopt'},headers=headers)
        assert response.status_code==201,response.text
    response=client.post('/api/v1/export-packages',json={'work_id':'work','mode':'sample','selection':'full_suite'},headers=headers)
    assert response.status_code==200,response.text
    downloaded=client.get('/api/v1/exports/'+response.json()['id']+'/download')
    assert downloaded.status_code==200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert len(archive.namelist())==8
        copies=[json.loads(archive.read(n)) for n in archive.namelist() if n.endswith('.json') and n!='manifest.json']
        assert copies[0]['shots'][1]['narration']=='Updated synthetic'
        movie=next(n for n in archive.namelist() if n.endswith('.mp4'))
        assert hashlib.sha256(archive.read(movie)).hexdigest()==video['sha256']
        def center_pixel(timestamp):
            frame=subprocess.run(['ffmpeg','-v','error','-i','pipe:0','-ss',timestamp,'-frames:v','1',
                '-vf','format=rgb24,crop=1:1:540:960','-f','rawvideo','pipe:1'],
                input=archive.read(movie),capture_output=True,check=True).stdout
            return tuple(frame)
        red,green,blue=center_pixel('0.5')
        assert green>220 and max(red,blue)<35
        red,green,blue=center_pixel('2.5')
        assert red>220 and max(green,blue)<35
        manifest=json.loads(archive.read('manifest.json'))
        assert any(material['id']==music_id and material['confirmation']=='user_confirmed'
                   for material in manifest['material_rights']['materials'])
        decoded=subprocess.run(['ffmpeg','-v','error','-i','pipe:0','-ss','2','-t','1','-map','0:a:0',
            '-ac','1','-ar','8000','-f','s16le','pipe:1'],input=archive.read(movie),capture_output=True,check=True).stdout
        samples=[sample for sample, in struct.iter_unpack('<h',decoded)]
        assert len(samples)==8000
        def amplitude(frequency):
            phase=[2*math.pi*frequency*i/8000 for i in range(len(samples))]
            return 2*math.hypot(sum(x*math.cos(t) for x,t in zip(samples,phase)),
                                sum(x*math.sin(t) for x,t in zip(samples,phase)))/len(samples)
        assert 3000<amplitude(440)<5000
        assert 300<amplitude(660)<900
