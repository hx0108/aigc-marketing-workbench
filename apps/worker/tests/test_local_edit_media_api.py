import hashlib
import subprocess
import pytest
from pathlib import Path
from unittest.mock import Mock
from PIL import Image
from sqlalchemy import select, func
from app import db, sources, exporting
from app.db import Record
from app.execution import Task, ExternalCall
from app.ledger import CallReservation
from app.job_repository import JobRepository
from marketing_worker import business
from marketing_worker.bridge import RenderBridge
from marketing_worker.runner import run_once
from marketing_worker.persistence import StepStore
from test_core import client


def test_provider_disabled_poster_subtitles_music_render_and_replay(client,tmp_path,monkeypatch):
    monkeypatch.setattr(business,'_configuration',None)
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    monkeypatch.setattr(exporting,'ROOT',tmp_path)
    font='C:/Windows/Fonts/msyh.ttc' if Path('C:/Windows/Fonts/msyh.ttc').is_file() else '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'
    monkeypatch.setenv('AIGC_RENDER_FONT',font)
    def asset(name):
        path=tmp_path/name
        return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    Image.new('RGB',(360,480),'teal').save(tmp_path/'image.png')
    subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','color=c=teal:s=160x240:r=25:d=2','-c:v','libx264','-threads','2',str(tmp_path/'clip.mp4')],check=True,capture_output=True)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','sine=frequency=440:duration=2',str(tmp_path/'voice.wav')],check=True,capture_output=True)
    content={'title':'Sample','body':'Sample','narration':'Sample','poster_title':'Sample','fact_refs':['appearance'],'selling_points':[],
             'shots':[{'duration':2,'narration':'Sample','fact_refs':['appearance'],'asset_slot':'scene_1'}]}
    renderer=RenderBridge(tmp_path,font)
    images={slot:asset('image.png') for slot in ('white','scene_1','scene_2')}
    video=renderer.video({'clips':[asset('clip.mp4')],'voice':asset('voice.wav'),'duration':2,'copy':content},'original/douyin/video')
    poster=renderer.poster({'copy':content,'images':images,'image_slot':'scene_1'},'original/douyin/poster')
    with db.Session.begin() as session:
        session.add_all([Record(id='sku',workspace='one',kind='sku',data={'name':'Sample'}),
            Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed','facts':{'appearance':'Sample'}}),
            Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','profile_id':'profile','platforms':['douyin'],'duration_seconds':2}),
            Task(id='original',workspace='one',phase='creation_run',state='running',fencing_token=1,payload={})])
    store=StepStore(db.Session,'one',1)
    for slot,image in images.items():store.write('original','image/'+slot,'succeeded',image)
    store.write('original','douyin/dynamic/0','succeeded',asset('clip.mp4'))
    store.write('original','douyin/voice','succeeded',asset('voice.wav'))
    business.persist_result(db.Session,{'id':'original','workspace':'one','fencing_token':1,'payload':{'work_id':'work'}},
        {'images':images,'platforms':{'douyin':{'video':{'state':'awaiting_review','result':video},'poster':{'state':'awaiting_review','result':poster}}},'copy':{'douyin':content}},tmp_path)
    with db.Session.begin() as session:session.get(Task,'original').state='succeeded'
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token']}
    music=client.post('/api/v1/skus/sku/sources',content=(tmp_path/'voice.wav').read_bytes(),headers={**headers,'X-Rights-Confirmed':'true','X-Filename':'music.wav','Content-Type':'audio/wav'})
    assert music.status_code==201,music.text
    # If the local factory accidentally touches provider configuration, fail immediately.
    forbidden=Mock(side_effect=AssertionError('supplier configuration accessed'))
    monkeypatch.setattr(business,'authorization_snapshot',forbidden)
    for index,changes in enumerate([{'poster_title':'New poster'},{'subtitle_style':'large'},{'music':music.json()['id']} ]):
        before=client.get('/api/v1/works/work').json()
        saved=client.patch('/api/v1/works/work/draft',json={'expected_revision':before['revision'],'changes':changes},headers=headers)
        assert saved.status_code==200,saved.text
        quote=client.post('/api/v1/works/work/change-quotes',headers=headers).json()
        assert quote['execution_mode']=='local_only' and quote['cost_upper_bound']==0
        action={'expected_revision':saved.json()['revision'],'quote_id':quote['quote_id'],'authorized':True}
        submitted=client.post('/api/v1/works/work/apply',json=action,headers={**headers,'Idempotency-Key':f'local-edit-{index}'})
        assert submitted.status_code==200,submitted.text
        with db.Session() as session:
            admitted=session.get(Task,submitted.json()['task_id'])
            safe=business.configured_services({'id':admitted.id,'workspace':'one','fencing_token':0,'payload':admitted.payload})
            for operation in ('text','product_image','dynamic','tts'):
                with pytest.raises(ValueError,match='external_operation_forbidden_in_local_edit'):
                    safe.invoke(operation,{},admitted.id+':forbidden')
        assert client.get('/api/v1/works/work').json()['current_result']==before['current_result']
        assert run_once(JobRepository(db.Session),'local-edit-worker',business.configured_services)
        with db.Session() as session:
            task=session.get(Task,submitted.json()['task_id'])
            assert task.state=='succeeded',task.payload
            work=session.get(Record,'work')
            assert work.data['current_result']!=before['current_result']
            result=session.get(Record,work.data['current_result'])
            assert all(session.get(Record,identifier).data['review']=='pending' for identifier in result.data['assets'])
            assert session.scalar(select(func.count()).select_from(ExternalCall))==0
            assert session.scalar(select(func.count()).select_from(CallReservation))==0
        replay=client.post('/api/v1/works/work/apply',json=action,headers={**headers,'Idempotency-Key':f'local-edit-{index}'})
        assert replay.json()==submitted.json()
    forbidden.assert_not_called()
