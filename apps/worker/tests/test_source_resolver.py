import hashlib
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PIL import Image
from app.db import Base,Record
from marketing_worker.source_resolver import resolve_sources


class ResolverTests(unittest.TestCase):
    def test_sources_edit_scope_tampering_and_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);engine=create_engine('sqlite:///'+str(root/'db.sqlite'));Base.metadata.create_all(engine);sessions=sessionmaker(engine)
            request={'sku_id':'sku','source_ids':['product','mask']}
            with sessions.begin() as session:
                for role in ['product','mask']:
                    path=root/(role+'.png');Image.new('RGB',(32,32),'white').save(path)
                    session.add(Record(id=role,workspace='ws',kind='source',data={'sku_id':'sku','rights_confirmed':True,'role':role,'object_key':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}))
                session.add(Record(id='creation',workspace='ws',kind='creation_request',data=request))
                session.add(Record(id='work',workspace='ws',kind='work',data={'creation_request_id':'creation'}))
            job={'workspace':'ws','payload':{'request':request}}
            first=resolve_sources(sessions,job,root,{})
            self.assertEqual(set(first),{'product','mask','white_background'})
            self.assertEqual(resolve_sources(sessions,{'workspace':'ws','payload':{'work_id':'work'}},root,{}),first)
            white=root/'white-background-1080x1440.png';original=white.read_bytes();white.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'white_background_integrity'):resolve_sources(sessions,job,root,{})
            white.write_bytes(original)
            with sessions.begin() as session:
                row=session.get(Record,'mask');row.data={**row.data,'sku_id':'other'}
            with self.assertRaisesRegex(ValueError,'source_scope'):resolve_sources(sessions,job,root,{})
            with sessions.begin() as session:
                row=session.get(Record,'mask');row.data={**row.data,'sku_id':'sku','rights_confirmed':False}
            with self.assertRaisesRegex(ValueError,'source_scope'):resolve_sources(sessions,job,root,{})
            with sessions.begin() as session:
                row=session.get(Record,'mask');row.data={**row.data,'rights_confirmed':True}
            (root/'product.png').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'source_hash'):resolve_sources(sessions,job,root,{})
            with self.assertRaisesRegex(ValueError,'synthetic_override'):resolve_sources(sessions,job,root,{'sku':first})
            engine.dispose()
