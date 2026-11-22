"""Photo-led advertising. The product always comes from the merchant's photographs."""
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .media import MediaError, probe


ASSETS = Path(__file__).with_name('campaign_assets')
PORTRAIT = (1080, 1440)
VIDEO = (1080, 1920)
FPS = 25
LANCZOS = Image.Resampling.LANCZOS
# Convert full-range photographs into standard limited-range HD video before encoding.
VIDEO_COLOR = 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=range=limited:colorspace=bt709'

# The two original bare-ear portrait plates are 1024 x 1536.
# Coordinates locate the concha, not the outer tip of an imaginary earbud.
PLATES = {
    'douyin': ('track.jpg', (581, 681), (59, 96), 'amber-set.jpg'),
    'xiaohongshu': ('terrace.jpg', (681, 512), (43, 72), 'blue-set.jpg'),
}


def _platform(value):
    if value not in PLATES:
        raise MediaError('unknown_campaign_platform')
    return PLATES[value]


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _publish(staged, output):
    """A retry can adopt an identical object, never a partial or conflicting one."""
    digest = _digest(staged)
    try:
        if os.name == 'nt':
            os.rename(staged, output)  # Windows rename is exclusive.
        else:
            os.link(staged, output)  # POSIX rename could overwrite another attempt.
    except FileExistsError:
        if _digest(output) != digest:
            raise MediaError('campaign_asset_conflict') from None
    return {'path': str(output), 'sha256': digest}


def _save(image, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        staged = Path(temp) / 'image.png'
        image.convert('RGB').save(staged, format='PNG', compress_level=4)
        return _publish(staged, output)


def _photo(path):
    with Image.open(path) as opened:
        if opened.width * opened.height > 40_000_000:
            raise MediaError('campaign_photo_too_large')
        opened.draft('RGB', (1920, 1920))
        opened.thumbnail((2304, 2304), LANCZOS)
        upright = ImageOps.exif_transpose(opened)
        if 'A' in upright.getbands() or 'transparency' in upright.info:
            layer = upright.convert('RGBA')
            background = Image.new('RGB', layer.size, 'white')
            background.paste(layer, mask=layer.getchannel('A'))
            return background
        return upright.convert('RGB')


def _subject(cutout):
    if cutout is None:
        return None
    if cutout.mode != 'RGBA':
        raise MediaError('campaign_cutout_alpha_required')
    alpha = cutout.getchannel('A')
    # Ignore near-invisible antialiasing several pixels outside the subject.
    bounds = alpha.point(lambda value: 255 if value >= 16 else 0).getbbox()
    if bounds is None:
        raise MediaError('campaign_cutout_has_no_subject')
    subject = cutout.crop(bounds)
    subject.putalpha(alpha.crop(bounds).point(lambda value: value if value >= 12 else 0))
    return subject


def _whole_photo(image, size):
    """Retain all photographed details; extend the image edges on a different canvas."""
    fitted = ImageOps.contain(image, size, LANCZOS)
    if fitted.size == size:
        return fitted
    broad = ImageOps.fit(image, (90, 160), method=LANCZOS).filter(ImageFilter.GaussianBlur(9))
    canvas = broad.resize(size, Image.Resampling.BILINEAR)
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def _on_surface(canvas, subject, fit, baseline):
    item = ImageOps.contain(subject, fit, LANCZOS)
    cx = canvas.width // 2
    x, y = cx - item.width // 2, baseline - item.height
    # Two contact shadows, sized from the photographed footprint, ground the object.
    for spread, depth, opacity in ((.44, .042, 57), (.22, .014, 88)):
        radius = max(2, round(item.width * spread))
        height = max(2, round(item.height * depth))
        shadow = Image.new('L', (radius * 4, height * 6))
        ImageDraw.Draw(shadow).ellipse((radius, 2 * height, 3 * radius, 4 * height), fill=opacity)
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, height * .72)))
        canvas.paste((27, 22, 19), (cx - radius * 2, baseline - height * 3), shadow)
    canvas.paste(item, (x, y), item.getchannel('A'))
    return canvas


def packshot(photo_paths, cutout, output):
    if not photo_paths:
        raise MediaError('campaign_photos_required')
    subject = _subject(cutout)
    if subject is None:
        canvas = _whole_photo(_photo(photo_paths[0]), PORTRAIT)
    else:
        canvas = Image.new('RGB', PORTRAIT, '#fbfaf8')
        canvas = _on_surface(canvas, subject, (740, 840), 1120)
    return {**_save(canvas, output), 'scene_kind': 'packshot', 'worn': False}


