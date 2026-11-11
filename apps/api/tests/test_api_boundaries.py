"""API boundary coverage: source isolation, immutable request inputs, validation."""
from test_core import client
from app import db
from app.auth import Account,password_hash

def sign_in(client,user='tester'):
    result=client.post('/api/v1/sessions',json={'username':user,'password':'test-password-123'})
    assert result.status_code==200
    return {'X-CSRF-Token':result.json()['csrf_token']}

def test_video_replacement_rejects_cross_work_multishot_and_tampered_asset(client,source_directory,monkeypatch):
    from hashlib import sha256
    from app.db import Record
    from app import sources
    monkeypatch.setattr(sources,'ROOT',source_directory)
    headers=sign_in(client)
    private_video=source_directory/'replacement.mp4'
    private_video.write_bytes(b'local fixture')
    with db.Session.begin() as session:
        session.add_all([
            Record(id='work-video',workspace='one',kind='work',data={'sku_id':'a','platforms':['douyin'],'current_result':'result-video'}),
            Record(id='result-video',workspace='one',kind='result_revision',data={'work_id':'work-video',
                'assets':['foreign-video','own-video'],'copy':{'douyin':{'shots':[{'duration':2},{'duration':3}]}}}),
            Record(id='foreign-video',workspace='one',kind='asset',data={'work_id':'other-work','media_kind':'video',
                'slot':'douyin','review':'approved'}),
            Record(id='own-video',workspace='one',kind='asset',data={'work_id':'work-video','media_kind':'video',
                'slot':'douyin','review':'approved','object_key':private_video.name,
                'sha256':sha256(private_video.read_bytes()).hexdigest()}),
        ])
    def select(asset_id):
        return client.patch('/api/v1/works/work-video/draft',headers=headers,
            json={'expected_revision':1,'changes':{'platform':'douyin','asset_id':asset_id}})
    for asset_id,code in [('foreign-video','REPLACEMENT_VIDEO_ASSET_REQUIRED'),('own-video','REPLACEMENT_VIDEO_REQUIRES_SINGLE_SHOT')]:
        response=select(asset_id)
        assert response.status_code==422,response.text
        assert response.json()['detail']['code']==code
    with db.Session.begin() as session:
        result=session.get(Record,'result-video')
        result.data={**result.data,'copy':{'douyin':{'shots':[{'duration':5}]}}}
    private_video.write_bytes(b'tampered fixture')
    rejected=select('own-video')
    assert rejected.status_code==422,rejected.text
    assert rejected.json()['detail']['code']=='REPLACEMENT_VIDEO_HASH_MISMATCH'
    private_video.write_bytes(b'local fixture')
    accepted=select('own-video')
    assert accepted.status_code==200,accepted.text

def upload_synthetic_product(client,headers,sku_id):
    from PIL import Image
    from io import BytesIO
    output=BytesIO();Image.new('RGB',(20,20),'red').save(output,format='PNG')
    response=client.post('/api/v1/skus/'+sku_id+'/sources',content=output.getvalue(),headers={**headers,'X-Filename':'test-product.png','X-Rights-Confirmed':'true'})
    assert response.status_code==201
    return response.json()['id']

def test_other_workspace_cannot_read_or_reference_source(client):
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'耳机','model':'A'},headers=headers).json()
    with db.Session() as s:
        s.add(Account(username='second',workspace='two',password_hash=password_hash('test-password-123')));s.commit()
    client.delete('/api/v1/sessions/current',headers=headers)
    other=sign_in(client,'second')
    assert client.get('/api/v1/skus/'+sku['id']).status_code==404
    assert client.post('/api/v1/skus/'+sku['id']+'/profiles',json={'facts':{'name':'x'}},headers=other).status_code==404

def test_creation_duration_and_platform_contract(client,source_directory,monkeypatch):
    from app import sources
    monkeypatch.setattr(sources,'ROOT',source_directory)
    h=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'耳机','model':'A','single_spec_confirmed':True},headers=h).json()
    image_id=upload_synthetic_product(client,h,sku['id'])
    p=client.post('/api/v1/skus/'+sku['id']+'/profiles',json={'facts':{'model':'A'},'source_ids':[image_id]},headers=h).json()
    assert client.post('/api/v1/profiles/'+p['id']+'/confirm',headers=h).status_code==200
    body={'profile_id':p['id'],'platforms':['douyin'],'duration_seconds':47}
    result=client.post('/api/v1/creation-requests',json=body,headers=h)
    assert result.status_code==201
    assert result.json()['duration_seconds']==47
    for duration in [0,-1,1.5,True]:
        assert client.post('/api/v1/creation-requests',json={**body,'duration_seconds':duration},headers=h).status_code==422
    for platforms in [[],['douyin','douyin'],['unknown']]:
        assert client.post('/api/v1/creation-requests',json={**body,'platforms':platforms},headers=h).status_code==422

