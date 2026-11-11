import unittest,tempfile,hashlib
from pathlib import Path
from types import SimpleNamespace
from app import exporting
class ExportTests(unittest.TestCase):
    def test_download_refuses_modified_package(self):
        with tempfile.TemporaryDirectory() as directory:
            old=exporting.ROOT;exporting.ROOT=Path(directory)
            try:
                path=exporting.ROOT/'package'
                path.write_bytes(b'original')
                data={'object_key':'package','sha256':hashlib.sha256(b'original').hexdigest()}
                self.assertEqual(exporting.verified_package_path(data),path)
                path.write_bytes(b'replaced')
                with self.assertRaisesRegex(ValueError,'PACKAGE_HASH_MISMATCH'):
                    exporting.verified_package_path(data)
            finally:exporting.ROOT=old

    def test_sample_requires_embedded_mark(self):
        work=SimpleNamespace(id='work',revision=1,data={'platforms':['douyin']})
        asset=SimpleNamespace(id='a',revision=1,data={'media_kind':'video','slot':'douyin','sample_marked':False})
        with self.assertRaisesRegex(ValueError,'SAMPLE_MARK_REQUIRED'):exporting.build_sample(work,[asset],'video_only')
    def test_hash_checked_before_packaging(self):
        with tempfile.TemporaryDirectory() as directory:
            old=exporting.ROOT;exporting.ROOT=Path(directory)
            try:
                (exporting.ROOT/'asset').write_bytes(b'media')
                asset=SimpleNamespace(id='a',revision=1,data={'media_kind':'video','slot':'douyin','sample_marked':True,'object_key':'asset','sha256':'wrong'})
                with self.assertRaisesRegex(ValueError,'MEDIA_HASH_MISMATCH'):exporting.build_sample(SimpleNamespace(id='w',revision=1,data={'platforms':['douyin']}),[asset],'video_only')
            finally:exporting.ROOT=old

    def test_full_suite_rejects_missing_platform_slots(self):
        asset=SimpleNamespace(id='a',revision=1,data={'media_kind':'video','slot':'douyin','sample_marked':True})
        work=SimpleNamespace(id='w',revision=1,data={'platforms':['douyin','xiaohongshu']})
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_SELECTION.*marketing_poster'):
            exporting.build_sample(work,[asset],'full_suite')

    def test_duplicate_slot_is_rejected(self):
        work=SimpleNamespace(id='w',revision=1,data={'platforms':['douyin']})
        assets=[SimpleNamespace(id=str(i),data={'media_kind':'video','slot':'douyin'}) for i in range(2)]
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_ASSET_SELECTION'):
            exporting.build_sample(work,assets,'video_only')

    def test_unselected_platform_is_rejected(self):
        work=SimpleNamespace(id='w',revision=1,data={'platforms':['douyin']})
        assets=[SimpleNamespace(id='a',data={'media_kind':'video','slot':'xiaohongshu'})]
        with self.assertRaisesRegex(ValueError,'UNSELECTED_PLATFORM_ASSET'):
            exporting.build_sample(work,assets,'video_only')
