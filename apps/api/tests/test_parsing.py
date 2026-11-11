import unittest,tempfile
from pathlib import Path
from app.parsing import parse_document
class ParseTests(unittest.TestCase):
    def test_retains_actual_paragraph_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'facts.txt';path.write_text('first\n\nthird',encoding='utf-8')
            result=parse_document(path,path.name)
            self.assertEqual([row['paragraph'] for row in result],[1,3])
    def test_image_requires_ocr(self):
        with self.assertRaisesRegex(ValueError,'OCR_REQUIRED'):parse_document('not-read.png','not-read.png')
    def test_isolated_parser_retains_chinese(self):
        from app.parsing import parse_isolated
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'facts.txt';path.write_text('耳机参数',encoding='utf-8')
            self.assertEqual(parse_isolated(path,path.name)[0]['text'],'耳机参数')
