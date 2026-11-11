import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from app.db import Base,Record
from app.uploads import reserve_upload,release_upload
class UploadTests(unittest.TestCase):
    def test_deleted_or_foreign_sku_cannot_reserve(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine)() as session:
            session.add(Record(id='deleted',workspace='w',kind='sku',data={'deleting':True}))
            session.add(Record(id='foreign',workspace='other',kind='sku',data={}))
            session.commit()
            for sku_id in ['deleted','foreign','missing']:
                with self.subTest(sku=sku_id):
                    with self.assertRaises(HTTPException) as error:
                        reserve_upload(session,'w',sku_id,'a.png',100)
                    self.assertEqual(error.exception.status_code,404)

    def test_inflight_slot_counts_and_release_restores_capacity(self):
        engine=create_engine('sqlite://');Base.metadata.create_all(engine)
        with sessionmaker(engine,expire_on_commit=False)() as session:
            session.add(Record(id='sku',workspace='w',kind='sku',data={}))
            for i in range(19):session.add(Record(workspace='w',kind='source',data={'sku_id':'sku','size':1,'type':'image'}))
            session.commit()
            lease=reserve_upload(session,'w','sku','a.png',100)
            with self.assertRaises(HTTPException):reserve_upload(session,'w','sku','b.png',100)
            session.rollback();release_upload(session,lease)
            self.assertIsNotNone(reserve_upload(session,'w','sku','b.png',100))
