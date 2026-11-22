"""Extract a reviewable cutout in the original pixel coordinate system."""
import re
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


def _perimeter(image):
    width, height = image.size
    pixels = image.load()
    return ([pixels[x, 0] for x in range(width)] +
            [pixels[x, height - 1] for x in range(width)] +
            [pixels[0, y] for y in range(1, height - 1)] +
            [pixels[width - 1, y] for y in range(1, height - 1)])


def _fill_subjects(edges):
    """Flood the exterior by horizontal runs. Even a large flat background
    adds one run per row to the work list instead of a Python object per pixel.
    """
    padded = ImageOps.expand(edges, border=1, fill=0)
    width, height = padded.size
    pixels = padded.tobytes()
    rows = [bytearray(pixels[start:start+width]) for start in range(0, len(pixels), width)]
    runs = re.compile(b'\x00+')
    pending = [(0, 0)]
    while pending:
        y, x = pending.pop()
        row = rows[y]
        if row[x] != 0:
            continue
        left = row.rfind(255, 0, x) + 1
        right = row.find(255, x)
        if right < 0:
            right = width
        row[left:right] = bytes([128]) * (right - left)
        for neighbor in (y-1, y+1):
            if 0 <= neighbor < height:
                pending.extend((neighbor, match.start())
                               for match in runs.finditer(rows[neighbor], left, right))
    filled = Image.frombytes('L', padded.size, b''.join(rows))
    return filled.crop((1, 1, width-1, height-1)).point(lambda value: 0 if value == 128 else 255)


def _segment_subject(image):
    """Infer a soft foreground mask without regenerating any product pixels."""
    import numpy as np
    import onnxruntime as ort
    from pathlib import Path

    model = Path(__file__).with_name('models') / 'u2netp.onnx'
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.enable_cpu_mem_arena = False
    options.enable_mem_pattern = False
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    net = ort.InferenceSession(str(model), options, providers=['CPUExecutionProvider'])
    pixels = np.asarray(image.convert('RGB').resize((320, 320), Image.Resampling.BILINEAR), dtype=np.float32)
    pixels /= max(float(pixels.max()), 1.)
    pixels -= np.array([.485, .456, .406], np.float32)
    pixels /= np.array([.229, .224, .225], np.float32)
    scores = net.run([net.get_outputs()[0].name], {net.get_inputs()[0].name:pixels.transpose(2, 0, 1)[None]})[0].squeeze()
    if not np.isfinite(scores).all() or scores.max() < .65:
        return None
    coverage = (scores > .5).mean()
    if not .005 <= coverage <= .94:
        return None
    alpha = np.clip((scores-.12)/.76, 0, 1)
    return Image.fromarray(np.uint8(alpha*255)).resize(image.size, Image.Resampling.LANCZOS)


def extract_matte(image: Image.Image) -> Image.Image | None:
    """Use embedded transparency or a low-variation backdrop, else return None.

    The caller applies EXIF orientation after merging the source and mask.
    Processing for opaque photos is bounded regardless of original image size.
    The returned mask always has the exact dimensions of the input.
    """
    if image.mode in ('RGBA', 'LA', 'PA') or 'transparency' in image.info:
        alpha = image.convert('RGBA').getchannel('A')
        low, high = alpha.getextrema()
        if high < 16:
            return None
        if low < 16 and high >= 128:
            # Stray nearly transparent pixels would otherwise expand the cutout
            # to the entire canvas. Preserve antialiasing and translucent detail.
            return alpha.point(lambda value: 0 if value < 8 else value)

    if min(image.size) < 16:
        return None
    if image.convert('RGB').getextrema() == ((0, 0), (0, 0), (0, 0)):
        return None
    predicted = _segment_subject(image)
    if predicted is not None:
        return predicted
    scale = min(1, 512 / max(image.size))
    analysis_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    if min(analysis_size) < 8:
        return None
    photo = image.resize(analysis_size, Image.Resampling.BOX).convert('RGB')
    photo = photo.filter(ImageFilter.GaussianBlur(0.7))
    width, height = photo.size
    patch = max(2, min(width, height) // 24)
    corners = [(0, 0), (width - patch, 0), (0, height - patch),
               (width - patch, height - patch)]
    backdrop = Image.new('RGB', (2, 2))
    backdrop.putdata([tuple(ImageStat.Stat(photo.crop((x, y, x + patch, y + patch))).median)
                      for x, y in corners])
    # A strongly varying backdrop makes the four-corner colour estimate unreliable.
    if any(high - low > 36 for low, high in backdrop.getextrema()):
        return None
    # The four samples are pixel centers. Bilinear interpolation models a
    # gently shaded table or studio sweep without cutting highlights from it.
    backdrop = backdrop.transform(photo.size, Image.Transform.EXTENT, (.5, .5, 1.5, 1.5),
                                  Image.Resampling.BILINEAR)
    red, green, blue = ImageChops.difference(photo, backdrop).split()
    distance = ImageChops.lighter(red, ImageChops.lighter(green, blue))
    perimeter = sorted(_perimeter(distance))
    noise = perimeter[int(.90 * len(perimeter))]
    if noise > 30 or perimeter[len(perimeter) // 2] > 16:
        return None
    threshold = max(7, noise + 6)
    outside = distance.point(lambda value: 0 if value <= threshold else 255)
    # Keep highlights inside closed object boundaries; only the background
    # connected to the outer border is discarded.
    matte = _fill_subjects(outside.filter(ImageFilter.MedianFilter(3)))
    count = matte.histogram()[255]
    if not .012 * width * height <= count <= .90 * width * height:
        return None
    strong = sum(distance.histogram()[threshold + 10:])
    if strong < count * .16 or sum(_perimeter(matte)) > 255 * len(perimeter) * .15:
        return None
    return matte.resize(image.size, Image.Resampling.LANCZOS)
