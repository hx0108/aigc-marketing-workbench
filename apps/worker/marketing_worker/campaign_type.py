"""Set a single display line for the track and morning editorial campaigns."""
from functools import lru_cache
from pathlib import Path
import unicodedata

from PIL import Image, ImageDraw, ImageFont


FONT_DIR = Path(__file__).with_name("campaign_assets") / "fonts"
FACES = {
    "douyin": "SourceHanSansCN-Heavy.otf",
    "xiaohongshu": "SourceHanSerifCN-SemiBold.otf",
}


@lru_cache(maxsize=16)
def _face(path, size):
    return ImageFont.truetype(str(path), size)


@lru_cache(maxsize=8192)
def _covered(path, character):
    face = _face(path, 18)
    mask = face.getmask(character)
    missing = face.getmask("\U0010ffff")
    return mask.size != missing.size or bytes(mask) != bytes(missing)


def headline(text, platform, size, color, *, fallback=None):
    """Return a tightly trimmed RGBA display line, ready for alpha compositing."""
    if platform not in FACES or size < 1 or "\n" in text:
        raise ValueError("invalid_campaign_headline")
    primary = FONT_DIR / FACES[platform]
    strong = platform == "douyin"
    tracking = size * (-.042 if strong else .036)
    groups = []
    for ch in text:
        if groups and unicodedata.combining(ch):
            groups[-1] += ch
        else:
            groups.append(ch)
    x = float(size)
    glyphs = []
    previous, previous_face = "", None
    for group in groups:
        path = fallback if fallback and not _covered(primary, group[0]) else primary
        face = _face(path, size)
        if face is previous_face and previous.isascii() and group.isascii():
            # Keep the foundry's pair kerning when tracking Latin titles.
            x += face.getlength(previous + group) - face.getlength(previous) - face.getlength(group)
        glyphs.append((round(x), group, face))
        x += face.getlength(group) + tracking
        previous, previous_face = group, face
    layer = Image.new("RGBA", (max(1, round(x + size)), 3 * size))
    draw = ImageDraw.Draw(layer)
    for left, group, face in glyphs:
        draw.text((left, size * 2), group, font=face, fill=color, anchor="ls")
    box = layer.getchannel("A").getbbox()
    if box is None:
        return Image.new("RGBA", (1, 1))
    layer = layer.crop(box)
    if strong:
        # A compact sprinter's stance with the upper edge leading the baseline.
        shear = .17
        extension = int(layer.height * shear) + 2
        layer = layer.transform((layer.width + extension, layer.height),
                                Image.Transform.AFFINE, (1, shear, -extension + 1, 0, 1, 0),
                                Image.Resampling.BICUBIC)
        layer = layer.resize((max(1, round(layer.width * .89)), layer.height), Image.Resampling.LANCZOS)
        layer = layer.crop(layer.getchannel("A").getbbox())
    return layer
