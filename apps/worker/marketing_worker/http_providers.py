"""Single-attempt HTTP adapters. The caller must reserve budget before submit."""
import httpx
import json
import copy
import re


class TextInputTooLarge(ValueError):
    code = 'text_input_too_large'


class ExternalUnknown(RuntimeError):
    code = 'external_unknown'
    def __init__(self, message, status_code=None, transport_error=None):
        super().__init__(message)
        self.status_code = status_code if type(status_code) is int and 500 <= status_code <= 599 else None
        allowed = {'ConnectTimeout','ReadTimeout','WriteTimeout','PoolTimeout','ConnectError','ReadError','WriteError','CloseError','LocalProtocolError','RemoteProtocolError','ProxyError','UnsupportedProtocol','TransportError'}
        self.transport_error = transport_error if transport_error in allowed else None


class ProviderRejected(RuntimeError):
    code = 'provider_rejected'
    def __init__(self,message,status_code=None,provider_code=None):
        super().__init__(message)
        self.status_code=status_code
        self.provider_code=provider_code


class HTTPProvider:
    defaults={}
    def __init__(self, key, base_url, model, client=None, parameters=None):
        if not key or not model or not base_url.startswith('https://'):
            raise ValueError('provider_configuration_required')
        self.model = model
        self.client = client or httpx.Client(timeout=120, follow_redirects=False)
        self.base_url = base_url.rstrip('/')
        self.headers = {'Authorization': 'Bearer ' + key}
        if parameters is not None and (not isinstance(parameters,dict) or set(parameters)-set(self.defaults)):
            raise ValueError('unsupported_provider_parameter')
        self.parameters=copy.deepcopy({**self.defaults,**(parameters or {})})
        self.validate_parameters()

    def validate_parameters(self):
        pass

    def request(self, method, path, payload=None):
        try:
            response = self.client.request(method, self.base_url + path, headers=self.headers, json=payload)
        except httpx.TransportError as error:
            raise ExternalUnknown('Provider response unavailable; do not resubmit', transport_error=type(error).__name__) from None
        if response.status_code >= 500:
            raise ExternalUnknown('Provider outcome uncertain', status_code=response.status_code)
        if not 200 <= response.status_code < 300:
            provider_code=None
            try:
                body=response.json()
                error=body.get('error',{}) if isinstance(body,dict) else {}
                value=error.get('code') if isinstance(error,dict) else None
                if isinstance(value,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}',value):provider_code=value
            except ValueError:
                pass
            raise ProviderRejected('Provider rejected request',response.status_code,provider_code)
        try:
            return response.json()
        except ValueError:
            raise ExternalUnknown('Invalid provider response') from None


class DeepSeek(HTTPProvider):
    defaults={'max_input_bytes':16384,'max_tokens':1024,'thinking':{'type':'disabled'}}
    def validate_parameters(self):
        for key,maximum in [('max_input_bytes',16384),('max_tokens',4096)]:
            value=self.parameters[key]
            if type(value) is not int or not 1<=value<=maximum:raise ValueError('invalid_text_limit')
        if self.parameters['thinking']!={'type':'disabled'}:raise ValueError('thinking_not_supported')
    def submit(self, messages, max_tokens=None):
        if len(json.dumps(messages,ensure_ascii=False).encode('utf-8'))>self.parameters.get('max_input_bytes',16384):raise TextInputTooLarge('text_input_too_large')
        limit=self.parameters.get('max_tokens',1024)
        if max_tokens is None:max_tokens=limit
        if not isinstance(max_tokens,int) or isinstance(max_tokens,bool) or not 1<=max_tokens<=limit:raise ValueError('output_token_limit')
        return self.request('POST', '/chat/completions', {'model': self.model, 'messages': messages, 'max_tokens': max_tokens, 'thinking':{'type':'disabled'},'response_format': {'type': 'json_object'}})


class MiniMaxImage(HTTPProvider):
    defaults = {'aspect_ratio': '9:16', 'n': 1, 'response_format': 'base64',
                'prompt_optimizer': False, 'aigc_watermark': True}

    def validate_parameters(self):
        if (self.model != 'image-01' or self.parameters != self.defaults or
            type(self.parameters['n']) is not int or
            self.parameters['prompt_optimizer'] is not False or
            self.parameters['aigc_watermark'] is not True):
            raise ValueError('unsupported_minimax_image_configuration')

    def submit(self, prompt):
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 1500:
            raise ValueError('invalid_minimax_image_prompt')
        response = self.request('POST', '/v1/image_generation', {
            'model': self.model, 'prompt': prompt, **self.parameters})
        try:
            code = response['base_resp']['status_code']
        except (KeyError, TypeError):
            raise ExternalUnknown('Missing MiniMax image response status') from None
        if type(code) is not int:
            raise ExternalUnknown('Invalid MiniMax image response status')
        if code in (1000, 1001, 1013):
            raise ExternalUnknown('MiniMax image outcome uncertain')
        if code != 0:
            raise ProviderRejected('MiniMax rejected image request', 200, str(code))
        return response


