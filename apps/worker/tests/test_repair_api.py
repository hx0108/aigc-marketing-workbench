import hashlib
from PIL import Image
from app import db,sources
from app.db import Record
from app.job_repository import JobRepository
from marketing_worker.runner import run_once
from test_core import client


def test_repair_api_to_worker_creates_pending_asset(client,tmp_path,monkeypatch):
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    with db.Session.begin() as session:
        session.add(Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed'}))
        session.add(Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','profile_id':'profile','current_result':'initial'}))
        session.add(Record(id='initial',workspace='one',kind='result_revision',data={'work_id':'work','assets':['candidate'],'result_number':1}))
        for identifier,color,kind in [('candidate','blue','asset'),('original','red','source'),('mask','white','source')]:
            path=tmp_path/(identifier+'.png');Image.new('RGB',(32,32),color).save(path)
            session.add(Record(id=identifier,workspace='one',kind=kind,data={'work_id':'work','sku_id':'sku','type':'image','rights_confirmed':True,'media_kind':'product_image','object_key':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token'],'Idempotency-Key':'repair-test'}
    response=client.post('/api/v1/assets/candidate/repairs',json={'original_source_id':'original','mask_source_id':'mask'},headers=headers)
    assert response.status_code==202
    assert run_once(JobRepository(db.Session),'test-owner')
    with db.Session() as session:
        asset=session.get(Record,response.json()['task_id']+':asset')
        assert asset.data['review']=='pending'
        assert asset.data['parent_asset_id']=='candidate'
        assert asset.data['sample_marked'] is True
        with Image.open(tmp_path/asset.data['object_key']) as image:assert image.getpixel((0,0))==(255,0,0)
        clean=tmp_path/asset.data['repair_render_key']
        assert hashlib.sha256(clean.read_bytes()).hexdigest()==asset.data['repair_render_sha256']
        with Image.open(clean) as image:assert image.getpixel((31,31))==(255,0,0)
        with Image.open(tmp_path/'candidate.png') as image:assert image.getpixel((0,0))==(0,0,255)
    result=client.get('/api/v1/works/work?include_activity=true').json()
    assert [asset['id'] for asset in result['repair_candidates']]==[response.json()['task_id']+':asset']
    assert result['current_result']=='initial'
    candidate_id=result['repair_candidates'][0]['id']
    assert 'repair_render_key' not in result['repair_candidates'][0]
    path='/api/v1/assets/'+candidate_id
    assert client.get(path+'/download').status_code==200
    assert client.post(path+'/apply-repair',json={'expected_revision':1},headers=headers).json()['detail']['code']=='REVIEW_REQUIRED'
    assert client.post(path+'/reviews',json={'decision':'adopt','reason':''},headers=headers).status_code==201
    applied=client.post(path+'/apply-repair',json={'expected_revision':1},headers=headers)
    assert applied.status_code==200,applied.text
    assert applied.json()['result_number']==2
    assert applied.json()['media_calls']==0
    with db.Session() as session:
        assert session.get(Record,'initial').data['assets']==['candidate']
        current=session.get(Record,applied.json()['current_result'])
        assert current.data['parent_revision']=='initial'
        assert current.data['assets']==[candidate_id]
    assert client.post(path+'/apply-repair',json={'expected_revision':1},headers=headers).json()['detail']['code']=='VERSION_CONFLICT'
    assert client.post(path+'/apply-repair',json={'expected_revision':2},headers=headers).json()['detail']['code']=='REPAIR_BASE_CHANGED'
