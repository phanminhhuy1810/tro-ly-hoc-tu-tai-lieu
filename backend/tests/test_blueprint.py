"""AI reads the whole document in parts, proposes chapters/lessons, the learner confirms."""
from unittest.mock import patch

import unittest

from study_backend import blueprint
from study_backend.blueprint import CourseBlueprint, PartReading, assemble
from test_slice import SliceFixture, TestProvider


class BlueprintProvider(TestProvider):
    async def generate(self, schema, instruction, fragments):
        if schema is PartReading:
            self.calls += 1
            self.instructions.append(instruction)
            # One topic per excerpt, but the last excerpt of each part is left unclaimed.
            claimed = fragments[:-1] or fragments
            return {'topics': [{'title': f['text'][:40], 'summary': f['text'][:120], 'source_refs': [f['id']]} for f in claimed], 'terms': ['prefix']}
        if schema is CourseBlueprint:
            self.calls += 1
            self.instructions.append(instruction)
            return {'subject': 'Mạng máy tính', 'goal': 'Tính được block /26', 'summary': 'IPv4 và chia mạng con.',
                    'chapters': [{'title': 'Địa chỉ IPv4', 'lessons': [{'title': 'IPv4 là gì', 'objective': 'Biết IPv4 có 32 bit', 'topics': [0]}]},
                                 {'title': 'Chia mạng con', 'lessons': [{'title': 'Block /26', 'objective': 'Tính số địa chỉ', 'topics': [1, 99]}]}],
                    'focus': ['Tính block'], 'study_tips': ['Làm lại ví dụ bằng tay'], 'rules': ['Giữ thuật ngữ tiếng Anh'],
                    'language': 'vi', 'language_note': 'Tiếng Việt, giữ thuật ngữ Anh', 'terms_to_keep': ['prefix']}
        return await super().generate(schema, instruction, fragments)


class BlueprintTests(SliceFixture):
    def setUp(self):
        with patch('test_slice.TestProvider', BlueprintProvider):
            super().setUp()
        source = self.source()
        self.src = self.client.post(f"/api/sources/{source['id']}/review", json={'expected_revision': 1, 'texts': [f['text'] for f in source['fragments']]}).json()
        self.ids = [f['id'] for f in self.src['fragments']]

    def start(self, **extra):
        return self.client.post(f"/api/sources/{self.src['id']}/blueprint", json={'expected_revision': self.src['revision'], **extra})

    def test_unreviewed_source_is_refused_without_calling_ai(self):
        fresh = self.source()
        response = self.client.post(f"/api/sources/{fresh['id']}/blueprint", json={'expected_revision': 1})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.provider.calls, 0)

    def test_whole_scope_is_read_then_every_excerpt_lands_in_one_lesson(self):
        result = self.job(self.start(goal='Ôn thi giữa kỳ'))
        self.assertEqual(result['status'], 'ready')
        value = self.client.get(f"/api/sources/{self.src['id']}/blueprint").json()
        assigned = [ref for chapter in value['chapters'] for lesson in chapter['lessons'] for ref in lesson['source_refs']]
        self.assertEqual(sorted(assigned), sorted(self.ids))
        self.assertEqual(len(assigned), len(set(assigned)))
        self.assertEqual([c['title'] for c in value['chapters']], ['Địa chỉ IPv4', 'Chia mạng con'])
        self.assertEqual(value['coverage']['placed_by_server'], 1)
        self.assertEqual(value['rules'], ['Giữ thuật ngữ tiếng Anh'])
        self.assertIn('Ôn thi giữa kỳ', self.provider.instructions[0])

    def test_long_documents_continue_in_a_new_job_without_rereading(self):
        with patch.object(blueprint, 'MAX_PART_FRAGMENTS', 1), patch.object(blueprint, 'PARTS_PER_JOB', 2):
            first = self.job(self.start())
            self.assertTrue(first['continuation_required'])
            self.assertEqual((first['read_parts'], first['total_parts']), (2, 3))
            calls = self.provider.calls
            second = self.job(self.start(resume_job_id='resume-1'))
        self.assertEqual(second['status'], 'ready')
        self.assertEqual(self.provider.calls - calls, 2)  # the third part + the roadmap, never parts 1–2 again

    def test_confirmed_roadmap_becomes_a_course_with_chapters(self):
        prefs = {'source_id': self.src['id'], 'subject': 'Mạng máy tính', 'goal': 'Tính block', 'fragment_ids': self.ids, 'language': 'vi',
                 'instructions': 'Giữ thuật ngữ tiếng Anh', 'expected_extraction_revision': self.src['revision']}
        lessons = [{'title': 'IPv4', 'objective': 'Biết 32 bit', 'source_refs': self.ids[:1], 'chapter': 'Địa chỉ'},
                   {'title': 'Block /26', 'objective': 'Tính số địa chỉ', 'source_refs': self.ids[1:], 'chapter': 'Chia mạng'}]
        missing = self.client.post('/api/plans/from-blueprint', json={'preferences': prefs, 'title': 'Mạng', 'lessons': lessons[:1]})
        self.assertEqual(missing.status_code, 422)
        twice = [lessons[0], {**lessons[1], 'source_refs': self.ids}]
        self.assertEqual(self.client.post('/api/plans/from-blueprint', json={'preferences': prefs, 'title': 'Mạng', 'lessons': twice}).status_code, 422)
        plan = self.client.post('/api/plans/from-blueprint', json={'preferences': prefs, 'title': 'Mạng', 'lessons': lessons})
        plan.raise_for_status()
        self.assertEqual(plan.json()['outline']['method'], 'ai_blueprint')
        course = self.client.post(f"/api/plans/{plan.json()['id']}/approve", json={'expected_revision': 1}).json()
        units = self.client.get(f"/api/courses/{course['course_id']}").json()['content']['units']
        self.assertEqual([(u['title'], u['chapter']) for u in units], [('IPv4', 'Địa chỉ'), ('Block /26', 'Chia mạng')])
        self.assertEqual(self.provider.calls, 0)