def scene(photo_paths, cutout, platform, output, *, worn):
    portrait, anchor, size, studio = _platform(platform)
    if not photo_paths:
        raise MediaError('campaign_photos_required')
    subject = _subject(cutout)
    if worn:
        if subject is None or subject.getchannel('A').getextrema()[0] >= 250:
            raise MediaError('campaign_wearable_cutout_required')
        with Image.open(ASSETS / portrait) as source:
            canvas = source.convert('RGB')
        item = ImageOps.contain(subject, size, LANCZOS)
        # A long stem extends below the ear. A stemless body sits around its centre.
        body_y = .27 if item.height > item.width * 1.35 else .49
        x = round(anchor[0] - item.width * .5)
        y = round(anchor[1] - item.height * body_y)
        matte = item.getchannel('A')
        shadow = Image.new('L', (item.width + 14, item.height + 14))
        shadow.paste(matte.point(lambda v: round(v * .50)), (7, 7))
        shadow = shadow.filter(ImageFilter.GaussianBlur(2.0))
        canvas.paste((51, 31, 24), (x - 5, y - 4), shadow)
        # Exposure follows the set. Geometry, marks and detail come from the cutout.
        light = (.96, .91, .84) if platform == 'douyin' else (.98, .97, .95)
        bands = [band.point(lambda v, gain=gain: round(v * gain))
                 for band, gain in zip(item.convert('RGB').split(), light)]
        canvas.paste(Image.merge('RGB', bands), (x, y), matte)
        canvas = ImageOps.fit(canvas, PORTRAIT, LANCZOS, centering=(.5, .35))
        kind = 'wearing'
    elif subject is not None:
        with Image.open(ASSETS / studio) as source:
            canvas = ImageOps.fit(source.convert('RGB'), PORTRAIT, LANCZOS)
        canvas = _on_surface(canvas, subject, (738, 720), 1140)
        kind = 'studio'
    else:
        index = 1 if platform == 'xiaohongshu' and len(photo_paths) > 1 else 0
        canvas = _whole_photo(_photo(photo_paths[index]), PORTRAIT)
        kind = 'photograph'
    return {**_save(canvas, output), 'scene_kind': kind, 'worn': bool(worn),
            'platform': platform}


def _wrapped(draw, text, font, width):
    lines = []
    for paragraph in text.splitlines() or ['']:
        line = ''
        for char in paragraph:
            if line and draw.textlength(line + char, font=font) > width:
                # Prefer a word boundary for merchant names in Latin scripts.
                if char.isascii() and char.isalnum() and ' ' in line:
                    head, line = line.rsplit(' ', 1)
                    lines.append(head)
                else:
                    lines.append(line)
                    line = ''
            line += char
        lines.append(line.strip())
    return lines


def _text_block(draw, text, font_path, box, largest, smallest, color, bold=False):
    left, top, right, bottom = box
    for size in range(largest, smallest - 1, -2):
        font = ImageFont.truetype(str(font_path), size)
        lines = _wrapped(draw, text, font, right - left)
        leading = round(size * 1.28)
        if leading * len(lines) <= bottom - top:
            stroke = 1 if bold and size >= 52 else 0
            for i, line in enumerate(lines):
                draw.text((left, top + i * leading), line, font=font, anchor='lt', fill=color,
                          stroke_width=stroke, stroke_fill=color)
            return
    raise MediaError('poster_text_overflow')


def _wash(canvas, color, edge, strength, height):
    # A gradual photographic scrim lets copy stay on the actual image.
    values = [round(strength * (1 - i / height) ** 2) for i in range(height)]
    if edge == 'bottom':
        values = values[::-1]
    mask = Image.frombytes('L', (1, height), bytes(values)).resize((canvas.width, height))
    canvas.paste(color, (0, canvas.height - height if edge == 'bottom' else 0), mask)


def _poster_line(canvas, text, platform, font, x, y, size, width, ink):
    from .campaign_type import headline
    layer = headline(text, platform, size, ink, fallback=font)
    if layer.width > width:
        layer = layer.resize((width, max(1, round(layer.height * width/layer.width))), LANCZOS)
    canvas.paste(layer, (x, y), layer)
    return layer.height


