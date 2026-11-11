import hashlib
import subprocess
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
import pytest
from sqlalchemy import func, select

from app import db, exporting, sources
from app.db import Record
from app.execution import ExternalCall, Task
from app.job_repository import JobRepository
from app.ledger import CallReservation
from marketing_worker import business
from marketing_worker.bridge import RenderBridge
from marketing_worker.persistence import StepStore
from marketing_worker.runner import run_once
from test_core import client


def test_uploaded_mp4_trims_one_shot_without_external_calls(client,tmp_path,monkeypatch):
    monkeypatch.setattr(business,'_configuration',None)
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    monkeypatch.setattr(exporting,'ROOT',tmp_path)
    font='C:/Windows/Fonts/msyh.ttc' if Path('C:/Windows/Fonts/msyh.ttc').is_file() else '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'
    monkeypatch.setenv('AIGC_RENDER_FONT',font)
    forbidden=Mock(side_effect=AssertionError('supplier configuration accessed'))
    monkeypatch.setattr(business,'authorization_snapshot',forbidden)

    def ffmpeg(*args):
        return subprocess.run(['ffmpeg','-v','error','-nostdin',*args],check=True,capture_output=True).stdout

    def asset(name):
        path=tmp_path/name
        return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

    Image.new('RGB',(360,480),'red').save(tmp_path/'image.png')
    ffmpeg('-f','lavfi','-i','color=c=red:s=160x240:r=25:d=2','-c:v','libx264','-threads','2',str(tmp_path/'original.mp4'))
    ffmpeg('-f','lavfi','-i','color=c=blue:s=160x240:r=25:d=1','-f','lavfi','-i','color=c=lime:s=160x240:r=25:d=2',
        '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0','-c:v','libx264','-threads','2',str(tmp_path/'upload.mp4'))
    ffmpeg('-f','lavfi','-i','sine=frequency=440:duration=4',str(tmp_path/'voice.wav'))
    content={'title':'Sample','body':'Sample','narration':'SampleSample','poster_title':'Sample','fact_refs':['appearance'],
        'shots':[{'duration':2,'narration':'Sample','fact_refs':['appearance'],'asset_slot':'scene_1'} for _ in range(2)]}
    renderer=RenderBridge(tmp_path,font)
    image=asset('image.png')
    images=dict.fromkeys(('white','scene_1','scene_2'),image)
    old_clip=asset('original.mp4')
    voice=asset('voice.wav')
    video=renderer.video({'clips':[old_clip,old_clip],'voice':voice,'duration':4,'copy':content},'original/douyin/video')
    poster=renderer.poster({'copy':content,'images':images,'image_slot':'scene_1'},'original/douyin/poster')
    with db.Session.begin() as session:
        session.add_all([Record(id='sku',workspace='one',kind='sku',data={'name':'Sample'}),
            Record(id='other-sku',workspace='one',kind='sku',data={'name':'Other'}),
            Record(id='image-source',workspace='one',kind='source',data={'sku_id':'sku','type':'image','rights_confirmed':True,
                'size':(tmp_path/'image.png').stat().st_size,'object_key':'image.png','sha256':image['sha256']}),
            Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed','facts':{'appearance':'Sample'},
                'source_ids':['image-source']}),
            Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','profile_id':'profile','platforms':['douyin'],'duration_seconds':4}),
            Task(id='original',workspace='one',phase='creation_run',state='running',fencing_token=1,payload={})])
    store=StepStore(db.Session,'one',1)
    for slot,item in images.items():store.write('original','image/'+slot,'succeeded',item)
    for index in range(2):store.write('original',f'douyin/dynamic/{index}','succeeded',old_clip)
    store.write('original','douyin/voice','succeeded',voice)
    original=business.persist_result(db.Session,{'id':'original','workspace':'one','fencing_token':1,'payload':{'work_id':'work'}},
        {'images':images,'platforms':{'douyin':{'video':{'state':'awaiting_review','result':video},
            'poster':{'state':'awaiting_review','result':poster}}},'copy':{'douyin':content}},tmp_path)
    with db.Session.begin() as session:session.get(Task,'original').state='succeeded'

    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token']}
    def upload(sku_id):
        result=client.post('/api/v1/skus/'+sku_id+'/sources',content=(tmp_path/'upload.mp4').read_bytes(),
            headers={**headers,'X-Rights-Confirmed':'true','X-Filename':'upload.mp4','Content-Type':'video/mp4'})
        assert result.status_code==201,result.text
        return result.json()
    uploaded=upload('sku')
    foreign=upload('other-sku')
    work_url='/api/v1/works/work'
    before=client.get(work_url).json()
    def save(source_id,start):
        return client.patch(work_url+'/draft',json={'expected_revision':before['revision'],
            'changes':{'shots':[{'index':0,'video_source_id':source_id,'start_seconds':start}]}},headers=headers)
    for source_id,start,code in [(foreign['id'],1,'VIDEO_SOURCE_REQUIRED'),
        (uploaded['id'],1.5,'VIDEO_SOURCE_TRIM_INVALID'),('https://example.invalid/a.mp4',1,'VIDEO_SOURCE_REQUIRED')]:
        rejected=save(source_id,start)
        assert rejected.status_code==422 and rejected.json()['detail']['code']==code,rejected.text
    saved=save(uploaded['id'],1)
    assert saved.status_code==200,saved.text
    quote=client.post(work_url+'/change-quotes',headers=headers).json()
    assert quote['invalidated_nodes']==['source_clip','video_compose'] and quote['cost_upper_bound']==0
    assert quote['execution_mode']=='local_only'
    applied=client.post(work_url+'/apply',json={'expected_revision':saved.json()['revision'],'quote_id':quote['quote_id'],'authorized':True},
        headers={**headers,'Idempotency-Key':'uploaded-mp4'})
    assert applied.status_code==200,applied.text
    assert client.get(work_url).json()['current_result']==original['result_revision']
    assert run_once(JobRepository(db.Session),'source-clip-worker',business.configured_services)

    with db.Session() as session:
        task=session.get(Task,applied.json()['task_id'])
        assert task.state=='succeeded',task.payload
        work=session.get(Record,'work')
        current=session.get(Record,work.data['current_result'])
        assert current.data['parent_revision']==original['result_revision']
        assert current.data['step_sources']=={'douyin/source_clip/0':task.id}
        reference=current.data['render_settings']['douyin']['shot_video_sources']['0']
        assert (reference['source_id'],reference['start_seconds'])==(uploaded['id'],1)
        assert session.scalar(select(func.count()).select_from(ExternalCall))==0
        assert session.scalar(select(func.count()).select_from(CallReservation))==0
        movie=Path(current.data['branches']['douyin']['video']['result']['path'])
        rights=exporting.export_rights(session,'one',work,current,'video_only',[session.get(Record,id) for id in current.data['assets']])
        assert any(item['id']==uploaded['id'] and item['confirmation']=='user_confirmed' and item['shot_index']==0
            for item in rights['materials'])
        exporting.require_release_rights(rights)
    def pixel(at):
        return tuple(ffmpeg('-ss',at,'-i',str(movie),'-frames:v','1',
            '-vf','format=rgb24,crop=1:1:540:960','-f','rawvideo','pipe:1'))
    red,green,blue=pixel('0.5')
    assert green>220 and max(red,blue)<35
    red,green,blue=pixel('2.5')
    assert red>220 and max(green,blue)<35
    assert hashlib.sha256(Path(video['path']).read_bytes()).hexdigest()==video['sha256']
    with db.Session.begin() as session:
        row=session.get(Record,uploaded['id'])
        row.data={**row.data,'rights_confirmed':False}
        work=session.get(Record,'work')
        result=session.get(Record,work.data['current_result'])
        rights=exporting.export_rights(session,'one',work,result,'video_only',[session.get(Record,id) for id in result.data['assets']])
        with pytest.raises(ValueError,match='MATERIAL_RIGHTS_UNVERIFIED'):
            exporting.require_release_rights(rights)
    current=client.get(work_url).json()
    reverted=client.patch(work_url+'/draft',json={'expected_revision':current['revision'],
        'changes':{'shots':[{'index':0,'asset_slot':'scene_1'}]}},headers=headers)
    assert reverted.status_code==200,reverted.text
    quote=client.post(work_url+'/change-quotes',headers=headers).json()
    assert quote['invalidated_nodes']==['video_compose'] and quote['cost_upper_bound']==0
    forbidden.assert_not_called()
