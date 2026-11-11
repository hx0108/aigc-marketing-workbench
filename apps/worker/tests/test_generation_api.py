import io
import hashlib
import json
import zipfile
from pathlib import Path
from unittest.mock import patch
from app import db, sources, exporting
from app.db import Record
from app.execution import Task
from marketing_worker.business import persist_result
from marketing_worker.pipeline import Pipeline
from test_core import client
from test_http_pipeline import HTTPPipelineTest


def test_http_generation_review_and_zip_api(client,tmp_path,monkeypatch):
    # Reuse the four-provider HTTP replacement scenario; its media renderer is real.
    monkeypatch.setenv('TMP',str(tmp_path))
    monkeypatch.setenv('TEMP',str(tmp_path))
    original=Pipeline.execute
    checked=[]
    def execute(pipeline,task_id,request):
        result=original(pipeline,task_id,request)
        root=Path(result['images']['white']['path']).parent
        monkeypatch.setattr(sources,'ROOT',root)
        monkeypatch.setattr(exporting,'ROOT',root)
        with db.Session.begin() as session:
            session.add(Record(id='profile',workspace='one',kind='profile',data={'status':'confirmed','source_ids':['other-source']}))
            session.add(Record(id='request',workspace='one',kind='creation_request',data={'profile_snapshot':{'source_ids':['original-source','unavailable-source']}}))
            session.add(Record(id='original-source',workspace='one',kind='source',data={'sku_id':'sku','rights_confirmed':True}))
            session.add(Record(id='unavailable-source',workspace='other',kind='source',data={'sku_id':'sku','rights_confirmed':True}))
            session.add(Record(id='work',workspace='one',kind='work',data={'sku_id':'sku','profile_id':'profile','creation_request_id':'request','platforms':['douyin'],'duration_seconds':2}))
            session.add(Task(id='api-generation',workspace='one',state='running',phase='creation_run',fencing_token=1,payload={}))
        stored=persist_result(db.Session,{'id':'api-generation','workspace':'one','fencing_token':1,'payload':{'work_id':'work'}},result,root)
        assert len(stored['assets'])==7
        login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
        headers={'X-CSRF-Token':login.json()['csrf_token']}
        poster_id=next(asset_id for asset_id in stored['assets'] if ':poster:' in asset_id)
        subset={'work_id':'work','mode':'sample','selection':'full_suite','asset_ids':[poster_id]}
        pending=client.post('/api/v1/export-packages',json=subset,headers=headers)
        assert pending.status_code==409 and pending.json()['detail']['code']=='REVIEW_REQUIRED'
        for asset_id in stored['assets']:
            reviewed=client.post('/api/v1/assets/'+asset_id+'/reviews',json={'decision':'adopt'},headers=headers)
            assert reviewed.status_code==201,reviewed.text
        partial=client.post('/api/v1/export-packages',json=subset,headers=headers)
        assert partial.status_code==200,partial.text
        partial_zip=client.get('/api/v1/exports/'+partial.json()['id']+'/download')
        assert partial_zip.status_code==200
        with zipfile.ZipFile(io.BytesIO(partial_zip.content)) as archive:
            partial_manifest=json.loads(archive.read('manifest.json'))
            assert len(archive.namelist())==2
            assert partial_manifest['partial'] is True
            assert [item['id'] for item in partial_manifest['assets']]==[poster_id]
            assert 'video/douyin' in partial_manifest['missing_items']
        invalid=client.post('/api/v1/export-packages',json={**subset,'asset_ids':['other-result']},headers=headers)
        assert invalid.status_code==409 and invalid.json()['detail']['code']=='INVALID_ASSET_SELECTION'
        packaged=client.post('/api/v1/export-packages',json={'work_id':'work','mode':'sample','selection':'full_suite'},headers=headers)
        assert packaged.status_code==200,packaged.text
        downloaded=client.get('/api/v1/exports/'+packaged.json()['id']+'/download')
        assert downloaded.status_code==200,downloaded.text
        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
            names=archive.namelist()
            assert 'manifest.json' in names
            assert len(names)==8
            assert any(name.endswith('.mp4') for name in names)
            manifest = json.loads(archive.read('manifest.json'))
            assert manifest['sku_id'] == 'sku'
            assert manifest['platforms'] == ['douyin']
            assert manifest['result_revision_id'] == stored['result_revision']
            assert manifest['work_status'] == 'awaiting_review'
            assert manifest['material_rights'] == {'source_provenance_available': True, 'materials': [
                {'id': 'original-source', 'kind': 'source', 'revision': 1, 'confirmation': 'user_confirmed'},
                {'id': 'unavailable-source', 'kind': 'source', 'revision': None, 'confirmation': 'unknown'},
            ]}
            for asset in manifest['assets']:
                filename = next(name for name in names if name.rsplit('.', 1)[0] == asset['id'])
                assert hashlib.sha256(archive.read(filename)).hexdigest() == asset['sha256']
                assert asset['label']['internal_sample'] is True
                assert asset['review'] == 'approved'
        checked.append(True)
        return result
    with patch.object(Pipeline,'execute',execute):
        HTTPPipelineTest('test_synthetic_http_to_real_media').test_synthetic_http_to_real_media()
    assert checked==[True]
