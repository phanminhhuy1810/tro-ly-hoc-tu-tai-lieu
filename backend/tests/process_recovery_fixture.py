"""Explicit provider double for an isolated process-crash integration test."""
import asyncio
import copy
import json
import os
import threading
from pathlib import Path

from study_backend.app import create_app
from study_backend.economy import POLICY
from study_backend.models import QUESTION_DRAFTS
from test_slice import TestProvider
from study_backend.extract import extract


class CrashProvider(TestProvider):
    async def generate(self, schema, instruction, fragments):
        with Path(os.environ['STUDY_TEST_CALLS']).open('a') as handle:
            handle.write(json.dumps({'schema': schema.__name__})+'\n')
        if os.environ.get('STUDY_TEST_BLOCK') == 'matching' and schema is QUESTION_DRAFTS['matching']:
            Path(os.environ['STUDY_TEST_READY']).write_text('waiting')
            await asyncio.Future()
        return await super().generate(schema, instruction, fragments)


policy = copy.deepcopy(POLICY)
policy['initial_quota'] = {}  # Exercise paid reserve/release on every job.
def read_source(name,data):
    if os.environ.get('STUDY_TEST_BLOCK')=='source':
        Path(os.environ['STUDY_TEST_READY']).write_text('source parsing')
        threading.Event().wait()
    return extract(name,data,ocr=False)
app = create_app(os.environ['STUDY_TEST_DB'], os.environ['STUDY_TEST_SOURCES'],
                 provider=CrashProvider(), coin_policy=policy,extractor=read_source)
