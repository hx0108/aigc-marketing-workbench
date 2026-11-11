"""Explicit composition root; never loads credentials from arbitrary desktop files."""
from .http_providers import DeepSeek, MiniMaxHailuoFast, MiniMaxImage, MiniMaxVideo, QwenTTS
from app.pricing import HAILUO_FAST_MODEL
from .persistence import AuthorizedServices


REQUIRED = {'text', 'product_image', 'dynamic', 'tts', 'video_render', 'poster_render'}

def provider_adapters(video_model):
    return {'text':DeepSeek,'image':MiniMaxImage,'video':MiniMaxHailuoFast if video_model==HAILUO_FAST_MODEL else MiniMaxVideo,'tts':QwenTTS}

def build_providers(config, environment, client=None):
    result = {}
    adapters=provider_adapters(config['video']['model'])
    for kind, key in [('text','DEEPSEEK_API_KEY'),('image','MINIMAX_API_KEY'),('video','MINIMAX_API_KEY'),('tts','DASHSCOPE_API_KEY')]:
        selected = config[kind]
        result[kind] = adapters[kind](environment[key], selected['base_url'], selected['model'], client,parameters=selected.get('parameters'))
    return result


def service_factory(sessions, configuration, policy_factory, handler_factory):
    """Only a trusted server configuration may enable calls, never request payload."""
    def create(job):
        if not configuration.get('enabled'):
            raise ValueError('pipeline_not_enabled')
        handlers = handler_factory(job)
        if not REQUIRED <= handlers.keys():
            raise ValueError('pipeline_handlers_incomplete')
        service=AuthorizedServices(sessions, configuration['budget_id'], policy_factory(job), handlers,
                                  configuration['bounds'], job['id'], job['workspace'], job['fencing_token'])
        service.provider_parameters={key:provider.parameters for key,provider in configuration['providers'].items()}
        return service
    return create
