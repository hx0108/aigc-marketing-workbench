import hashlib
from pathlib import Path
import subprocess
import wave

import pytest

from marketing_worker.bridge import RenderBridge
from marketing_worker.media import MediaError, narration_duration
from marketing_worker.pipeline import failure_details


def test_video_render_preserves_short_speech_and_appends_silence(tmp_path):
    clip, short, long = (tmp_path / name for name in ('clip.mp4','short.wav','long.wav'))
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=32x32:d=2',
        '-c:v','libx264',str(clip)],check=True,timeout=20)
    for path, seconds in ((short,1),(long,3)):
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'sine=frequency=440:duration={seconds}',
            '-c:a','pcm_s16le',str(path)],check=True,timeout=20)

    def reference(path):
        return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

    bridge = RenderBridge(tmp_path, '')
    payload = {'clips':[reference(clip)],'voice':reference(short),'duration':2,
               'copy':{'shots':[{'duration':2,'narration':'Test narration'}]}}
    result = bridge.video(payload, 'short')
    assert reference(short) == payload['voice']
    alignment = result['voice_alignment']
    assert alignment['mode'] == 'tail_silence'
    assert (alignment['source_seconds'], alignment['target_seconds']) == (1, 2)
    assert alignment['source_sha256'] == payload['voice']['sha256']
    padded = next(path for path in tmp_path.glob('*.wav') if path not in (short,long))
    assert alignment['render_sha256'] == reference(padded)['sha256']
    with wave.open(str(short)) as source, wave.open(str(padded)) as derivative:
        assert derivative.getframerate() == source.getframerate()
        original_samples = source.readframes(source.getnframes())
        assert derivative.readframes(source.getnframes()) == original_samples
        tail = derivative.readframes(source.getnframes())
        assert len(tail) == len(original_samples) and not any(tail)
    for output in (Path(result['path']),Path(result['release']['path'])):
        assert narration_duration(output) == pytest.approx(2, abs=.05)
        decoded = subprocess.run(['ffmpeg','-v','error','-ss','1.4','-i',str(output),
            '-t','0.2','-map','0:a:0','-f','s16le','pipe:1'],capture_output=True,check=True,timeout=20).stdout
        assert len(decoded) > 0 and not any(decoded)

    files_before = set(tmp_path.iterdir())
    with pytest.raises(MediaError, match='voice_duration_mismatch') as error:
        bridge.video({**payload,'voice':reference(long)}, 'too-long')
    assert failure_details(error.value) == {'code':'voice_duration_mismatch'}
    assert set(tmp_path.iterdir()) == files_before