def poster(scene_path, platform, title, points, font, output, *, internal_sample, scene_kind=None):
    _platform(platform)
    if (not isinstance(title, str) or not title.strip() or len(title) > 200
            or len(points) > 8 or any(not isinstance(p, str) or len(p) > 200 for p in points)):
        raise MediaError('poster_text_overflow')
    with Image.open(scene_path) as photo:
        canvas = ImageOps.fit(photo.convert('RGB'), PORTRAIT, LANCZOS)
    dark = platform == 'douyin'
    ink = '#fff9ed' if dark else '#142c39'
    wash = (18, 13, 13) if dark else (241, 248, 247)
    title = title.strip()
    # Both original running plates leave the upper-left clear. Keep the entire
    # photographic lower half intact on short campaigns, including the runner's kit.
    detail_lines = [p.strip() for p in points if p.strip() and p.strip() != title]
    details = '\n'.join(detail_lines)
    short = (scene_kind == 'wearing' and len(title) <= 12 and len(details) <= 26
             and '\n' not in title and len(detail_lines) <= 2
             and all('\n' not in part for part in detail_lines))
    if short and dark:
        details = ' · '.join(detail_lines)
    _wash(canvas, wash, 'top', (104 if dark else 102) if short else 218, 570)
    draw = ImageDraw.Draw(canvas)
    label = 'AI生成 · 内部样片 · 未经审核' if internal_sample else 'AI生成'
    marker = ImageFont.truetype(str(font), 24)
    draw.text((1010, 46), label, anchor='rt', fill=ink, font=marker, stroke_width=1,
              stroke_fill='#191818' if dark else '#eff5f3')
    if short and dark:
        first, comma, last = title.partition('，')
        if comma and last:
            _poster_line(canvas, first + comma, platform, font, 63, 126, 110, 442, ink)
            _poster_line(canvas, last, platform, font, 85, 246, 163, 456, '#ffac61')
        else:
            _poster_line(canvas, title, platform, font, 60, 135, 124, 648, ink)
        detail_box = (66, 69, 714, 119)
    elif short and 4 <= len(title) <= 8 and all('\u3400' <= c <= '\u9fff' for c in title):
        # Vertical reading order runs from the smaller right column to the
        # larger left one. Its footprint stays left of the hair and ear.
        split = title.index('的') + 1 if '的' in title[1:-1] else len(title)//2
        for column, x, top, size, advance in [(title[:split],179,98,65,76),(title[split:],63,159,94,104)]:
            for index,char in enumerate(column):
                _poster_line(canvas, char, platform, font, x, top+index*advance, size, size, ink)
        baseline = max(98+split*76,159+(len(title)-split)*104)+30
        detail_box = (64, baseline, 408, baseline+108)
    else:
        size = 103 if dark else 90
        measure = ImageFont.truetype(str(font),size)
        lines = _wrapped(draw,title,measure,872)
        if len(lines) <= 3:
            y = 101
            for line in lines:
                if line:
                    y += _poster_line(canvas,line,platform,font,66,y,size,870,ink) + 12
        else:
            _text_block(draw,title,font,(66,100,956,433),78,24,ink,bold=dark)
        if details:
            _wash(canvas, wash, 'bottom', 220, 330)
        detail_box = (68, 1180, 949, 1370)
    if details:
        _text_block(draw, details, font, detail_box, 32 if short else 36, 20, ink)
    return {**_save(canvas, output), 'width': 1080, 'height': 1440,
            'kind': 'marketing_poster', 'sample_marked': internal_sample}


class CampaignEncodeError(MediaError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _ffmpeg(args, timeout=180):
    try:
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-filter_threads', '1',
                        '-filter_complex_threads', '1', *args],
                       check=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise CampaignEncodeError('campaign_ffmpeg_timeout') from error
    except subprocess.CalledProcessError as error:
        # Persist a diagnosis on the task step without leaking merchant input paths.
        detail = (error.stderr or b'').lower()
        exhausted = any(mark in detail for mark in (
            b'out of memory', b'cannot allocate memory', b'not enough memory',
            b'resource temporarily unavailable', b'pthread_create failed'))
        code = 'campaign_ffmpeg_resources' if exhausted else f'campaign_ffmpeg_exit_{error.returncode}'
        raise CampaignEncodeError(code) from error


