"""Inline assistance pinned to one question or reading section, not global chat."""
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import BackgroundTasks, Depends, HTTPException, Request
from pydantic import Field
from .language import language_instruction, validate_language
from .learning import public_question
from .models import ChatReply, Model


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def context_history(values, budget=6000):
    """Keep the latest complete messages for AI; full history remains in SQLite."""
    chosen = []
    for value in reversed(values[-8:]):
        content = {k: v for k, v in value['content'].items() if k != 'student'}
        item = {'role': value['role'], 'action': value['action'], 'content': content}
        size = len(dump(item))
        if size > budget:
            break
        chosen.append(item);budget -= size
    return list(reversed(chosen))


class SectionContext(Model):
    expected_revision: int = Field(ge=1)


class HelpDraft(Model):
    text: str = Field(max_length=2000)
    expected_version: int = Field(ge=0)


class HelpAction(Model):
    action: Literal['hint', 'reveal', 'explain', 'ask', 'simpler', 'detail']
    message: str = Field(default='', max_length=2000)


class SaveHelpNote(Model):
    message_id: str = Field(min_length=1, max_length=64)


def register_inline_help(app, database, jobs, owned, user, course_snapshot, course_plan,
                         unit_from, approved_fragments, active_test, generate_checked):
    def thread(db, thread_id, owner, require_access=True):
        row = owned(db, 'help_threads', thread_id, owner)
        if active_test(db, owner, row['course_id']):
            raise HTTPException(403, 'Trợ giúp trong câu mở lại sau khi nộp/hủy lượt kiểm tra.')
        if require_access:
            course_snapshot(db, row['course_id'], owner)
        return row, json.loads(row['context_json'])

    def create(db, owner, course, context_key, context):
        previous = db.execute('SELECT id FROM help_threads WHERE owner_id=? AND context_key=?', (owner, context_key)).fetchone()
        if previous:
            return {'thread_id': previous[0], 'created': False, 'ai_called': False}
        thread_id = uuid.uuid4().hex
        db.execute('INSERT INTO help_threads VALUES (?,?,?,?,?,?,?)', (thread_id, owner, course['id'], course['revision'], context_key, dump(context), stamp()))
        return {'thread_id': thread_id, 'created': True, 'ai_called': False}

    def student(db, owner, context):
        if context['kind'] != 'question':
            return None
        session = owned(db, 'study_sessions', context['session_id'], owner)
        answer = db.execute('SELECT answer_json,result_json,assisted FROM answers WHERE session_id=? AND item_id=?', (session['id'], context['question']['id'])).fetchone()
        draft = db.execute('SELECT answer_json FROM session_drafts WHERE session_id=? AND item_id=?', (session['id'], context['question']['id'])).fetchone()
        selected = json.loads(answer['answer_json']) if answer else None
        proposed = json.loads(draft[0]) if draft and not answer else None
        q = context['question']
        options = {f'option-{i}': text for i, text in enumerate(q['options'])}
        left = {f'left-{i}': text for i, text in enumerate(q['left'])}
        def display(value):
            if isinstance(value, dict):
                return {left.get(k, k): options.get(v, v) if isinstance(v, str) else v for k, v in value.items()}
            if isinstance(value, list):
                return [options.get(v, v) if isinstance(v, str) else v for v in value]
            return options.get(value, value) if isinstance(value, str) else value
        return {'session_status': session['status'], 'submitted': bool(answer),
                'answer': selected, 'answer_display': display(selected),
                'draft': proposed, 'draft_display': display(proposed),
                'feedback': json.loads(answer['result_json']) if answer else None}

    def warning(db, row, context):
        if context['kind'] != 'question':
            return None
        flag = db.execute("SELECT reason FROM question_review_flags WHERE course_id=? AND question_revision_id=? AND state='needs_review'", (row['course_id'], context['question']['question_revision_id'])).fetchone()
        return {'state': 'needs_review', 'reason': flag[0], 'reference_is_verified': False} if flag else None

    def assist(db, owner, context, kind):
        if context['kind'] != 'question':
            return
        session = owned(db, 'study_sessions', context['session_id'], owner)
        if session['status'] == 'open':
            db.execute('INSERT OR IGNORE INTO assistance_events VALUES (?,?,?,?)', (session['id'], context['question']['id'], 'inline:' + kind, stamp()))
            db.execute('UPDATE answers SET assisted=1 WHERE session_id=? AND item_id=?', (session['id'], context['question']['id']))

    def messages(db, thread_id):
        return [{'id': r['id'], 'role': r['role'], 'action': r['action'], 'content': json.loads(r['content_json']), 'created_at': r['created_at']}
                for r in db.execute('SELECT * FROM help_messages WHERE thread_id=? ORDER BY created_at,id', (thread_id,))]

    @app.post('/api/sessions/{session_id}/items/{item_id}/help')
    def question_thread(session_id: str, item_id: str, owner=Depends(user)):
        with database.connection(write=True) as db:
            session = owned(db, 'study_sessions', session_id, owner)
            if session['exam'] and session['status'] == 'open' or active_test(db, owner, session['course_id']):
                raise HTTPException(403, 'Nộp hoặc hủy kiểm tra trước khi dùng trợ giúp.')
            q = next((q for q in json.loads(session['items_json']) if q['id'] == item_id), None)
            if not q:
                raise HTTPException(404, 'Câu không thuộc lượt của bạn.')
            course = course_snapshot(db, session['course_id'], owner, session['course_revision'])
            unit = unit_from(course, q['unit_id'], ready=True)
            plan = course_plan(db, course, owner, unit)
            fragments = approved_fragments(db, plan, course['creator_id'], q['source_refs'])
            context = {'kind': 'question', 'session_id': session_id, 'question': q,
                       'unit_id': unit['id'], 'unit_title': unit['title'], 'fragments': fragments,
                       'preferences': json.loads(plan['preferences_json'])}
            return create(db, owner, course, 'question:' + session_id + ':' + item_id, context)

    def content_thread(course_id, unit_id, index, body, owner, kind):
        with database.connection(write=True) as db:
            course = course_snapshot(db, course_id, owner)
            if active_test(db, owner, course_id):
                raise HTTPException(403, 'Trợ giúp mở lại sau khi nộp/hủy kiểm tra.')
            if course['revision'] != body.expected_revision:
                raise HTTPException(409, 'Bài đã đổi; chọn đúng phiên bản đoạn đang đọc.')
            unit = unit_from(course, unit_id, ready=True)
            sections = unit['data']['mindmap' if kind == 'mindmap' else 'sections']
            if not 0 <= index < len(sections):
                raise HTTPException(404, 'Không có ý mindmap này trong bài.' if kind == 'mindmap' else 'Không có đoạn này trong bài.')
            section = sections[index]
            if not set(section['source_refs']) <= set(unit['source_refs']):
                raise HTTPException(422, 'Nguồn của ý đang chọn không thuộc phạm vi bài này; chưa mở trợ giúp hoặc gọi AI.')
            plan = course_plan(db, course, owner, unit)
            context = {'kind': kind, 'section_index': index, 'section': section,
                       'unit_id': unit_id, 'unit_title': unit['title'],
                       'preferences': json.loads(plan['preferences_json']),
                       'fragments': approved_fragments(db, plan, course['creator_id'], section['source_refs'])}
            if kind == 'mindmap': context['node_index'] = index
            key = f'{kind}:{course_id}:{course["revision"]}:{unit_id}:{index}'
            return create(db, owner, course, key, context)

    @app.post('/api/courses/{course_id}/units/{unit_id}/sections/{section_index}/help')
    def section_thread(course_id: str, unit_id: str, section_index: int, body: SectionContext, owner=Depends(user)):
        return content_thread(course_id, unit_id, section_index, body, owner, 'section')

    @app.post('/api/courses/{course_id}/units/{unit_id}/mindmap/{node_index}/help')
    def mindmap_thread(course_id: str, unit_id: str, node_index: int, body: SectionContext, owner=Depends(user)):
        return content_thread(course_id, unit_id, node_index, body, owner, 'mindmap')

    @app.get('/api/help/threads/{thread_id}')
    def read(thread_id: str, owner=Depends(user)):
        with database.connection() as db:
            row, context = thread(db, thread_id, owner, require_access=False)
            draft = db.execute('SELECT text,version FROM help_drafts WHERE thread_id=?', (thread_id,)).fetchone()
            pending = [r['id'] for r in db.execute("SELECT id,payload_json FROM jobs WHERE owner_id=? AND task='inline_help' AND status IN ('queued','running')", (owner,)) if json.loads(r['payload_json']).get('thread_id') == thread_id]
            safe = {k: context[k] for k in ['kind', 'unit_id', 'unit_title']}
            if context['kind'] == 'question':
                safe['question'] = public_question(context['question']);safe['session_id'] = context['session_id']
            else:
                safe.update(section_index=context['section_index'], section=context['section'])
                if context['kind'] == 'mindmap': safe['node_index'] = context['node_index']
            return {'id': thread_id, 'course_id': row['course_id'], 'revision': row['course_revision'],
                    'context': safe, 'student': student(db, owner, context), 'reference_warning': warning(db, row, context),
                    'messages': messages(db, thread_id), 'source_excerpts': context['fragments'],
                    'draft': dict(draft) if draft else {'text': '', 'version': 0}, 'pending_jobs': pending}

    @app.put('/api/help/threads/{thread_id}/draft')
    def save_draft(thread_id: str, body: HelpDraft, owner=Depends(user)):
        with database.connection(write=True) as db:
            thread(db, thread_id, owner)
            previous = db.execute('SELECT version FROM help_drafts WHERE thread_id=?', (thread_id,)).fetchone()
            version = previous[0] if previous else 0
            if body.expected_version != version:
                raise HTTPException(409, 'Bản nháp câu này đã đổi ở cửa sổ khác.')
            db.execute('INSERT INTO help_drafts VALUES (?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET text=excluded.text,version=excluded.version,updated_at=excluded.updated_at', (thread_id, body.text, version + 1, stamp()))
            return {'text': body.text, 'version': version + 1}

    @app.post('/api/help/threads/{thread_id}/notebook')
    def save_note(thread_id: str, body: SaveHelpNote, owner=Depends(user)):
        with database.connection(write=True) as db:
            row, context = thread(db, thread_id, owner, require_access=False)
            message = db.execute("SELECT * FROM help_messages WHERE id=? AND thread_id=? AND role='assistant'", (body.message_id, thread_id)).fetchone()
            if not message:
                raise HTTPException(404, 'Chọn lời giải của trợ lý trong đúng hội thoại này.')
            prior = db.execute("SELECT entry_id FROM notebook_origins WHERE owner_id=? AND kind='inline_help' AND origin_id=?", (owner, body.message_id)).fetchone()
            if prior:
                note_id = prior[0]
                if db.execute('SELECT 1 FROM notebook_deleted WHERE entry_id=?', (note_id,)).fetchone():
                    raise HTTPException(409, 'Ghi chú này đã xóa; phục hồi bản cũ thay vì tạo bản trùng.')
            else:
                value = json.loads(message['content_json'])
                selected = context.get('question') or context['section']
                heading = selected.get('prompt') or selected['title']
                text = heading + '\n\n' + value.get('text', '')
                if 'reference' in value:
                    answer = value['reference']
                    if isinstance(answer, list):
                        answer = '\n'.join(f"{selected['left'][i]} → {selected['options'][j]}" if selected.get('kind') == 'matching' else selected['options'][j] for i, j in enumerate(answer))
                    text += '\n\nTham khảo: ' + str(answer)
                # Automation label, not a claim that saved assistance is source truth.
                text += '\n\n[Lời trợ giúp tham khảo; cần đối chiếu nguồn.]'
                note_id = uuid.uuid4().hex
                db.execute('INSERT INTO notebook_entries VALUES (?,?,?,?,?,?,?,?)', (note_id, owner, text[:10000], 'ai', dump(value.get('source_refs', [])), stamp(), stamp(), 1))
                db.execute('INSERT INTO notebook_origins VALUES (?,?,?,?,?)', (note_id, owner, 'inline_help', body.message_id, row['course_revision']))
            note = owned(db, 'notebook_entries', note_id, owner)
            return {'id': note['id'], 'body': note['body'], 'label': note['label'], 'source_refs': json.loads(note['refs_json']), 'version': note['version'], 'updated_at': note['updated_at']}

    def fixed_reply(db, row, context, action, owner):
        q = context['question'];step = 0
        def tr(vi, en):
            return en if context['preferences'].get('language') == 'en' else vi
        if action == 'hint':
            # Number of committed hints is authoritative; repeated exhausted
            # hints reuse the final result rather than farming events/messages.
            count = db.execute("SELECT count(*) FROM help_messages WHERE thread_id=? AND action='hint'", (row['id'],)).fetchone()[0]
            total = max(1, len(q['options'])-1) if q['kind'] == 'mcq' else max(1, len(q['answer'])-1) if q['kind'] == 'cloze' else len(q['options']) if q['kind'] in {'matching', 'ordering'} else max(1, len(q['rubric']))
            step = min(count + 1, total)
        key = f'fixed:{action}:{step}'
        previous = db.execute('SELECT content_json FROM help_messages WHERE thread_id=? AND event_key=?', (row['id'], key)).fetchone()
        assist(db, owner, context, action)
        if previous:
            return {'reply': json.loads(previous[0]), 'ai_called': False, 'cached': True, 'thread_id': row['id']}
        value = {'source_refs': q['source_refs'], 'ai_generated': False, 'action': action,
                 'reference_warning': warning(db, row, context), 'step': step}
        if action in {'reveal', 'explain'}:
            value['reference'] = q['answer']
            if action == 'explain':
                value.update(text=q['explanation'], rubric=q.get('rubric', []))
            else:
                value['text'] = tr('Đáp án tham khảo đã lưu.', 'The saved reference answer.')
        elif q['kind'] == 'mcq':
            wrong = [i for i, x in enumerate(q['options']) if x != q['answer']][:step]
            value.update(text=tr('Có thể loại các lựa chọn này.', 'These choices can be eliminated.'), eliminated_option_ids=[f'option-{i}' for i in wrong])
        elif q['kind'] == 'cloze':
            value.update(text=tr('Phần đầu của đáp án tham khảo.', 'The start of the reference answer.'), prefix=q['answer'][:step])
        elif q['kind'] == 'ordering':
            value.update(text=tr('Các bước đầu theo thứ tự tham khảo.', 'The first steps in the reference order.'), ordered_option_ids=[f'option-{i}' for i in q['answer'][:step]])
        elif q['kind'] == 'matching':
            value.update(text=tr('Một phần cặp ghép theo đáp án tham khảo.', 'Some pairs from the reference answer.'), pairs={f'left-{i}': f'option-{q["answer"][i]}' for i in range(step)})
        else:
            value.update(text=tr('Đối chiếu từng tiêu chí; đây chưa phải chấm điểm.', 'Review each criterion; this is not a grade.'), criteria=q['rubric'][:step])
        db.execute('INSERT INTO help_messages VALUES (?,?,?,?,?,?,?)', (uuid.uuid4().hex, row['id'], 'assistant', action, dump(value), key, stamp()))
        return {'reply': value, 'ai_called': False, 'cached': False, 'thread_id': row['id']}

    @app.post('/api/help/threads/{thread_id}/actions')
    async def action(thread_id: str, body: HelpAction, background: BackgroundTasks, request: Request, owner=Depends(user)):
        with database.connection(write=True) as db:
            row, context = thread(db, thread_id, owner)
            if context['kind'] == 'question' and body.action in {'hint', 'reveal', 'explain'}:
                return fixed_reply(db, row, context, body.action, owner)
            if context['kind'] in {'section', 'mindmap'} and body.action == 'explain':
                cached = db.execute("SELECT content_json FROM help_messages WHERE thread_id=? AND role='assistant' AND action='explain' ORDER BY created_at DESC", (thread_id,)).fetchone()
                if cached and not json.loads(cached[0]).get('needs_more_source'):
                    return {'thread_id': thread_id, 'reply': json.loads(cached[0]), 'ai_called': False, 'cached': True}
            if body.action == 'reveal':
                raise HTTPException(422, 'Đoạn đọc không có đáp án để hiện.')
            if body.action == 'ask' and not body.message.strip():
                raise HTTPException(422, 'Nhập câu hỏi cho phần đang học.')
            current_student = student(db, owner, context)
            reference_warning = warning(db, row, context)
            history = context_history(messages(db, thread_id))
        prompts = {'hint': 'Gợi ý bước đầu cho đúng đoạn này, chưa nói hết lời giải.',
                   'explain': 'Giải thích đúng phần đang chọn theo nguồn.',
                   'simpler': 'Giải thích lại bằng cách dễ hiểu cho sinh viên, có ví dụ nhỏ. Không đổi chủ đề.',
                   'detail': 'Làm rõ hơn phần giải thích vừa có, bám đúng nội dung và câu hỏi này.',
                   'ask': body.message.strip()}
        message = prompts[body.action]
        payload = {'thread_id': thread_id, 'course_id': row['course_id'], 'revision': row['course_revision'],
                   'action': body.action, 'message': message, 'student': current_student}
        # Replaying a confirmed intent must not become a new charge just because
        # the learner answered or moved on while the response was in flight.
        identity = jobs.identity(request, 'inline_help', {k: v for k, v in payload.items() if k != 'student'}, owner=owner)

        def prepare(db):
            thread(db, thread_id, owner)  # Permission/test state can change while quote is open.
            assist(db, owner, context, body.action)
            job_key = identity['key'] or uuid.uuid4().hex
            db.execute('INSERT INTO help_messages VALUES (?,?,?,?,?,?,?)', (uuid.uuid4().hex, thread_id, 'user', body.action, dump({'text': message, 'student': current_student}), 'request:' + job_key, stamp()))

        async def work(job_id):
            selected = {k: v for k, v in context.items() if k not in {'fragments', 'preferences'}}
            instruction = ('Bạn đang hỗ trợ TRỰC TIẾP một câu hỏi hoặc đoạn đọc đã xác định. Không hỏi lại môn/phần nào khi context đã có. '
                           'Chỉ dùng đúng snapshot và nguồn của nó. Đáp án tham khảo có thể sai: nếu reference_warning có giá trị, nêu đang cần đối chiếu và không cố bảo vệ đáp án. '
                           'Nếu người học hỏi về lựa chọn của mình, nêu rõ answer_display hoặc draft_display đang chọn và đối chiếu với nguồn. Draft là nháp chưa nộp, không tự coi là đã chấm. '
                           'Không tự chấm điểm hay đổi bài. Nếu thiếu nguồn thì needs_more_source=true. Trả text, source_refs, needs_more_source. '
                           + dump({'pinned_context': selected, 'student': current_student, 'reference_warning': reference_warning,
                                   'thread_history': history, 'request': message}) + language_instruction(context['preferences']))
            reply = await generate_checked(ChatReply, instruction, context['fragments'])
            validate_language(reply, context['preferences'])
            with database.connection(write=True) as db:
                jobs.check(db, job_id)
                message_id = uuid.uuid4().hex
                db.execute('INSERT INTO help_messages VALUES (?,?,?,?,?,?,?)', (message_id, thread_id, 'assistant', body.action, dump({**reply, 'ai_generated': True}), 'job:' + job_id, stamp()))
                draft = db.execute('SELECT text,version FROM help_drafts WHERE thread_id=?', (thread_id,)).fetchone()
                if draft and not reply['needs_more_source'] and draft['text'].strip() == body.message.strip():
                    db.execute('UPDATE help_drafts SET text=?,version=version+1,updated_at=? WHERE thread_id=?', ('', stamp(), thread_id))
                result = {**reply, 'thread_id': thread_id, 'message_id': message_id}
                jobs.finish(db, job_id, result)
                return result
        return jobs.create(owner, 'inline_help', payload, background, work, identity, prepare)
