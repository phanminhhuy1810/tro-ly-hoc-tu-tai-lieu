"""Behavior checks for experiment plumbing; never call or grade the live model."""
import importlib.util
import io
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('network_bench', ROOT/'benchmark.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
BUNDLE = json.loads((ROOT/'benchmark-bundle.json').read_text())
WORK = {row['id']: row for row in BUNDLE['workloads']}


class FakeConnection:
    events = []
    def __init__(self, *args, **kwargs):
        self.sock = self
        self.closed = False
    def settimeout(self, timeout):
        pass
    def request(self, method, path, payload, headers):
        self.payload = json.loads(payload)
    def getresponse(self):
        response = io.BytesIO(b''.join(json.dumps(e).encode()+b'\n' for e in self.events))
        response.status = 200
        return response
    def close(self):
        self.closed = True


class Checks(unittest.TestCase):
    def question(self):
        return {'kind': 'mcq', 'prompt': 'Network của172.29.217.10/19?',
                'options': ['172.29.192.0', '172.29.0.0', '172.29.224.0', '172.29.217.0'],
                'answer': '172.29.192.0', 'explanation': '32 địa chỉ mỗi block trong octet3.',
                'source_refs': ['pdf-p23', 'pdf-p26']}

    def test_valid_json_can_still_have_wrong_fixed_answer(self):
        q = self.question()
        q['answer'] = '172.29.224.0'
        result = bench.evaluate(json.dumps(q), WORK['mcq'], BUNDLE['fragments'])
        self.assertTrue(result['schema_valid'])
        self.assertTrue(result['refs_valid'])
        self.assertFalse(result['oracle_pass'])

    def test_unknown_source_and_unselected_key_fail(self):
        q = self.question()
        q.update(answer='A', source_refs=['page404'])
        result = bench.evaluate(json.dumps(q), WORK['mcq'], BUNDLE['fragments'])
        self.assertFalse(result['schema_valid'])
        self.assertFalse(result['refs_valid'])

    def test_identical_prompts_independent_of_model_and_pipeline_reading(self):
        before = bench.build_messages(WORK['pipeline_mcq_1'], BUNDLE['fragments'])
        self.assertEqual(before, bench.build_messages(WORK['pipeline_mcq_1'], BUNDLE['fragments']))
        self.assertEqual(WORK['mcq']['oracle']['answer'], '172.29.192.0')
        self.assertEqual(BUNDLE['oracle']['broadcast'], '172.29.223.255')
        self.assertEqual(BUNDLE['oracle']['usable_hosts'], 8190)

    def test_empty_event_is_not_first_content_and_stream_failure_keeps_partial(self):
        FakeConnection.events = [{'message': {'content': ''}}, {'message': {'content': '{"text":'}}, {'error': 'interrupted'}]
        with patch.object(bench.http.client, 'HTTPConnection', FakeConnection):
            row = bench.stream_call('test', WORK['term'], BUNDLE['fragments'], time.monotonic()+5, 5)
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['content'], '{"text":')
        self.assertEqual(len(row['events']), 3)
        self.assertGreaterEqual(row['first_content_seconds'], row['first_event_seconds'])
        self.assertFalse(row['validation']['json_valid'])

    def test_deadline_does_not_start_a_request(self):
        with patch.object(bench.http.client, 'HTTPConnection') as connection:
            row = bench.stream_call('test', WORK['term'], BUNDLE['fragments'], time.monotonic()-1, 5)
        connection.assert_not_called()
        self.assertEqual(row['status'], 'skipped_deadline')


if __name__ == '__main__':
    unittest.main()
