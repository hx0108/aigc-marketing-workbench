import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from app.db import Base,Record
from app.execution import Task,ExternalCall
from app.recovery import recover,select_static_fallback
class RecoveryTests(unittest.TestCase):
    def test_unknown_external_step_cannot_be_retried(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine,expire_on_commit=False)() as s:
            task=Task(id='t',workspace='w',state='failed',phase='creation_run',payload={})
            s.add_all([task,Record(id='t:voice',workspace='w',kind='task_step',data={'task_id':'t','state':'failed'}),ExternalCall(id='t:voice',intent_key='t:voice',task_id='t',state='external_unknown',request_hash='h')]);s.commit()
            with self.assertRaises(HTTPException):recover(s,task)
            self.assertEqual(task.state,'failed')
    def test_static_fallback_preserves_external_call(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine,expire_on_commit=False)() as s:
            task=Task(id='t',workspace='w',state='external_unknown',phase='creation_run',payload={'profile_id':'p','request':{'platforms':['douyin']}})
            s.add_all([task,Record(id='p',workspace='w',kind='profile',data={'status':'confirmed'}),Record(id='t:copy',workspace='w',kind='task_step',data={'state':'succeeded','result':{'douyin':{'shots':[{}]}}}),Record(id='t:douyin/dynamic/0',workspace='w',kind='task_step',data={'state':'external_unknown'}),ExternalCall(id='t:douyin/dynamic/0',intent_key='t:douyin/dynamic/0',task_id='t',state='external_unknown',request_hash='h')]);s.commit()
            select_static_fallback(s,task,['douyin/0'],True)
            self.assertEqual(task.state,'queued')
            self.assertEqual(s.get(ExternalCall,'t:douyin/dynamic/0').state,'external_unknown')
            step=s.get(Record,'t:douyin/dynamic/0')
            step.data={**step.data,'task_id':'t'}
            s.add(Record(id='t:douyin/static/0',workspace='w',kind='task_step',data={'task_id':'t','state':'failed'}))
            task.state='partial';s.commit()
            recover(s,task)
            self.assertEqual(task.state,'queued')
            self.assertEqual(s.get(ExternalCall,'t:douyin/dynamic/0').state,'external_unknown')
