import unittest
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.execution import Budget
from app.ledger import prepare, settle

class LedgerTests(unittest.TestCase):
    def test_subprecision_cost_cannot_round_to_zero(self):
        with self.sessions.begin() as s:
            with self.assertRaisesRegex(ValueError,'INVALID_MONEY_PRECISION'):
                prepare(s,'b','c','hash','0.000000001')
            self.assertEqual(s.get(Budget,'b').reserved,Decimal('0'))

    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(self.engine)
        with self.sessions.begin() as s:
            s.add(Budget(id='b',workspace='w',cap=Decimal('10'),reserved=0,settled=0))
    def test_replay_and_partial_settlement_preserve_remaining(self):
        with self.sessions.begin() as s:
            prepare(s,'b','c','hash','8')
            prepare(s,'b','c','hash','8')
            settle(s,'b','c','e','3',False,'provider-bill-1')
            settle(s,'b','c','e','3',False,'provider-bill-1')
            b=s.get(Budget,'b')
            self.assertEqual((b.reserved,b.settled),(Decimal('5'),Decimal('3')))
            with self.assertRaisesRegex(ValueError,'BUDGET_INSUFFICIENT'):
                prepare(s,'b','other','hash','3')
            settle(s,'b','c','final','0',True,'final-no-further-charge')
            self.assertEqual((b.reserved,b.settled),(Decimal('0'),Decimal('3')))
    def test_conflicting_replay_rejected(self):
        with self.sessions.begin() as s:
            prepare(s,'b','c','hash','8')
            with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
                prepare(s,'b','c','changed','8')
            with self.assertRaisesRegex(ValueError,'IDEMPOTENCY_CONFLICT'):
                prepare(s,'b','c','hash','9')
    def test_provider_overcharge_is_recorded_not_hidden(self):
        with self.sessions.begin() as s:
            prepare(s,'b','c','hash','8')
            settle(s,'b','c','e','11',True,'actual-bill')
            b=s.get(Budget,'b')
            self.assertEqual(b.settled,Decimal('11'))
            with self.assertRaisesRegex(ValueError,'BUDGET_INSUFFICIENT'):
                prepare(s,'b','next','hash','1')
    def test_missing_evidence_keeps_reservation(self):
        with self.sessions.begin() as s:
            prepare(s,'b','c','hash','8')
            with self.assertRaisesRegex(ValueError,'EVIDENCE'):
                settle(s,'b','c','e','0',True,'')
            self.assertEqual(s.get(Budget,'b').reserved,Decimal('8'))

if __name__=='__main__':unittest.main()
