import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from app.db import Base,Record
from app.execution import Task
from app.recovery import recover
class RecoveryInvariantTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://');Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.s=sessionmaker(self.engine,expire_on_commit=False)();self.addCleanup(self.s.close)
        self.task=Task(id='t',workspace='w',state='failed',phase='creation_run',payload={})
        self.s.add(self.task);self.s.commit()
    def test_local_resume_preserves_successful_step(self):
        self.s.add(Record(id='t:copy',workspace='w',kind='task_step',data={'task_id':'t','state':'succeeded','result':{'title':'saved'}}));self.s.commit()
        recover(self.s,self.task)
        self.assertEqual(self.task.state,'queued')
        self.assertEqual(self.s.get(Record,'t:copy').data['result'],{'title':'saved'})
    def test_revoked_profile_cannot_resume(self):
        self.s.add(Record(id='p',workspace='w',kind='profile',data={'status':'revoked'}))
        self.task.payload={'profile_id':'p'};self.s.commit()
        with self.assertRaises(HTTPException) as error:recover(self.s,self.task)
        self.assertEqual(error.exception.detail['code'],'FACT_REVOKED')
        self.assertEqual(self.task.state,'failed')
    def test_static_fallback_rejects_unselected_platform(self):
        from app.recovery import select_static_fallback
        self.task.payload={'profile_id':'p','request':{'platforms':['douyin']}}
        self.s.add_all([Record(id='p',workspace='w',kind='profile',data={'status':'confirmed'}),Record(id='t:copy',workspace='w',kind='task_step',data={'state':'succeeded','result':{'xiaohongshu':{'shots':[{}]}}})]);self.s.commit()
        with self.assertRaises(HTTPException) as error:select_static_fallback(self.s,self.task,['xiaohongshu/0'],True)
        self.assertEqual(error.exception.status_code,422)
        self.assertEqual(self.task.state,'failed')
