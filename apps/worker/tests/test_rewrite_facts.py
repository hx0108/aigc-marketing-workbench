import tempfile
import unittest
from types import SimpleNamespace
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base,Record
from marketing_worker.edits import rewrite_handler
from marketing_worker.fact_validation import NumericFactError


class RewriteFactsTests(unittest.TestCase):
    def test_rewrite_requires_matching_numeric_fact_before_candidate_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=create_engine('sqlite:///'+directory+'/db');Base.metadata.create_all(engine);sessions=sessionmaker(engine)
            with sessions.begin() as session:session.add(Record(id='profile',workspace='ws',kind='profile',data={'status':'confirmed','facts':{'power':'20W'}}))
            job={'id':'rewrite','workspace':'ws','payload':{'profile_id':'profile','platform':'douyin','instruction':'rewrite','work_id':'work','base_draft_revision':1}}
            class Service:
                value='200W'
                def invoke(self,*args):return {'douyin':{'title':self.value,'fact_refs':['power']}}
            service=Service()
            with self.assertRaises(NumericFactError):rewrite_handler(SimpleNamespace(sessions=sessions),job,lambda job:service)
            with sessions() as session:self.assertEqual(list(session.scalars(select(Record).where(Record.kind=='copy_candidate'))),[])
            service.value='20W'
            result=rewrite_handler(SimpleNamespace(sessions=sessions),job,lambda job:service)
            self.assertEqual(result['candidate_id'],'rewrite:candidate')
            engine.dispose()
