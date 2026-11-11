"""Synthetic bill fixtures only: no supplier or production ledger is contacted."""
import copy,hashlib,json,tempfile,unittest
from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
from pydantic import ValidationError
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from app.db import Base,Record
from app.execution import Budget,Task,ExternalCall,reserve
from app.ledger import prepare,CostEvent,CallReservation
from app.billing import BillManifest,BillingReceipt,reconcile_bill

class BillImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.evidence=self.root/'synthetic-bill.txt';self.evidence.write_bytes(b'SYNTHETIC TEST EVIDENCE - NOT A REAL SUPPLIER BILL\n')
        self.archive=self.root/'private-evidence'
        self.hash=hashlib.sha256(b'fixed synthetic request').hexdigest()
        self.engine=create_engine('sqlite://');Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(self.engine,expire_on_commit=False)
        with self.sessions.begin() as session:
            session.add_all([Budget(id='budget',workspace='workspace',cap=10,reserved=0,settled=0),Budget(id='other-budget',workspace='workspace',cap=10,reserved=0,settled=0),Task(id='task',workspace='workspace',state='external_unknown',phase='creation_run',payload={})]);session.flush()
            prepare(session,'budget','call',self.hash,'8')
            session.add(ExternalCall(id='call',intent_key='call',task_id='task',request_hash=self.hash,state='external_unknown'))
        self.manifest={'schema_version':1,'provider':'synthetic-provider','provider_account':'test-account','bill_id':'test-bill','workspace':'workspace','currency':'CNY','evidence_kind':'supplier_bill','amount_semantics':'incremental','evidence_sha256':hashlib.sha256(self.evidence.read_bytes()).hexdigest(),'lines':[{'line_id':'line-1','budget_id':'budget','call_id':'call','request_hash':self.hash,'amount':'3','final':False}]}
    def tearDown(self):
        self.engine.dispose();self.temp.cleanup()
    def apply(self,manifest=None,apply=True):
        with self.sessions.begin() as session:
            return reconcile_bill(session,manifest or self.manifest,self.evidence,'test-administrator',apply=apply,evidence_root=self.archive)
    def assert_budget(self,reserved,settled):
        with self.sessions() as session:
            budget=session.get(Budget,'budget')
            self.assertEqual((budget.reserved,budget.settled),(Decimal(reserved),Decimal(settled)))
    def test_dry_run_does_not_archive_or_change_unknown_reservation(self):
        result=self.apply(apply=False)
        self.assertEqual(result['new_charge_total'],'3.00000000');self.assertFalse(result['ledger_changed'])
        self.assertFalse(self.archive.exists());self.assert_budget('8','0')
        with self.sessions() as session:self.assertEqual(session.scalar(select(func.count()).select_from(BillingReceipt)),0)
    def test_partial_duplicate_and_final_bill_preserve_execution_state(self):
        self.assertEqual(self.apply()['imported_events'],1);self.assert_budget('5','3')
        from app.task_views import task_view
        with self.sessions() as session:self.assertTrue(task_view(session,session.get(Task,'task'))['unknown_cost_flag'])
        repeated=self.apply();self.assertEqual(repeated['duplicate_events'],1);self.assertFalse(repeated['ledger_changed']);self.assert_budget('5','3')
        final=copy.deepcopy(self.manifest);final['lines'][0].update(line_id='line-final',amount='0',final=True)
        self.apply(final);self.assert_budget('0','3')
        with self.sessions() as session:
            self.assertTrue(session.get(CallReservation,'call').finalized)
            self.assertEqual(session.get(ExternalCall,'call').state,'external_unknown')
            self.assertEqual(session.get(Task,'task').state,'external_unknown')
            self.assertFalse(task_view(session,session.get(Task,'task'))['unknown_cost_flag'])
            receipts=session.scalars(select(BillingReceipt)).all();self.assertEqual(len(receipts),2)
            self.assertEqual(receipts[0].reviewed_by,'test-administrator')
            archived=self.archive/receipts[0].evidence_key
            self.assertEqual(hashlib.sha256(archived.read_bytes()).hexdigest(),self.manifest['evidence_sha256'])
    def test_invalid_amount_precision_and_currency_are_rejected(self):
        for amount in ('-1','NaN','Infinity','1e999','0.000000001',1.25,True):
            invalid=copy.deepcopy(self.manifest);invalid['lines'][0]['amount']=amount
            with self.subTest(amount=amount),self.assertRaises(ValidationError):self.apply(invalid)
        invalid=copy.deepcopy(self.manifest);invalid['currency']='USD'
        with self.assertRaises(ValidationError):self.apply(invalid)
        invalid=copy.deepcopy(self.manifest);invalid['evidence_kind']='usage_estimate'
        with self.assertRaises(ValidationError):self.apply(invalid)
        self.assert_budget('8','0')
    def test_wrong_budget_or_request_hash_does_not_settle(self):
        for key,value,error in [('budget_id','other-budget','CALL_BUDGET_MISMATCH'),('request_hash','0'*64,'CALL_REQUEST_HASH_MISMATCH')]:
            invalid=copy.deepcopy(self.manifest);invalid['lines'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,error):self.apply(invalid)
        invalid=copy.deepcopy(self.manifest);invalid['workspace']='another-workspace'
        with self.assertRaisesRegex(ValueError,'BUDGET_SCOPE_MISMATCH'):self.apply(invalid)
        self.assert_budget('8','0');self.assertFalse(self.archive.exists())
    def test_same_bill_line_cannot_be_changed_or_reassigned(self):
        self.apply()
        changed=copy.deepcopy(self.manifest);changed['lines'][0]['amount']='4'
        with self.assertRaisesRegex(ValueError,'BILL_LINE_CONFLICT'):self.apply(changed)
        self.assert_budget('5','3')
    def test_missing_or_changed_evidence_keeps_reservation(self):
        self.evidence.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'EVIDENCE_HASH_MISMATCH'):self.apply()
        self.evidence.unlink()
        with self.assertRaisesRegex(ValueError,'EVIDENCE_FILE_REQUIRED'):self.apply()
        self.assert_budget('8','0')
    def test_batch_is_atomic_when_later_call_has_wrong_budget(self):
        invalid=copy.deepcopy(self.manifest)
        invalid['lines'].append({**invalid['lines'][0],'line_id':'line-2','budget_id':'other-budget'})
        with self.sessions.begin() as session:
            with self.assertRaisesRegex(ValueError,'CALL_BUDGET_MISMATCH'):reconcile_bill(session,invalid,self.evidence,'admin',apply=True,evidence_root=self.archive)
            self.assertEqual(session.scalar(select(func.count()).select_from(CostEvent)),0)
        self.assert_budget('8','0')
    def test_overcharge_is_recorded_and_blocks_new_budget_reservations(self):
        actual=copy.deepcopy(self.manifest);actual['lines'][0].update(amount='9',final=True)
        result=self.apply(actual);self.assertEqual(result['budget_holds'],['budget']);self.assert_budget('0','9')
        with self.sessions.begin() as session:
            self.assertTrue(session.get(Record,'budget-hold:budget').data['active'])
            with self.assertRaisesRegex(ValueError,'BUDGET_HELD_FOR_REVIEW'):reserve(session,'budget',Decimal('0.5'))
    def test_cli_defaults_to_dry_run_and_requires_explicit_apply(self):
        from app import reconcile
        path=self.root/'manifest.json';path.write_text(json.dumps(self.manifest),encoding='utf-8')
        arguments=['import','--manifest',str(path),'--evidence',str(self.evidence),'--reviewed-by','test-administrator']
        with patch.object(reconcile,'engine',self.engine),patch.object(reconcile,'Session',self.sessions),patch.dict('os.environ',{'DATABASE_URL':'sqlite://','AIGC_BILLING_EVIDENCE_ROOT':str(self.archive)}):
            output=StringIO()
            with redirect_stdout(output):self.assertEqual(reconcile.main(arguments),0)
            self.assertEqual(json.loads(output.getvalue())['mode'],'dry_run');self.assert_budget('8','0')
            with redirect_stdout(StringIO()):self.assertEqual(reconcile.main(arguments+['--apply']),0)
            self.assert_budget('5','3')
    def test_eight_decimal_bill_amounts_are_preserved_exactly(self):
        precise=copy.deepcopy(self.manifest)
        precise['lines'][0]['amount']='0.001306'
        precise['lines'].append({**precise['lines'][0],'line_id':'minimum-unit','amount':'0.00000004'})
        self.apply(precise)
        self.assert_budget('7.99869396','0.00130604')
        with self.sessions() as session:
            amounts=set(session.scalars(select(BillingReceipt.amount)).all())
            self.assertEqual(amounts,{Decimal('0.00130600'),Decimal('0.00000004')})

