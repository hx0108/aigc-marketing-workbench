"""Administrator-reviewed supplier bills; no public HTTP mutation surface."""
from __future__ import annotations
import hashlib,json,os,uuid
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,StrictBool,field_validator,model_validator
from sqlalchemy import String,Numeric,Boolean,DateTime,ForeignKey,CheckConstraint,UniqueConstraint,select,func
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,Record
from .execution import Budget,ExternalCall,Task
from .ledger import CallReservation,CostEvent,money,settle,MONEY_QUANTUM

MAX_EVIDENCE_BYTES=64*1024*1024

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

class BillLine(BaseModel):
    model_config=ConfigDict(extra='forbid')
    line_id:str=Field(min_length=1,max_length=200)
    budget_id:str=Field(min_length=1,max_length=200)
    call_id:str=Field(min_length=1,max_length=512)
    request_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    amount:str=Field(min_length=1,max_length=32)
    final:StrictBool
    @field_validator('amount')
    @classmethod
    def valid_amount(cls,value):
        try:
            amount=money(value)
        except (ValueError,InvalidOperation):raise ValueError('INVALID_AMOUNT') from None
        return format(amount.quantize(MONEY_QUANTUM),'f')

class BillManifest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version:Literal[1]
    provider:str=Field(min_length=1,max_length=100)
    provider_account:str=Field(min_length=1,max_length=200)
    bill_id:str=Field(min_length=1,max_length=200)
    workspace:str=Field(min_length=1,max_length=200)
    currency:Literal['CNY']
    evidence_kind:Literal['supplier_bill']
    amount_semantics:Literal['incremental']
    evidence_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    lines:list[BillLine]=Field(min_length=1,max_length=1000)
    @model_validator(mode='after')
    def unique_lines(self):
        if len({line.line_id for line in self.lines})!=len(self.lines):raise ValueError('DUPLICATE_BILL_LINE')
        return self

class BillingReceipt(Base):
    __tablename__='billing_receipts'
    __table_args__=(UniqueConstraint('provider','provider_account','bill_id','line_id',name='uq_supplier_bill_line'),CheckConstraint('amount >= 0'),)
    id:Mapped[str]=mapped_column(String,primary_key=True)
    workspace:Mapped[str]=mapped_column(String,index=True)
    provider:Mapped[str]=mapped_column(String)
    provider_account:Mapped[str]=mapped_column(String)
    bill_id:Mapped[str]=mapped_column(String)
    line_id:Mapped[str]=mapped_column(String)
    budget_id:Mapped[str]=mapped_column(ForeignKey('budgets.id'))
    call_id:Mapped[str]=mapped_column(ForeignKey('call_reservations.id'))
    request_hash:Mapped[str]=mapped_column(String)
    currency:Mapped[str]=mapped_column(String)
    amount:Mapped[Decimal]=mapped_column(Numeric(18,8))
    final:Mapped[bool]=mapped_column(Boolean)
    evidence_sha256:Mapped[str]=mapped_column(String)
    evidence_key:Mapped[str]=mapped_column(String)
    reviewed_by:Mapped[str]=mapped_column(String)
    imported_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),server_default=func.now())

def evidence_hash(path):
    path=Path(path)
    if not path.is_file():raise ValueError('EVIDENCE_FILE_REQUIRED')
    count=0;digest=hashlib.sha256()
    with path.open('rb') as source:
        while chunk:=source.read(1024*1024):
            count+=len(chunk)
            if count>MAX_EVIDENCE_BYTES:raise ValueError('EVIDENCE_TOO_LARGE')
            digest.update(chunk)
    if not count:raise ValueError('EVIDENCE_FILE_EMPTY')
    return digest.hexdigest()

def archive_evidence(path,expected,root):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    key=expected+'.evidence';destination=root/key
    if destination.exists():
        if evidence_hash(destination)!=expected:raise ValueError('ARCHIVED_EVIDENCE_CORRUPTED')
        return key
    temporary=root/('staging-'+uuid.uuid4().hex)
    try:
        with Path(path).open('rb') as source,temporary.open('xb') as output:
            total=0
            while chunk:=source.read(1024*1024):
                total+=len(chunk)
                if total>MAX_EVIDENCE_BYTES:raise ValueError('EVIDENCE_TOO_LARGE')
                output.write(chunk)
        if evidence_hash(temporary)!=expected:raise ValueError('EVIDENCE_HASH_MISMATCH')
        try:
            if os.name=='nt':os.rename(temporary,destination)
            else:os.link(temporary,destination)
        except FileExistsError:
            if evidence_hash(destination)!=expected:raise ValueError('ARCHIVED_EVIDENCE_CORRUPTED')
    finally:temporary.unlink(missing_ok=True)
    return key

def event_id(manifest,line):
    return 'supplier-bill:'+hashlib.sha256(canonical([manifest.provider,manifest.provider_account,manifest.bill_id,line.line_id]).encode()).hexdigest()

