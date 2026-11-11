import unittest,tempfile,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from app.parsing import parse_isolated
class OfflineScanTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='win32','Installed Windows OCR engine')
    def test_scan_keeps_page_regions_and_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scanned.pdf'
            blank=Image.new('RGB',(1200,600),'white')
            page=blank.copy();draw=ImageDraw.Draw(page)
            draw.text((80,80),'测试商品',font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',64),fill='black')
            draw.text((80,220),'12345',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',72),fill='black')
            blank.save(path,'PDF',save_all=True,append_images=[page],resolution=150)
            result=parse_isolated(path,path.name)
            self.assertEqual(result[0]['page'],1)
            self.assertEqual(result[0]['status'],'unreadable')
            second=result[1]
            self.assertEqual(second['page'],2)
            self.assertEqual(second['status'],'ocr_candidate')
            self.assertIn('12345',''.join(second['text'].split()))
            self.assertIsNone(second['confidence'])
            self.assertTrue(second['requires_review'])
            self.assertTrue(second['lines'][0]['words'][0]['region']['width']>0)