class AssembleTests(unittest.TestCase):
    def test_overlaps_go_to_the_first_lesson_and_oversized_lessons_split(self):
        selected = [{'id': f'f{i}', 'text': 'x' * 100, 'locator': {'type': 'line', 'line': i}} for i in range(12)]
        topics = [{'source_refs': [f'f{i}' for i in range(10)]}, {'source_refs': ['f3', 'f10']}]
        plan = {'chapters': [{'title': 'A', 'lessons': [{'title': 'Một', 'objective': 'o', 'topics': [0]}, {'title': 'Hai', 'objective': 'o', 'topics': [1]}]}]}
        chapters, coverage = assemble(plan, topics, selected)
        lessons = chapters[0]['lessons']
        self.assertEqual([(l['title'], len(l['source_refs'])) for l in lessons], [('Một (phần 1)', 5), ('Một (phần 2)', 5), ('Hai', 2)])
        self.assertEqual(lessons[2]['source_refs'], ['f10', 'f11'])
        self.assertEqual(coverage['placed_by_server'], 1)
        self.assertEqual(coverage['lessons_split_to_fit'], 1)


class LenientOutputTests(unittest.TestCase):
    def test_overlong_suggestions_are_trimmed_instead_of_failing(self):
        reading = PartReading.model_validate({'topics': [{'title': 't' * 300, 'summary': 's', 'source_refs': ['R1']}] * 12,
                                              'terms': [f'term {i}' for i in range(14)] + ['  ']})
        self.assertEqual((len(reading.topics), len(reading.terms), len(reading.topics[0].title)), (10, 12, 160))
        plan = CourseBlueprint.model_validate({'subject': 'Mạng', 'goal': 'g', 'summary': 's', 'language': 'vi-en',
                                               'chapters': [{'title': 'C', 'lessons': [{'title': 'L', 'objective': 'o', 'topics': [0]}]}],
                                               'rules': ['r'] * 9})
        self.assertEqual((plan.language, len(plan.rules)), ('vi', 6))