def test_generation_without_server_configuration_never_creates_paid_task(client,source_directory,monkeypatch):
    from app import sources
    monkeypatch.setattr(sources,'ROOT',source_directory)
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'耳机','model':'A','specification':'白色'},headers=headers).json()
    image_id=upload_synthetic_product(client,headers,sku['id'])
    profile=client.post('/api/v1/skus/'+sku['id']+'/profiles',json={'facts':{'name':'耳机'},'source_ids':[image_id]},headers=headers).json()
    assert client.post('/api/v1/profiles/'+profile['id']+'/confirm',headers=headers).status_code==200
    request=client.post('/api/v1/creation-requests',json={'profile_id':profile['id'],'platforms':['douyin'],'duration_seconds':15},headers=headers).json()
    result=client.post('/api/v1/creation-requests/'+request['id']+'/runs',json={'authorized':True},headers={**headers,'Idempotency-Key':'repeat-safe'})
    assert result.status_code==409
    assert client.get('/api/v1/tasks').json()['items']==[]

def test_export_does_not_mix_historical_assets(client):
    from app.db import Record
    h=sign_in(client)
    with db.Session() as s:
        s.add(Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','platforms':['douyin'],'current_result':'result'}))
        s.add(Record(id='result',workspace='one',kind='result_revision',data={'work_id':'work','assets':[]}))
        s.add(Record(id='old',workspace='one',kind='asset',data={'work_id':'work','media_kind':'video','slot':'douyin','sample_marked':False}))
        s.commit()
    response=client.post('/api/v1/export-packages',json={'work_id':'work','mode':'sample','selection':'video_only'},headers=h)
    assert response.status_code==409
    assert response.json()['detail']['code']=='MEDIA_NOT_AVAILABLE'

def test_adopt_candidate_does_not_merge_another_platform_draft(client):
    from app.db import Record
    h=sign_in(client)
    with db.Session() as s:
        s.add(Record(id='work',workspace='one',kind='work',data={'platforms':['douyin','xiaohongshu'],'draft':{'platform':'douyin','narration':'manual'}}))
        s.add(Record(id='candidate',workspace='one',kind='copy_candidate',data={'work_id':'work','platform':'xiaohongshu','base_draft_revision':1,'changes':{'title':'candidate'}}))
        s.commit()
    response=client.post('/api/v1/copy-versions/candidate/adopt',json={'expected_revision':1},headers=h)
    assert response.status_code==409
    assert response.json()['detail']['code']=='DRAFT_PLATFORM_CONFLICT'
    with db.Session() as s:
        assert s.get(Record,'work').data['draft']=={'platform':'douyin','narration':'manual'}

import pytest
@pytest.fixture
def source_directory():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:yield Path(directory)

def test_streamed_source_roundtrip_and_parse(client,source_directory,monkeypatch):
    from app import sources
    monkeypatch.setattr(sources,'ROOT',source_directory)
    headers=sign_in(client)
    sku=client.post('/api/v1/skus',json={'name':'耳机','model':'A'},headers=headers).json()
    content='型号 A\n颜色 白色'.encode('utf-8')
    upload=client.post('/api/v1/skus/'+sku['id']+'/sources',content=content,headers={**headers,'X-Filename':'facts.txt','X-Rights-Confirmed':'true'})
    assert upload.status_code==201
    source=upload.json()
    assert client.get('/api/v1/sources/'+source['id']+'/download').content==content
    document=client.get('/api/v1/sources/'+source['id']+'/download?inline=true')
    assert document.headers['content-disposition'].startswith('attachment;')
    assert document.headers['cache-control']=='private, no-store'
    parsed=client.post('/api/v1/sources/'+source['id']+'/parse',headers=headers)
    assert parsed.status_code==200
    assert parsed.json()['locators'][1]['paragraph']==2
    from sqlalchemy import select
    from app.db import Record
    with db.Session() as s:
        assert s.scalars(select(Record).where(Record.kind=='upload_reservation')).all()==[]

def test_rejection_updates_exact_asset_review_projection(client):
    from app.db import Record
    h=sign_in(client)
    with db.Session() as s:
        s.add_all([Record(id='p',workspace='one',kind='profile',data={'status':'confirmed'}),Record(id='w',workspace='one',kind='work',data={'profile_id':'p'}),Record(id='a',workspace='one',kind='asset',data={'work_id':'w','review':'pending'})]);s.commit()
    response=client.post('/api/v1/assets/a/reviews',json={'decision':'reject','reason':'商品结构错误'},headers=h)
    assert response.status_code==201
    assert response.json()['asset_revision']==1
    with db.Session() as s:
        asset=s.get(Record,'a')
        assert asset.data['review']=='rejected'
        assert asset.revision==1


def test_unknown_task_cancel_keeps_budget_reserved(client):
    from app.execution import Task,Budget
    from decimal import Decimal
    h=sign_in(client)
    with db.Session() as s:
        s.add(Task(id='unknown-task',workspace='one',state='external_unknown',phase='creation_run',payload={}))
        s.add(Budget(id='unknown-budget',workspace='one',cap=Decimal('10'),reserved=Decimal('6'),settled=Decimal('1')))
        s.commit()
    detail=client.get('/api/v1/tasks/unknown-task')
    assert 'cancel' in detail.json()['next_actions']
    response=client.post('/api/v1/tasks/unknown-task/actions',json={'action':'cancel'},headers=h)
    assert response.status_code==200
    with db.Session() as s:
        assert s.get(Task,'unknown-task').state=='canceled'
        assert s.get(Budget,'unknown-budget').reserved==Decimal('6')

def test_deleted_rows_do_not_consume_visible_page_slots(client):
    from app.db import Record
    sign_in(client)
    with db.Session() as s:
        s.add_all([Record(id='0-deleted',workspace='one',kind='sku',data={'name':'deleted','deleting':True}),Record(id='1-visible',workspace='one',kind='sku',data={'name':'first'}),Record(id='2-visible',workspace='one',kind='sku',data={'name':'second'})]);s.commit()
    first=client.get('/api/v1/skus?limit=1&offset=0').json()['items']
    second=client.get('/api/v1/skus?limit=1&offset=1').json()['items']
    assert [r['id'] for r in first]==['1-visible']
    assert [r['id'] for r in second]==['2-visible']

def test_repair_request_is_idempotent_and_does_not_replace_asset(client):
    from app.db import Record
    from app.execution import Task
    h={**sign_in(client),'Idempotency-Key':'repair-once'}
    with db.Session() as s:
        s.add_all([Record(id='p',workspace='one',kind='profile',data={'status':'confirmed'}),Record(id='w',workspace='one',kind='work',data={'profile_id':'p','sku_id':'sku','current_result':'old-result'}),Record(id='a',workspace='one',kind='asset',data={'work_id':'w','media_kind':'product_image'}),Record(id='original',workspace='one',kind='source',data={'sku_id':'sku','type':'image','rights_confirmed':True}),Record(id='mask',workspace='one',kind='source',data={'sku_id':'sku','type':'image','rights_confirmed':True})]);s.commit()
    body={'original_source_id':'original','mask_source_id':'mask'}
    first=client.post('/api/v1/assets/a/repairs',json=body,headers=h)
    second=client.post('/api/v1/assets/a/repairs',json=body,headers=h)
    assert first.status_code==second.status_code==202
    assert first.json()['task_id']==second.json()['task_id']
    conflict=client.post('/api/v1/assets/a/repairs',json={**body,'mask_source_id':'original'},headers=h)
    assert conflict.status_code==409
    with db.Session() as s:
        assert s.get(Record,'w').data['current_result']=='old-result'
        assert s.get(Record,'a').revision==1
        assert s.get(Task,first.json()['task_id']).phase=='repair_asset'

def test_conflicting_fact_candidates_require_explicit_choice(client,tmp_path,monkeypatch):
    from app.db import Record
    from app import sources
    from PIL import Image
    import hashlib
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    image=tmp_path/'facts-product.png'
    Image.new('RGB',(16,16),'red').save(image)
    h=sign_in(client)
    with db.Session() as s:
        s.add(Record(id='sku-facts',workspace='one',kind='sku',data={'name':'test','model':'sku-facts','single_spec_confirmed':True}))
        s.add(Record(id='image-facts',workspace='one',kind='source',data={'sku_id':'sku-facts','type':'image',
            'rights_confirmed':True,'object_key':image.name,'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}))
        s.add(Record(id='source-facts',workspace='one',kind='source',data={'sku_id':'sku-facts','type':'document'}))
        for key,value,page in [('fact-a','A',1),('fact-b','B',2)]:
            s.add(Record(id=key,workspace='one',kind='fact_candidate',data={'sku_id':'sku-facts','source_id':'source-facts','key':'型号','value':value,'locator':{'source_id':'source-facts','page':page}}))
        s.commit()
    conflicts=client.get('/api/v1/skus/sku-facts/fact-candidates').json()
    assert conflicts['conflicting_keys']==['型号']
    rejected=client.post('/api/v1/skus/sku-facts/profiles',json={'facts':{},'candidate_ids':['fact-a','fact-b']},headers=h)
    assert rejected.status_code==422
    assert rejected.json()['detail']['code']=='FACT_CONFLICT'
    profile_payload={'facts':{},'source_ids':['image-facts','source-facts']}
    unresolved=client.post('/api/v1/skus/sku-facts/profiles',json=profile_payload,headers=h)
    confirmation=client.post('/api/v1/profiles/'+unresolved.json()['id']+'/confirm',headers=h)
    assert confirmation.status_code==409 and confirmation.json()['detail']['code']=='FACT_CONFLICT_UNRESOLVED'
    selected=client.post('/api/v1/skus/sku-facts/profiles',json={**profile_payload,'candidate_ids':['fact-b']},headers=h)
    assert selected.status_code==201
    assert selected.json()['facts']=={'name':'test','merchant_sku':'sku-facts','型号':'B'}
    assert selected.json()['fact_sources']['name']['origin']=='catalog'
    assert selected.json()['fact_sources']['型号']=={'source_id':'source-facts','page':2}
    assert selected.json()['status']=='draft'
    assert client.post('/api/v1/profiles/'+selected.json()['id']+'/confirm',headers=h).status_code==200
