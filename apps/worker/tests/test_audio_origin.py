from marketing_worker.results import audio_url


def test_upgrade_only_known_dashscope_origin_preserves_signed_query():
    value='http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a.wav?signature=example'
    assert audio_url({'output':{'audio':{'url':value}}}) == value.replace('http:', 'https:', 1)


def test_other_origins_are_not_upgraded_or_trusted():
    for value in ('http://evil.example/a.wav', 'http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com.evil.example/a', 'http://user@dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a', 'http://dashscope-result-bj.oss-cn-beijing.aliyuncs.com:80/a'):
        assert audio_url({'output':{'audio':{'url':value}}}) == value
