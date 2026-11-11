"""Read-only pre-migration relational integrity counts; no IDs or amounts emitted."""
import os
from sqlalchemy import create_engine,text
engine=create_engine(os.environ['DATABASE_URL'])
queries={
'call_without_task':'SELECT count(*) FROM external_calls c LEFT JOIN tasks t ON t.id=c.task_id WHERE t.id IS NULL',
'reservation_without_call':'SELECT count(*) FROM call_reservations r LEFT JOIN external_calls c ON c.id=r.id WHERE c.id IS NULL',
'reservation_workspace_mismatch':'SELECT count(*) FROM call_reservations r JOIN external_calls c ON c.id=r.id JOIN tasks t ON t.id=c.task_id JOIN budgets b ON b.id=r.budget_id WHERE t.workspace<>b.workspace',
'receipt_mismatch':'SELECT count(*) FROM billing_receipts x JOIN call_reservations r ON r.id=x.call_id JOIN budgets b ON b.id=r.budget_id WHERE x.workspace<>b.workspace OR x.budget_id<>r.budget_id',
}
with engine.connect() as c:
    counts={key:c.execute(text(sql)).scalar() for key,sql in queries.items()}
print(counts)
if any(counts.values()):raise SystemExit(2)
