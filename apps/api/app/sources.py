"""Private, bounded input storage. No source bytes are sent externally."""
from pathlib import Path
from io import BytesIO
from errno import EDQUOT, ENOSPC
from shutil import disk_usage
import hashlib, os, uuid, zipfile
from PIL import Image
from fastapi import HTTPException
ROOT=Path(os.environ.get('AIGC_STORAGE_ROOT','./storage')).resolve()
AUDIO_FORMATS={'.mp3':'mp3','.wav':'wav'}


def authorized_music(session,workspace,sku_id,record_id):
    from .db import Record
    record=session.get(Record,record_id)
    if not record or record.workspace!=workspace or record.data.get('deleting') or record.data.get('rights_confirmed') is not True:
        return None
    if record.kind=='source' and record.data.get('type')=='audio' and record.data.get('sku_id')==sku_id:
        return record
    if record.kind=='asset' and record.data.get('media_kind')=='audio':
        return record
    return None
def inspect(data, name):
    suffix=Path(name).suffix.lower()
    if suffix in {'.png','.jpg','.jpeg'}:
        try:
            with Image.open(BytesIO(data)) as im:
                if im.format not in {'JPEG','PNG'} or im.width*im.height>40000000:raise ValueError()
                im.verify()
        except Exception:raise HTTPException(422,'图片损坏或像素超限')
        return 'image'
    if suffix=='.mp4':
        import tempfile, subprocess, json
        try:
            with tempfile.TemporaryDirectory() as directory:
                media=Path(directory)/'input.mp4';media.write_bytes(data)
                result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-f','mov','-show_format','-show_streams','-of','json',str(media)],capture_output=True,timeout=30,check=True)
                info=json.loads(result.stdout)
                duration=float(info['format']['duration'])
                if not 0<duration<=120 or not any(x.get('codec_type')=='video' for x in info['streams']):raise ValueError()
        except Exception:raise HTTPException(422,'视频损坏、无视频流或超过120秒')
        return 'video'
    if suffix=='.txt':
        try:data.decode('utf-8')
        except UnicodeDecodeError:raise HTTPException(422,'TXT必须为UTF-8')
        return 'document'
    if suffix=='.pdf':
        try:
            from pypdf import PdfReader
            pdf=PdfReader(BytesIO(data))
            if pdf.is_encrypted or len(pdf.pages)>100:raise ValueError()
        except Exception:raise HTTPException(422,'PDF损坏、加密或超100页')
        return 'document'
    if suffix=='.docx':
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                if sum(x.file_size for x in z.infolist())>100*1024*1024 or 'word/document.xml' not in z.namelist():raise ValueError()
                if any('vba' in n.lower() for n in z.namelist()):raise ValueError()
        except Exception:raise HTTPException(422,'DOCX损坏或展开大小超限')
        return 'document'
    raise HTTPException(422,'目前上传支持PNG/JPEG/TXT/PDF/DOCX')
def store(data):
    key=uuid.uuid4().hex
    ROOT.mkdir(parents=True,exist_ok=True)
    target=ROOT/key
    target.write_bytes(data)
    return key,hashlib.sha256(data).hexdigest()


def storage_full():
    return HTTPException(507,detail={'code':'STORAGE_CAPACITY_INSUFFICIENT','message':'素材存储空间不足，上传未保存'})


def minimum_free_upload_space():
    try:
        minimum=int(os.environ.get('AIGC_MIN_FREE_DISK_BYTES','0'))
        if minimum<0:raise ValueError
        return minimum
    except ValueError:
        raise HTTPException(503,detail={'code':'STORAGE_CAPACITY_UNAVAILABLE','message':'暂时无法检查素材存储空间'}) from None


def require_upload_space(minimum,incoming):
    if minimum==0:
        return
    try:
        available=disk_usage(ROOT).free
    except OSError:
        raise HTTPException(503,detail={'code':'STORAGE_CAPACITY_UNAVAILABLE','message':'暂时无法检查素材存储空间'}) from None
    if available-incoming<minimum:
        raise storage_full()


