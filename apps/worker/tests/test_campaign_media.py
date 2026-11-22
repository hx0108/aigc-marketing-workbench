import subprocess
import struct
import sys
import wave
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat
import pytest

from marketing_worker import campaign_media as media
from marketing_worker.media import MediaError, probe


@pytest.mark.parametrize("band,brightness", [("top", 180), ("bottom", 40)])
def test_product_detail_caption_uses_measured_clear_area(tmp_path, monkeypatch, band, brightness):
    from marketing_worker import campaign_finish
    from marketing_worker.bridge import local_render_font

    monkeypatch.setattr(campaign_finish, "_quiet_band", lambda clip: (band, brightness))
    overlay = tmp_path / "detail.png"
    campaign_finish._overlay(overlay, "银色圆面", "", local_render_font(), "douyin",
                             "detail", "default", False, tmp_path / "product.mp4")
    with Image.open(overlay) as image:
        _, top, _, bottom = image.getchannel("A").getbbox()
    assert bottom < 960 if band == "top" else top > 960


def test_short_chinese_end_card_keeps_the_final_stop_with_the_headline():
    from marketing_worker.bridge import local_render_font
    from marketing_worker.campaign_finish import _block
    draw = ImageDraw.Draw(Image.new('RGB', (1080, 1920)))
    text = '把喜欢的歌，带出门。'
    lines, font = _block(draw, text, local_render_font(), 88, 855, 3)
    assert lines == [text]
    assert draw.textlength(lines[0], font=font) <= 855


def test_photo_copy_can_use_a_confirmed_selling_point():
    from marketing_worker.photo_campaign import _copy
    from marketing_worker.pipeline import validate_copy
    facts = {'name':'概念耳机', '核心卖点':'续航8小时'}
    request = {'profile_snapshot':{'facts':facts}, 'facts':[{'id':k,'value':v,'validity':'active'} for k,v in facts.items()],
               'platforms':['douyin','xiaohongshu'], 'photo_sources':[{'source_id':'case'}], 'duration_seconds':15}
    content = validate_copy(_copy(request), request)
    for item in content.values():
        assert facts['核心卖点'] in item['body']
        assert item['selling_points'] == ['概念耳机','续航8小时']
        assert item['fact_refs'] == ['name','核心卖点']
        detail = next(shot for shot in item['shots'] if shot['visual_description']=='商品外形特写')
        assert detail['narration'] == facts['核心卖点'] and detail['fact_refs'] == ['核心卖点']
        assert item['narration'] == ''.join(shot.get('narration','') for shot in item['shots'])
    for revised in ({'name':'概念耳机'}, {'name':'概念耳机','卖点':'珍珠白机身搭配银色圆形饰面和暖橙色装饰线条'}):
        request['duration_seconds'] = 6
        request.update(profile_snapshot={'facts':revised},facts=[{'id':k,'value':v,'validity':'active'} for k,v in revised.items()])
        for item in validate_copy(_copy(request), request).values():
            detail = next(shot for shot in item['shots'] if shot['visual_description']=='商品外形特写')
            assert 'narration' not in detail


def earbud(color):
    layer = Image.new('RGBA', (80, 140))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((9, 7, 69, 76), fill=color)
    draw.rounded_rectangle((34, 55, 55, 132), radius=8, fill=color)
    return layer