def reconcile_bill(session,manifest,evidence_file,reviewed_by,apply=False,evidence_root=None):
    """One bill is atomic. Caller owns commit; dry runs never archive or settle."""
    if not isinstance(manifest,BillManifest):manifest=BillManifest.model_validate(manifest)
    if not isinstance(reviewed_by,str) or not reviewed_by.strip() or len(reviewed_by)>200:raise ValueError('ADMIN_REVIEWER_REQUIRED')
    if evidence_hash(evidence_file)!=manifest.evidence_sha256:raise ValueError('EVIDENCE_HASH_MISMATCH')
    root=Path(evidence_root or os.environ.get('AIGC_BILLING_EVIDENCE_ROOT','runtime/billing-evidence'))
    with session.begin_nested():
        budgets={}
        for identifier in sorted({line.budget_id for line in manifest.lines}):
            budget=session.scalar(select(Budget).where(Budget.id==identifier).with_for_update())
            if budget is None or budget.workspace!=manifest.workspace:raise ValueError('BUDGET_SCOPE_MISMATCH')
            budgets[identifier]=budget
        validated=[];closing=set()
        for line in manifest.lines:
            call=session.get(ExternalCall,line.call_id)
            reservation=session.get(CallReservation,line.call_id)
            if call is None or reservation is None:raise ValueError('CALL_NOT_FOUND')
            if reservation.budget_id!=line.budget_id:raise ValueError('CALL_BUDGET_MISMATCH')
            task=session.get(Task,call.task_id)
            if task is None or task.workspace!=manifest.workspace:raise ValueError('CALL_WORKSPACE_MISMATCH')
            if call.request_hash!=line.request_hash or reservation.request_hash!=line.request_hash:raise ValueError('CALL_REQUEST_HASH_MISMATCH')
            identifier=event_id(manifest,line);previous=session.get(BillingReceipt,identifier)
            signature=(manifest.workspace,line.budget_id,line.call_id,line.request_hash,manifest.currency,Decimal(line.amount),line.final,manifest.evidence_sha256)
            if previous:
                old=(previous.workspace,previous.budget_id,previous.call_id,previous.request_hash,previous.currency,previous.amount,previous.final,previous.evidence_sha256)
                if old!=signature:raise ValueError('BILL_LINE_CONFLICT')
            elif reservation.finalized or line.call_id in closing:raise ValueError('CALL_ALREADY_SETTLED')
            if line.final and not previous:closing.add(line.call_id)
            validated.append((line,identifier,previous,reservation))
        if not apply:return {'mode':'dry_run','validated':len(validated),'new_events':sum(previous is None for _,_,previous,_ in validated),'duplicate_events':sum(previous is not None for _,_,previous,_ in validated),'new_charge_total':str(sum((Decimal(line.amount) for line,_,previous,_ in validated if previous is None),Decimal(0))),'currency':manifest.currency,'lines':[{'call_id':line.call_id,'budget_id':line.budget_id,'amount':line.amount,'final':line.final,'duplicate':previous is not None} for line,_,previous,_ in validated],'evidence_sha256':manifest.evidence_sha256,'ledger_changed':False}
        key=archive_evidence(evidence_file,manifest.evidence_sha256,root)
        imported=0;duplicates=0;holds=set()
        for line,identifier,previous,reservation in validated:
            if previous:
                duplicates+=1;continue
            evidence=canonical({'evidence_kind':manifest.evidence_kind,'provider':manifest.provider,'provider_account':manifest.provider_account,'bill_id':manifest.bill_id,'line_id':line.line_id,'sha256':manifest.evidence_sha256,'object_key':key})
            settle(session,line.budget_id,line.call_id,identifier,line.amount,line.final,evidence)
            session.add(BillingReceipt(id=identifier,workspace=manifest.workspace,provider=manifest.provider,provider_account=manifest.provider_account,bill_id=manifest.bill_id,line_id=line.line_id,budget_id=line.budget_id,call_id=line.call_id,request_hash=line.request_hash,currency=manifest.currency,amount=Decimal(line.amount),final=line.final,evidence_sha256=manifest.evidence_sha256,evidence_key=key,reviewed_by=reviewed_by.strip()))
            settled=session.scalar(select(func.sum(CostEvent.amount)).where(CostEvent.call_id==line.call_id)) or Decimal(0)
            if settled>reservation.upper_bound:
                identifier_hold='budget-hold:'+line.budget_id
                hold=session.get(Record,identifier_hold)
                if hold is None:session.add(Record(id=identifier_hold,workspace=manifest.workspace,kind='budget_hold',data={'active':True,'reason':'SUPPLIER_UPPER_BOUND_EXCEEDED','provider':manifest.provider,'call_id':line.call_id,'bill_event_id':identifier,'evidence_sha256':manifest.evidence_sha256}))
                else:hold.data={**hold.data,'active':True}
                holds.add(line.budget_id)
            imported+=1
        session.flush()
        return {'mode':'applied','imported_events':imported,'duplicate_events':duplicates,'evidence_sha256':manifest.evidence_sha256,'budget_holds':sorted(holds),'ledger_changed':bool(imported)}
