"""Eight-place ledger and budget-race evidence, isolated from real budgets."""
import os,uuid
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine,text,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.execution import Budget
from app.ledger import prepare,settle,CallReservation,MAX_MONEY
engine=create_engine(os.environ['DATABASE_URL'])
if engine.dialect.name!='postgresql':raise RuntimeError('PostgreSQL required')
schema='verify_precision_'+uuid.uuid4().hex
with engine.begin() as connection:connection.execute(text('CREATE SCHEMA '+schema))
scoped=engine.execution_options(schema_translate_map={None:schema})
try:
    Base.metadata.create_all(scoped);sessions=sessionmaker(scoped)
    with sessions.begin() as session:
        session.add(Budget(id='small',workspace='test',cap=Decimal('0.001306'),reserved=0,settled=0))
        session.add(Budget(id='capacity',workspace='test',cap=MAX_MONEY,reserved=0,settled=0))
    def attempt(index):
        try:
            with sessions.begin() as session:prepare(session,'small','call-'+str(index),'synthetic-hash','0.001306')
            return True
        except ValueError as error:
            if str(error)!='BUDGET_INSUFFICIENT':raise
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
    assert sum(results)==1
    with sessions.begin() as session:
        call=session.scalar(select(CallReservation).where(CallReservation.budget_id=='small'))
        assert call.remaining==Decimal('0.00130600')
        settle(session,'small',call.id,'synthetic-event','0.00000004',False,'synthetic precision fixture, not provider usage')
    with sessions() as session:
        budget=session.get(Budget,'small')
        assert budget.reserved==Decimal('0.00130596') and budget.settled==Decimal('0.00000004')
        assert session.get(Budget,'capacity').cap==MAX_MONEY
    print('PostgreSQL 18,8 precision: 0.001306 and 4e-8 exact; one concurrent reservation winner; 10 integer digits retained')
finally:
    with engine.begin() as connection:connection.execute(text('DROP SCHEMA '+schema+' CASCADE'))
    engine.dispose()
