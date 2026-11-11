import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


class MediaError(ValueError):
    pass


class VoiceDurationMismatch(MediaError):
    code = 'voice_duration_mismatch'

    def __init__(self):
        super().__init__(self.code)


def save_image(image, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        image.save(stream, format='PNG')
    with Image.open(output) as check:
        check.verify()
    return {'path': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def compose_product(product, mask, background, output):
    """Use an explicit reviewed mask; never claim automatic segmentation."""
    with Image.open(product) as source, Image.open(mask) as matte, Image.open(background) as scene:
        if source.size != matte.size or source.size != scene.size:
            raise MediaError('image_size_mismatch')
        return save_image(Image.composite(source.convert('RGB'), scene.convert('RGB'), matte.convert('L')), output)


def place_product(product, mask, background, output):
    """Fit reviewed foreground proportionally into arbitrary background dimensions."""
    with Image.open(product) as source, Image.open(mask) as matte, Image.open(background) as scene:
        if source.size != matte.size:
            raise MediaError('mask_size_mismatch')
        foreground=source.convert('RGBA')
        foreground.putalpha(matte.convert('L'))
        bounds=foreground.getbbox()
        if bounds is None:
            raise MediaError('empty_product_mask')
        foreground=foreground.crop(bounds)
        foreground=ImageOps.contain(foreground,(int(scene.width*.75),int(scene.height*.75)),Image.Resampling.LANCZOS)
        canvas=scene.convert('RGBA')
        canvas.alpha_composite(foreground,((canvas.width-foreground.width)//2,(canvas.height-foreground.height)//2))
        return save_image(canvas.convert('RGB'),output)


def repair_patch(candidate, original, mask, output):
    """White mask pixels restore exact original pixels at matching coordinates."""
    return compose_product(original, mask, candidate, output)


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)], capture_output=True, timeout=30, check=True)
    return json.loads(result.stdout)


def render_poster(product, output, title, selling_points, font_path, width=1080, height=1440, layout='classic', internal_sample=True, creative_plan=None, detail_product=None):
    """Render a real PNG, reject text overflow rather than silently truncate."""
    if not 320 <= width <= 4096 or not 320 <= height <= 4096:
        raise MediaError('invalid_dimensions')
    if layout not in ('classic','product_top'):
        raise MediaError('unsupported_poster_layout')
    output = Path(output)
    if output.exists():
        raise MediaError('immutable_output_exists')
    if creative_plan is not None:
        return render_detail_poster(product,output,title,selling_points,font_path,width,height,internal_sample,creative_plan,detail_product)
    short_edge = min(width, height)
    font = ImageFont.truetype(str(font_path), max(20, short_edge // 24))
    canvas = Image.new('RGB', (width, height), '#f5f7f4')
    draw = ImageDraw.Draw(canvas)
    margin = short_edge // 12
    marker = ImageFont.truetype(str(font_path), max(16, short_edge // 40))
    label = 'AI生成 · 内部样片 · 未经审核' if internal_sample else 'AI生成'
    label_y = height - margin
    label_bounds = draw.textbbox((margin, label_y), label, font=marker, anchor='lb')
    if label_bounds[0] < 0 or label_bounds[2] > width - margin:
        raise MediaError('poster_label_overflow')
    product_top = int(height * (.45 if layout == 'classic' else .06))
    product_bottom = min(product_top + int(height * .5), label_bounds[1] - 4)
    text_bottom = min(int(height * (.4 if layout == 'classic' else .9)), label_bounds[1] - 4)
    y = margin if layout == 'classic' else int(height * .62)
    for text in [title, *selling_points]:
        for paragraph in text.split('\n'):
            line = ''
            for char in paragraph:
                if line and draw.textlength(line + char, font=font) > width - 2 * margin:
                    y = draw_poster_line(draw, line, font, margin, y, width, text_bottom)
                    line = ''
                line += char
            y = draw_poster_line(draw, line, font, margin, y, width, text_bottom)
        y += font.size // 5
    with Image.open(product) as source:
        source.load()
        image = ImageOps.contain(source.convert('RGBA'), (width - 2 * margin, product_bottom - product_top))
        canvas.paste(image, ((width - image.width) // 2, product_top), image)
    draw.text((margin, label_y), label, font=marker, fill='#a33b32', anchor='lb')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        canvas.save(stream, format='PNG')
    with Image.open(output) as verified:
        verified.verify()
    return {'path': str(output), 'width': width, 'height': height, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'kind': 'marketing_poster','sample_marked':internal_sample}


def draw_poster_line(draw, line, font, margin, y, width, bottom):
    left, top, right, ink_bottom = draw.textbbox((margin, y), line, font=font, anchor='lt')
    if left < 0 or top < 0 or right > width - margin or ink_bottom > bottom or y >= bottom:
        raise MediaError('poster_text_overflow')
    draw.text((margin, y), line, font=font, fill='#173e36', anchor='lt')
    return max(ink_bottom, y + round(font.size * 1.4))


def static_clip(image,output,duration):
    if duration<=0 or Path(output).exists():raise MediaError('invalid_static_clip')
    subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-filter_threads','1','-threads','2','-loop','1','-i',str(image),'-t',str(duration),'-vf','scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2','-r','25','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-threads','2',str(output)],capture_output=True,timeout=600,check=True)
    if abs(float(probe(output)['format']['duration'])-duration)>.15:raise MediaError('static_duration_mismatch')
    return {'path':str(output),'sha256':hashlib.sha256(Path(output).read_bytes()).hexdigest()}


def compose_video(video, audio, output, duration):
    """Mux an already generated video and voice without time stretching."""
    if duration <= 0 or Path(output).exists():
        raise MediaError('invalid_duration_or_existing_output')
    for path in (video, audio):
        actual = float(probe(path)['format']['duration'])
        if abs(actual - duration) > .15:
            raise MediaError('duration_mismatch')
    subprocess.run(['ffmpeg', '-nostdin', '-n', '-filter_threads', '1', '-threads', '2', '-i', str(video), '-threads', '2', '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-c:a', 'aac', '-threads', '2', '-movflags', '+faststart', str(output)], capture_output=True, timeout=600, check=True)
    metadata = probe(output)
    if abs(float(metadata['format']['duration']) - duration) > .15:
        raise MediaError('output_duration_mismatch')
    return metadata


def narration_duration(path):
    from math import isfinite

    metadata = probe(path)
    stream = next((item for item in metadata['streams'] if item['codec_type'] == 'audio'), None)
    try:
        seconds = float(stream.get('duration', metadata['format'].get('duration'))) if stream else 0
    except (TypeError, ValueError):
        seconds = 0
    if not isfinite(seconds) or seconds <= 0:
        raise MediaError('invalid_voice_duration')
    return seconds


def pad_narration(source, output, duration):
    """Create an uncompressed tail-silence derivative without limiting the speech stream."""
    import os

    with tempfile.TemporaryDirectory(dir=Path(output).parent) as directory:
        staged = Path(directory) / 'voice.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(source),
            '-map', '0:a:0', '-af', f'apad=whole_dur={duration}', '-c:a', 'pcm_s16le', str(staged)],
            capture_output=True, timeout=60, check=True)
        if abs(narration_duration(staged) - duration) > .001:
            raise MediaError('voice_padding_duration_mismatch')
        try:
            os.link(staged, output)
        except FileExistsError:
            if staged.read_bytes() != Path(output).read_bytes():
                raise MediaError('voice_padding_asset_conflict') from None


def timeline_font_options(font_path):
    if sys.platform == 'win32':
        return r'C\:/Windows/Fonts/arial.ttf', r'C\:/Windows/Fonts', 'Arial'
    try:
        path = Path(font_path).resolve(strict=True)
        if not path.is_file():
            raise ValueError()
        family = ImageFont.truetype(str(path), 24).getname()[0]
        if not family or any(character in family for character in "',;:\\") or any(character in str(path) for character in "'\\\n\r"):
            raise ValueError()
    except (OSError, ValueError, TypeError):
        raise MediaError('invalid_timeline_font') from None
    return str(path).replace(':', r'\:'), str(path.parent).replace(':', r'\:'), family


def source_clip_handler(payload,intent,renderer):
    """Trim a checked MP4 into a silent normalized timeline input."""
    from math import isfinite
    import os

    source=renderer.input_path(payload['source'])
    start,duration=payload['start_seconds'],payload['duration']
    if not all(type(value) in (int,float) and isfinite(value) for value in (start,duration)) or not 0<=start<120 or not 0<duration<=120:
        raise MediaError('video_source_trim_invalid')
    output=renderer.path(intent,'.mp4')
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        staged=Path(directory)/'clip.mp4'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-filter_threads','1','-threads','2',
            '-ss',str(start),'-protocol_whitelist','file,pipe','-f','mov','-i',str(source),'-t',str(duration),
            '-map','0:v:0','-an','-vf','scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25',
            '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-threads','2',str(staged)],
            capture_output=True,timeout=600,check=True)
        info=probe(staged)
        if abs(float(info['format']['duration'])-duration)>.05 or [item['codec_type'] for item in info['streams']]!=['video']:
            raise MediaError('video_source_clip_duration_mismatch')
        digest=hashlib.sha256(staged.read_bytes()).hexdigest()
        try:
            os.link(staged,output)
        except FileExistsError:
            if hashlib.sha256(output.read_bytes()).hexdigest()!=digest:
                raise MediaError('video_source_clip_conflict') from None
    return {'path':str(output),'sha256':digest}


def compose_timeline(clips, audio, output, duration, shots, music=None, subtitle_style='default', internal_sample=True, *, font_path=None, creative_copy=None):
    if subtitle_style not in ('default','large','small','dark_on_light'):
        raise MediaError('unsupported_subtitle_style')
    if len(clips) != len(shots) or not clips or Path(output).exists():
        raise MediaError('invalid_timeline')
    if abs(sum(float(s['duration']) for s in shots) - duration) > .001:
        raise MediaError('timeline_duration_mismatch')
    marker_font, font_directory, subtitle_family = timeline_font_options(font_path)
    for clip, shot in zip(clips, shots):
        if abs(float(probe(clip)['format']['duration']) - float(shot['duration'])) > .15:
            raise MediaError('clip_duration_mismatch')
    if abs(float(probe(audio)['format']['duration']) - duration) > .15:
        raise MediaError('voice_duration_mismatch')
    command = ['ffmpeg', '-nostdin', '-n', '-filter_complex_threads', '1', '-filter_threads', '1']
    for clip in clips:
        command += ['-threads', '2', '-i', str(Path(clip).resolve())]
    command += ['-threads', '2', '-i', str(Path(audio).resolve())]
    if music:
        command += ['-stream_loop','-1','-threads','2','-i',str(Path(music).resolve())]
    filters = [f'[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,setpts=PTS-STARTPTS[v{i}]' for i in range(len(clips))]
    filters.append(''.join(f'[v{i}]' for i in range(len(clips))) + f'concat=n={len(clips)}:v=1:a=0[combined]')
    label='AI GENERATED - INTERNAL PREVIEW - UNREVIEWED' if internal_sample else 'AI GENERATED'
    filters.append(f"[combined]drawtext=fontfile='{marker_font}':text='{label}':fontsize=24:fontcolor=white:box=1:boxcolor=black@0.65:x=(w-tw)/2:y={20 if creative_copy and creative_copy.get('visual_plan') else 'h-80'}[outv]")
    if music:
        filters.append(f'[{len(clips)+1}:a]volume=0.15,atrim=duration={duration}[music]')
        filters.append(f'[{len(clips)}:a][music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=false:latency=true[outa]')
    with tempfile.TemporaryDirectory() as temporary:
        if creative_copy and creative_copy.get('visual_plan'):
            plan=creative_copy['visual_plan']
            order=plan.get('information_order')
            if order not in ('hero_detail_close','context_detail_choice') or plan.get('version')!='creative-direction-v1':
                raise MediaError('invalid_video_creative_plan')
            # Reserve a top band by shrinking the entire picture; never cover product pixels.
            dark=order=='hero_detail_close'
            background='0x152b2b' if dark else '0xf5f1e9'
            foreground='0xf7f5ed' if dark else '0x233c36'
            filters.append(f'[outv]scale=918:1632,pad=1080:1920:81:220:color={background}[card0]')
            selected=[creative_copy.get('title','')]+list(creative_copy.get('selling_points',[]))[:1 if duration<=6 else min(3,int(duration//4))]
            selected=[text for text in selected if text]
            cardfont=str(Path(font_path).resolve()).replace('\\','/').replace(':',r'\:')
            for index,text in enumerate(selected):
                if not isinstance(text,str) or len(text)>200:raise MediaError('video_card_text_overflow')
                measure=ImageDraw.Draw(Image.new('RGB',(1,1)))
                for card_size in range(48,27,-1):
                    font=ImageFont.truetype(str(font_path),card_size)
                    if measure.textlength(text,font=font)<=940:break
                else:raise MediaError('video_card_text_overflow')
                card=Path(temporary)/f'card{index}.txt';card.write_text(text,encoding='utf-8')
                escaped_card=str(card.resolve()).replace('\\','/').replace(':',r'\:')
                start=duration*index/len(selected);end=duration*(index+1)/len(selected)
                filters.append(f"[card{index}]drawtext=fontfile='{cardfont}':textfile='{escaped_card}':expansion=none:fontsize={card_size}:fontcolor={foreground}:x="+('(w-tw)/2' if dark else '70')+f":y=100:enable='gte(t,{start})*lt(t,{end})'[card{index+1}]")
            filters.append(f'[card{len(selected)}]null[creativev]')
        subtitle = Path(temporary)/'captions.srt'
        def timestamp(seconds):
            milliseconds=round(seconds*1000)
            return f'{milliseconds//3600000:02}:{milliseconds//60000%60:02}:{milliseconds//1000%60:02},{milliseconds%1000:03}'
        cursor=0.; captions=[]
        for index, shot in enumerate(shots):
            end=cursor+float(shot['duration'])
            text=str(shot.get('narration','')).replace('\r',' ').replace('\n',' ')
            if text:
                captions.append(f'{index+1}\n{timestamp(cursor)} --> {timestamp(end)}\n{text}\n')
            cursor=end
        subtitle.write_text('\n'.join(captions), encoding='utf-8')
        if captions:
            escaped=str(subtitle.resolve()).replace('\\','/').replace(':','\\:')
            size={'default':20,'large':28,'small':14,'dark_on_light':20}[subtitle_style]
            if creative_copy and creative_copy.get('visual_plan'):size=max(8,size//2)
            colors=''
            if subtitle_style in ('default','dark_on_light'):
                text_color,box_color=('000000','F3F4F5') if subtitle_style=='dark_on_light' else ('FFFFFF','20262B')
                colors=f',PrimaryColour=&H00{text_color},OutlineColour=&H00{box_color},BorderStyle=3,Outline=3,Shadow=0'
            filters.append(f"[{'creativev' if creative_copy and creative_copy.get('visual_plan') else 'outv'}]subtitles=filename='{escaped}':fontsdir='{font_directory}':force_style='FontName={subtitle_family},FontSize={size}{colors}'[captioned]")
        if captions:
            command += ['-i', str(subtitle)]
        command += ['-filter_complex', ';'.join(filters), '-map', '[captioned]' if captions else ('[creativev]' if creative_copy and creative_copy.get('visual_plan') else '[outv]'), '-map', '[outa]' if music else f'{len(clips)}:a:0']
        if captions:
            command += ['-map', f'{len(clips)+1+(1 if music else 0)}:s:0', '-c:s', 'mov_text', '-metadata:s:s:0', 'title='+subtitle_style]
        command += ['-c:v','libx264','-preset','ultrafast','-c:a','aac','-threads','2','-movflags','+faststart',str(output)]
        subprocess.run(command, capture_output=True, timeout=600, check=True)
    result=probe(output)
    if abs(float(result['format']['duration'])-duration)>.15:
        raise MediaError('output_duration_mismatch')
    return result


def render_detail_poster(product,output,title,points,font_path,width,height,internal_sample,plan,detail_product=None):
    """Versioned local editorial modules; crops never invent a product angle."""
    if len(title)>200 or len(points)>8 or any(not isinstance(point,str) or len(point)>200 for point in points):
        raise MediaError('poster_text_overflow')
    order=plan.get('information_order')
    if plan.get('version')!='creative-direction-v1' or order not in ('hero_detail_close','context_detail_choice'):
        raise MediaError('invalid_poster_creative_plan')
    bold=order=='hero_detail_close'
    scale=width/1080
    margin=int(64*scale); gap=int(24*scale)
    canvas=Image.new('RGB',(width,height),'#152b2b' if bold else '#f5f1e9')
    draw=ImageDraw.Draw(canvas)
    ink='#f7f5ed' if bold else '#233c36'
    accent='#b7d8c0' if bold else '#426959'
    def text_box(text,box,size,color):
        x,y,right,bottom=box
        for pixels in range(max(16,int(size*scale)),max(12,int(20*scale))-1,-1):
            font=ImageFont.truetype(str(font_path),pixels)
            lines=[]
            for para in str(text).split('\n'):
                line=''
                for char in para:
                    if line and draw.textlength(line+char,font=font)>right-x:
                        lines.append(line);line=''
                    line+=char
                lines.append(line)
            step=int(pixels*1.4)
            if len(lines)*step<=bottom-y:
                for line in lines:
                    draw.text((x,y),line,font=font,fill=color);y+=step
                return
        raise MediaError('poster_text_overflow')
    text_box(title,(margin,int(height*.045),width-margin,int(height*.185)),66,ink)
    with Image.open(product) as opened:
        source=opened.convert('RGB')
        hero=(margin,int(height*.205),width-margin,int(height*.61))
        fitted=ImageOps.contain(source,(hero[2]-hero[0],hero[3]-hero[1]),Image.Resampling.LANCZOS)
        canvas.paste(fitted,(hero[0]+(hero[2]-hero[0]-fitted.width)//2,hero[1]+(hero[3]-hero[1]-fitted.height)//2))
        # Center crop of the supplied scene is explicitly a detail, not a new view.
        if detail_product:
            with Image.open(detail_product) as detail:source=detail.convert('RGB')
        crop=source.crop((int(source.width*.28),int(source.height*.28),int(source.width*.72),int(source.height*.72)))
        y=int(height*.64); bottom=int(height*.87); split=int(width*.42)
        detail_x=margin if bold else width-split
        canvas.paste(ImageOps.fit(crop,(split-margin,bottom-y),Image.Resampling.LANCZOS),(detail_x,y))
    draw=ImageDraw.Draw(canvas)
    text_box('局部展示',(detail_x,int(height*.875),detail_x+split-margin,int(height*.915)),22,accent)
    entries=list(points)
    if not entries:entries=['查看商品外观与细节']
    area_top=int(height*.64);area_bottom=int(height*.91)
    row=(area_bottom-area_top)//len(entries)
    text_left=split+gap if bold else margin
    text_right=width-margin if bold else width-split-gap
    for index,point in enumerate(entries):
        y=area_top+index*row
        draw.line((text_left,y,text_right,y),fill=accent,width=max(1,int(scale)))
        text_box(str(index+1).zfill(2),(text_left,y+int(10*scale),text_left+int(45*scale),y+row),22,accent)
        text_box(point,(text_left+int(55*scale),y+int(10*scale),text_right,y+row-int(8*scale)),30,ink)
    label='AI生成 · 内部样片 · 未经审核' if internal_sample else 'AI生成'
    text_box(label,(margin,int(height*.95),width-margin,int(height*.99)),22,accent)
    result=save_image(canvas,output)
    return {**result,'width':width,'height':height,'kind':'marketing_poster','sample_marked':internal_sample,'creative_layout':order,'detail_source':'white_image_crop' if detail_product else 'same_image_crop'}
