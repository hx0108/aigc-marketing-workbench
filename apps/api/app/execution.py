from sqlalchemy import UniqueConstraint, CheckConstraint, Numeric
from decimal import Decimal
from .db import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, JSON, DateTime,func,Index
from datetime import datetime,timezone

class Budget(Base):
    __tablename__='budgets'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    workspace:Mapped[str]=mapped_column(String,index=True)
    cap:Mapped[Decimal]=mapped_column(Numeric(18,8))
    reserved:Mapped[Decimal]=mapped_column(Numeric(18,8),default=0)
    settled:Mapped[Decimal]=mapped_column(Numeric(18,8),default=0)
    __table_args__=(CheckConstraint('cap >= 0 AND reserved >= 0 AND settled >= 0'),)
class Task(Base):
    __tablename__='tasks'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    workspace:Mapped[str]=mapped_column(String,index=True)
    state:Mapped[str]=mapped_column(String,index=True,default='queued')
    phase:Mapped[str]=mapped_column(String,default='preflight')
    fencing_token:Mapped[int]=mapped_column(Integer,default=0)
    payload:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True,default=lambda:datetime.now(timezone.utc),server_default=func.now())
    __table_args__=(Index('ix_tasks_workspace_created','workspace',created_at.desc(),'id'),)
class ExternalCall(Base):
    __tablename__='external_calls'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    intent_key:Mapped[str]=mapped_column(String,unique=True)
    task_id:Mapped[str]=mapped_column(String,index=True)
    state:Mapped[str]=mapped_column(String,default='prepared')
    request_hash:Mapped[str]=mapped_column(String)
    workspace:Mapped[str|None]=mapped_column(String,nullable=True)


from sqlalchemy import event,select
@event.listens_for(ExternalCall,'before_insert')
def assign_call_workspace(mapper,connection,target):
    workspace=connection.execute(select(Task.workspace).where(Task.id==target.task_id)).scalar_one_or_none()
    if workspace is not None:
        if target.workspace is not None and target.workspace!=workspace:raise ValueError('CALL_WORKSPACE_MISMATCH')
        target.workspace=workspace


def reserve(session,budget_id,amount):
    from sqlalchemy import select
    from .db import Record
    from .ledger import money
    amount=money(amount)
    budget=session.scalar(select(Budget).where(Budget.id==budget_id).with_for_update())
    hold=session.get(Record,'budget-hold:'+budget_id)
    if hold and hold.kind=='budget_hold' and hold.data.get('active'):raise ValueError('BUDGET_HELD_FOR_REVIEW')
    if not budget or amount<=0 or budget.settled+budget.reserved+amount>budget.cap:
        raise ValueError('BUDGET_INSUFFICIENT')
    budget.reserved+=amount
    session.flush()
