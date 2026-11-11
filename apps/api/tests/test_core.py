import os
os.environ['DATABASE_URL']='sqlite://'
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import db
from app.auth import Account,password_hash
from app import execution
from app.main import app
import pytest
@pytest.fixture
def client():
    from app.auth import attempts
    attempts.clear()
    db.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    db.Session.configure(bind=db.engine);db.initialize()
    with db.Session() as s:
        s.add(Account(username='tester',workspace='one',password_hash=password_hash('test-password-123')));s.commit()
    with TestClient(app) as c:yield c

def test_auth_and_csrf(client):
    assert client.get('/api/v1/skus').status_code==401
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    assert login.status_code==200
    assert client.post('/api/v1/skus',json={'name':'耳机','model':'A'}).status_code==403
    result=client.post('/api/v1/skus',json={'name':'耳机','model':'A'},headers={'X-CSRF-Token':login.json()['csrf_token']})
    assert result.status_code==201
    assert len(client.get('/api/v1/skus').json()['items'])==1

def test_budget_reserved_is_not_available(client):
    from decimal import Decimal
    with db.Session() as s:
        s.add(execution.Budget(id='global',workspace='system',cap=Decimal('10'),reserved=Decimal('8'),settled=Decimal('1')));s.commit()
        with pytest.raises(ValueError):execution.reserve(s,'global',Decimal('2'))
        s.rollback()
        execution.reserve(s,'global',Decimal('1'));s.commit()
        assert s.get(execution.Budget,'global').reserved==Decimal('9')

def test_logout_revokes_copied_session_cookie(client):
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    token=client.cookies.get('aigc_session')
    assert client.delete('/api/v1/sessions/current',headers={'X-CSRF-Token':login.json()['csrf_token']}).status_code==204
    client.cookies.set('aigc_session',token)
    assert client.get('/api/v1/skus').status_code==401

def test_login_failure_rate_limit(client):
    for _ in range(5):
        assert client.post('/api/v1/sessions',json={'username':'tester','password':'wrong-password-123'}).status_code==401
    assert client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'}).status_code==429


def test_work_activity_is_independent_of_the_current_task_page(client):
    with db.Session.begin() as session:
        session.add(db.Record(id='work',workspace='one',kind='work',data={}))
        session.add_all([
            execution.Task(id='z-current',workspace='one',phase='creation_run',state='running',payload={'work_id':'work','request':{'platforms':['douyin']}}),
            execution.Task(id='a-first-page',workspace='one',phase='creation_run',state='succeeded',payload={'work_id':'elsewhere'}),
            execution.Task(id='foreign',workspace='other',phase='creation_run',state='queued',payload={'work_id':'work'}),
        ])
        session.add(db.Record(id='z-current:copy',workspace='one',kind='task_step',data={'state':'succeeded'}))
        session.add(db.Record(id='z-current:image/white',workspace='one',kind='task_step',data={'state':'succeeded'}))
    client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    assert [task['id'] for task in client.get('/api/v1/tasks?limit=1').json()['items']]==['a-first-page']
    assert 'has_active_tasks' not in client.get('/api/v1/works/work').json()
    activity=client.get('/api/v1/works/work?include_activity=true').json()
    assert activity['has_active_tasks'] is True
    assert activity['creation_task']['progress_stage']==1
    assert activity['creation_task']['next_actions']==['pause','cancel']
    with db.Session.begin() as session:
        session.get(execution.Task,'z-current').state='paused'
    activity=client.get('/api/v1/works/work?include_activity=true').json()
    assert activity['has_active_tasks'] is False
    assert activity['creation_task']['next_actions']==['resume','cancel']


def test_work_fact_sources_follow_the_result_and_frozen_profile(client):
    with db.Session.begin() as session:
        session.add_all([
            db.Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','profile_id':'profile',
                'creation_request_id':'request','current_result':'result','platforms':['douyin']}),
            db.Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed','facts':{'weight':'900克'}}),
            db.Record(id='request',workspace='one',kind='creation_request',data={'profile_snapshot':{
                'facts':{'weight':'90克','unused':'保密备注'},'fact_sources':{'weight':{'source_id':'source','page':2}}}}),
            db.Record(id='result',workspace='one',kind='result_revision',data={'work_id':'work','copy':{
                'douyin':{'fact_refs':['weight'],'shots':[{'fact_refs':['weight']}]}}}),
            db.Record(id='source',workspace='one',kind='source',data={'sku_id':'sku','name':'规格说明.pdf'}),
        ])
    client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    endpoint='/api/v1/works/work/fact-sources'
    response=client.get(endpoint+'?platform=douyin')
    assert response.status_code==200,response.text
    assert response.json()['items']==[{'id':'weight','value':'90克','source_name':'规格说明.pdf',
                                      'origin':None,'page':2,'paragraph':None}]
    assert client.get(endpoint+'?platform=xiaohongshu').status_code==422


def test_music_upload_requires_rights_and_a_real_audio_stream(client,tmp_path,monkeypatch):
    import io,wave
    from app import sources
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    auth={'X-CSRF-Token':login.json()['csrf_token']}
    sku=client.post('/api/v1/skus',json={'name':'合成商品','model':'music-test'},headers=auth).json()['id']
    path=f'/api/v1/skus/{sku}/sources'
    headers={**auth,'X-Filename':'music.wav','Content-Type':'audio/wav'}
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as audio:
        audio.setparams((1,2,8000,0,'NONE','not compressed'))
        audio.writeframes(bytes(16000))
    assert client.post(path,content=buffer.getvalue(),headers=headers).status_code==422
    headers['X-Rights-Confirmed']='true'
    invalid=client.post(path,content=b'not audio',headers=headers)
    assert invalid.status_code==422 and invalid.json()['detail']['code']=='MUSIC_FORMAT_INVALID'
    uploaded=client.post(path,content=buffer.getvalue(),headers=headers)
    assert uploaded.status_code==201,uploaded.text
    assert uploaded.json()['type']=='audio'
    with db.Session() as session:
        source_id=uploaded.json()['id']
        assert sources.authorized_music(session,'one',sku,source_id) is not None
        assert sources.authorized_music(session,'other',sku,source_id) is None
        assert sources.authorized_music(session,'one','other-sku',source_id) is None
