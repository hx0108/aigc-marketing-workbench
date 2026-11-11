from types import SimpleNamespace

import pytest
from fastapi import Request
from sqlalchemy import select

from app import db, sources
from test_core import client


@pytest.mark.parametrize('available,expected',[
    ([107],507),                        # The declared eight bytes do not fit above the floor.
    ([108,108,103],507),                # First chunk fits; the second would breach the floor.
    ([108,108,104,100],201),            # Exactly the remaining floor is allowed.
])
def test_upload_capacity_respects_media_disk_floor(client,tmp_path,monkeypatch,available,expected):
    monkeypatch.setenv('AIGC_MIN_FREE_DISK_BYTES','100')
    monkeypatch.setattr(sources,'ROOT',tmp_path)
    previous=tmp_path/'other-source'
    previous.write_bytes(b'already stored')
    login=client.post('/api/v1/sessions',json={'username':'tester','password':'test-password-123'})
    csrf={'X-CSRF-Token':login.json()['csrf_token']}
    sku=client.post('/api/v1/skus',json={'name':'fixture','model':'fixture'},headers=csrf).json()['id']
    checks=iter(available)
    partial_sizes=[]

    def disk_usage(root):
        assert root==tmp_path
        partial_sizes.append([path.stat().st_size for path in root.iterdir() if path!=previous])
        return SimpleNamespace(free=next(checks))

    async def stream(request):
        yield b'abcd'
        yield b'efgh'
        yield b''

    monkeypatch.setattr(sources,'disk_usage',disk_usage)
    monkeypatch.setattr(Request,'stream',stream)
    result=client.post(f'/api/v1/skus/{sku}/sources',content=b'abcdefgh',headers={
        **csrf,'X-Filename':'fixture.txt','X-Rights-Confirmed':'true',
    })
    assert result.status_code==expected
    assert previous.read_bytes()==b'already stored'
    with db.Session() as session:
        assert session.scalars(select(db.Record).where(db.Record.kind=='upload_reservation')).all()==[]
        stored=session.scalars(select(db.Record).where(db.Record.kind=='source')).all()
        if expected==507:
            assert result.json()['detail']['code']=='STORAGE_CAPACITY_INSUFFICIENT'
            assert stored==[] and list(tmp_path.iterdir())==[previous]
        else:
            assert len(stored)==1 and (tmp_path/stored[0].data['object_key']).read_bytes()==b'abcdefgh'
    if len(available)>1:
        assert partial_sizes[:3]==[[],[0],[4]]
