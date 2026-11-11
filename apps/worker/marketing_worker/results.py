import base64
import binascii
import json
import time
from .http_providers import ExternalUnknown, ProviderRejected

def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate_json_key')
        result[key]=value
    return result

def reject_constant(value):
    raise ValueError('nonfinite_json_number')


def text_result(response):
    try:
        choice = response['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('incomplete')
        return json.loads(choice['message']['content'],object_pairs_hook=unique_object,parse_constant=reject_constant)
    except (KeyError, IndexError, TypeError, ValueError):
        raise ProviderRejected('Invalid structured copy response') from None


def image_url(response):
    try:
        return response['data'][0]['url']
    except (KeyError, IndexError, TypeError):
        raise ProviderRejected('Image result missing') from None


def image_bytes(response):
    try:
        encoded = response['data']['image_base64']
        if not isinstance(encoded, list) or len(encoded) != 1:
            raise ValueError()
        item = encoded[0]
        if not isinstance(item, str) or not 0 < len(item) <= 28 * 1024 * 1024:
            raise ValueError()
        return base64.b64decode(item, validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise ProviderRejected('Invalid MiniMax image result') from None


def audio_url(response):
    try:
        url = response['output']['audio']['url']
        from urllib.parse import urlsplit, urlunsplit
        if not isinstance(url, str):
            raise TypeError()
        parsed = urlsplit(url)
        # DashScope returns this exact signed origin with HTTP despite supporting TLS.
        if (parsed.scheme == 'http' and parsed.hostname == 'dashscope-result-bj.oss-cn-beijing.aliyuncs.com'
                and parsed.netloc == parsed.hostname and not parsed.fragment):
            return urlunsplit(('https', parsed.netloc, parsed.path, parsed.query, ''))
        return url
    except (KeyError, TypeError):
        raise ProviderRejected('Audio result missing') from None


def await_video(provider, external_id, save_status, canceled, timeout=600, interval=3):
    """Query only a persisted external ID; never submit a replacement task."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if canceled():
            raise ExternalUnknown('Canceled locally; remote outcome still requires reconciliation')
        response = provider.query(external_id)
        status = response.get('status')
        save_status(external_id, response)
        if status == 'succeeded':
            try:
                return response['content']['video_url']
            except (KeyError, TypeError):
                raise ExternalUnknown('Succeeded task has no downloadable video') from None
        if status in ('failed', 'expired', 'canceled'):
            raise ProviderRejected('Remote video task did not succeed')
        if status not in ('queued', 'running'):
            raise ExternalUnknown('Unknown remote state')
        time.sleep(interval)
    raise ExternalUnknown('Remote task polling deadline exceeded')
