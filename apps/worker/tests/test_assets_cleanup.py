import tempfile
import unittest
from pathlib import Path

import httpx
from PIL import UnidentifiedImageError

from marketing_worker.assets import download


class DownloadCleanupTests(unittest.TestCase):
    def test_empty_failed_download_does_not_block_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'image.png'
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b''))) as client:
                with self.assertRaises(UnidentifiedImageError):
                    download('https://assets.example/image', target, {'assets.example'}, 'image', client,
                             lambda *args, **kwargs: [(2, 1, 6, '', ('8.8.8.8', 443))])
            self.assertFalse(target.exists())

    def test_existing_immutable_asset_survives_download_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'image.png'
            target.write_bytes(b'existing-asset')
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'new'))) as client:
                with self.assertRaises(FileExistsError):
                    download('https://assets.example/image', target, {'assets.example'}, 'image', client,
                             lambda *args, **kwargs: [(2, 1, 6, '', ('8.8.8.8', 443))])
            self.assertEqual(target.read_bytes(), b'existing-asset')
