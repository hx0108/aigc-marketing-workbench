import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from marketing_worker.media import compose_timeline

class RenderResourceTests(unittest.TestCase):
    def test_timeline_bounds_decoders_filter_and_encoder_without_reducing_format(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('marketing_worker.media.probe',return_value={'format':{'duration':'2'}}),patch('marketing_worker.media.timeline_font_options',return_value=('/fonts/cjk.ttf','/fonts','Test CJK')),patch('marketing_worker.media.subprocess.run') as run:
                compose_timeline([root/'clip.mp4'],root/'audio.wav',root/'out.mp4',2,[{'duration':2,'narration':'test'}])
            command=run.call_args.args[0]
            self.assertEqual(command[command.index('-filter_complex_threads')+1],'1')
            self.assertEqual(command[command.index('-filter_threads')+1],'1')
            self.assertEqual(command.count('-threads'),3)
            self.assertTrue(all(command[index+1]=='2' for index,arg in enumerate(command) if arg=='-threads'))
            self.assertIn('scale=1080:1920',command[command.index('-filter_complex')+1])
            self.assertIn('fps=25',command[command.index('-filter_complex')+1])
            self.assertIn("drawtext=fontfile='/fonts/cjk.ttf'",command[command.index('-filter_complex')+1])
            self.assertIn("fontsdir='/fonts':force_style='FontName=Test CJK",command[command.index('-filter_complex')+1])
            self.assertEqual(command[command.index('-c:v')+1],'libx264')
