"""Per-call reservations. Caller owns transaction and authorizes task scope first."""
from decimal import Decimal,InvalidOperation
from sqlalchemy import String, Numeric, Boolean, ForeignKey, CheckConstraint, select
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .execution import Budget, reserve

MONEY_QUANTUM=Decimal('0.00000001')
MAX_MONEY=Decimal('9999999999.99999999')

def money(value):
    try:amount = Decimal(str(value))
    except InvalidOperation:raise ValueError('INVALID_MONEY_PRECISION') from None
    if not amount.is_finite() or amount < 0 or amount > MAX_MONEY or amount != amount.quantize(MONEY_QUANTUM):
        raise ValueError('INVALID_MONEY_PRECISION')
    return amount

class CallReservation(Base):
    __tablename__ = 'call_reservations'
    __table_args__ = (CheckConstraint('upper_bound > 0 AND remaining >= 0 AND remaining <= upper_bound'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey('budgets.id'))
    request_hash: Mapped[str] = mapped_column(String)
    upper_bound: Mapped[Decimal] = mapped_column(Numeric(18,8))
    remaining: Mapped[Decimal] = mapped_column(Numeric(18,8))
    finalized: Mapped[bool] = mapped_column(Boolean, default=False)
    workspace: Mapped[str|None] = mapped_column(String,nullable=True)

class CostEvent(Base):
    __tablename__ = 'cost_events'
    __table_args__ = (CheckConstraint('amount >= 0'),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    call_id: Mapped[str] = mapped_column(ForeignKey('call_reservations.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(18,8))
    final: Mapped[bool] = mapped_column(Boolean)
    evidence: Mapped[str] = mapped_column(String)
    workspace: Mapped[str|None] = mapped_column(String,nullable=True)


def prepare(session, budget_id, call_id, request_hash, upper_bound):
    amount = money(upper_bound)
    if amount <= 0:
        raise ValueError('INVALID_COST_BOUND')
    budget = session.scalar(select(Budget).where(Budget.id == budget_id).with_for_update())
    if budget is None:
        raise ValueError('BUDGET_INSUFFICIENT')
    old = session.get(CallReservation, call_id)
    if old:
        if old.budget_id != budget_id or old.request_hash != request_hash or old.upper_bound != amount:
            raise ValueError('IDEMPOTENCY_CONFLICT')
        return old
    reserve(session, budget_id, amount)
    call = CallReservation(id=call_id, budget_id=budget_id, request_hash=request_hash, remaining=amount, upper_bound=amount,workspace=budget.workspace)
    session.add(call)
    session.flush()
    return call


def settle(session, budget_id, call_id, event_id, amount, final, evidence):
    """Amount is an incremental charge, never a cumulative provider total."""
    amount = money(amount)
    if not evidence:
        raise ValueError('SETTLEMENT_EVIDENCE_REQUIRED')
    budget = session.scalar(select(Budget).where(Budget.id == budget_id).with_for_update())
    call = session.scalar(select(CallReservation).where(CallReservation.id == call_id).with_for_update())
    if budget is None or call is None or call.budget_id != budget_id:
        raise ValueError('CALL_NOT_FOUND')
    old = session.get(CostEvent, event_id)
    if old:
        if (old.call_id, old.amount, old.final, old.evidence) != (call_id, amount, final, evidence):
            raise ValueError('EVENT_CONFLICT')
        return
    if call.finalized:
        raise ValueError('CALL_ALREADY_SETTLED')
    released = call.remaining if final else min(call.remaining, amount)
    budget.reserved -= released
    budget.settled += amount
    call.remaining -= released
    call.finalized = final
    session.add(CostEvent(id=event_id, call_id=call_id, amount=amount, final=final, evidence=evidence,workspace=budget.workspace))
    session.flush()
