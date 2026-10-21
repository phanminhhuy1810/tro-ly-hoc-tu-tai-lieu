import copy
import json
import unittest

from study_backend.models import Question
from study_backend.question_quality import verify_mcq_options
from test_slice import SliceFixture


class QuantityOptionTests(unittest.TestCase):
    def test_equivalent_units_do_not_create_two_correct_choices(self):
        for pair in [('32 bits, 2 parts', '4 bytes, 2 parts'), ('4 bit', '0.5 byte'), ('32 BITS', '32 bits')]:
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                verify_mcq_options({'kind': 'mcq', 'options': list(pair)})
        verify_mcq_options({'kind': 'mcq', 'options': ['-32 bits', '32 bits', '4 bytes, other condition']})
        verify_mcq_options({'kind': 'mcq', 'options': ['x=-1', 'x=1', '4 bytes']})

    def test_new_ai_or_manual_question_is_rejected_before_persistence(self):
        with self.assertRaises(ValueError):
            Question(kind='mcq', prompt='IPv4 size?', options=['32 bits', '4 bytes'], answer='32 bits', explanation='32 bits = 4 bytes', source_refs=['p8'])


class LegacyMCQTests(SliceFixture):
    def test_an_entire_bad_legacy_bank_is_quarantined_and_old_attempt_unchanged(self):
        course = self.course(); base = '/api/courses/' + course['id']
        prior = self.client.post(base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()
        before = self.client.get('/api/sessions/' + prior['id']).json()
        content = copy.deepcopy(course['content'])
        question = content['units'][0]['data']['questions'][0]
        question.update(prompt='IPv4 size?', options=['32 bits', '4 bytes'], answer='32 bits')
        content['units'][0]['data']['questions'] = [question]
        with self.app.state.database.connection(write=True) as db:
            db.execute('UPDATE course_revisions SET content_json=? WHERE course_id=? AND revision=2', (json.dumps(content), course['id']))
        weak = self.client.post(base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1', 'exercise': 'weak'})
        self.assertEqual(weak.status_code, 409)
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM question_review_flags WHERE course_id=? AND state='needs_review'", (course['id'],)).fetchone()[0], 1)
        refused = self.client.post(base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'})
        self.assertEqual(refused.status_code, 422)
        self.assertTrue(refused.json()['bank_warnings'])
        with self.app.state.database.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM question_review_flags WHERE course_id=? AND state='needs_review'", (course['id'],)).fetchone()[0], 1)
        self.assertEqual(self.client.get('/api/sessions/' + prior['id']).json(), before)
