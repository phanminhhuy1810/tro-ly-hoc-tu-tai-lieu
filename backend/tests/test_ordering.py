import copy
import json
import unittest
from pathlib import Path
from study_backend.ordering import verify_ordering, derive_generated_ordering
from study_backend.extract import explicit_sequence
from study_backend.models import QUESTION_DRAFTS
from test_slice import SliceFixture


FRAGMENTS = [{'id': 'procedure', 'text': 'Quy trình: (1) đọc prefix; (2) tính số bit host; (3) tìm block chứa IP; (4) xác định network và broadcast; (5) đếm host dùng được.', 'locator': {}}]


class OrderingEvidenceTests(unittest.TestCase):
    def test_real_chain_rule_steps_are_not_contaminated_by_the_function_argument_zero(self):
        root=Path(__file__).resolve().parents[2]
        run=json.loads((root/'experiments/08-quality-evaluation/results/dev-v4-chapter.json').read_text())
        case=next(x for x in run['runs'] if x['case_id']=='calc-dev-chain')
        source=case['source_snapshot']['fragments']
        self.assertIn("h'(0)",source[1]['text'])
        self.assertTrue(explicit_sequence(source))
        steps=[f for f in source if f['text'].startswith(('1. ','2. ','3. ','4. '))]
        self.assertEqual(len(steps),4)
        phrases=[f['text'].split('. ',1)[1] for f in reversed(steps)]
        question={'kind':'ordering','options':phrases,'source_refs':[f['id'] for f in steps]}
        derived,_=derive_generated_ordering(question,source)
        self.assertEqual(derived['answer'],[3,2,1,0])
        self.assertEqual(derived['source_refs'],question['source_refs'])
        self.assertEqual(derived['options'],phrases)
        from study_backend.question_completion import missing_questions
        info=missing_questions(case['course_snapshot']['content']['units'][0],case['course_snapshot']['content']['preferences'],source)
        ordering=next(x for x in info if x['stage']=='ordering')
        self.assertTrue(ordering['can_generate']);self.assertEqual(ordering['origin'],'backend_source_rechecked')
        self.assertNotIn('chưa có',ordering['reason'])

    def test_function_arguments_and_equations_are_not_numbered_procedures(self):
        for text in ["f(1) Read the prefix; f(2) Calculate host bits.",
                     "h′(1) Read the prefix; h′(2) Calculate host bits.",
                     '(1) = read the prefix; (2) = calculate host bits.']:
            with self.subTest(text=text):self.assertFalse(explicit_sequence([{'id':'math','text':text}]))

    def test_explicit_parenthesized_step_labels_and_zero_based_procedures_still_work(self):
        for text in ['Step(1) Read the prefix; Step(2) Calculate host bits.',
                     'Quy trình: (0) đọc prefix; (1) tính số bit host;',
                     'Procedure:(1) read the prefix;(2) calculate host bits.']:
            with self.subTest(text=text):self.assertTrue(explicit_sequence([{'id':'steps','text':text}]))

    def question(self):
        return {'kind': 'ordering', 'options': ['Tính số bit host (6 bit)', 'Tìm block chứa IP (64–127)', 'Đọc prefix (/26)', 'Xác định network và broadcast', 'Đếm host dùng được'],
                'answer': [2, 0, 1, 3, 4], 'source_refs': ['procedure']}

    def test_key_is_checked_against_source_steps_not_a_permutation_alone(self):
        q = self.question();verify_ordering(q, FRAGMENTS)
        q['answer'] = [2, 0, 3, 1, 4]
        with self.assertRaisesRegex(ValueError, 'đảo thứ tự'):
            verify_ordering(q, FRAGMENTS)

    def test_unverifiable_paraphrase_wrong_refs_or_duplicate_step_is_not_silently_accepted(self):
        for change in [{'source_refs': ['other']}, {'options': ['Read', 'Compute', 'Group', 'Borders', 'Count']}, {'options': ['Đọc prefix', 'Đọc prefix', 'Đọc prefix', 'Đọc prefix', 'Đọc prefix']}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_ordering({**self.question(), **change}, FRAGMENTS)
        bilingual = self.question();bilingual['options'][2] = 'Read the prefix — "đọc prefix"'
        verify_ordering(bilingual, FRAGMENTS)

    def test_bare_numbered_actions_across_lines_are_steps_without_inventing_a_heading(self):
        fragments=[{'id':f'source:2:{i}','text':text,'locator':{'line':i+1}} for i,text in enumerate([
            '1. Đọc prefix và tính số bit host.', '2. Tính kích thước block.', '3. Xác định block chứa octet cuối.'
        ])]
        self.assertTrue(explicit_sequence(fragments))
        question={'kind':'ordering','options':['Tính kích thước block','Đọc prefix và tính số bit host','Xác định block chứa octet cuối'],
                  'answer':[1,0,2],'source_refs':[f['id'] for f in fragments]}
        verify_ordering(question,fragments)
        with self.assertRaisesRegex(ValueError,'đảo thứ tự'):verify_ordering({**question,'answer':[0,1,2]},fragments)

    def test_numbered_concepts_and_nonconsecutive_labels_stay_insufficient(self):
        for text in ['1. Network address\n2. Broadcast address', '1. Read the prefix\n3. Calculate host bits']:
            with self.subTest(text=text):self.assertFalse(explicit_sequence([{'id':'source','text':text,'locator':{}}]))

    def test_separate_documents_cannot_jointly_look_like_one_procedure(self):
        fragments=[{'id':f'collection:1:{i}','text':f'Step {i+1}: '+text,'locator':{
            'component_source_id':f'doc-{i}','component_revision':1,'component_fragment_id':f'doc-{i}:1:0'}}
            for i,text in enumerate(['Read the prefix','Calculate host bits'])]
        self.assertFalse(explicit_sequence(fragments))
        with self.assertRaises(ValueError):verify_ordering({'kind':'ordering','options':['Read the prefix','Calculate host bits'],
            'answer':[0,1],'source_refs':[f['id'] for f in fragments]},fragments)

    def test_a_missing_source_range_does_not_bridge_unrelated_numbered_steps(self):
        fragments=[{'id':'source:2:1','text':'Step 1: Read the prefix','locator':{}},
                   {'id':'source:2:3','text':'Step 2: Calculate host bits','locator':{}}]
        self.assertFalse(explicit_sequence(fragments))

    def test_scoped_procedure_heading_qualifies_cited_steps_without_citing_heading(self):
        fragments=[{'id':f'source:2:{i}','text':text,'locator':{}} for i,text in enumerate([
            'Quy trình tìm khối:', '1. Bỏ hai biên để tìm host.', '2. Tìm địa chỉ còn lại.'
        ])]
        q={'kind':'ordering','options':['Tìm địa chỉ còn lại','Bỏ hai biên để tìm host'],
           'answer':[1,0],'source_refs':['source:2:1','source:2:2']}
        verify_ordering(q,fragments)
        self.assertEqual(q['source_refs'],['source:2:1','source:2:2'])
        with self.assertRaises(ValueError):verify_ordering(q,fragments[1:])

    def test_a_heading_cannot_replace_citations_for_the_actual_selected_steps(self):
        fragments=[{'id':f'source:2:{i}','text':text,'locator':{}} for i,text in enumerate([
            'Quy trình tìm khối:', '1. Bỏ hai biên để tìm host.', '2. Tìm địa chỉ còn lại.'
        ])]
        q={'kind':'ordering','options':['Tìm địa chỉ còn lại','Bỏ hai biên để tìm host'],'answer':[1,0]}
        for refs in [['source:2:0'],['source:2:1'],['outside']]:
            with self.subTest(refs=refs),self.assertRaises(ValueError):verify_ordering({**q,'source_refs':refs},fragments)

    def test_heading_from_another_component_does_not_authorize_bare_unrecognized_steps(self):
        fragments=[{'id':'a:2:0','text':'Quy trình tìm khối:','locator':{}},
                   {'id':'b:2:0','text':'1. Bỏ hai biên để tìm host.','locator':{}},
                   {'id':'b:2:1','text':'2. Tìm địa chỉ còn lại.','locator':{}}]
        q={'kind':'ordering','options':['Tìm địa chỉ còn lại','Bỏ hai biên để tìm host'],
           'answer':[1,0],'source_refs':['b:2:0','b:2:1']}
        with self.assertRaises(ValueError):verify_ordering(q,fragments)

    def test_two_cited_procedures_with_conflicting_order_are_not_resolved_by_first_match(self):
        fragments=[{'id':'ref','text':'Procedure: (1) read the prefix; (2) calculate host bits.\n'
                    'Procedure: (1) calculate host bits; (2) read the prefix.'}]
        q={'kind':'ordering','options':['read the prefix','calculate host bits'],'answer':[0,1],'source_refs':['ref']}
        with self.assertRaisesRegex(ValueError,'mâu thuẫn'):verify_ordering(q,fragments)

    def test_procedure_heading_is_not_borrowed_by_a_later_concept_list_or_from_future_text(self):
        concept='1. Network address\n2. Broadcast address'
        for text in ['Procedure: (1) read the prefix; (2) calculate host bits.\nConcepts:\n'+concept,
                     concept+'\nQuy trình sẽ được mô tả sau.']:
            with self.subTest(text=text):
                q={'kind':'ordering','options':['Network address','Broadcast address'],'answer':[0,1],'source_refs':['ref']}
                with self.assertRaises(ValueError):verify_ordering(q,[{'id':'ref','text':text,'locator':{}}])


class OrderingPipelineTests(SliceFixture):
    def test_chapter_with_function_values_still_calls_and_saves_its_supported_ordering(self):
        text="Ví dụ h(x)=(3x+1)^4 cho h'(0)=12.\nQuy trình dùng chain rule:\n1. Xác định hàm trong và hàm ngoài.\n2. Lấy đạo hàm hàm ngoài rồi thế hàm trong vào.\n3. Tính đạo hàm hàm trong.\n4. Nhân hai kết quả để được đạo hàm hàm hợp."
        source=self.client.post('/api/sources/text',json={'name':'chain-rule.txt','text':text}).json()
        source=self.client.post('/api/sources/'+source['id']+'/review',json={'expected_revision':1,'texts':[f['text'] for f in source['fragments']]}).json()
        prefs={**self.preferences(source),'subject':'Vi tích phân','question_types':['ordering'],'question_count':1}
        plan=self.client.post('/api/plans/from-source-sections',json=prefs).json()
        cid=self.client.post('/api/plans/'+plan['id']+'/approve',json={'expected_revision':1}).json()['course_id']
        original=self.provider.generate;seen=[]
        async def model(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['ordering']:
                seen.append(schema)
                steps=[f for f in fragments if f['text'].startswith(('1. ','2. ','3. ','4. '))]
                return {'question':{'kind':'ordering','prompt':'Sắp xếp quy trình trong nguồn.',
                        'options':[f['text'].split('. ',1)[1] for f in reversed(steps)],
                        'answer':[3,2,1,0],'explanation':'Theo bốn bước đánh số nguồn.',
                        'source_refs':[f['id'] for f in steps]},'reason':''}
            return await original(schema,instruction,fragments)
        self.provider.generate=model
        self.job(self.client.post('/api/courses/'+cid+'/generate',json={'expected_revision':1,'unit_id':'unit-1'}))
        unit=self.client.get('/api/courses/'+cid+'/editor').json()['content']['units'][0]
        self.assertEqual(len(seen),1);self.assertEqual(unit['data']['questions'][0]['answer'],[3,2,1,0])
        self.assertTrue(unit['generation']['question_coverage']['complete'])
        self.assertEqual(self.client.get('/api/sources/'+source['id']).json(),source)


class LegacyOrderingTests(SliceFixture):
    def test_legacy_bad_key_is_excluded_from_new_sessions_old_snapshot_kept_and_manual_fix_checked(self):
        course = self.course();base = '/api/courses/' + course['id']
        old = self.client.post(base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'}).json()
        # Emulate a pre-validator model output which is a valid permutation but
        # contradicts the explicit order in the same source.
        with self.app.state.database.connection(write=True) as db:
            content = copy.deepcopy(course['content'])
            content['units'][0]['data']['questions'][3]['answer'] = [1, 0]
            db.execute('UPDATE course_revisions SET content_json=? WHERE course_id=? AND revision=2', (json.dumps(content), course['id']))
        response = self.client.post(base + '/sessions', json={'expected_revision': 2, 'unit_id': 'unit-1'})
        response.raise_for_status();new = response.json()
        self.assertNotIn('ordering', [q['kind'] for q in new['questions']])
        self.assertTrue(new['scope']['bank_warnings'])
        preserved = self.client.get('/api/sessions/' + old['id']).json()
        self.assertEqual(len(preserved['questions']), 5)
        bad = content['units'][0]['data']['questions'][3]
        denied = self.client.post(base + '/proposals', json={'expected_revision': 2, 'unit_id': 'unit-1', 'target': 'question', 'index': 3, 'request': 'check key', 'replacement': bad})
        self.assertEqual(denied.status_code, 422)
        good = {**bad, 'answer': [0, 1]}
        proposal = self.client.post(base + '/proposals', json={'expected_revision': 2, 'unit_id': 'unit-1', 'target': 'question', 'index': 3, 'request': 'fix saved order', 'replacement': good})
        proposal.raise_for_status()
