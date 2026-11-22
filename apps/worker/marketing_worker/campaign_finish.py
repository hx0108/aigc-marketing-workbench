"""Full-frame finishing for photo campaigns. All screen copy is rasterized as text."""
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageFont

from .media import MediaError, probe


def _block(draw, text, font_path, size, width, max_lines):
    """Fit captions by measured glyph width, including unspaced Chinese text."""
    text = " ".join(str(text).split())
    initial = ImageFont.truetype(str(font_path), size)
    short_headline = draw.textlength(text, font=initial) <= width * 1.18
    for pixels in range(size, 23, -3):
        font = ImageFont.truetype(str(font_path), pixels)
        lines, line = [], ""
        for char in text:
            if line and draw.textlength(line + char, font=font) > width:
                split = len(line) - 1 if char in "。，、！？：；）》】”’….,!?" and len(line) > 1 else len(line)
                lines.append(line[:split].rstrip())
                line = line[split:]
            line += char
        if line:
            lines.append(line.strip())
        if len(lines) <= (1 if short_headline else max_lines):
            return lines, font
    raise MediaError("video_card_text_overflow")


def _label(path, internal, font_path):
    layer = Image.new("RGBA", (1080, 1920))
    draw = ImageDraw.Draw(layer)
    font = ImageFont.truetype(str(font_path), 25)
    label = "AI生成 · 内部样片 · 待复核" if internal else "AI生成"
    box = draw.textbbox((78, 120), label, font=font, anchor="lt")
    draw.rounded_rectangle((65, 110, box[2]+13, box[3]+10), radius=8, fill=(12, 20, 24, 182))
    draw.text((78, 120), label, font=font, anchor="lt", fill="white")
    layer.save(path)


def _quiet_band(clip):
    from PIL import ImageStat
    probe_frame = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-threads", "1", "-i", str(clip),
         "-vf", "scale=108:192:force_original_aspect_ratio=decrease,pad=108:192:(ow-iw)/2:(oh-ih)/2",
         "-frames:v", "1", "-pix_fmt", "gray", "-threads", "1", "-f", "rawvideo", "pipe:1"],
        check=True, capture_output=True, timeout=30)
    frame = Image.frombytes("L", (108,192), probe_frame.stdout)
    choices = []
    for band, y in (("top",20), ("bottom",132)):
        stat = ImageStat.Stat(frame.crop((7, y, 87, y+27)))
        choices.append((stat.stddev[0], band, stat.mean[0]))
    _, band, luminance = min(choices)
    return band, luminance


def _overlay(path, title, name, font_path, platform, section, style, wearing, clip):
    from .campaign_type import headline
    layer = Image.new("RGBA", (1080, 1920))
    draw = ImageDraw.Draw(layer)
    if not title and not (section=="close" and name):
        layer.save(path)
        return
    brisk = platform == "douyin"
    band, luminance = ("top" if section=="opening" else "bottom", 42 if brisk else 177)
    if not wearing:
        band, luminance = _quiet_band(clip)
    dark = style != "light_on_dark" and (style=="dark_on_light" or luminance > 140)
    ink = "#172e39" if dark else "#fff8e9"
    accent = "#feab54" if brisk and not dark else ink
    x = 80
    y = 203 if band=="top" else 1334
    scale = {"large":1.08, "small":.82}.get(style,1)
    if wearing and section == "detail" and len(title) <= 16 and "\n" not in title:
        caption = headline(title, platform, round(47*scale), ink, fallback=font_path)
        if caption.width <= 760:
            left, top = 80, 1550
            backing = (245,245,237,229) if dark else (15,22,23,224)
            draw.rectangle((left, top, left+caption.width+50, top+caption.height+30), fill=backing)
            draw.rectangle((left, top, left+4, top+caption.height+30), fill="#f39548")
            layer.alpha_composite(caption, (left+25, top+15))
            layer.save(path)
            return
    if section=="detail" or style=="dark_on_light":
        scrim=(246,245,237) if dark else (12,19,21)
        for row in range(y-42,min(y+358,1920)):
            opacity = min(1,(row-y+42)/42,(y+358-row)/70)
            draw.line((0,row,946,row),fill=(*scrim,round(200*opacity)))

    def line(text, pixels, left, top, color, available):
        art = headline(text,platform,max(18,round(pixels*scale)),color,fallback=font_path)
        if art.width > available:
            art = art.resize((available,max(1,round(art.height*available/art.width))),Image.Resampling.LANCZOS)
        layer.alpha_composite(art,(left,top))
        return art.height

    vertical_title = 3 <= len(title) <= 9 and all("\u3400" <= ch <= "\u9fff" for ch in title)
    if wearing and section=="opening" and not brisk and vertical_title:
        # Read the two columns from right to left in the open sky beside the runner.
        cut = len(title) // 2
        if "的" in title[1:-2]:
            cut = title.index("的",1)+1
        for phrase,left,top,pixels in ((title[:cut],185,248,67),(title[cut:],76,310,82)):
            for ch in phrase:
                line(ch,pixels,left,top,ink,97)
                top+=round(pixels*scale)+13
    elif wearing and section=="opening" and brisk and "，" in title and len(title)<=12:
        lead, hero=title.split("，",1)
        top=y+line(lead+"，",79,x,y,ink,550)+22
        if hero:
            line(hero,157,x+40,top,accent,721)
    else:
        size = 99 if section!="detail" else 53
        if section == "close" and len(title) <= 12:
            lines = [title] if title else []
        else:
            lines,_ = _block(draw,title,font_path,round(size*scale),806,3)
        if section=="close" and name and name!=title:
            names,small = _block(draw,name,font_path,31,784,2)
            draw.line((x,y+12,x+44,y+12),fill=accent,width=4)
            for part in names:
                draw.text((x+59,y),part,font=small,anchor="lt",fill=ink)
                y+=small.size+8
            y+=16
        for part in lines:
            y+=line(part,size,x,y,ink,806)+12
    layer.save(path)


