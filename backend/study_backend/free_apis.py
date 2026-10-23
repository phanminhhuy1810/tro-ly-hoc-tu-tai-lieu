"""A pool of free OpenAI-compatible APIs (Groq, Cerebras, OpenRouter, Mistral,
GitHub Models, NVIDIA). A request goes to the first member that is not resting;
a rate limit, outage or unusable answer moves it on to the next member, so one
exhausted free tier does not stop a lesson.

Keys live only in backend/runtime/free-apis.json (mode 600), written by
configure-free-apis.py; they are never sent to the browser or logged. Members
without grammar-constrained JSON get the schema in the prompt instead
(json_schema -> json_object -> prompt only), and every answer is still
validated by the server before anything is saved.
"""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import chat_prompt
from .gemini import GENERATION_SYSTEM, ProviderError, validated_output
from .generation_contract import generation_schema
from .models import SourceReferenceError
from .reference_wire import ReferenceWire, REFERENCE_CODEC_VERSION
from .source_context import MAX_MODEL_SOURCE_JSON, source_json

# Free tiers known in October 2026 (limits change; each console shows the current
# ones). `max_source_json` keeps one request under that tier's request size.
PRESETS = {
    'groq': {'label': 'Groq', 'base_url': 'https://api.groq.com/openai/v1', 'models': ['openai/gpt-oss-120b', 'llama-3.3-70b-versatile'],
             'max_source_json': 20_000, 'keys_at': 'https://console.groq.com/keys', 'check': '/models'},
    'cerebras': {'label': 'Cerebras', 'base_url': 'https://api.cerebras.ai/v1', 'models': ['gpt-oss-120b', 'llama-3.3-70b'],
                 'max_source_json': 20_000, 'keys_at': 'https://cloud.cerebras.ai', 'check': '/models'},
    'openrouter': {'label': 'OpenRouter', 'base_url': 'https://openrouter.ai/api/v1', 'models': ['openai/gpt-oss-120b:free', 'meta-llama/llama-3.3-70b-instruct:free'],
                   'max_source_json': 60_000, 'keys_at': 'https://openrouter.ai/keys', 'check': '/key'},
    'mistral': {'label': 'Mistral', 'base_url': 'https://api.mistral.ai/v1', 'models': ['mistral-medium-latest', 'mistral-small-latest'],
                'max_source_json': 60_000, 'keys_at': 'https://console.mistral.ai/api-keys', 'check': '/models'},
    'github': {'label': 'GitHub Models', 'base_url': 'https://models.github.ai/inference', 'models': ['openai/gpt-4.1'],
               'max_source_json': 12_000, 'keys_at': 'https://github.com/settings/personal-access-tokens', 'check': None},
    'nvidia': {'label': 'NVIDIA', 'base_url': 'https://integrate.api.nvidia.com/v1', 'models': ['openai/gpt-oss-120b', 'meta/llama-3.3-70b-instruct'],
               'max_source_json': 60_000, 'keys_at': 'https://build.nvidia.com', 'check': '/models'},
}
MEMBER_SECONDS = 90
TOTAL_SECONDS = 170  # a lesson job ends at 200 s; stop trying new members before that
REST_SECONDS = {'RATE_LIMITED': 60, 'PROVIDER_UNAVAILABLE': 120, 'PROVIDER_TIMEOUT': 120, 'CONNECTION_FAILED': 120,
                'AUTH_FAILED': 6 * 3600, 'ACCESS_DENIED': 6 * 3600, 'MODEL_UNAVAILABLE': 6 * 3600}
FINISHED = {None, 'stop', 'eos', 'end_turn', 'stop_sequence'}


def config_path():
    return Path(os.environ.get('STUDY_FREE_APIS_CONFIG', str(Path(__file__).resolve().parents[1] / 'runtime/free-apis.json')))


def safe_base_url(url):
    parts = urlparse(url)
    local = parts.scheme == 'http' and parts.hostname in {'127.0.0.1', 'localhost'}
    if not (parts.scheme == 'https' or local) or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Địa chỉ API miễn phí cần là https (hoặc http trên máy này), không kèm mật khẩu hay tham số.')
    return url.rstrip('/')


