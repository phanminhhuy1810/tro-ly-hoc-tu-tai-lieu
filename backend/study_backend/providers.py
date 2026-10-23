"""Server-owned model catalogue, private user preferences, and per-job binding."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from fastapi import Depends, HTTPException
from pydantic import Field

from .ai import KaggleAI, LocalAI, configured_ai
from .gemini import GeminiAI, ProviderError, private_config
from .models import Model
from .job_progress import request_progress
from .source_context import MAX_MODEL_SOURCE_JSON


@dataclass(frozen=True)
class Choice:
    id: str
    label: str
    client: object
    external: bool = False

    def metadata(self):
        fn = getattr(self.client, 'metadata', None)
        return fn() if fn else {'provider': type(self.client).__name__, 'model': getattr(self.client, 'model', 'unreported_test_adapter')}

    def enabled(self):
        return getattr(self.client, 'enabled', True)

    def configured(self):
        fn = getattr(self.client, 'configured', None)
        return fn() if fn else True


class ProviderRegistry:
    def __init__(self, choices, default_id):
        self.choices = {x.id: x for x in choices}
        if len(self.choices) != len(choices) or default_id not in self.choices:
            raise ValueError('Danh sách model cần ID riêng và một mặc định đã cấu hình.')
        self.default_id = default_id
        self.database = None
        self._bound = ContextVar('study_ai_choice', default=None)
        self._status_cache = {}
        self._outcomes = {}

    def record_outcome(self, model_id, error=None):
        self._outcomes[model_id] = {'last_request_status': 'failed' if error else 'succeeded',
                                    'last_error_code': getattr(error, 'code', 'INVALID_OUTPUT') if error else None}
        self._status_cache.pop(model_id, None)

    def preference(self, owner):
        if owner:
            with self.database.connection() as db:
                row = db.execute('SELECT * FROM ai_preferences WHERE owner_id=?', (owner,)).fetchone()
            if row:
                return {'model_id': row['model_id'], 'revision': row['revision'], 'updated_at': row['updated_at'], 'allow_external': bool(row['allow_external'])}
        return {'model_id': self.default_id, 'revision': 0, 'updated_at': None,
                'allow_external': self.choices[self.default_id].external}

    def resolve(self, owner):
        pref = self.preference(owner)
        choice = self.choices.get(pref['model_id'])
        if choice is None:
            raise HTTPException(503, {'code': 'MODEL_REMOVED', 'message': 'Model đã chọn không còn được cấu hình; chọn nguồn khác. Nội dung đã lưu vẫn còn.'})
        if not choice.enabled() or not choice.configured():
            raise HTTPException(503, {'code': 'PROVIDER_DISABLED', 'message': 'Model đã chọn chưa được bật hoặc thiếu cấu hình; không tự đổi model.'})
        if choice.external and not pref['allow_external']:
            raise HTTPException(409, 'Xác nhận gửi trích đoạn sang nguồn AI ngoài máy trước khi sử dụng.')
        return choice, pref

    def source_budget(self, owner):
        """Source characters one request to this learner's model may carry."""
        choice, _ = self.resolve(owner)
        return getattr(choice.client, 'max_source_json', MAX_MODEL_SOURCE_JSON)

    def identity_metadata(self, owner):
        choice, pref = self.resolve(owner)
        return choice.id, {**choice.metadata(), 'model_choice_id': choice.id, 'selection_revision': pref['revision']}

    @contextmanager
    def pin(self, model_id):
        if model_id not in self.choices:
            raise ProviderError('MODEL_REMOVED', 'Model của job không còn được cấu hình; chưa đổi sang model khác.')
        token = self._bound.set(model_id)
        try:
            yield
        finally:
            self._bound.reset(token)

    def bound_client(self):
        choice = self.choices.get(self._bound.get())
        if choice is None:
            raise RuntimeError('AI request needs an explicitly pinned job model.')
        return choice.client

    async def generate(self, schema, instruction, fragments):
        from .generation_contract import QuestionRejected
        if any(f.get('locator',{}).get('unreadable_math') for f in fragments):
            raise ProviderError('SOURCE_REVIEW_REQUIRED','Phạm vi còn công thức Office Math chưa đọc được. Sửa tay trong bản trích hoặc bỏ đoạn đó khỏi phạm vi; chưa gọi AI để đoán.',False)
        client = self.bound_client()
        progress = request_progress(schema.__name__, hasattr(client, 'generate_stream'))
        try:
            if progress and hasattr(client, 'generate_stream'):
                result = await client.generate_stream(schema, instruction, fragments, progress)
            else:
                result = await client.generate(schema, instruction, fragments)
        except QuestionRejected:
            if progress:progress.rejected()
            raise
        if progress: progress.received()
        return result

    async def transcribe_image(self, image):
        client = self.bound_client()
        if not hasattr(client, 'transcribe_image'):
            raise ProviderError('CAPABILITY_UNAVAILABLE', 'Model này chưa có bộ đọc ảnh; sửa tay và bản trích đã lưu vẫn dùng được.')
        progress = request_progress('VisionText', False)
        value = await client.transcribe_image(image)
        if progress: progress.received()
        return value

    async def choice_status(self, choice, refresh=False):
        cached = self._status_cache.get(choice.id)
        if not refresh and cached and time.monotonic() - cached[0] < 10:
            return {**cached[1], **self._outcomes.get(choice.id, {})}
        try:
            status = await asyncio.wait_for(choice.client.status(), timeout=6)
            # Only allow known public fields. Never forward arbitrary provider payloads.
            value = {**choice.metadata(), 'ready': bool(status.get('ready')),
                     **{k: status[k] for k in ['code', 'generation_verified'] if k in status}}
        except (Exception, asyncio.TimeoutError):
            value = {**choice.metadata(), 'ready': False, 'code': 'UNAVAILABLE'}
        self._status_cache[choice.id] = (time.monotonic(), value)
        return {**value, **self._outcomes.get(choice.id, {})}

    async def status(self, owner=None):
        pref = self.preference(owner)
        choice = self.choices.get(pref['model_id'])
        if not choice:
            return {'ready': False, 'model_choice_id': pref['model_id'], 'code': 'MODEL_REMOVED'}
        return {**await self.choice_status(choice), 'model_choice_id': choice.id, 'selection_revision': pref['revision']}

    async def catalog(self, owner):
        pref = self.preference(owner)
        choices = list(self.choices.values())
        statuses = await asyncio.gather(*(self.choice_status(c) for c in choices))
        models = []
        for choice, status in zip(choices, statuses):
            enabled, configured = bool(choice.enabled()), bool(choice.configured())
            models.append({**status, 'id': choice.id, 'label': choice.label, 'external': choice.external,
                           'configured': configured, 'enabled': enabled,
                           'selectable': enabled and configured and status['ready'],
                           'capabilities': {'text': True, 'image_review_adapter': hasattr(choice.client, 'transcribe_image')},
                           'data_destination': 'external_provider' if choice.external else 'this_machine'})
        return {'default_model_id': self.default_id, 'selected_model_id': pref['model_id'],
                'selection_revision': pref['revision'], 'models': models,
                'unsupported': [{'id': 'cursor', 'selectable': False, 'reason': 'Cursor Cloud Agents API điều khiển agent trên repository; chưa phải adapter sinh bài/chat cho sản phẩm này.'}]}


