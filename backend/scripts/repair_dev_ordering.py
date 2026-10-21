"""One-off maintenance for the exact self-authored browser trial, never user files.

Builds a scoped proposal before optional --apply. Does not mint a login token,
rewrite attempts, use AI, or change public/shared course content. Runtime
evidence explicitly distinguishes this maintenance path from an HTTP/UI test.
"""
import argparse
import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from study_backend.db import Database
from study_backend.ordering import source_order, verify_ordering
from study_backend.learning import question_item

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'c44feeece5c441089388b6ef88cd4b1d'


def dump(value):
    return json.dumps(value, ensure_ascii=False)


def main(apply=False):
    original = (ROOT / 'backend/runtime/sources' / SOURCE).read_bytes()
    assert original == (ROOT / 'experiments/02-local-ai/fixtures/subnet-dev.txt').read_bytes(), 'Not the exact self-authored fixture'
    database = Database(ROOT / 'backend/runtime/study.sqlite3')
    report = {'scope': 'Offline transactional maintenance of exact private self-authored dev fixture; not UI/HTTP proof',
              'source_id': SOURCE, 'source_sha256': hashlib.sha256(original).hexdigest(),
              'verified_at': datetime.now(timezone.utc).isoformat(), 'repairs': []}
    with database.connection(write=True) as db:
        owner = db.execute('SELECT owner_id FROM sources WHERE id=?', (SOURCE,)).fetchone()[0]
        courses = db.execute('SELECT c.id,c.active_revision,r.content_json,r.plan_id FROM courses c JOIN course_revisions r ON r.course_id=c.id AND r.revision=c.active_revision JOIN plans p ON p.id=r.plan_id WHERE p.source_id=? AND c.owner_id=?', (SOURCE, owner)).fetchall()
        for course in courses:
            publication = db.execute('SELECT visibility FROM course_publications WHERE course_id=?', (course['id'],)).fetchone()
            assert not publication or publication[0] == 'private', 'Never maintain shared/public content automatically'
            content = json.loads(course['content_json'])
            for unit in content['units']:
                if not unit.get('data'):
                    continue
                plan_id = unit.get('source_plan_id', course['plan_id'])
                plan = db.execute('SELECT * FROM plans WHERE id=? AND owner_id=? AND source_id=?', (plan_id, owner, SOURCE)).fetchone()
                assert plan is not None
                revision = json.loads(plan['preferences_json'])['extraction_revision']
                source = db.execute('SELECT content_json FROM extraction_revisions WHERE source_id=? AND revision=?', (SOURCE, revision)).fetchone()
                fragments = [f for f in json.loads(source[0]) if f['id'] in unit['source_refs']]
                for index, question in enumerate(unit['data']['questions']):
                    if question['kind'] != 'ordering':
                        continue
                    # The known legacy option adds "số" inside the original
                    # step phrase. Retain the source phrase so the same strict
                    # validator used for new questions can verify this repair.
                    options = [x.replace('Đếm số host dùng được', 'Đếm host dùng được') for x in question['options']]
                    candidate = {**question, 'options': options}
                    expected = source_order(candidate, fragments)
                    if expected == question['answer'] and options == question['options']:
                        continue
                    before = copy.deepcopy(question)
                    after = {**candidate, 'answer': expected}
                    verify_ordering(after, fragments)
                    changed = copy.deepcopy(content)
                    next(u for u in changed['units'] if u['id'] == unit['id'])['data']['questions'][index] = after
                    proposal = uuid.uuid4().hex
                    stamp = datetime.now(timezone.utc).isoformat()
                    request = 'Sửa riêng đáp án ordering bị đảo bước 3–4, đối chiếu quy trình trong đúng bản trích đã duyệt; không sửa lịch sử.'
                    db.execute('INSERT INTO revision_proposals VALUES (?,?,?,?,?,?,?,?,?)', (proposal, owner, course['id'], course['active_revision'], dump({'unit_id': unit['id'], 'target': 'question', 'index': index}), request, dump({'before': before, 'after': after, 'content': changed}), 'preview', stamp))
                    snapshot = db.execute('SELECT items_json,result_json FROM study_sessions WHERE course_id=? ORDER BY id', (course['id'],)).fetchall()
                    old_digest = hashlib.sha256(dump([tuple(r) for r in snapshot]).encode()).hexdigest()
                    item = question_item(course['id'], unit['id'], index, before)
                    db.execute("INSERT OR IGNORE INTO question_review_flags VALUES (?,?,?,?,?)", (course['id'], item['question_revision_id'], 'needs_review', request, stamp))
                    new_revision = None
                    if apply:
                        new_revision = course['active_revision'] + 1
                        db.execute('INSERT INTO course_revisions VALUES (?,?,?,?,?)', (course['id'], new_revision, course['plan_id'], dump(changed), stamp))
                        assert db.execute('UPDATE courses SET active_revision=? WHERE id=? AND active_revision=?', (new_revision, course['id'], course['active_revision'])).rowcount == 1
                        db.execute("UPDATE revision_proposals SET status='applied' WHERE id=?", (proposal,))
                    snapshot_after = db.execute('SELECT items_json,result_json FROM study_sessions WHERE course_id=? ORDER BY id', (course['id'],)).fetchall()
                    assert old_digest == hashlib.sha256(dump([tuple(r) for r in snapshot_after]).encode()).hexdigest()
                    report['repairs'].append({'course_id': course['id'], 'base_revision': course['active_revision'], 'new_revision': new_revision, 'proposal_id': proposal,
                                              'before': before, 'after': after, 'source_fragments': fragments, 'attempt_snapshots_unchanged_sha256': old_digest, 'old_reference_flagged': True})
                    # This maintenance scope is exactly the known single defect.
                    assert len(report['repairs']) == 1, 'More than one defect: roll back and review scope'
    report['applied'] = apply;report['ai_called'] = False;report['coin_spent'] = 0
    target = ROOT / 'backend/evidence/ordering-key-repair.json'
    if report['repairs']:
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'repairs': len(report['repairs']), 'applied': apply, 'evidence': str(target)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
