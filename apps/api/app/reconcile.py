"""Local administrator billing CLI. Never submits supplier requests."""
import argparse,json,os,sys
from pathlib import Path
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from .db import engine,Session
from .billing import BillManifest,reconcile_bill
from .execution import Budget,ExternalCall,Task
from .ledger import CallReservation

def local_database_only():
    if not os.environ.get('DATABASE_URL'):raise ValueError('DATABASE_URL_REQUIRED')
    if engine.dialect.name not in {'postgresql','sqlite'}:raise ValueError('UNSUPPORTED_DATABASE')
    if engine.dialect.name=='postgresql' and engine.url.host not in {None,'localhost','127.0.0.1','::1'}:raise ValueError('LOCAL_DATABASE_REQUIRED')

def main(argv=None):
    parser=argparse.ArgumentParser(description='本机管理员供应商账单对账；默认仅预检，不调用供应商。')
    commands=parser.add_subparsers(dest='command',required=True)
    inspect=commands.add_parser('inspect',help='列出指定空间预算尚未结清的调用，不显示原始资料或密钥')
    inspect.add_argument('--workspace',required=True);inspect.add_argument('--budget-id',required=True)
    inspect.add_argument('--limit',type=int,default=100);inspect.add_argument('--after-call-id',default='')
    importing=commands.add_parser('import',help='导入管理员已核对的增量账单映射；无--apply仅预检')
    importing.add_argument('--manifest',type=Path,required=True);importing.add_argument('--evidence',type=Path,required=True)
    importing.add_argument('--reviewed-by',required=True,help='已核对账单原件及调用映射的管理员标识')
    importing.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    try:
        local_database_only()
        with Session.begin() as session:
            if args.command=='inspect':
                if not 1<=args.limit<=1000:raise ValueError('INVALID_LIMIT')
                budget=session.get(Budget,args.budget_id)
                if budget is None or budget.workspace!=args.workspace:raise ValueError('BUDGET_SCOPE_MISMATCH')
                rows=session.execute(select(CallReservation,ExternalCall).join(ExternalCall,ExternalCall.id==CallReservation.id).join(Task,Task.id==ExternalCall.task_id).where(CallReservation.budget_id==args.budget_id,CallReservation.finalized==False,Task.workspace==args.workspace,CallReservation.id>args.after_call_id).order_by(CallReservation.id).limit(args.limit+1)).all()
                more=len(rows)>args.limit;rows=rows[:args.limit]
                result={'budget_id':budget.id,'reserved':str(budget.reserved),'settled':str(budget.settled),'items':[{'call_id':reservation.id,'request_hash':reservation.request_hash,'upper_bound':str(reservation.upper_bound),'reserved_remaining':str(reservation.remaining),'execution_state':call.state} for reservation,call in rows],'next_after_call_id':rows[-1][0].id if more else None}
            else:
                if not args.manifest.is_file() or args.manifest.stat().st_size>2*1024*1024:raise ValueError('MANIFEST_FILE_INVALID')
                manifest=BillManifest.model_validate_json(args.manifest.read_text(encoding='utf-8-sig'))
                result=reconcile_bill(session,manifest,args.evidence,args.reviewed_by,apply=args.apply)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 0
    except ValidationError:
        print(json.dumps({'error':'INVALID_BILL_MANIFEST','ledger_changed':False}),file=sys.stderr);return 2
    except (OSError,ValueError) as error:
        code=str(error) if isinstance(error,ValueError) and str(error).replace('_','').isalnum() else 'BILL_IMPORT_FAILED'
        print(json.dumps({'error':code,'ledger_changed':False}),file=sys.stderr);return 2
    except SQLAlchemyError:
        print(json.dumps({'error':'DATABASE_OPERATION_FAILED','ledger_changed':False}),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