async def receive_upload(request,name,declared_size):
    """Bounded streaming write; return immutable object only after validation."""
    key=uuid.uuid4().hex
    path=ROOT/key
    size=0;digest=hashlib.sha256()
    limit=(200 if name.lower().endswith('.mp4') else 30)*1024*1024
    minimum=minimum_free_upload_space()
    created=False
    try:
        ROOT.mkdir(parents=True,exist_ok=True)
        require_upload_space(minimum,declared_size)
        with path.open('xb',buffering=0) as stream:
            created=True
            async for chunk in request.stream():
                if not chunk:continue
                size+=len(chunk)
                if size>limit:raise HTTPException(413,'文件超过大小限制')
                require_upload_space(minimum,len(chunk))
                if stream.write(chunk)!=len(chunk):raise storage_full()
                digest.update(chunk)
        require_upload_space(minimum,0)
        from starlette.concurrency import run_in_threadpool
        kind=await run_in_threadpool(inspect_saved,path,name,size)
        return key,digest.hexdigest(),size,kind
    except OSError as error:
        if created:path.unlink(missing_ok=True)
        if error.errno in (ENOSPC,EDQUOT):raise storage_full() from None
        raise
    except BaseException:
        if created:path.unlink(missing_ok=True)
        raise

def inspect_saved(path,name,size):
    import subprocess,json
    suffix=Path(name).suffix.lower()
    if suffix in AUDIO_FORMATS:
        if size>20*1024*1024:raise HTTPException(413,'配乐超过20MB')
        try:
            result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-f',AUDIO_FORMATS[suffix],
                '-show_format','-show_streams','-of','json',str(path)],capture_output=True,timeout=30,check=True)
            media=json.loads(result.stdout)
            streams=media['streams']
            if (not 0<float(media['format']['duration'])<=300 or len(streams)!=1 or
                streams[0].get('codec_type')!='audio' or
                not (streams[0]['codec_name']=='mp3' if suffix=='.mp3' else streams[0]['codec_name'].startswith('pcm_'))):
                raise ValueError()
        except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError):
            raise HTTPException(422,detail={'code':'MUSIC_FORMAT_INVALID','message':'请选择不超过 5 分钟的 MP3 或 PCM WAV 配乐'}) from None
        return 'audio'
    if name.lower().endswith('.mp4'):
        try:
            result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-f','mov','-show_format','-show_streams','-of','json',str(path)],capture_output=True,timeout=30,check=True)
            media=json.loads(result.stdout)
            if not 0<float(media['format']['duration'])<=120 or not any(x.get('codec_type')=='video' for x in media['streams']):raise ValueError()
        except Exception:raise HTTPException(422,'视频损坏、无视频流或超过120秒')
        return 'video'
    kind=inspect(path.read_bytes(),name)
    if kind=='image' and size>20*1024*1024:raise HTTPException(413,'图片超过20MB')
    return kind


def authorized_video_clip(session,workspace,sku_id,source_id,start_seconds,duration):
    import json
    import subprocess
    from decimal import Decimal, InvalidOperation
    from .db import Record

    if not isinstance(source_id,str) or not 0<len(source_id)<=128 or '://' in source_id:
        raise ValueError('video_source_required')
    row=session.get(Record,source_id)
    if (not row or row.workspace!=workspace or row.kind!='source' or row.data.get('sku_id')!=sku_id
        or row.data.get('type')!='video' or row.data.get('rights_confirmed') is not True
        or row.data.get('deleting') or row.data.get('physical_deleted')):
        raise ValueError('video_source_required')
    try:
        start, length=Decimal(str(start_seconds)),Decimal(str(duration))
        if not start.is_finite() or not length.is_finite() or not 0<=start<120 or not 0<length<=120:
            raise ValueError()
    except (InvalidOperation,ValueError):
        raise ValueError('video_source_trim_invalid') from None
    try:
        path=(ROOT/row.data['object_key']).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError()
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=row.data.get('sha256'):
                raise ValueError()
    except (KeyError,OSError,TypeError,ValueError):
        raise ValueError('video_source_hash_mismatch') from None
    try:
        result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-f','mov',
            '-select_streams','v:0','-show_entries','stream=duration:stream_disposition=attached_pic',
            '-of','json',str(path)],capture_output=True,timeout=30,check=True)
        stream=json.loads(result.stdout)['streams'][0]
        available=Decimal(stream['duration'])
        if stream.get('disposition',{}).get('attached_pic') or not available.is_finite() or start+length>available:
            raise ValueError()
    except (OSError,subprocess.SubprocessError,InvalidOperation,IndexError,ValueError,KeyError,TypeError):
        raise ValueError('video_source_trim_invalid') from None
    return {'path':str(path),'sha256':row.data['sha256'],'revision':row.revision,
            'source_id':row.id,'start_seconds':float(start)}
