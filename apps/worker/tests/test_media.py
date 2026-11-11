import tempfile
import sys
import unittest
from pathlib import Path
from PIL import Image
from marketing_worker.media import compose_product, repair_patch, render_poster, MediaError
from marketing_worker.providers import UnconfiguredProvider, ProviderNotConfigured

POSTER_FONT = Path('C:/Windows/Fonts/msyh.ttc' if sys.platform=='win32' else '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name, color in [('product', 'red'), ('background', 'blue'), ('mask', 'white')]:
            Image.new('RGB', (64, 64), color).save(self.root / (name + '.png'))

    def tearDown(self):
        self.temp.cleanup()

    def test_original_pixels_and_immutable_output(self):
        paths = [self.root / (name + '.png') for name in ['product', 'mask', 'background', 'out']]
        compose_product(*paths)
        with Image.open(paths[-1]) as image:
            self.assertEqual(image.getpixel((20, 20)), (255, 0, 0))
        with self.assertRaises(FileExistsError):
            compose_product(*paths)

    def test_patch_restores_original(self):
        repair_patch(self.root/'background.png', self.root/'product.png', self.root/'mask.png', self.root/'repair.png')
        with Image.open(self.root/'repair.png') as image:
            self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))

    def test_poster_png_and_overflow(self):
        font = POSTER_FONT
        result = render_poster(self.root/'product.png', self.root/'poster.png', '商品', ['真实卖点'], font)
        self.assertEqual(result['width'], 1080)
        with self.assertRaises(MediaError):
            render_poster(self.root/'product.png', self.root/'overflow.png', '长文案'*1000, [], font)
        self.assertFalse((self.root/'overflow.png').exists())

    def test_unconfigured_never_succeeds(self):
        with self.assertRaises(ProviderNotConfigured):
            UnconfiguredProvider().submit({})

    def test_poster_layout_changes_real_pixels_and_rejects_unknown(self):
        font=POSTER_FONT
        first=render_poster(self.root/'product.png',self.root/'classic.png','标题',[],font)
        second=render_poster(self.root/'product.png',self.root/'top.png','标题',[],font,layout='product_top')
        self.assertNotEqual(first['sha256'],second['sha256'])
        with self.assertRaises(MediaError):
            render_poster(self.root/'product.png',self.root/'bad.png','标题',[],font,layout='arbitrary')

    def test_poster_keeps_product_and_sample_label_visible_on_wide_canvas(self):
        output = self.root / 'wide.png'
        render_poster(
            self.root / 'product.png', output, '商品', [],
            POSTER_FONT, width=1600, height=320,
        )
        with Image.open(output) as image:
            product_rows = [y for y in range(image.height) if image.getpixel((800, y)) == (255, 0, 0)]
            label_rows = [
                y for y in range(image.height)
                if any(color == (163, 59, 50) for _, color in image.crop((0, y, 300, y + 1)).getcolors(300))
            ]
            self.assertTrue(product_rows)
            self.assertTrue(label_rows)
            self.assertLess(max(product_rows), min(label_rows))

    def test_versioned_detail_poster_uses_existing_pixels_and_rejects_overflow(self):
        outputs=[]
        for order in ('hero_detail_close','context_detail_choice'):
            target=self.root/(order+'.png')
            result=render_poster(self.root/'product.png',target,'真实商品细节',['白色外观','圆润轮廓'],POSTER_FONT,creative_plan={'version':'creative-direction-v1','information_order':order})
            self.assertEqual(result['detail_source'],'same_image_crop')
            with Image.open(target) as image:self.assertEqual(image.getpixel((150 if order=='hero_detail_close' else 800,1000)),(255,0,0))
            outputs.append(result['sha256'])
        self.assertNotEqual(*outputs)
        with self.assertRaises(MediaError):
            render_poster(self.root/'product.png',self.root/'too-long.png','长'*10000,[],POSTER_FONT,creative_plan={'version':'creative-direction-v1','information_order':'hero_detail_close'})
        self.assertFalse((self.root/'too-long.png').exists())
