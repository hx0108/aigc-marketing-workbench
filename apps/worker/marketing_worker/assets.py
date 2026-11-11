"""Private immutable downloads from explicitly configured provider result hosts."""
import hashlib
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse
import httpx
from PIL import Image
from .media import probe


def download(url, destination, allowed_hosts, kind, client=None, resolver=socket.getaddrinfo):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.hostname not in allowed_hosts or parsed.port not in (None, 443):
        raise ValueError('untrusted_asset_url')
    addresses = resolver(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('private_asset_address')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    client = client or httpx.Client(timeout=120, follow_redirects=False, trust_env=False)
    pinned = httpx.URL(url).copy_with(host=addresses[0][4][0])
    digest = hashlib.sha256()
    count = 0
    created = False
    try:
        with client.stream('GET', pinned, headers={'Host': parsed.hostname}, extensions={'sni_hostname': parsed.hostname.encode()}, follow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError('asset_download_failed')
            with destination.open('xb') as output:
                created = True
                for chunk in response.iter_bytes():
                    count += len(chunk)
                    if count > 200 * 1024 * 1024:
                        raise ValueError('asset_too_large')
                    digest.update(chunk)
                    output.write(chunk)
        if kind == 'image':
            with Image.open(destination) as image:
                image.verify()
        else:
            metadata = probe(destination)
            required = 'video' if kind == 'video' else 'audio'
            if not any(stream.get('codec_type') == required for stream in metadata['streams']):
                raise ValueError('asset_media_type_mismatch')
    except Exception:
        # Never remove an existing immutable object on exclusive-open failure.
        if created and destination.exists():
            destination.unlink()
        raise
    return {'path':str(destination), 'sha256':digest.hexdigest(), 'size':count}
