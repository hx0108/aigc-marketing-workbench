"""HTTP admission to real persisted queue/Worker; provider results are explicit fixtures."""
import hashlib
from decimal import Decimal
from PIL import Image
from sqlalchemy import select
from test_core import client
from app import db, sources
from app.db import Record
from app.execution import Budget, Task
from app.job_repository import JobRepository
from marketing_worker import business
from marketing_worker.runner import run_once


def test_http_creation_to_worker_result(client, monkeypatch, tmp_path):
    monkeypatch.setattr(sources, 'ROOT', tmp_path)
    auth={'providers':{'video':'MiniMax-Hailuo-2.3-Fast'},'provider_parameters':{'video':{'resolution':'768P','duration':6}},'price_version':'minimax-cn-hailuo-fast-2026-11-11','budget_id':'flow-budget','consent_version':'test','bounds':{'text':'0.1','product_image':'0.025','dynamic':'1.35','tts':'0.05'}}
    monkeypatch.setattr(business,'readiness',lambda:[])
    monkeypatch.setattr(business,'authorization_snapshot',lambda *args:auth)
    path=tmp_path/'product.png';Image.new('RGB',(32,32),'red').save(path)
    item={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    with db.Session.begin() as s:
        s.add(Record(id='sku',workspace='one',kind='sku',data={'name':'Synthetic','model':'TEST','single_spec_confirmed':True}))
        for name in ('image','mask'):
            s.add(Record(id=name,workspace='one',kind='source',data={'sku_id':'sku','type':'image','rights_confirmed':True,'object_key':'product.png','sha256':item['sha256']}))
        s.add(Record(id='profile',workspace='one',kind='profile',data={'sku_id':'sku','status':'confirmed','facts':{'name':'Synthetic'},'fact_sources':{'name':{'source_id':'image'}},'source_ids':['image','mask'],'source_selection':{'product':{'source_id':'image'},'mask':{'source_id':'mask'}}}))
        s.add(Budget(id='flow-budget',workspace='one',cap=Decimal('3.11'),reserved=0,settled=0))
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    headers={'X-CSRF-Token':login.json()['csrf_token'],'Idempotency-Key':'flow-one'}
    quote=client.post('/api/v1/creation-requests',headers=headers,json={'profile_id':'profile','platforms':['douyin','xiaohongshu'],'duration_seconds':5,'budget_limit':'3.11'})
    assert quote.status_code==201,quote.text
    assert quote.json()['status']=='ready',quote.text
    url='/api/v1/creation-requests/'+quote.json()['id']+'/runs'
    submitted=client.post(url,headers=headers,json={'authorized':True})
    assert submitted.status_code==202,submitted.text
    task_id=submitted.json()['task_id']
    calls=[]
    class FixtureServices:
        def invoke(self,kind,payload,intent):
            calls.append(kind)
            if kind=='text':
                return {p:{'title':p,'body':p,'narration':p,'poster_title':p,'shots':[{'duration':5,'narration':p,'fact_refs':['name']}]} for p in ['douyin','xiaohongshu']}
            return item
        def persist_result(self,job,result):
            return business.persist_result(db.Session,job,result,tmp_path)
    assert run_once(JobRepository(db.Session),'independent-test-worker',lambda job:FixtureServices())
    with db.Session() as s:
        task=s.get(Task,task_id);assert task.state=='succeeded',task.payload
        work=s.get(Record,submitted.json()['work_id']);assert work.data['current_result']
        result=s.get(Record,work.data['current_result']);assert set(result.data['branches'])=={'douyin','xiaohongshu'}
        assert all(s.get(Record,asset).data['review']=='pending' for asset in result.data['assets'])
    repeated=client.post(url,headers=headers,json={'authorized':True})
    assert repeated.json()['task_id']==task_id
    assert calls.count('text')==1
