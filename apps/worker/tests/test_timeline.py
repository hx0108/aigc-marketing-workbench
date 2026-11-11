import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import httpx
from PIL import Image
from marketing_worker.assets import download
from marketing_worker.media import compose_timeline, probe, MediaError


class IntegrationTests(unittest.TestCase):
    def test_download_pins_dns_and_verifies_png(self):
        raw=io.BytesIO(); Image.new('RGB',(8,8),'red').save(raw,format='PNG')
        seen=[]
        def handler(request):
            seen.append(request)
            return httpx.Response(200,content=raw.getvalue())
        resolver=lambda *a,**kw:[(2,1,6,'',('8.8.8.8',443))]
        with tempfile.TemporaryDirectory() as directory:
            result=download('https://assets.example/image',Path(directory)/'image.png',{'assets.example'},'image',httpx.Client(transport=httpx.MockTransport(handler)),resolver)
            self.assertGreater(result['size'],0)
            self.assertEqual(seen[0].url.host,'8.8.8.8')
            self.assertEqual(seen[0].headers['host'],'assets.example')
            with self.assertRaises(ValueError):
                download('https://assets.example/image',Path(directory)/'bad.png',{'assets.example'},'image',resolver=lambda *a,**kw:[(2,1,6,'',('127.0.0.1',443))])

    def test_real_multi_shot_video_audio_subtitle(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for index,color in enumerate(['red','blue']):
                subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c={color}:s=160x240:r=25:d=1','-c:v','libx264',str(root/f'{index}.mp4')],check=True,capture_output=True)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=2',str(root/'voice.wav')],check=True,capture_output=True)
            linux_font=Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc') if sys.platform!='win32' else None
            captions=['商品外观','查看细节'] if linux_font else ['first','second']
            shots=[{'duration':1,'narration':caption} for caption in captions]
            metadata=compose_timeline([root/'0.mp4',root/'1.mp4'],root/'voice.wav',root/'out.mp4',2,shots,font_path=linux_font)
            self.assertAlmostEqual(float(metadata['format']['duration']),2,delta=.15)
            self.assertEqual({s['codec_type'] for s in metadata['streams']},{'video','audio','subtitle'})
            subtitles=subprocess.run(['ffmpeg','-v','error','-i',str(root/'out.mp4'),'-map','0:s:0','-f','srt','-'],
                check=True,capture_output=True).stdout.decode('utf-8')
            self.assertTrue(all(caption in subtitles for caption in captions))
            with self.assertRaises(MediaError):
                compose_timeline([root/'0.mp4',root/'1.mp4'],root/'voice.wav',root/'out.mp4',2,shots)
