"""Serve the workbench and a synthetic sample on a persistent local-only database."""
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
from threading import Event, Thread

from PIL import Image, ImageDraw
from starlette.staticfiles import StaticFiles
import uvicorn


ROOT = Path(__file__).resolve().parents[1]
TRIAL = ROOT / 'runtime' / 'local-trial'
STORAGE = TRIAL / 'storage'
WORKSPACE = 'local-trial'
USERNAME = 'local-trial'


def prepare():
    from app.auth import Account, password_hash
    from app.db import Record, Session, initialize

    initialize()
    with Session.begin() as session:
        credentials = TRIAL / 'login.txt'
        if not session.get(Account, USERNAME):
            password = secrets.token_urlsafe(18)
            credentials.write_text(password + '\n', encoding='utf-8')
            session.add(Account(username=USERNAME, workspace=WORKSPACE, password_hash=password_hash(password)))
        if session.get(Record, 'trial-work'):
            return

        poster = STORAGE / 'trial-poster.png'
        picture = Image.new('RGB', (360, 480), '#ebf2ef')
        draw = ImageDraw.Draw(picture)
        draw.rounded_rectangle((100, 132, 260, 340), radius=42, fill='#365e59')
        draw.rectangle((0, 450, 359, 479), fill='black')
        draw.text((12, 458), 'AI GENERATED - INTERNAL SAMPLE', fill='white')
        picture.save(poster)
        clip = STORAGE / 'trial-video.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-loop', '1', '-i', str(poster),
            '-t', '3', '-vf', 'pad=360:640:0:80', '-pix_fmt', 'yuv420p', '-c:v', 'libx264',
            '-threads', '2', '-movflags', '+faststart', str(clip)], check=True, timeout=30)

        def add(identifier, kind, **data):
            session.add(Record(id=identifier, kind=kind, workspace=WORKSPACE, data=data))

        add('trial-sku', 'sku', name='合成测试商品', merchant_sku='LOCAL-001', model='LOCAL-001',
            color='深绿', specification='单规格', current_profile_id='trial-profile')
        add('trial-profile', 'profile', sku_id='trial-sku', status='confirmed', facts={'name':'合成测试商品'})
        add('trial-work', 'work', sku_id='trial-sku', profile_id='trial-profile', platforms=['douyin'],
            duration_seconds=3, status='partial', missing_items=['douyin/poster'], current_result='trial-result')
        add('trial-result', 'result_revision', work_id='trial-work', result_number=1,
            assets=['trial-video'], copy={'douyin':{'title':'三秒看清商品外观', 'body':'本地合成测试素材',
                'narration':'查看合成商品外观', 'poster_title':'商品外观', 'selling_points':[]}})
        add('trial-video', 'asset', work_id='trial-work', media_kind='video', slot='douyin',
            object_key=clip.name, sha256=hashlib.sha256(clip.read_bytes()).hexdigest(),
            sample_marked=True, review='approved', extension='.mp4')


def main():
    STORAGE.mkdir(parents=True, exist_ok=True)
    os.environ['DATABASE_URL'] = 'sqlite:///' + (TRIAL / 'app.db').as_posix()
    os.environ['AIGC_STORAGE_ROOT'] = str(STORAGE)
    os.environ.pop('AIGC_PIPELINE_CONFIG', None)
    os.environ.pop('AIGC_RULESET_FILE', None)
    sys.path[:0] = [str(ROOT / 'apps' / name) for name in ('api', 'worker')]
    from app.main import app
    from app.job_repository import JobRepository
    from marketing_worker.runner import run_with_heartbeat
    from marketing_worker.business import configured_services
    from uuid import uuid4

    build = ROOT / 'apps/web/dist'
    app.state.readiness_static_root = build
    instance = uuid4().hex
    app.state.readiness_worker_instance = instance
    app.mount('/', StaticFiles(directory=build, html=True))
    prepare()
    stop = Event()
    worker = Thread(target=run_with_heartbeat, args=(JobRepository(), instance, stop, STORAGE, configured_services), daemon=True)
    worker.start()
    try:
        uvicorn.run(app, host='127.0.0.1', port=4174, access_log=False)
    finally:
        stop.set()
        worker.join(timeout=2)


if __name__ == '__main__':
    main()