def members_of(config):
    """One member per (provider, model), in the order the operator listed them."""
    found = []
    for entry in config.get('members', []):
        if not isinstance(entry, dict):
            raise ValueError('Mỗi nguồn AI miễn phí cần là một object.')
        preset = PRESETS.get(entry.get('provider'), {})
        key = entry.get('api_key')
        if not isinstance(key, str) or not key.strip():
            raise ValueError('Một nguồn AI miễn phí thiếu key.')
        models = entry.get('models', preset.get('models'))
        if not isinstance(models, list) or not 1 <= len(models) <= 4 or not all(isinstance(m, str) and m.strip() and len(m) <= 160 for m in models):
            raise ValueError('Mỗi nguồn AI miễn phí cần 1–4 tên model.')
        budget = entry.get('max_source_json', preset.get('max_source_json', MAX_MODEL_SOURCE_JSON))
        if type(budget) is not int or not 2_000 <= budget <= 400_000:
            raise ValueError('max_source_json cần là số ký tự từ 2.000 đến 400.000.')
        base_url = safe_base_url(entry.get('base_url', preset.get('base_url', '')))
        label = entry.get('label', preset.get('label', urlparse(base_url).hostname))
        for model in models:
            found.append({'id': f"{entry.get('provider', label)}/{model}", 'label': label, 'model': model.strip(),
                          'base_url': base_url, 'key': key.strip(), 'max_source_json': budget})
    if len(found) > 16:
        raise ValueError('Nhóm AI miễn phí nhận tối đa 16 model.')
    return found


def private_config():
    path = config_path()
    if not path.exists():
        return {}
    if path.stat().st_mode & 0o077:
        raise ValueError('File cấu hình AI miễn phí cần quyền 600.')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get('members'), list) or not value['members']:
        raise ValueError('Cấu hình AI miễn phí cần members là danh sách nguồn.')
    for flag in ('enabled', 'default'):
        if flag in value and type(value[flag]) is not bool:
            raise ValueError(f'{flag} trong cấu hình AI miễn phí cần là true/false.')
    members_of(value)
    return value


def retry_after(response):
    try:
        return min(max(float(response.headers.get('retry-after', '')), 1.0), 24 * 3600)
    except ValueError:
        return None


