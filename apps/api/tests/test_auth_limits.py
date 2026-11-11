import unittest,tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.auth_limits import consume,LoginRateLimit
class PersistentLoginLimitTests(unittest.TestCase):
    def test_limit_survives_new_session_factory_and_resets_after_window(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        factory=sessionmaker(engine)
        self.assertEqual([consume('ip','client',now=100,sessions=factory)[0] for _ in range(5)],[True]*5)
        self.assertFalse(consume('ip','client',now=101,sessions=sessionmaker(engine))[0])
        self.assertTrue(consume('ip','client',now=160,sessions=factory)[0])
        with factory() as session:
            self.assertNotIn('client',session.query(LoginRateLimit).one().key)
    def test_concurrent_attempts_have_exactly_five_winners(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=create_engine('sqlite:///'+str(Path(directory)/'limits.db'))
            try:
                Base.metadata.create_all(engine);factory=sessionmaker(engine)
                with ThreadPoolExecutor(max_workers=8) as pool:
                    outcomes=list(pool.map(lambda _:consume('account','person',now=100,sessions=factory)[0],range(16)))
                self.assertEqual(sum(outcomes),5)
            finally:engine.dispose()
