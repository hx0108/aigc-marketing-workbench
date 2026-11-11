import unittest
from io import BytesIO
from PIL import Image
from fastapi import HTTPException
from app.sources import inspect
class SourceTests(unittest.TestCase):
    def test_valid_png(self):
        b=BytesIO();Image.new('RGB',(10,10)).save(b,format='PNG')
        self.assertEqual(inspect(b.getvalue(),'a.png'),'image')
    def test_disguised_image(self):
        with self.assertRaises(HTTPException):inspect(b'not-image','a.png')
    def test_invalid_utf8(self):
        with self.assertRaises(HTTPException):inspect(b'\xff','a.txt')
    def test_executable_rejected(self):
        with self.assertRaises(HTTPException):inspect(b'MZ','a.exe')