def decoded_frame(path, seconds):
    return subprocess.run(['ffmpeg', '-v', 'error', '-filter_threads', '1', '-threads', '1',
        '-ss', str(seconds), '-i', str(path), '-frames:v', '1', '-vf', 'scale=90:160',
        '-threads', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'],
        capture_output=True, timeout=30, check=True).stdout


@pytest.mark.parametrize(('failure', 'code'), [
    (subprocess.CalledProcessError(1, ['ffmpeg'], stderr=b'Cannot allocate memory'), 'campaign_ffmpeg_resources'),
    (subprocess.CalledProcessError(22, ['ffmpeg'], stderr=b'invalid format'), 'campaign_ffmpeg_exit_22'),
    (subprocess.TimeoutExpired(['ffmpeg'], 1), 'campaign_ffmpeg_timeout'),
])
def test_encoding_failures_have_persistable_step_codes(monkeypatch, failure, code):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(subprocess, 'run', fail)
    with pytest.raises(MediaError) as caught:
        media._ffmpeg([])
    assert caught.value.code == code and caught.value.__cause__ is failure


@pytest.mark.parametrize('platform', ['douyin', 'xiaohongshu'])
def test_wearing_uses_the_uploaded_earbud_only_at_the_ear(platform, tmp_path):
    photos = []
    for i, color in enumerate(('#ab1626', '#184abe')):
        subject = earbud(color)
        photo = tmp_path / f'photo-{i}.png'
        subject.save(photo)
        out = media.scene([photo], subject, platform, tmp_path/f'scene-{i}.png', worn=True)
        assert out['worn'] and out['platform'] == platform
        with Image.open(out['path']) as artwork:
            photos.append(artwork.copy())
    bounds = ImageChops.difference(*photos).getbbox()
    assert bounds is not None
    left, top, right, bottom = bounds
    assert 500 < left < right < 800 and 410 < top < bottom < 820
    assert right-left > 25 and bottom-top > 50
    with pytest.raises(MediaError, match='wearable_cutout_required'):
        media.scene([photo], None, platform, tmp_path/'bad.png', worn=True)
    assert not (tmp_path / 'bad.png').exists()


def test_full_photos_do_not_need_a_mask_and_retain_their_orientation(tmp_path):
    main, alternate = tmp_path/'main.jpg', tmp_path/'alternate.jpg'
    image = Image.new('RGB', (120, 60), 'red')
    ImageDraw.Draw(image).rectangle((60, 0, 119, 59), fill='blue')
    exif = Image.Exif()
    exif[274] = 6
    image.save(main, exif=exif)
    Image.new('RGB', (120, 90), 'lime').save(alternate)
    a = media.scene([main,alternate], None, 'douyin', tmp_path/'a.png', worn=False)
    b = media.scene([main,alternate], None, 'xiaohongshu', tmp_path/'b.png', worn=False)
    assert a['scene_kind'] == b['scene_kind'] == 'photograph'
    with Image.open(a['path']) as first, Image.open(b['path']) as second:
        assert first.size == second.size == (1080, 1440)
        assert first.getpixel((540, 300))[0] > 240
        assert first.getpixel((540, 1140))[2] > 240
        assert second.getpixel((540, 720))[1] > 240


def test_poster_preserves_immutable_versions_and_distinguishes_sample(tmp_path):
    font = Path('C:/Windows/Fonts/msyh.ttc' if sys.platform == 'win32'
                else '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')
    source = tmp_path / 'scene.png'
    Image.new('RGB', (1080, 1440), (84, 129, 147)).save(source)
    def make(title, target, sample):
        return media.poster(source, 'xiaohongshu', title, ['白色耳机'], font, target, internal_sample=sample)
    target = tmp_path / 'poster.png'
    first = make('晨跑的耳边风景', target, False)
    assert make('晨跑的耳边风景', target, False) == first
    with pytest.raises(MediaError, match='campaign_asset_conflict'):
        make('另一个标题', target, False)
    sample = make('晨跑的耳边风景', tmp_path/'preview.png', True)
    assert sample['sha256'] != first['sha256'] and sample['sample_marked']


def test_photo_film_contains_exact_action_cut_and_a_separate_moving_product(tmp_path):
    subject = earbud('red')
    photo = tmp_path/'source.png'
    subject.save(photo)
    wear = media.scene([photo], subject, 'douyin', tmp_path/'wear.png', worn=True)
    opener = media.clip(wear['path'], 'douyin', 0, 3, tmp_path/'open.mp4', worn=True)
    stream = probe(opener['path'])['streams'][0]
    assert (stream['width'], stream['height'], stream['pix_fmt'], stream['nb_frames']) == (
        1080, 1920, 'yuv420p', '75')
    assert (stream['color_range'], stream['color_space']) == ('tv', 'bt709')
    # At 3 s the 24-frame opening precedes three edited, generated phases of a stride.
    expected = decoded_frame(media.ASSETS/'stride.mp4', .12)
    assert len(expected) == 90*160*3 and decoded_frame(opener['path'], 1.08) == expected
    assert decoded_frame(opener['path'], 2.4) != expected
    product = media.clip(photo, 'douyin', 1, 1.2, tmp_path/'product.mp4', subject=subject)
    product_stream = probe(product['path'])['streams'][0]
    assert (product_stream['pix_fmt'], product_stream['color_range'], product_stream['color_space']) == (
        'yuv420p', 'tv', 'bt709')
    frames = [Image.frombytes('RGB', (90,160), decoded_frame(product['path'], t)) for t in (0,.6,1)]
    assert ImageStat.Stat(ImageChops.difference(frames[0], frames[-1])).mean[0] > 3
    # The merchant's red body remains visible over the independent moving set and light.
    for frame in frames:
        pixels = struct.iter_unpack('3B', frame.tobytes())
        assert sum(r > 200 and g < 75 and b < 75 for r, g, b in pixels) > 1300


def test_original_stereo_scores_are_platform_specific_and_exact_length(tmp_path):
    scores = []
    for platform in ('douyin','xiaohongshu'):
        score = media.score(platform, 2.4, tmp_path/(platform+'.wav'))
        with wave.open(score['path'], 'rb') as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getnframes()) == (48000, 2, 115200)
            samples = wav.readframes(115200)
            assert max(samples) > 0 and samples[::4] != samples[2::4]
        scores.append(score['sha256'])
    assert scores[0] != scores[1]
