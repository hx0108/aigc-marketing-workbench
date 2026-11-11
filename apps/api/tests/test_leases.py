import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.execution import Task,ExternalCall
from app.job_repository import JobRepository
class LeaseTests(unittest.TestCase):
    def test_heartbeat_fences_owner_and_canceled_tasks(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine);sessions=sessionmaker(engine)
        with sessions.begin() as s:s.add(Task(id='t',workspace='w',state='queued',phase='creation_run',payload={}))
        repo=JobRepository(sessions);job=repo.claim('worker')
        self.assertFalse(repo.heartbeat('t',job['fencing_token'],'wrong'))
        self.assertTrue(repo.heartbeat('t',job['fencing_token'],'worker'))
        with sessions.begin() as s:s.get(Task,'t').state='canceled'
        self.assertFalse(repo.heartbeat('t',job['fencing_token'],'worker'))
    def test_expired_pipeline_with_submission_becomes_unknown(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine);sessions=sessionmaker(engine)
        with sessions.begin() as s:
            s.add(Task(id='t',workspace='w',state='running',phase='creation_run',fencing_token=1,payload={'_lease':{'owner':'worker','expires':1}}))
            s.add(ExternalCall(id='c',intent_key='c',task_id='t',state='submitting',request_hash='h'))
        repo=JobRepository(sessions)
        self.assertEqual(repo.recover_expired(now=2),1)
        self.assertFalse(repo.complete('t',1,{}))
        with sessions() as s:self.assertEqual(s.get(Task,'t').state,'external_unknown')
