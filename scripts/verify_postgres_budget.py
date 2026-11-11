"""Run explicitly against an isolated PostgreSQL schema; no external AI calls."""
import os, uuid, threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.execution import Budget, Task
from app.ledger import prepare, settle
from app.job_repository import JobRepository

def main():
    url=os.environ['TEST_DATABASE_URL']
    if not url.startswith('postgresql'):
        raise RuntimeError('PostgreSQL required')
    schema='budget_test_'+uuid.uuid4().hex
    admin=create_engine(url)
    with admin.begin() as c:c.execute(text('CREATE SCHEMA '+schema))
    engine=create_engine(url,connect_args={'options':'-csearch_path='+schema})
    try:
        Base.metadata.create_all(engine)
        sessions=sessionmaker(engine)
        with sessions.begin() as s:s.add(Budget(id='b',workspace='test',cap=Decimal('10'),reserved=0,settled=0))
        barrier=threading.Barrier(2)
        def submit(index):
            barrier.wait(timeout=10)
            try:
                with sessions.begin() as s:prepare(s,'b',str(index),'hash','7')
                return 'accepted'
            except ValueError as e:
                if str(e)!='BUDGET_INSUFFICIENT':raise
                return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(submit,[1,2]))
        assert sorted(results)==['accepted','rejected'],results
        with sessions() as s:assert s.get(Budget,'b').reserved==Decimal('7')
        print('PASS: concurrent PostgreSQL submissions accepted=1 rejected=1 reserved=7')
        with sessions.begin() as s:
            s.add(Budget(id='replay',workspace='test',cap=Decimal('10'),reserved=0,settled=0))
        replay_barrier=threading.Barrier(2)
        def replay(_):
            replay_barrier.wait(timeout=10)
            with sessions.begin() as s:prepare(s,'replay','same-call','same-hash','7')
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(replay,[1,2]))
        with sessions() as s:assert s.get(Budget,'replay').reserved==Decimal('7')
        event_barrier=threading.Barrier(2)
        def event(_):
            event_barrier.wait(timeout=10)
            with sessions.begin() as s:settle(s,'replay','same-call','same-event','2',True,'verified-final-bill')
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(event,[1,2]))
        with sessions() as s:
            budget=s.get(Budget,'replay')
            assert budget.reserved==0 and budget.settled==Decimal('2')
        print('PASS: concurrent identical call reserved once; duplicate final bill settled once')
        with sessions.begin() as s:
            s.add(Task(id='task',workspace='test',state='queued',phase='creation_run',payload={}))
        claim_barrier=threading.Barrier(2)
        repository=JobRepository(sessions)
        def claim(owner):
            claim_barrier.wait(timeout=10)
            return repository.claim(owner)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims=list(pool.map(claim,['worker-a','worker-b']))
        winners=[job for job in claims if job]
        assert len(winners)==1,claims
        token=winners[0]['fencing_token']
        with sessions.begin() as s:
            task=s.get(Task,'task');task.state='canceled';task.fencing_token+=1
        assert not repository.complete('task',token,{'late':'result'})
        with sessions() as s:assert s.get(Task,'task').state=='canceled'
        print('PASS: PostgreSQL concurrent claims winner=1; late result cannot revive cancellation')
    finally:
        engine.dispose()
        with admin.begin() as c:c.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()
if __name__=='__main__':main()