def _camera(image, target, frames, start_zoom, stop_zoom, anchor, drift):
    # Cubic easing; the original outline never rotates into an unphotographed view.
    progress = f'(on/{max(1, frames - 1)})'
    ease = f'({progress}*{progress}*(3-2*{progress}))'
    zoom = f'{start_zoom}+({stop_zoom}-{start_zoom})*{ease}'
    x = f'(iw-iw/zoom)*({anchor[0]}+{drift}*({progress}-.5))'
    y = f'(ih-ih/zoom)*{anchor[1]}'
    zoompan = f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s=1080x1920:fps={FPS}"
    _ffmpeg(['-threads', '1', '-i', str(image), '-vf', 'format=yuv444p,' + zoompan + ',setsar=1,' + VIDEO_COLOR,
             '-frames:v', str(frames), '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
             '-tune', 'zerolatency', '-crf', '17', '-pix_fmt', 'yuv420p', '-threads', '1',
             '-movflags', '+faststart', str(target)])


def _light_strip(size, color, opacity):
    """One feathered slant of light, rendered small then enlarged for continuous tone."""
    w, h = max(16, size[0] // 8), max(16, size[1] // 8)
    mask = Image.new('L', (w, h))
    draw = ImageDraw.Draw(mask)
    draw.polygon([(w*.54, 0), (w*.95, 0), (w*.42, h), (w*.11, h)], fill=opacity)
    mask = mask.filter(ImageFilter.GaussianBlur(max(1, w * .095))).resize(size, LANCZOS)
    light = Image.new('RGBA', size, color)
    light.putalpha(mask)
    return light


def _moving_product(subject, platform, frames, target, folder, closing):
    """Move the photographed cutout, raking light and floor shadow independently."""
    _, _, _, studio = _platform(platform)
    with Image.open(ASSETS / studio) as plate:
        backdrop = ImageOps.fit(plate.convert('RGB'), VIDEO, LANCZOS)
    backdrop.save(folder / 'stage.jpg', quality=94, subsampling=0)
    backdrop.close()

    # The macro can enter from off frame. The end shot keeps the whole product in view.
    limit = (720, 905) if closing else (956, 1270)
    product = ImageOps.contain(subject, limit, LANCZOS)
    pad = round(max(product.size) * .10)
    item = Image.new('RGBA', (product.width + 2*pad, product.height + 2*pad))
    item.paste(product, (pad, pad))
    item.save(folder / 'object.png', compress_level=2)
    shine = _light_strip((max(120, round(item.width*.64)), item.height),
                         '#ffead3' if platform == 'douyin' else '#f7ffff', 45)
    shine.save(folder / 'shine.png', compress_level=2)
    beam = _light_strip((510, 1920), '#f4a966' if platform == 'douyin' else '#eff8ff', 27)
    beam.save(folder / 'light.png', compress_level=2)

    shadow_width = round(product.width*.92)
    shadow_height = max(34, round(product.height*.088))
    shadow = Image.new('RGBA', (shadow_width + 100, shadow_height * 4))
    ImageDraw.Draw(shadow).ellipse((50, shadow_height*1.4, shadow.width-50, shadow_height*2.6),
                                   fill=(24, 21, 24, 88))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(4, shadow_height*.32)))
    shadow.save(folder / 'shadow.png', compress_level=2)

    seconds = max(1, frames-1) / FPS
    progress = f'min(1,t/{seconds})'
    # Ease to a firm hold near the end, leaving room for the campaign tagline.
    settle = f'(1-pow(1-min(1,t/{seconds*.84}),3))' if closing else f'((1-cos(PI*{progress}))/2)'
    fast = platform == 'douyin'
    start_x, dx = ((66, -74) if closing else (-77, 104)) if fast else (
        (-38, 42) if closing else (50, -72))
    start_y, dy = (58, -68) if closing else (71, -136)
    angle = f'{.065 if fast else -.035}*(1-{settle})' if closing else (
        f'-.087+.159*{settle}' if fast else f'.043-.087*{settle}')
    x = f'(main_w-overlay_w)/2+{start_x}+({dx})*{settle}'
    y = f'(main_h-overlay_h)/2-{128 if closing else 55}+{start_y}+({dy})*{settle}'
    # loop holds a decoded frame in memory; it does not re-read PNGs every video frame.
    clock = f'loop=loop=-1:size=1,setpts=N/({FPS}*TB)'
    filters = [
        f'[0:v]format=yuv420p,{clock}[back]',
        f"[back][1:v]overlay=x='-w+(W+w)*{progress}':y=0[set]",
        f"[set][2:v]overlay=x='(W-w)/2+{start_x*.5}+({dx*.55})*{settle}':"
        f"y='{1410 if closing else 1630}-h/2'[floor]",
        '[3:v]format=rgba,split[product][maskinput]',
        '[maskinput]alphaextract[matte]',
        f'[product]format=rgb24,{clock}[still]',
        f"[still][4:v]overlay=x='-w+(W+w)*{progress}':y=0:format=rgb[illuminated]",
        f"[illuminated][matte]alphamerge,rotate=a='{angle}':ow=iw:oh=ih:c=black@0[layer]",
        f"[floor][layer]overlay=x='{x}':y='{y}',setsar=1,{VIDEO_COLOR}[film]",
    ]
    inputs = []
    for name in ('stage.jpg', 'light.png', 'shadow.png', 'object.png', 'shine.png'):
        inputs += ['-threads', '1', '-framerate', str(FPS), '-i', str(folder / name)]
    _ffmpeg([*inputs, '-filter_complex', ';'.join(filters), '-map', '[film]',
             '-frames:v', str(frames), '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
             '-tune', 'zerolatency', '-crf', '17', '-threads', '1',
             '-movflags', '+faststart', str(target)])