def compose_campaign(clips, audio, output, duration, shots, music=None, subtitle_style="default",
                     internal_sample=True, *, font_path, creative_copy, platform):
    if not clips or len(clips) != len(shots) or output.exists():
        raise MediaError("invalid_timeline")
    if abs(sum(float(shot["duration"]) for shot in shots) - duration) > .001:
        raise MediaError("timeline_duration_mismatch")
    with TemporaryDirectory(dir=output.parent) as folder:
        folder = Path(folder)
        segments = []
        mark = folder / "label.png"
        _label(mark, internal_sample, font_path)
        for i, (clip, shot) in enumerate(zip(clips, shots)):
            if abs(float(probe(clip)["format"]["duration"]) - float(shot["duration"])) > .15:
                raise MediaError("clip_duration_mismatch")
            card = folder / f"card-{i}.png"
            section = "opening" if i == 0 else "close" if i == len(shots)-1 else "detail"
            title = shot.get("narration") or ""
            _overlay(card, title, creative_copy.get("product_name", ""), font_path, platform,
                     section, subtitle_style, creative_copy.get("wearing_campaign", False), clip)
            offset = "0"
            if title and section in {"opening","close"}:
                offset = "-48*pow(max(0,1-t/0.24),3)" if platform=="douyin" else "0"
            vertical = "18*pow(max(0,1-t/0.40),2)" if platform=="xiaohongshu" and section!="detail" else "0"
            part = folder / f"shot-{i}.mp4"
            # Opening all 1080p decoders together would exceed the small production worker's memory.
            command = ["ffmpeg","-v","error","-nostdin","-n","-filter_complex_threads","1",
                       "-threads","1","-i",str(clip),"-threads","1","-i",str(card),"-threads","1","-i",str(mark),
                       "-filter_complex","[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                       "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25[shot];"
                       f"[shot][1:v]overlay=x='{offset}':y='{vertical}':eof_action=repeat[titled];"
                       "[titled][2:v]overlay=eof_action=repeat,format=yuv420p[v]",
                       "-map","[v]","-frames:v",str(round(float(shot["duration"])*25)),
                       "-an","-c:v","libx264","-threads","1","-preset","veryfast","-tune","zerolatency",
                       "-crf","18","-video_track_timescale","25000",str(part)]
            subprocess.run(command, check=True, capture_output=True, timeout=180)
            segments.append(f"file '{part.name}'")
        sequence = folder / "shots.ffconcat"
        sequence.write_text("\n".join(segments), encoding="ascii")
        command = ["ffmpeg","-v","error","-nostdin","-n","-filter_complex_threads","1",
                   "-f","concat","-safe","1","-i",str(sequence),"-threads","1","-i",str(audio)]
        audio_map = "1:a:0"
        if music:
            command += ["-stream_loop","-1","-threads","1","-i",str(music),"-filter_complex",
                        f"[2:a]volume=0.15,atrim=duration={duration}[bed];"
                        "[1:a][bed]amix=inputs=2:duration=first:normalize=0,"
                        "alimiter=limit=0.95:level=false:latency=true[sound]"]
            audio_map = "[sound]"
        command += ["-map", "0:v:0", "-map", audio_map,
                    "-t", str(duration), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "48000", "-movflags", "+faststart", str(output)]
        subprocess.run(command, capture_output=True, check=True, timeout=600)
    metadata = probe(output)
    if abs(float(metadata["format"]["duration"]) - duration) > .1:
        raise MediaError("output_duration_mismatch")
    return metadata
