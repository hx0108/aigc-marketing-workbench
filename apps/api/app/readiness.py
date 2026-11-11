"""Read-only readiness checks for the HTTP service and its local dependencies."""
from html.parser import HTMLParser
import os
from pathlib import Path
from shutil import disk_usage

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


class ViteAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        url = attributes.get('src') if tag == 'script' else attributes.get('href') if tag == 'link' else None
        if url and url.startswith('/') and not url.startswith('//'):
            self.paths.append(url.lstrip('/'))


def database_ready(session):
    try:
        return session.execute(text('SELECT 1')).scalar_one() == 1
    except (SQLAlchemyError, OSError):
        return False


def storage_ready(root):
    try:
        return root.is_dir() and os.access(root, os.R_OK | os.W_OK | os.X_OK) and disk_usage(root).free > 0
    except OSError:
        return False


def static_ready(root):
    if root is None:
        return True
    try:
        root = Path(root).resolve()
        parser = ViteAssets()
        parser.feed((root / 'index.html').read_text(encoding='utf-8'))
        if not any(path.startswith('assets/') and path.endswith('.js') for path in parser.paths):
            return False
        paths = [(root / path).resolve() for path in parser.paths]
        return all(path.is_relative_to(root) and path.is_file() and path.stat().st_size > 0 for path in paths)
    except (OSError, UnicodeError, ValueError):
        return False


def is_ready(session, storage_root, static_root=None):
    return database_ready(session) and storage_ready(storage_root) and static_ready(static_root)