def clip(image_path, platform, shot_index, duration, output, *, worn=False, full_bleed=False,
         subject=None, closing=False):
    _platform(platform)
    if not 0 < float(duration) <= 120 or not isinstance(shot_index, int) or shot_index < 0:
        raise MediaError('invalid_campaign_shot')
    frames = max(1, round(float(duration) * FPS))
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        temp = Path(temp)
        master = temp / 'master.mp4'
        brisk = platform == 'douyin'
        if subject is not None and not worn:
            _moving_product(_subject(subject), platform, frames, master, temp, closing)
        else:
            source = _photo(image_path)
            if worn or full_bleed:
                source = ImageOps.fit(source, VIDEO, LANCZOS, centering=(.58 if worn else .5, .5))
            else:
                source = _whole_photo(source, VIDEO)
            still = temp / 'frame.jpg'
            source.save(still, quality=97, subsampling=0)
            source.close()
        if subject is None and brisk and worn and shot_index == 0 and frames >= 55:
            # Establish the actual earpiece first, then cut with three phases of a stride.
            opening = min(24, frames // 3)
            _camera(still, temp / 'open.mp4', opening, 1.08, 1.19, (.57, .46), .06)
            _camera(still, temp / 'return.mp4', frames - opening - 18,
                    1.34, 1.21, (.59, .45), -.10)
            with (temp / 'stride.mp4').open('xb') as dest:
                dest.write((ASSETS / 'stride.mp4').read_bytes())
            (temp / 'sequence.txt').write_text("file 'open.mp4'\nfile 'stride.mp4'\nfile 'return.mp4'\n",
                                               encoding='ascii')
            _ffmpeg(['-f', 'concat', '-safe', '1', '-i', str(temp/'sequence.txt'),
                     '-map', '0:v:0', '-c', 'copy', '-movflags', '+faststart', str(master)])
        elif subject is None or worn:
            if worn:
                anchor = (.59, .44) if brisk else (.69, .32)
                framing = (1.07, 1.30) if brisk else (1.17, 1.03)
            elif shot_index % 3 == 1:
                anchor = (.56, .44)
                framing = (1.32, 1.73) if brisk else (1.42, 1.18)
            else:
                anchor = (.50, .52)
                framing = (1.21, 1.01) if brisk else (1.04, 1.16)
            _camera(still, master, frames, *framing, anchor, .18 if brisk else -.13)
        info = probe(master)
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        if int(video['nb_frames']) != frames or abs(float(video['duration']) - frames / FPS) > .02:
            raise MediaError('campaign_clip_duration_mismatch')
        return _publish(master, target)


def score(platform, duration, output):
    _platform(platform)
    seconds = float(duration)
    if not 0 < seconds <= 120:
        raise MediaError('invalid_campaign_duration')
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    asset = ASSETS / ('pulse.ogg' if platform == 'douyin' else 'daybreak.ogg')
    fade = min(.65, seconds / 3)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        staged = Path(temp) / 'score.wav'
        _ffmpeg(['-stream_loop', '-1', '-i', str(asset), '-t', str(seconds), '-vn',
                 '-af', f'afade=t=out:st={seconds - fade}:d={fade}',
                 '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', str(staged)])
        return {**_publish(staged, target), 'media_role': 'original_instrumental'}
