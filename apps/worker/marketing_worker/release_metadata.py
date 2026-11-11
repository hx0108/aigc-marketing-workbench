"""Write implicit labels to private PNG and MP4 release derivatives."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image, PngImagePlugin


def labelled_derivative(source, digest, artifact, root):
    producer = os.environ.get('AIGC_RELEASE_CONTENT_PRODUCER', '').strip()
    propagator = os.environ.get('AIGC_RELEASE_CONTENT_PROPAGATOR', '').strip()
    if not producer and not propagator:
        return source
    if not producer or not propagator:
        raise ValueError('release_identity_incomplete')
    if producer != propagator:
        raise ValueError('release_first_write_identity_mismatch')
    if max(len(producer), len(propagator)) > 256 or any(
        ord(char) < 32 for identity in (producer, propagator) for char in identity
    ):
        raise ValueError('release_identity_invalid')

    identifier = hashlib.sha256(json.dumps([artifact, digest, producer]).encode()).hexdigest()
    metadata = {
        'Label': '1', 'ContentProducer': producer, 'ProduceID': identifier,
        'ReservedCode1': '', 'ContentPropagator': propagator, 'PropagateID': identifier,
        'ReservedCode2': '',
    }
    value = json.dumps(metadata, ensure_ascii=True, separators=(',', ':'))
    output_id = hashlib.sha256(value.encode()).hexdigest()
    suffix = source.suffix.lower()
    output = Path(root) / (output_id + '-labelled' + suffix)
    with TemporaryDirectory(dir=root) as directory:
        staged = Path(directory) / output.name
        if suffix == '.png':
            tags = PngImagePlugin.PngInfo()
            tags.add_text('AIGC', '{"AIGC":' + value + '}')
            with Image.open(source) as image:
                if image.format != 'PNG':
                    raise ValueError('release_label_format_unsupported')
                image.save(staged, pnginfo=tags)
        elif suffix == '.mp4':
            subprocess.run([
                'ffmpeg', '-v', 'error', '-nostdin', '-i', str(source),
                '-map', '0', '-c', 'copy', '-metadata', 'AIGC=' + value,
                '-movflags', 'use_metadata_tags+faststart', str(staged),
            ], check=True, capture_output=True, timeout=120)
        else:
            raise ValueError('release_label_format_unsupported')
        try:
            os.link(staged, output)
        except FileExistsError:
            if hashlib.sha256(staged.read_bytes()).digest()!=hashlib.sha256(output.read_bytes()).digest():
                raise ValueError('release_label_derivative_conflict') from None
    return output
