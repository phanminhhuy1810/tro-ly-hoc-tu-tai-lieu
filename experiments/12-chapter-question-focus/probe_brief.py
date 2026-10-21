"""One bounded local ChapterBrief diagnostic. Raw content stays private.

This does not insert a job, publish a lesson, retry a failed generation, or
reinterpret the historical v4 failure as though its raw output were saved.
"""
import asyncio
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from study_backend.ai import LocalAI
from study_backend.chapter_context import ChapterBrief, digest, partition, reading_instruction, CHAPTER_BRIEF_PROMPT_VERSION
from study_backend.question_generation import content_preferences
from study_backend.reference_wire import ReferenceWire

PRIVATE = ROOT / 'backend/runtime/chapter-quality-diagnostic'


def write_new(path, value, private=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if private else 0o644), 'w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def active():
    with sqlite3.connect('file:' + str(ROOT / 'backend/runtime/study.sqlite3') + '?mode=ro', uri=True) as db:
        return db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]


class Trace:
    def __init__(self):
        self.started = time.monotonic()
        self.raw, self.metrics, self.posts = '', {}, []
        self.fallbacks, self.first_chunk_ms = 0, None

    def chunk(self, value):
        if not value: return
        if len(self.raw) + len(value) > 100_000: raise ValueError('Output bounded')
        if self.first_chunk_ms is None: self.first_chunk_ms = round((time.monotonic() - self.started) * 1000, 3)
        self.raw += value

    def usage(self, value):
        self.metrics.update(value)

    def fallback(self):
        self.fallbacks += 1
        if self.fallbacks > 1: raise ValueError('No second protocol fallback')


async def main(phase):
    result_path = Path(__file__).parent / ('results/ftc-' + phase + '-brief.json')
    raw_path = PRIVATE / ('ftc-' + phase + '-raw.json')
    assert not result_path.exists() and not raw_path.exists(), 'Never overwrite a run'
    captured = json.loads((PRIVATE / 'ftc-input.json').read_text())
    assert not ((PRIVATE / 'ftc-input.json').stat().st_mode & 0o077)
    fragments, prefs = captured['fragments'], captured['prefs']
    instruction = reading_instruction('map', prefs)
    equivalent = instruction == captured['old_instruction']
    assert (phase == 'baseline') == equivalent, 'Baseline must match; revised must identify a changed prompt'
    instruction_sha = hashlib.sha256(instruction.encode()).hexdigest()
    if equivalent: assert instruction_sha == captured['instruction_sha256']
    assert len(partition(fragments)) == 1
    old = json.loads((ROOT / 'experiments/08-quality-evaluation/results/dev-v4-chapter.json').read_text())
    case = next(c for c in old['runs'] if c['case_id'] == captured['case_id'])
    with sqlite3.connect('file:' + str(ROOT / 'backend/runtime/study.sqlite3') + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM chapter_contexts WHERE id=? AND owner_id=?',
                         (case['chapter_context']['context_id'], case['qa_owner_id'])).fetchone()
        manifest = json.loads(row['manifest_json'])
        plan = db.execute('SELECT * FROM plans WHERE id=? AND owner_id=?', (row['plan_id'], case['qa_owner_id'])).fetchone()
        assert plan['status'] == 'approved' and json.loads(plan['preferences_json']) == prefs
        assert manifest['input_sha256'] == digest(fragments)
        assert manifest['preferences_sha256'] == digest(content_preferences(prefs))
    assert active() == 0, 'No parallel app inference'
    trace = Trace()

    class ProbeLocal(LocalAI):
        model = 'gemma4:12b-mlx'

        def client(self, timeout):
            client = super().client(timeout)
            async def request(request):
                if request.url.path != '/api/chat': return
                payload = json.loads(request.content)
                trace.posts.append({'num_predict': payload['options']['num_predict'], 'format': 'format' in payload,
                                    'payload_sha256': hashlib.sha256(request.content).hexdigest()})
                assert len(trace.posts) <= 2 and (len(trace.posts) == 1 or trace.fallbacks == 1)
            client.event_hooks['request'].append(request)
            return client

    provider = ProbeLocal()
    started_at = datetime.now(timezone.utc).isoformat()
    value, error = None, None
    try:
        value = await asyncio.wait_for(provider.generate_stream(ChapterBrief, instruction, fragments, trace), 195)
    except Exception as exc:
        error = {'class': type(exc).__name__, 'code': getattr(exc, 'code', None)}
    elapsed = round(time.monotonic() - trace.started, 3)
    raw = trace.raw.strip()
    if raw.startswith('```json\n') and raw.endswith('\n```'): raw = raw[8:-4]
    validation = {'valid': False}
    try:
        ReferenceWire(fragments).validated(ChapterBrief, raw)
        validation['valid'] = True
    except Exception as exc:
        validation['error_class'] = type(exc).__name__
        if callable(getattr(exc, 'errors', None)):
            validation['fields'] = [list(e['loc']) for e in exc.errors(include_input=False, include_url=False)[:8]]
    write_new(raw_path, {'raw': trace.raw, 'validated_value': value, 'error': error, 'instruction': instruction}, True)
    report = {'purpose': 'single_adapter_diagnostic_not_end_to_end_or_historical_raw',
              'case_id': captured['case_id'], 'model': provider.model, 'started_at': started_at,
              'elapsed_seconds': elapsed, 'first_chunk_ms': trace.first_chunk_ms,
              'source_input_sha256': digest(fragments), 'source_fragments': len(fragments),
              'source_characters': sum(len(f['text']) for f in fragments),
              'phase': phase, 'instruction_exactly_matches_captured_template': equivalent, 'instruction_sha256': instruction_sha,
              'brief_prompt_version': 'legacy_template_captured' if equivalent else CHAPTER_BRIEF_PROMPT_VERSION,
              'schema_sha256': digest(ChapterBrief.model_json_schema()), 'posts': trace.posts,
              'usage': trace.metrics, 'error': error, 'raw_characters': len(trace.raw),
              'raw_sha256': hashlib.sha256(trace.raw.encode()).hexdigest(), 'offline_exact_raw_validation': validation,
              'adapter_accepted': value is not None, 'raw_private': True, 'published': False,
              'semantic_calls': len(trace.posts) - trace.fallbacks, 'protocol_fallbacks': trace.fallbacks,
              'app_active_jobs_after': active(), 'external_inference': False, 'automatic_semantic_retry': False,
              'historical_failure_finish_reason_remains_unknown': True}
    write_new(result_path, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['baseline', 'revised'], default='baseline')
    asyncio.run(main(parser.parse_args().phase))