class MiniMaxVideo(HTTPProvider):
    defaults = {'resolution': '768P', 'ratio': 'adaptive', 'aigc_watermark': True}

    def validate_parameters(self):
        if (self.model != 'MiniMax-H3' or self.parameters != self.defaults or
            self.parameters['aigc_watermark'] is not True):
            raise ValueError('unsupported_minimax_video_configuration')

    def submit(self, content, duration=5):
        from app.pricing import minimax_video_seconds
        seconds = minimax_video_seconds(duration)
        if (len(content) != 2 or content[0].get('type') != 'text' or
            content[1].get('type') != 'image_url'):
            raise ValueError('minimax_video_requires_one_first_frame')
        first_frame = {**content[1], 'role': 'first_frame'}
        response = self.request('POST', '/v2/video_generation', {
            'model': self.model, 'content': [content[0], first_frame],
            'duration': seconds, **self.parameters})
        task_id = response.get('task_id') if isinstance(response, dict) else None
        if not isinstance(task_id, str) or not re.fullmatch(r'[0-9]{1,32}', task_id):
            raise ExternalUnknown('Invalid MiniMax video task ID')
        return {'id': task_id, 'model': self.model}

    def query(self, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r'[0-9]{1,32}', task_id):
            raise ValueError('invalid_task_id')
        response = self.request('GET', '/v2/query/video_generation/' + task_id)
        try:
            task = response['task']
            if task['id'] != task_id or task['model'] != self.model:
                raise ValueError()
            status = task['status']
            normalized = {'id': task_id, 'model': self.model, 'status': status}
            if status == 'succeeded':
                normalized['content'] = {'video_url': task['content']['url']}
                normalized['usage'] = task.get('usage')
            if status == 'cancelled':
                normalized['status'] = 'canceled'
            return normalized
        except (KeyError, TypeError, ValueError):
            raise ExternalUnknown('Invalid MiniMax video status') from None


class MiniMaxHailuoFast(MiniMaxVideo):
    defaults = {'resolution':'768P','duration':6,'prompt_optimizer':False}

    def validate_parameters(self):
        from app.pricing import HAILUO_FAST_MODEL
        if (self.model != HAILUO_FAST_MODEL or self.base_url != 'https://api.minimax.cn'
            or self.parameters != self.defaults or self.parameters['prompt_optimizer'] is not False
            or type(self.parameters['duration']) is not int):
            raise ValueError('unsupported_minimax_video_configuration')

    @staticmethod
    def check_response(response):
        try:
            code = response['base_resp']['status_code']
        except (KeyError, TypeError):
            raise ExternalUnknown('Invalid MiniMax video response') from None
        if type(code) is not int:
            raise ExternalUnknown('Invalid MiniMax video response')
        if code:
            raise ProviderRejected('MiniMax video request rejected', 200, str(code))

    def submit(self, content, duration=6):
        import base64
        from io import BytesIO
        from PIL import Image
        from app.pricing import hailuo_fast_seconds
        hailuo_fast_seconds(duration)
        try:
            prompt, frame = content
            if prompt['type'] != 'text' or frame['type'] != 'image_url':raise ValueError()
            text = prompt['text']
            if not isinstance(text,str) or not 0 < len(text) <= 2000:raise ValueError()
            first_frame = frame['image_url']['url']
            header, encoded = first_frame.split(',', 1)
            if header not in {'data:image/png;base64','data:image/jpeg;base64','data:image/webp;base64'} or len(encoded) >= 27_000_000:raise ValueError()
            data = base64.b64decode(encoded,validate=True)
            with Image.open(BytesIO(data)) as image:
                short, long = sorted(image.size)
                if short <= 300 or 2*long >= 5*short or len(data) >= 20_000_000 or 'data:'+Image.MIME[image.format]+';base64' != header:raise ValueError()
                image.verify()
        except (AttributeError, KeyError, OSError, TypeError, ValueError):
            raise ValueError('invalid_hailuo_first_frame') from None
        response = self.request('POST','/v1/video_generation',{
            'model':self.model,'prompt':text,'first_frame_image':first_frame,**self.parameters})
        self.check_response(response)
        task_id = response.get('task_id')
        if not isinstance(task_id,str) or not re.fullmatch(r'[0-9]{1,32}',task_id):
            raise ExternalUnknown('Invalid MiniMax video task ID')
        return {'id':task_id,'model':self.model}

    def query(self, task_id):
        if not isinstance(task_id,str) or not re.fullmatch(r'[0-9]{1,32}',task_id):
            raise ValueError('invalid_task_id')
        try:
            response = self.request('GET','/v1/query/video_generation?task_id='+task_id)
            self.check_response(response)
            if response['task_id'] != task_id:raise ValueError()
            status = {'Preparing':'queued','Queueing':'queued','Processing':'running','Success':'succeeded','Fail':'failed'}[response['status']]
            result = {'id':task_id,'model':self.model,'status':status}
            if status == 'succeeded':
                file_id = response['file_id']
                if not isinstance(file_id,str) or not re.fullmatch(r'[0-9]{1,32}',file_id):raise ValueError()
                retrieved = self.request('GET','/v1/files/retrieve?file_id='+file_id)
                self.check_response(retrieved)
                file = retrieved['file']
                if str(file['file_id']) != file_id or file['purpose'] != 'video_generation':raise ValueError()
                url = file['download_url']
                if not isinstance(url,str) or not url.startswith('https://'):raise ValueError()
                result['content'] = {'video_url':url}
            return result
        except (KeyError, TypeError, ValueError, ProviderRejected):
            raise ExternalUnknown('Invalid MiniMax video status or result') from None


class QwenTTS(HTTPProvider):
    def submit(self, text, voice='Cherry'):
        if not text or len(text) > 600:
            raise ValueError('tts_text_length')
        return self.request('POST', '/services/aigc/multimodal-generation/generation', {'model': self.model, 'input': {'text': text, 'voice': voice, 'language_type': 'Chinese'}})