def local_models():
    """An explicit server allowlist persists across starts; never downloads a model."""
    if 'STUDY_LOCAL_MODELS' in os.environ:
        extra=[name.strip() for name in os.environ['STUDY_LOCAL_MODELS'].split(',') if name.strip()]
    else:
        path=Path(os.environ.get('STUDY_LOCAL_MODELS_CONFIG',str(Path(__file__).resolve().parents[1]/'runtime/local-models.json')))
        extra=[]
        if path.exists():
            if path.stat().st_mode & 0o077:
                raise ValueError('File danh sách model local cần quyền 600.')
            try:
                value=json.loads(path.read_text())
                if not isinstance(value,dict) or set(value)!={'models'} or not isinstance(value['models'],list):raise ValueError()
                extra=value['models']
            except (OSError,UnicodeError,ValueError) as exc:
                raise ValueError('Danh sách model local chưa hợp lệ; dùng JSON chỉ gồm models là danh sách tên.') from exc
    models=[LocalAI.model]+extra
    if any(not isinstance(name,str) or not name or len(name)>160 or any(c.isspace() or ord(c)<32 for c in name) for name in models):
        raise ValueError('Tên model local cần là tên đã cài, không chứa khoảng trắng hoặc ký tự điều khiển.')
    models=list(dict.fromkeys(models))
    if len(models)>8:raise ValueError('Danh sách local chỉ nhận tối đa 8 model, gồm model gốc.')
    return models


