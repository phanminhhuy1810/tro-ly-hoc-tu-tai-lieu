"""Durable bounded job progress; streamed text is never a committed answer."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import re
import time


class JobCancelled(Exception):
    pass


_reporter = ContextVar('study_job_progress', default=None)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def initial(db, job_id):
    value = {'phase': 'queued', 'requests': [], 'preview': None, 'planned_stages': None,
             'saved_stages': 0, 'reused_stages': 0, 'started_at': None, 'completed_at': None}
    db.execute('INSERT INTO job_progress VALUES (?,?,?,?)', (job_id, 1, json.dumps(value), stamp()))


def read(db, job_id):
    row = db.execute('SELECT * FROM job_progress WHERE job_id=?', (job_id,)).fetchone()
    return {**json.loads(row['content_json']), 'version': row['version'], 'updated_at': row['updated_at']} if row else None


def write(db, job_id, value):
    db.execute('UPDATE job_progress SET version=version+1,content_json=?,updated_at=? WHERE job_id=?',
               (json.dumps(value, ensure_ascii=False), stamp(), job_id))


def terminal(db, job_id, phase):
    value = read(db, job_id)
    if value is not None:
        row = db.execute('SELECT status FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row and row[0] in {'succeeded', 'failed', 'cancelled'}:
            phase = row[0]
        value.update(phase=phase, preview=None, completed_at=stamp())
        if value.get('started_at'):
            value['elapsed_ms'] = round((datetime.now(timezone.utc) - datetime.fromisoformat(value['started_at'])).total_seconds() * 1000, 3)
        for request in value['requests']:
            if request['phase'] in {'connecting', 'receiving'}:
                request['phase'] = phase
                if request.get('started_at'):
                    request['elapsed_ms']=round(max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(request['started_at'])).total_seconds()*1000),3)
        value.pop('version', None); value.pop('updated_at', None)
        write(db, job_id, value)


def json_text_prefix(raw):
    """Read only a root-level JSON text string; never nested answers/references.

    Escape sequences and surrogate pairs may cross network chunks. Return only
    complete codepoints, without treating the partial JSON as valid output.
    """
    raw = raw.lstrip()
    if raw.startswith('```json\n'):
        raw = raw[8:]
    if not raw.startswith('{'):
        return ''
    decoder = json.JSONDecoder(); pos = 1
    try:
        while True:
            while pos < len(raw) and raw[pos].isspace(): pos += 1
            key, end = decoder.raw_decode(raw, pos)
            if not isinstance(key, str): return ''
            pos = end
            while pos < len(raw) and raw[pos].isspace(): pos += 1
            if raw[pos] != ':': return ''
            pos += 1
            while pos < len(raw) and raw[pos].isspace(): pos += 1
            if key != 'text':
                _, pos = decoder.raw_decode(raw, pos)
                while pos < len(raw) and raw[pos].isspace(): pos += 1
                if raw[pos] != ',': return ''
                pos += 1
                continue
            if raw[pos] != '"': return ''
            pos += 1; result = []
            escapes = {'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
            while pos < len(raw) and len(result) < 4000:
                ch = raw[pos]
                if ch == '"': break
                if ch == '\\':
                    pos += 1
                    if pos >= len(raw): break
                    ch = raw[pos]
                    if ch == 'u':
                        if pos + 5 > len(raw): break
                        code = int(raw[pos + 1:pos + 5], 16); pos += 4
                        if 0xD800 <= code <= 0xDBFF:
                            if pos + 7 > len(raw): break
                            if raw[pos + 1:pos + 3] != '\\u': return ''
                            low = int(raw[pos + 3:pos + 7], 16)
                            if not 0xDC00 <= low <= 0xDFFF: return ''
                            code = 0x10000 + ((code - 0xD800) << 10) + low - 0xDC00
                            pos += 6
                        elif 0xDC00 <= code <= 0xDFFF: return ''
                        ch = chr(code)
                    elif ch in escapes: ch = escapes[ch]
                    else: return ''
                elif ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF: return ''
                result.append(ch); pos += 1
            return ''.join(result)
    except (ValueError, IndexError):
        return ''


class Reporter:
    def __init__(self, database, job_id, task):
        self.database, self.job_id, self.task = database, job_id, task
        self.started = time.monotonic(); self.last_write = 0
        with database.connection(write=True) as db:
            self.value = read(db, job_id)
            self.value.pop('version', None); self.value.pop('updated_at', None)
            self.value.update(phase='running', started_at=stamp())
            write(db, job_id, self.value)

    def flush(self, force=False):
        at = time.monotonic()
        if not force and at - self.last_write < 0.15: return
        with self.database.connection(write=True) as db:
            row = db.execute('SELECT status FROM jobs WHERE id=?', (self.job_id,)).fetchone()
            if not row or row[0] != 'running': raise JobCancelled()
            # Worker-side saved-stage updates must survive subsequent chunks.
            stored = read(db, self.job_id)
            for key in ('planned_stages', 'saved_stages', 'reused_stages', 'chapter_context'):
                if key in stored:self.value[key] = stored[key]
            write(db, self.job_id, self.value)
        self.last_write = at

    def request(self, schema, streaming):
        if len(self.value['requests']) >= 12:
            raise ValueError('Lượt AI vượt giới hạn số request; không tiếp tục tạo vòng lặp.')
        item = {'index': len(self.value['requests']) + 1, 'schema': schema[:80], 'phase': 'connecting',
                'streaming': bool(streaming), 'started_at': stamp(), 'first_chunk_ms': None,
                'first_text_ms': None, 'elapsed_ms': None, 'chunks': 0, 'characters': 0, 'usage': {}}
        self.value['requests'].append(item); self.value.update(phase='connecting', preview=None)
        self.flush(True)
        return RequestProgress(self, item, schema == 'ChatReply' and self.task in {'chat', 'inline_help'})


class RequestProgress:
    def __init__(self, reporter, item, preview_allowed):
        self.reporter, self.item, self.preview_allowed = reporter, item, preview_allowed
        self.started, self.raw = time.monotonic(), ''

    def chunk(self, text):
        if not isinstance(text, str) or not text: return
        if len(self.raw) + len(text) > 100_000:
            raise ValueError('Đầu ra AI vượt giới hạn; chưa lưu câu trả lời.')
        self.raw += text
        self.item['chunks'] += 1; self.item['characters'] = len(self.raw)
        first = self.item['first_chunk_ms'] is None
        if first: self.item['first_chunk_ms'] = round((time.monotonic() - self.started) * 1000, 3)
        self.item['phase'] = self.reporter.value['phase'] = 'receiving'
        text = json_text_prefix(self.raw) if self.preview_allowed else ''
        first_text = bool(text) and self.item['first_text_ms'] is None
        if first_text: self.item['first_text_ms'] = round((time.monotonic() - self.started) * 1000, 3)
        if text:
            self.reporter.value['preview'] = {'text': text, 'validated': False, 'request_index': self.item['index']}
        self.reporter.flush(first or first_text)

    def usage(self, data):
        allowed = {'input_tokens', 'output_tokens', 'cached_input_tokens', 'total_tokens',
                   'load_duration_ns', 'prompt_eval_duration_ns', 'eval_duration_ns', 'total_duration_ns'}
        self.item['usage'].update({k: v for k, v in data.items() if k in allowed and type(v) is int and 0 <= v <= 10**15})
        if isinstance(data.get('provider_finish_reason'),str) and data['provider_finish_reason'] in {'stop','length','load','unload','unknown'}:
            self.item['usage']['provider_finish_reason']=data['provider_finish_reason']
        # Computed by our validators, never arbitrary provider payloads. Keep
        # proof that a key was derived or syntax/display labels normalized.
        for key,maximum in {'json_trailing_commas_removed':64,'ordering_answer_derived':1,'ordering_step_labels_removed':8,'cloze_source_mask_derived':1,'cloze_candidate_rejected':1,'ordering_candidate_rejected':1,'mcq_candidate_rejected':1,'question_empty_reason_normalized':1,'reference_alias_count':2000}.items():
            value=data.get(key)
            if type(value) is int and 0<=value<=maximum:self.item['usage'][key]=value
        for key in ('raw_json_sha256','normalized_json_sha256','ordering_model_options_sha256','cloze_statement_sha256','reference_alias_map_sha256'):
            value=data.get(key)
            if isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value):self.item['usage'][key]=value
        if data.get('ordering_answer_method') in {'explicit_source_step_positions_v1','explicit_scoped_source_steps_v2'}:
            self.item['usage']['ordering_answer_method']=data['ordering_answer_method']
        # Metrics must survive a later parser/finish-reason failure too; a
        # successful received() callback is not guaranteed on that path.
        self.reporter.flush(True)

    def fallback(self):
        self.item['protocol_fallbacks'] = self.item.get('protocol_fallbacks', 0) + 1
        self.reporter.flush(True)

    def received(self):
        self.item.update(phase='received', elapsed_ms=round((time.monotonic() - self.started) * 1000, 3))
        self.reporter.value['phase'] = 'validating'
        self.reporter.flush(True)

    def rejected(self):
        self.item.update(phase='rejected', elapsed_ms=round((time.monotonic() - self.started) * 1000, 3))
        self.reporter.value['phase'] = 'validating'
        self.reporter.flush(True)


@contextmanager
def bind(reporter):
    token = _reporter.set(reporter)
    try: yield
    finally: _reporter.reset(token)


def request_progress(schema, streaming):
    reporter = _reporter.get()
    return reporter.request(schema, streaming) if reporter else None


def saved(db, job_id, total, done, reused):
    value = read(db, job_id)
    if value is not None:
        value.update(planned_stages=total, saved_stages=done, reused_stages=reused)
        value.pop('version', None); value.pop('updated_at', None)
        write(db, job_id, value)


def chapter(db, job_id, progress):
    value = read(db, job_id)
    if value is not None:
        value['chapter_context'] = progress
        value.pop('version', None); value.pop('updated_at', None)
        write(db, job_id, value)
