"""Private, expiring Worker instance evidence shared by the API and Worker."""
from pathlib import Path
import os
from tempfile import NamedTemporaryFile
from time import time
from uuid import UUID


INTERVAL_SECONDS = 3
MAX_AGE_SECONDS = 12


def heartbeat_path(root, instance):
    return Path(root) / '.worker-heartbeats' / (UUID(str(instance)).hex + '.pulse')


def publish(root, instance):
    path = heartbeat_path(root, instance)
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        staged = Path(stream.name)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def remove(root, instance):
    heartbeat_path(root, instance).unlink(missing_ok=True)


def fresh(root, instance, *, now=None):
    try:
        modified = heartbeat_path(root, instance).stat().st_mtime
        age = (time() if now is None else now) - modified
        return 0 <= age <= MAX_AGE_SECONDS
    except (ValueError, OSError):
        return False