def configured_registry(injected=None):
    if injected is not None:
        return ProviderRegistry([Choice('injected', 'Injected test adapter', injected)], 'injected')
    primary = configured_ai()
    choices = []
    models = local_models()
    for model in models:
        client = LocalAI(); client.model = model
        choices.append(Choice('local:' + model, model + ' · máy này', client))
    if isinstance(primary, KaggleAI):
        kaggle = primary
    else:
        path = Path(os.environ.get('STUDY_KAGGLE_CONFIG', str(Path(__file__).resolve().parents[1] / 'runtime/kaggle-private.json')))
        kaggle = None
        if path.is_file():
            if path.stat().st_mode & 0o077:
                raise ValueError('File cấu hình Kaggle cần quyền 600.')
            kaggle = KaggleAI(json.loads(path.read_text()))
    if kaggle:
        choices.append(Choice('kaggle:' + kaggle.model, kaggle.model + ' · Kaggle', kaggle, True))
    gemini_models = list(dict.fromkeys(m.strip() for m in os.environ.get('STUDY_GEMINI_MODELS', ','.join(private_config().get('models', ['gemini-2.5-flash']))).split(',') if m.strip()))
    if not 1 <= len(gemini_models) <= 8:
        raise ValueError('STUDY_GEMINI_MODELS cần 1–8 tên model.')
    for model in gemini_models:
        choices.append(Choice('gemini:' + model, model + ' · Gemini API', GeminiAI(model), True))
    default_id = ('kaggle:' if isinstance(primary, KaggleAI) else 'local:') + primary.model
    return ProviderRegistry(choices, default_id)


class AISelection(Model):
    model_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)
    allow_external: bool = False


def register_providers(app, registry, database, user):
    @app.get('/api/ai/models')
    async def models(owner=Depends(user)):
        return await registry.catalog(owner)

    @app.put('/api/ai/selection')
    async def selection(body: AISelection, owner=Depends(user)):
        choice = registry.choices.get(body.model_id)
        if not choice:
            raise HTTPException(422, 'Chỉ chọn model có trong danh sách do server cấu hình.')
        if not choice.enabled() or not choice.configured():
            raise HTTPException(503, 'Model này chưa được người vận hành bật hoặc thiếu cấu hình.')
        if choice.external and not body.allow_external:
            raise HTTPException(422, 'Cần xác nhận gửi các trích đoạn đã chọn tới nhà cung cấp AI ngoài máy.')
        if not (await registry.choice_status(choice, refresh=True))['ready']:
            raise HTTPException(503, 'Model đang không khả dụng; chưa thay lựa chọn đã lưu hoặc dữ liệu học.')
        with database.connection(write=True) as db:
            row = db.execute('SELECT revision FROM ai_preferences WHERE owner_id=?', (owner,)).fetchone()
            version = row['revision'] if row else 0
            if version != body.expected_revision:
                raise HTTPException(409, 'Lựa chọn AI đã đổi ở nơi khác; tải lại trước khi lưu.')
            db.execute('INSERT INTO ai_preferences VALUES (?,?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET model_id=excluded.model_id,revision=excluded.revision,allow_external=excluded.allow_external,updated_at=excluded.updated_at',
                       (owner, choice.id, version + 1, int(body.allow_external), datetime.now(timezone.utc).isoformat()))
        return {'model_id': choice.id, 'revision': version + 1, **choice.metadata(), 'external': choice.external}
