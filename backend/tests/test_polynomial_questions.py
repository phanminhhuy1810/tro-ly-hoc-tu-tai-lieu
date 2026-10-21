"""Narrow exact-polynomial MCQ proofs; unsupported cases remain unproved."""
import copy
import json
import unittest
from pathlib import Path
from fractions import Fraction

from study_backend.polynomial_questions import polynomial, Unsupported, CompositionError, composition_proof, verify_composition
from study_backend.models import Question, QUESTION_DRAFTS
from study_backend.generation_contract import validated_generation, QuestionRejected
from test_slice import SliceFixture


def candidate():
    return {'kind': 'mcq',
            'prompt': 'Xét hàm hợp $h(x)=(3x+1)^4$. Hàm trong và hàm ngoài nào sau đây là chính xác?',
            'options': ['Hàm trong là $g(x)=3x+1$, hàm ngoài là $f(u)=u^4$',
                        'Hàm trong là $g(x)=x^4$, hàm ngoài là $f(u)=3u+1$',
                        'Hàm trong là $g(x)=3x$, hàm ngoài là $f(u)=(u+1)^4$'],
            'answer': 'Hàm trong là $g(x)=3x+1$, hàm ngoài là $f(u)=u^4$',
            'explanation': 'Chain rule.', 'source_refs': ['p']}


class PolynomialProofTests(unittest.TestCase):
    def test_two_correct_decompositions_are_proved_without_editing_or_selecting_a_key(self):
        q = candidate(); before = copy.deepcopy(q)
        proof = composition_proof(q)
        self.assertEqual(proof['valid_option_indices'], [0, 2])
        with self.assertRaises(CompositionError) as raised: verify_composition(q)
        self.assertEqual(raised.exception.code, 'MCQ_COMPOSITION_NOT_UNIQUE')
        self.assertEqual(q, before)
        with self.assertRaises(ValueError): Question.model_validate(q)

    def test_single_correct_decomposition_and_wrong_key_are_distinguished(self):
        q = candidate(); q['options'][2] = 'Hàm trong là g(x)=3x, hàm ngoài là f(u)=(u+2)^4'
        verify_composition(q)
        q['answer'] = q['options'][1]
        with self.assertRaises(CompositionError) as raised: verify_composition(q)
        self.assertEqual(raised.exception.code, 'MCQ_COMPOSITION_KEY_CONFLICT')
        q['options'][0] = 'g(x)=3x+2, f(u)=u^4'; q['answer'] = q['options'][0]
        self.assertEqual(composition_proof(q)['valid_option_indices'], [])

    def test_exact_coefficients_unary_precedence_implicit_products_and_composition(self):
        self.assertEqual(polynomial('0.1x^2 + x/3 - 2', 'x'), (Fraction(-2), Fraction(1,3), Fraction(1,10)))
        self.assertEqual(polynomial('-x^2 + 2x(x+1)', 'x'), (Fraction(0), Fraction(2), Fraction(1)))
        q = candidate(); q.update(prompt='For h(x)=(2x-1)^2, choose the inner function and outer function.',
            options=['g(x)=2x-1, f(u)=u^2', 'g(x)=x-1/2, f(u)=4u^2', 'g(x)=x-1, f(u)=2u^2'])
        self.assertEqual(composition_proof(q)['valid_option_indices'], [0,1])

    def test_partial_formulas_unknown_domains_labels_and_unsafe_or_oversized_syntax_are_not_guessed(self):
        for text in ('sin(x)', '1/(x+1)', 'sqrt(x)', 'x^0', 'x^-1', 'x^1000000', '__import__("os")',
                     'x.__class__', 'x[0]', 'x;' + 'a'*300, '2 3', 'x y', 'X+1'):
            with self.subTest(text=text), self.assertRaises((ValueError, Unsupported)): polynomial(text, 'x')
        for option in ('g(x)=2,5x, f(u)=u^4', 'Không phải g(x)=3x, f(u)=(u+1)^4',
                       'g(x)=3x, f(u)=(u+1)^4 với u>0', 'g(x)=sqrt(x), f(u)=u^4'):
            q = candidate(); q['options'][2] = option
            self.assertIsNone(composition_proof(q))

    def test_a_fixed_decomposition_or_wrong_choice_question_is_outside_this_guard(self):
        for prompt in ('Cho h(x)=(3x+1)^4 và g(x)=3x+1. Chọn hàm trong và hàm ngoài theo g đã ấn định.',
                       'Xét h(x)=(3x+1)^4. Chọn hàm trong và hàm ngoài SAI.', 'Chọn đáp án đúng.'):
            q = candidate(); q['prompt'] = prompt
            self.assertIsNone(composition_proof(q)); verify_composition(q)

    def test_generated_bad_candidate_is_rejected_as_one_stage_not_a_silent_key_repair(self):
        q = candidate(); before = copy.deepcopy(q)
        with self.assertRaises(QuestionRejected) as raised:
            validated_generation(QUESTION_DRAFTS['mcq'], json.dumps({'question': q, 'reason': ''}), fragments=[{'id':'p','text':'Source'}])
        self.assertEqual(raised.exception.code, 'MCQ_COMPOSITION_NOT_UNIQUE')
        self.assertEqual(q, before)
        self.assertIn('candidate_sha256', raised.exception.details)

    def test_the_actual_dev_v5_saved_question_has_the_same_two_correct_options(self):
        path = Path(__file__).resolve().parents[2] / 'experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json'
        case = next(c for c in json.loads(path.read_text())['runs'] if c['case_id'] == 'calc-dev-chain')
        q = case['job']['partial']['questions']['mcq']['question']; before = copy.deepcopy(q)
        self.assertEqual(composition_proof(q)['valid_option_indices'], [0,2])
        with self.assertRaises(CompositionError): verify_composition(q)
        self.assertEqual(q, before)


class PolynomialWorkflowTests(SliceFixture):
    def test_ambiguous_legacy_question_is_quarantined_without_changing_old_attempt(self):
        course = self.course(); base = '/api/courses/' + course['id']
        attempt = self.client.post(base + '/sessions', json={'expected_revision':2, 'unit_id':'unit-1'}).json()
        old = self.client.get('/api/sessions/' + attempt['id']).json()
        content = copy.deepcopy(course['content']); refs = content['units'][0]['source_refs']
        q = candidate(); q['source_refs'] = refs; content['units'][0]['data']['questions'] = [q]
        with self.app.state.database.connection(write=True) as db:
            db.execute('UPDATE course_revisions SET content_json=? WHERE course_id=? AND revision=2', (json.dumps(content), course['id']))
        response = self.client.post(base + '/sessions', json={'expected_revision':2, 'unit_id':'unit-1'})
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json()['bank_warnings'])
        self.assertEqual(self.client.get('/api/sessions/' + attempt['id']).json(), old)
        self.assertEqual(self.client.get(base + '/editor').json()['content'], content)
