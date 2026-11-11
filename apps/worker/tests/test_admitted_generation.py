from decimal import Decimal
import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
import pytest
from app import db,sources,exporting
from app.db import Record
from app.execution import Task,Budget
from app.job_repository import JobRepository
from app.ledger import CallReservation
from sqlalchemy import select
from marketing_worker import business
from marketing_worker.configuration import verify_consent
from marketing_worker.persistence import AuthorizedServices
from marketing_worker.pipeline import Pipeline
from marketing_worker.runner import run_once
from test_core import client
import test_http_pipeline as scenario


@pytest.mark.parametrize('recover_poster',[False,True],ids=['complete-first-run','recover-local-poster'])
def test_admission_authorization_generation_export(client,tmp_path,monkeypatch,recover_poster):
    captured={}; original_handlers=scenario.handlers; original_execute=Pipeline.execute
    def capture(*args,**kwargs):
        registry=original_handlers(*args,**kwargs)
        captured.update(registry=registry,providers=args[0],root=args[1])
        return registry
    def intercept(pipeline,task_id,request):
        if task_id!='test':return original_execute(pipeline,task_id,request)
        root=Path(captured['root']);monkeypatch.setattr(sources,'ROOT',root);monkeypatch.setattr(exporting,'ROOT',root)
        settings={'workspace':'one','enabled':True,'providers':{key:{'model':provider.model} for key,provider in captured['providers'].items()},'bounds':{kind:'0.1000' for kind in ('text','product_image','dynamic','tts')},'budget_id':'budget','price_version':'synthetic-fixture','consent_version':'synthetic-fixture'}
        def policy_factory(job):
            def policy(*args):
                with db.Session() as session:verify_consent(session,job,settings)
            return policy
        monkeypatch.setattr(business,'_configuration',{**settings,'providers':captured['providers'],'private_root':str(root),'font':'C:/Windows/Fonts/msyh.ttc','allowed_hosts':['assets.example'],'video_price_verified':True,'sessions':db.Session,'policy_factory':policy_factory,'source_factory':lambda job:None,'save_remote':lambda *args:None,'publish_image':lambda *args:None})
        with db.Session.begin() as session:
            session.add(Budget(id='budget',workspace='one',cap=Decimal('10'),reserved=0,settled=0))
            session.add(Record(id='sku',workspace='one',kind='sku',data={'name':'Synthetic','model':'fixture','single_spec_confirmed':True}))
            selection={}
            for role in ('product','mask'):
                path=root/(role+'.png');digest=hashlib.sha256(path.read_bytes()).hexdigest()
                selection[role]={'source_id':role,'sha256':digest,'revision':1}
                session.add(Record(id=role,workspace='one',kind='source',data={'sku_id':'sku','type':'image','role':role,'rights_confirmed':True,'object_key':path.name,'sha256':digest}))
            session.add(Record(id='profile',workspace='one',kind='profile',data={'sku_id':'sku','status':'confirmed','facts':{'f1':'synthetic'},'fact_sources':{'f1':{'source_id':'product','region':'whole','origin':'synthetic_fixture'}},'source_ids':['product','mask'],'source_selection':selection}))
        login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
        headers={'X-CSRF-Token':login.json()['csrf_token'],'Idempotency-Key':'synthetic-create'}
        with db.Session.begin() as session:
            session.get(Budget,'budget').cap=Decimal('0.49')
        low=client.post('/api/v1/creation-requests',json={'profile_id':'profile','platforms':['douyin'],'duration_seconds':2,'brief':''},headers=headers)
        assert low.status_code==201,low.text
        assert low.json()['status']=='blocked' and low.json()['quote'] is None
        assert low.json()['blockers'][0]['code']=='BUDGET_INSUFFICIENT'
        with db.Session.begin() as session:
            session.get(Budget,'budget').cap=Decimal('10')
        created=client.post('/api/v1/creation-requests',json={'profile_id':'profile','platforms':['douyin'],'duration_seconds':2,'brief':''},headers=headers)
        assert created.status_code==201,created.text
        assert created.json()['status']=='ready',created.text
        assert created.json()['blockers']==[]
        assert Decimal(created.json()['quote']['cost_upper_bound'])==Decimal('10')
        assert Decimal(created.json()['quote']['minimum_reservation'])==Decimal('0.50')
        with db.Session.begin() as session:
            session.get(Budget,'budget').cap=Decimal('9')
        stale=client.post('/api/v1/creation-requests/'+created.json()['id']+'/runs',json={'authorized':True},headers=headers)
        assert stale.status_code==409 and stale.json()['detail']['code']=='CREATION_QUOTE_CHANGED'
        with db.Session.begin() as session:
            assert list(session.scalars(select(Task)))==[]
            session.get(Budget,'budget').cap=Decimal('10')
        started=client.post('/api/v1/creation-requests/'+created.json()['id']+'/runs',json={'authorized':True},headers=headers)
        assert started.status_code==202,started.text
        poster=captured['registry']['poster_render']
        if recover_poster:
            def fail_poster(payload,intent):
                raise ValueError('synthetic_local_poster_failure')
            captured['registry']['poster_render']=fail_poster
        def services(job):
            if job['payload'].get('execution_mode') == 'local_only':
                return business.configured_services(job)
            service=AuthorizedServices(db.Session,'budget',policy_factory(job),captured['registry'],settings['bounds'],job['id'],'one',job['fencing_token'])
            service.provider_parameters={key:provider.parameters for key,provider in captured['providers'].items()}
            service.private_root=root
            def persist(current,result):
                saved=business.persist_result(db.Session,current,result,root)
                if current['id']==started.json()['task_id']:
                    captured['creation_result']=result
                return saved
            service.persist_result=persist
            return service
        assert run_once(JobRepository(db.Session),'owner',services)
        if recover_poster:
            task_id=started.json()['task_id']
            work_id=started.json()['work_id']
            partial=client.get('/api/v1/works/'+work_id+'?include_activity=true').json()
            assert partial['missing_items']==['douyin/poster']
            assert partial['creation_task']['next_actions']==['recover']
            video=next(asset for asset in partial['assets'] if asset['media_kind']=='video')
            assert client.post('/api/v1/assets/'+video['id']+'/reviews',json={'decision':'adopt'},headers=headers).status_code==201
            response=client.post('/api/v1/tasks/'+task_id+'/actions',json={'action':'recover'},headers=headers)
            assert response.status_code==200,response.text
            assert response.json()['execution_state']=='queued'
            captured['registry']['poster_render']=poster
            assert run_once(JobRepository(db.Session),'owner',services)
            current=client.get('/api/v1/works/'+work_id+'?include_activity=true').json()
            assert current['result']['parent_revision']==partial['result']['id']
            assert current['missing_items']==[]
            assert next(asset for asset in current['assets'] if asset['id']==video['id'])['review']=='approved'
            assert next(asset for asset in current['assets'] if asset['media_kind']=='marketing_poster')['review']=='pending'
        else:
            work_path='/api/v1/works/'+started.json()['work_id']
            prior=client.get(work_path).json()
            video=next(asset for asset in prior['assets'] if asset['media_kind']=='video')
            old_poster=next(asset for asset in prior['assets'] if asset['media_kind']=='marketing_poster')
            assert client.post('/api/v1/assets/'+video['id']+'/reviews',json={'decision':'adopt'},headers=headers).status_code==201
            invalid=client.patch(work_path+'/draft',json={'expected_revision':prior['revision'],
                'changes':{'platform':'douyin','poster_points':'invalid string'}},headers=headers)
            assert invalid.status_code==422
            draft=client.patch(work_path+'/draft',json={'expected_revision':prior['revision'],
                'changes':{'platform':'douyin','poster_layout':'product_top','poster_points':['合成测试卖点']}},headers=headers)
            assert draft.status_code==200,draft.text
            quote=client.post(work_path+'/change-quotes',headers=headers).json()
            assert quote['invalidated_nodes']==['poster_render'] and Decimal(quote['cost_upper_bound'])==0
            submitted=client.post(work_path+'/apply',json={'expected_revision':draft.json()['revision'],
                'quote_id':quote['quote_id'],'authorized':True},headers={**headers,'Idempotency-Key':'synthetic-poster-edit'})
            assert submitted.status_code==200,submitted.text
            assert client.get(work_path).json()['current_result']==prior['current_result']
            assert run_once(JobRepository(db.Session),'owner',services)
            current=client.get(work_path).json()
            assert current['draft']=={}
            assert current['result']['render_settings']['douyin']['poster_layout']=='product_top'
            assert current['result']['copy']['douyin']['selling_points']==['合成测试卖点']
            assert next(asset for asset in current['assets'] if asset['media_kind']=='video')['id']==video['id']
            assert next(asset for asset in current['assets'] if asset['media_kind']=='video')['review']=='approved'
            assert next(asset for asset in current['assets'] if asset['media_kind']=='marketing_poster')['sha256']!=old_poster['sha256']
        with db.Session() as session:
            task=session.get(Task,started.json()['task_id'])
            assert task.state=='succeeded',task.payload
            work=session.get(Record,started.json()['work_id']);result=session.get(Record,work.data['current_result'])
            assets=result.data['assets']
            assert len(assets)==7
            assert len(list(session.scalars(select(CallReservation))))==5
            assert session.get(Budget,'budget').reserved==Decimal('.5')
        for identifier in assets:
            assert client.post('/api/v1/assets/'+identifier+'/reviews',json={'decision':'adopt'},headers=headers).status_code==201
        package=client.post('/api/v1/export-packages',json={'work_id':started.json()['work_id'],'mode':'sample','selection':'full_suite'},headers=headers)
        assert package.status_code==200,package.text
        download=client.get('/api/v1/exports/'+package.json()['id']+'/download')
        assert download.status_code==200
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            assert manifest['missing_items']==[]
            assert {asset['id'] for asset in manifest['assets']}==set(assets)
        return captured['creation_result']
    with patch.object(scenario,'handlers',capture),patch.object(Pipeline,'execute',intercept):
        scenario.HTTPPipelineTest().test_synthetic_http_to_real_media()
