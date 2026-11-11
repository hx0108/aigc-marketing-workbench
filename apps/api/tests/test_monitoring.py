from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.db import Base
from app.execution import Budget, Task, ExternalCall
from app.monitoring import snapshot


def test_monitor_reports_scoped_unknown_budget_and_queue_without_mutation():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    now=datetime(2026,11,11,tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add_all([
            Task(id='a',workspace='one',state='queued',payload={'secret':'not in report'},created_at=now-timedelta(seconds=60)),
            Task(id='b',workspace='two',state='failed',payload={}),
            Budget(id='budget1',workspace='one',cap=1,reserved=1,settled=1),
        ])
        session.flush()
        session.add(ExternalCall(id='call',intent_key='call',task_id='a',request_hash='hash',state='external_unknown'))
        session.commit()
        result=snapshot(session,'one',30,now)
        assert result['task_states']=={'queued':1}
        assert result['oldest_queue_seconds']==60
        assert {x['code'] for x in result['alerts']}=={'BUDGET_OVER_CAP','EXTERNAL_OUTCOME_UNKNOWN','QUEUE_AGE_EXCEEDED'}
        assert 'secret' not in str(result) and result['alert_delivery']=='not_configured'
        assert session.get(Budget,'budget1').reserved==Decimal(1)
        assert session.get(ExternalCall,'call').state=='external_unknown'
        assert session.scalar(select(func.count()).select_from(Task))==2
        missing=snapshot(session,'two',now=now)
        assert missing['queue_threshold_configured'] is False and missing['oldest_queue_seconds'] is None
        assert missing['alerts']==[{'code':'FAILED_TASKS','severity':'warning','count':1}]
