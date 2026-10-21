"""One real local-model completion, on an isolated copy of an existing QA course.

This is a development regression case, not held-out model evaluation. The live
course, profile selection, Coin and source files are never modified by this probe.
"""
import hashlib
import json
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from study_backend.ai import LocalAI
from study_backend.app import create_app
from study_backend.providers import Choice, ProviderRegistry

ROOT = Path(__file__).resolve().parents[2]
COURSE = '98ff5b545574402f811f17de49c199cb'
MODEL = 'gemma4:12b-mlx'
CHOICE = 'local:' + MODEL


def run():
    live = sqlite3.connect(f'file:{ROOT}/backend/runtime/study.sqlite3?mode=ro', uri=True)
    live.row_factory = sqlite3.Row
    if live.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:
        raise SystemExit('A live job is active; probe did not run.')
    course_row = dict(live.execute('SELECT * FROM courses WHERE id=?', (COURSE,)).fetchone())
    revision_row = dict(live.execute('SELECT * FROM course_revisions WHERE course_id=? AND revision=?',
                                   (COURSE, course_row['active_revision'])).fetchone())
    path = ROOT/'backend/runtime/question-completion-qa.sqlite3'
    if path.exists(): raise SystemExit('QA copy already exists; retain it and the original evidence.')
    path.touch(mode=0o600)
    clone = sqlite3.connect(path)
    live.backup(clone)
    token = secrets.token_urlsafe(32)
    clone.execute('INSERT INTO auth_sessions VALUES (?,?,?,?)',
                  (hashlib.sha256(token.encode()).hexdigest(), course_row['owner_id'],
                   int(time.time())+3600, datetime.now(timezone.utc).isoformat()))
    clone.commit(); clone.close()

    calls = []
    class ObservedLocal(LocalAI):
        async def generate_stream(self, schema, instruction, fragments, progress):
            calls.append(schema.__name__)
            return await super().generate_stream(schema, instruction, fragments, progress)
    ai = ObservedLocal(); ai.model = MODEL
    registry = ProviderRegistry([Choice(CHOICE, MODEL, ai)], CHOICE)
    app = create_app(path, ROOT/'backend/runtime/sources', provider_registry=registry, economy_enabled=False)
    report = {'purpose': __doc__, 'course_id': COURSE, 'model': MODEL,
              'economy_disabled_in_clone': True, 'live_coin_changed': False,
              'automatic_retries': 0, 'new_model_stages': calls}
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.cookies.set('study_session', token)
        before = client.get(f'/api/courses/{COURSE}/editor').json()
        unit = before['content']['units'][0]
        options = client.get(f'/api/courses/{COURSE}/question-completion?unit_id='+unit['id'])
        options.raise_for_status(); report['options'] = options.json()
        assert [x['stage'] for x in options.json()['missing'] if x['can_generate']] == ['ordering']
        old_session = client.post(f'/api/courses/{COURSE}/sessions',
                                 json={'expected_revision': before['revision'], 'unit_id': unit['id']})
        old_session.raise_for_status(); old_session = old_session.json()
        # Answer one real old MCQ; keep this session on its original revision.
        response = client.post('/api/sessions/'+old_session['id']+'/answers',
                               json={'item_id': old_session['questions'][0]['id'],
                                     'answer': unit['data']['questions'][0]['answer']})
        response.raise_for_status()
        old_session = client.get('/api/sessions/'+old_session['id']).json()
        start = time.monotonic()
        response = client.post(f'/api/courses/{COURSE}/question-completion',
                               json={'expected_revision': before['revision'],
                                     'unit_id': unit['id'], 'stages': ['ordering']})
        response.raise_for_status()
        job = client.get('/api/jobs/'+response.json()['job_id']).json()
        report.update(job=job, elapsed_seconds=round(time.monotonic()-start, 3))
        unchanged = client.get(f'/api/courses/{COURSE}/editor').json()
        report['preview_did_not_change_content'] = unchanged == before
        if job['status'] == 'succeeded':
            proposal = client.get('/api/proposals/'+job['result']['proposal_id']).json()
            report['preview'] = proposal
            assert proposal['after']['questions'][:-1] == unit['data']['questions']
            applied = client.post('/api/proposals/'+proposal['id']+'/apply',
                                  json={'expected_revision': before['revision']})
            applied.raise_for_status()
            after = client.get(f'/api/courses/{COURSE}/editor').json()
            target = after['content']['units'][0]
            report['applied_revision'] = after['revision']
            report['non_question_content_unchanged'] = (
                {k:v for k,v in target['data'].items() if k != 'questions'} ==
                {k:v for k,v in unit['data'].items() if k != 'questions'})
            report['old_session_unchanged'] = client.get('/api/sessions/'+old_session['id']).json() == old_session
            report['source_binding_unchanged'] = all(target.get(k) == unit.get(k) for k in ('source_refs','source_plan_id'))
            report['old_provider_unchanged'] = target['generation']['provider'] == unit['generation']['provider']
            report['coverage'] = target['generation']['question_coverage']
            session = client.post(f'/api/courses/{COURSE}/sessions',
                                 json={'expected_revision': after['revision'], 'unit_id': unit['id']})
            session.raise_for_status(); session = session.json()
            report['old_question_ids_unchanged'] = [q['id'] for q in session['questions'][:-1]] == [q['id'] for q in old_session['questions']]
            answer = client.post('/api/sessions/'+session['id']+'/answers',
                                 json={'item_id': session['questions'][-1]['id'],
                                       'answer': target['data']['questions'][-1]['answer']})
            answer.raise_for_status(); report['new_question_grade'] = answer.json()
            report['new_question'] = target['data']['questions'][-1]
        report['live_course_unchanged'] = dict(live.execute('SELECT * FROM courses WHERE id=?', (COURSE,)).fetchone()) == course_row
        report['live_revision_unchanged'] = dict(live.execute('SELECT * FROM course_revisions WHERE course_id=? AND revision=?',
                                               (COURSE, course_row['active_revision'])).fetchone()) == revision_row
    live.close()
    destination = ROOT/'backend/evidence/question-completion-real-trial.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if isinstance(v, (str, float, bool)) and k != 'purpose'}, ensure_ascii=False))
    print('status:', job['status'], 'stages:', calls, 'error:', job.get('error'))
    if report.get('coverage'): print('coverage:', json.dumps(report['coverage'], ensure_ascii=False))


if __name__ == '__main__': run()
