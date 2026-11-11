"""Synthetic PostgreSQL bill replay proof in a disposable isolated schema."""
import hashlib,os,tempfile,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from decimal import Decimal
from sqlalchemy import create_engine,text,select,func
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.execution import Budget,Task,ExternalCall
from app.ledger import prepare,CostEvent
from app.billing import BillingReceipt,reconcile_bill
engine=create_engine(os.environ['DATABASE_URL'])
if engine.dialect.name!='postgresql':raise RuntimeError('PostgreSQL required')
schema='verify_bill_'+uuid.uuid4().hex
with engine.begin() as connection:connection.execute(text('CREATE SCHEMA '+schema))
scoped=engine.execution_options(schema_translate_map={None:schema})
try:
    Base.metadata.create_all(scoped);sessions=sessionmaker(scoped)
    fingerprint=hashlib.sha256(b'synthetic-request').hexdigest()
    with sessions.begin() as session:
        session.add(Budget(id='isolated-budget',workspace='isolated-workspace',cap=10,reserved=0,settled=0));session.flush()
        session.add(Task(id='task',workspace='isolated-workspace',state='external_unknown',phase='text',payload={}))
        prepare(session,'isolated-budget','call',fingerprint,'8')
        session.add(ExternalCall(id='call',intent_key='call',task_id='task',state='external_unknown',request_hash=fingerprint))
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);evidence=root/'synthetic.txt';evidence.write_bytes(b'SYNTHETIC BILL TEST ONLY')
        manifest={'schema_version':1,'provider':'test','provider_account':'test','bill_id':'test','workspace':'isolated-workspace','currency':'CNY','evidence_kind':'supplier_bill','amount_semantics':'incremental','evidence_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest(),'lines':[{'line_id':'1','budget_id':'isolated-budget','call_id':'call','request_hash':fingerprint,'amount':'3','final':False}]}
        def import_once(_):
            with sessions.begin() as session:return reconcile_bill(session,manifest,evidence,'test-admin',apply=True,evidence_root=root/'archive')
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(import_once,range(2)))
        assert sum(result['imported_events'] for result in results)==1
        assert sum(result['duplicate_events'] for result in results)==1
        with sessions() as session:
            budget=session.get(Budget,'isolated-budget')
            assert (budget.reserved,budget.settled)==(Decimal('5'),Decimal('3'))
            assert session.scalar(select(func.count()).select_from(CostEvent))==1
            assert session.scalar(select(func.count()).select_from(BillingReceipt))==1
    print('PostgreSQL synthetic billing: concurrent duplicate charged once; remaining reservation preserved')
finally:
    with engine.begin() as connection:connection.execute(text('DROP SCHEMA '+schema+' CASCADE'))
    engine.dispose()

