import tempfile
import unittest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, Record
from marketing_worker.configuration import verify_consent
from marketing_worker.http_providers import DeepSeek

class ConsentTests(unittest.TestCase):
    def test_configuration_change_and_revocation_block_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=create_engine('sqlite:///'+str(Path(directory)/'test.db'))
            Base.metadata.create_all(engine)
            sessions=sessionmaker(engine)
            settings={'providers':{'text':{'model':'approved'}},'price_version':'v1','budget_id':'budget','consent_version':'v1','bounds':{'text':'1'}}
            snapshot={**settings,'providers':{'text':'approved'},'provider_parameters':{'text':DeepSeek.defaults},'profile_id':'profile','source_ids':['source'],'platforms':['douyin'],'duration_seconds':5}
            job={'workspace':'ws','payload':{'profile_id':'profile','request':{'consent_id':'consent','source_ids':['source'],'platforms':['douyin'],'duration_seconds':5}}}
            with sessions.begin() as session:
                session.add(Record(id='consent',workspace='ws',kind='processing_consent',data=snapshot))
                session.add(Record(id='profile',workspace='ws',kind='profile',data={'status':'confirmed'}))
            with sessions.begin() as session:
                verify_consent(session,job,settings)
                for key,value in [('source_ids',['different']),('platforms',['xiaohongshu']),('duration_seconds',15)]:
                    changed={**job,'payload':{**job['payload'],'request':{**job['payload']['request'],key:value}}}
                    with self.subTest(scope=key),self.assertRaisesRegex(ValueError,'consent_scope_mismatch'):
                        verify_consent(session,changed,settings)
                for key,value in [('providers',{'text':{'model':'different'}}),('providers',{'text':{'model':'approved','parameters':{'max_tokens':512}}}),('bounds',{'text':'2'}),('price_version','v2')]:
                    with self.subTest(key=key),self.assertRaisesRegex(ValueError,'authorization_scope_changed'):
                        verify_consent(session,job,{**settings,key:value})
                session.get(Record,'profile').data={'status':'revoked'}
                with self.assertRaisesRegex(ValueError,'fact_revoked'):
                    verify_consent(session,job,settings)
                with self.assertRaisesRegex(ValueError,'processing_consent_required'):
                    verify_consent(session,{**job,'workspace':'other'},settings)
            engine.dispose()

    def test_edit_authorization_uses_work_creation_request(self):
        engine=create_engine('sqlite://')
        Base.metadata.create_all(engine)
        settings={'providers':{'text':{'model':'approved'}},'price_version':'v1','budget_id':'budget','consent_version':'v1','bounds':{'text':'1'}}
        snapshot={**settings,'providers':{'text':'approved'},'provider_parameters':{'text':DeepSeek.defaults},'profile_id':'profile','request_id':'original-request','work_id':'work','draft':{'platform':'douyin','voice':'Cherry'}}
        job={'workspace':'ws','payload':{'consent_id':'consent','profile_id':'profile','work_id':'work','draft':snapshot['draft']}}
        with sessionmaker(engine)() as session:
            session.add(Record(id='consent',workspace='ws',kind='processing_consent',data=snapshot))
            session.add(Record(id='profile',workspace='ws',kind='profile',data={'status':'confirmed'}))
            work=Record(id='work',workspace='ws',kind='work',data={'creation_request_id':'original-request'})
            session.add(work);session.commit()
            verify_consent(session,job,settings)
            work.data={'creation_request_id':'other-request'}
            with self.assertRaisesRegex(ValueError,'consent_scope_mismatch'):
                verify_consent(session,job,settings)
        engine.dispose()