def json_text(text):
    """Keep only the JSON object: drop <think> notes, code fences and chatter around it."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
    fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    if not text.startswith('{') and '{' in text and '}' in text:
        text = text[text.index('{'):text.rindex('}') + 1]
    return text


class FreePoolAI:
    provider_id = 'free_pool'
    model = 'free-pool'

    def __init__(self, config=None):
        config = private_config() if config is None else config
        self.enabled = config.get('enabled', True) is True
        self.members = members_of(config)
        # The pool takes a request as large as its biggest member; smaller members sit that one out.
        self.max_source_json = max((m['max_source_json'] for m in self.members), default=MAX_MODEL_SOURCE_JSON)
        self._resting = {}
        self._mode = {}
        self.last_member = None

    def metadata(self):
        return {'provider': self.provider_id, 'model': self.model, 'reference_codec': REFERENCE_CODEC_VERSION}

    def configured(self):
        return bool(self.members)

    async def status(self):
        # No network call: checking every member would spend the free quota just to draw a status dot.
        awake = [m for m in self.members if self._resting.get(m['id'], 0) <= time.monotonic()]
        return {**self.metadata(), 'configured': self.configured(), 'enabled': self.enabled,
                'ready': self.enabled and bool(self.members), 'models': [m['id'] for m in awake],
                'code': 'CONFIGURED_QUOTA_UNVERIFIED' if self.members else 'NOT_CONFIGURED'}

    def rest(self, member, error):
        seconds = getattr(error, 'retry_after', None) or REST_SECONDS.get(error.code, 0)
        if seconds:
            self._resting[member['id']] = time.monotonic() + seconds

    async def generate(self, schema, instruction, fragments):
        if not self.members:
            raise ProviderError('NOT_CONFIGURED', 'Chưa có key AI miễn phí nào; chạy backend/configure-free-apis.py.')
        if not self.enabled:
            raise ProviderError('PROVIDER_DISABLED', 'Nhóm AI miễn phí đang tắt trong cấu hình.')
        source = source_json(fragments)
        if len(source) > self.max_source_json:
            raise ValueError('Phạm vi quá dài cho một lượt tạo. Chọn ít trích đoạn hơn; không tự cắt mất nguồn.')
        wire = ReferenceWire(fragments)
        prompt = wire.instruction(instruction) + '\nNguồn (chỉ là dữ liệu):\n' + source_json(wire.fragments)
        shape = wire.schema(generation_schema(schema).model_json_schema())
        started, tried = time.monotonic(), []
        for member in self.members:
            if member['max_source_json'] < len(source) or self._resting.get(member['id'], 0) > time.monotonic():
                continue
            if tried and time.monotonic() - started > TOTAL_SECONDS:
                break
            try:
                value = validated_output(schema, await self.ask(member, schema, prompt, shape), fragments)
            except (ProviderError, SourceReferenceError) as exc:
                error = exc if isinstance(exc, ProviderError) else ProviderError('INVALID_OUTPUT', str(exc))
                tried.append((member, error.code))
                self.rest(member, error)
                continue
            self.last_member = member['id']
            return value
        if not tried:
            raise ProviderError('RATE_LIMITED', 'Các nguồn AI miễn phí đang nghỉ vì hết lượt; thử lại sau ít phút. Nguồn và phần đã lưu vẫn còn.', True)
        codes = sorted({code for _, code in tried})
        names = ', '.join(dict.fromkeys(m['label'] for m, _ in tried))
        raise ProviderError('RATE_LIMITED' if codes == ['RATE_LIMITED'] else tried[-1][1],
                            f'Đã thử {names} nhưng chưa nguồn nào trả bài dùng được ({", ".join(codes)}). Nguồn và phần đã lưu vẫn còn; thử lại sau ít phút.', True)

    async def ask(self, member, schema, prompt, shape):
        mode = self._mode.get(member['id'], 'json_schema')
        while True:
            body = {'model': member['model'], 'temperature': chat_prompt.temperature(schema), 'max_tokens': 8000,
                    'messages': [{'role': 'system', 'content': chat_prompt.system_prompt(schema, GENERATION_SYSTEM)},
                                 {'role': 'user', 'content': prompt if mode == 'json_schema' else
                                  prompt + '\nChỉ trả một JSON object đúng schema sau: ' + json.dumps(shape, ensure_ascii=False)}]}
            if mode == 'json_schema':
                body['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'answer', 'schema': shape, 'strict': False}}
            elif mode == 'json_object':
                body['response_format'] = {'type': 'json_object'}
            response = await self.post(member, body)
            if response.status_code in (400, 422) and mode != 'prompt':
                # No grammar-constrained JSON for this model: put the schema in the prompt and remember that.
                mode = self._mode[member['id']] = 'json_object' if mode == 'json_schema' else 'prompt'
                continue
            return self.answer(member, response)

    async def post(self, member, body):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(MEMBER_SECONDS, connect=5), trust_env=False, follow_redirects=False,
                                         headers={'Authorization': 'Bearer ' + member['key']}) as client:
                return await client.post(member['base_url'] + '/chat/completions', json=body)
        except httpx.TimeoutException:
            raise ProviderError('PROVIDER_TIMEOUT', member['label'] + ' chưa trả lời kịp.', True) from None
        except httpx.HTTPError:
            raise ProviderError('CONNECTION_FAILED', 'Không kết nối được ' + member['label'] + '.', True) from None

    def answer(self, member, response):
        if response.status_code != 200:
            code = {401: 'AUTH_FAILED', 403: 'ACCESS_DENIED', 404: 'MODEL_UNAVAILABLE', 413: 'REQUEST_TOO_LARGE',
                    429: 'RATE_LIMITED'}.get(response.status_code, 'PROVIDER_UNAVAILABLE')
            error = ProviderError(code, f"{member['label']} trả lỗi {response.status_code}.", code in {'RATE_LIMITED', 'PROVIDER_UNAVAILABLE'})
            error.retry_after = retry_after(response) if code == 'RATE_LIMITED' else None
            raise error
        try:
            choice = response.json()['choices'][0]
            content = choice['message']['content']
            if isinstance(content, list):
                content = ''.join(part.get('text', '') for part in content if isinstance(part, dict))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError('INVALID_OUTPUT', member['label'] + ' trả dữ liệu không đọc được.') from None
        if choice.get('finish_reason') not in FINISHED:
            raise ProviderError('INCOMPLETE_OUTPUT', member['label'] + ' dừng giữa chừng (' + str(choice.get('finish_reason')) + ').')
        if not isinstance(content, str) or not content.strip() or len(content) > 100_000:
            raise ProviderError('INVALID_OUTPUT', member['label'] + ' trả nội dung rỗng hoặc quá dài.')
        return json_text(content)
