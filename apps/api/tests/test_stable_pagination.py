import unittest
from datetime import datetime,timezone
from sqlalchemy import create_engine,select,update
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from app.db import Base,Record
from app.pagination import page,timestamp
class StablePaginationTests(unittest.TestCase):
    def test_created_cursor_handles_ties_unknown_time_and_concurrent_insert(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine,expire_on_commit=False)() as session:
            for identifier,year in [('a',2021),('b',2021),('c',2020),('legacy',2019)]:
                session.add(Record(id=identifier,workspace='w',kind='work',created_at=datetime(year,1,1,tzinfo=timezone.utc),data={}))
            session.commit();session.execute(update(Record).where(Record.id=='legacy').values(created_at=None));session.commit()
            statement=select(Record).where(Record.workspace=='w',Record.kind=='work')
            rows,cursor=page(session,statement,Record,'w','works','created_desc',2,0,None)
            self.assertEqual([r.id for r in rows],['a','b'])
            session.add(Record(id='new',workspace='w',kind='work',created_at=datetime(2022,1,1,tzinfo=timezone.utc),data={}))
            session.delete(session.get(Record,'a'));session.commit()
            rows,next_cursor=page(session,statement,Record,'w','works','created_desc',1,0,cursor)
            self.assertEqual([r.id for r in rows],['c'])
            rows,final=page(session,statement,Record,'w','works','created_desc',2,0,next_cursor)
            self.assertEqual([r.id for r in rows],['legacy']);self.assertIsNone(timestamp(rows[0].created_at));self.assertIsNone(final)
            with self.assertRaises(HTTPException):page(session,statement,Record,'w','works','id_asc',2,0,cursor)
            with self.assertRaises(HTTPException):page(session,statement,Record,'other','works','created_desc',2,0,cursor)
    def test_legacy_default_id_order_is_preserved(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine)() as session:
            session.add_all([Record(id='z',workspace='w',kind='work',data={}),Record(id='a',workspace='w',kind='work',data={})]);session.commit()
            rows,cursor=page(session,select(Record),Record,'w','works','id_asc',1,0,None)
            self.assertEqual(rows[0].id,'a')
            rows,_=page(session,select(Record),Record,'w','works','id_asc',1,0,cursor)
            self.assertEqual(rows[0].id,'z')
