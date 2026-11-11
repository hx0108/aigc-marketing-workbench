import hashlib
import subprocess
import pytest
from marketing_worker.business import normalize_minimax_clip
from marketing_worker.media import probe

@pytest.mark.parametrize('duration,accepted', [(5.875,True),(5.5,False),(6.25,True)])
def test_provider_frame_rounding_preserves_speed_and_source(tmp_path,duration,accepted):
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c=red:s=64x64:r=24:d={duration}','-c:v','libx264','-threads','1',str(source)],check=True,capture_output=True,timeout=30)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    asset={'path':str(source),'sha256':digest}
    if not accepted:
        with pytest.raises(ValueError,match='minimax_clip_shorter'):normalize_minimax_clip(asset,6,tmp_path/'out.mp4')
    else:
        result=normalize_minimax_clip(asset,6,tmp_path/'out.mp4')
        assert abs(float(probe(result['path'])['format']['duration'])-6)<.05
        assert result['duration_alignment']['mode']==('tail_frame_hold' if duration<6 else 'trim_tail')
        assert result['duration_alignment']['source_sha256']==digest
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
