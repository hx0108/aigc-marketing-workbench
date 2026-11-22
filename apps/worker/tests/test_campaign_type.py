from PIL import ImageChops, ImageFont
import pytest

from marketing_worker.campaign_type import FACES, FONT_DIR, headline


@pytest.mark.parametrize("platform,family,weight", [
    ("douyin", "Source Han Sans", "Heavy"),
    ("xiaohongshu", "Source Han Serif", "SemiBold"),
])
def test_display_face_renders_mixed_product_headline(platform, family, weight):
    face = ImageFont.truetype(str(FONT_DIR / FACES[platform]), 96)
    assert family in face.getname()[0]
    assert weight in " ".join(face.getname())
    rendered = headline("跑向晨光 · AIR 3", platform, 96, "#f7efdc")
    assert rendered.mode == "RGBA"
    assert rendered.getbbox() == (0, 0, *rendered.size)
    assert rendered.width > 5 * 96


def test_same_product_words_have_distinct_title_shapes():
    words = "戴上，开跑。"
    track = headline(words, "douyin", 128, "white").getchannel("A")
    morning = headline(words, "xiaohongshu", 128, "white").getchannel("A")
    assert track.width < morning.width
    delta = ImageChops.difference(track.resize(morning.size), morning)
    assert sum(delta.histogram()[128:]) > morning.width * morning.height * .12
