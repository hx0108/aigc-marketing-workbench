import unittest,tempfile,hashlib
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from app.db import Base,Record
from app import sources
from app.source_selection import select_sources
class SourceSelectionTests(unittest.TestCase):
    def test_explicit_mask_selection_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            Image.new('RGB',(20,20),'red').save(root/'product.png')
            Image.new('RGB',(20,20),'blue').save(root/'new.png')
            mask=Image.new('L',(20,20),0);ImageDraw.Draw(mask).rectangle((5,5,15,15),fill=255);mask.save(root/'mask.png')
            engine=create_engine('sqlite://');Base.metadata.create_all(engine)
            with sessionmaker(engine,expire_on_commit=False)() as session,patch.object(sources,'ROOT',root):
                session.add(Record(id='sku',workspace='w',kind='sku',data={}))
                session.add(Record(id='other-product',workspace='w',kind='source',data={'sku_id':'other-sku','role':'product'}))
                for key in ('product.png','new.png','mask.png'):
                    session.add(Record(id=key,workspace='w',kind='source',data={'sku_id':'sku','type':'image','rights_confirmed':True,'object_key':key,'sha256':hashlib.sha256((root/key).read_bytes()).hexdigest()}))
                session.commit()
                with self.assertRaises(HTTPException):select_sources(session,'w','sku',1,'product.png','mask.png',False)
                first=select_sources(session,'w','sku',1,'product.png','mask.png',True)
                select_sources(session,'w','sku',2,'new.png','mask.png',True)
                self.assertEqual(session.get(Record,first['id']).data['sources']['product']['source_id'],'product.png')
                self.assertIsNone(session.get(Record,'product.png').data['role'])
                self.assertEqual(session.get(Record,'other-product').data['role'],'product')
