import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from study_backend.ai import LocalAI
from study_backend.providers import local_models


class LocalModelConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.path=Path(self.tmp.name)/'local-models.json'
        self.env=patch.dict(os.environ,{'STUDY_LOCAL_MODELS_CONFIG':str(self.path)},clear=False);self.env.start()
        self.old=os.environ.pop('STUDY_LOCAL_MODELS',None)

    def tearDown(self):
        self.env.stop();self.tmp.cleanup()

    def write(self,value):
        self.path.write_text(json.dumps(value));self.path.chmod(0o600)

    def test_persistent_allowlist_keeps_original_model_and_deduplicates(self):
        self.assertEqual(local_models(),[LocalAI.model])
        self.write({'models':['gemma4:12b-mlx',LocalAI.model,'gemma4:12b-mlx']})
        self.assertEqual(local_models(),[LocalAI.model,'gemma4:12b-mlx'])
        self.assertEqual(local_models(),[LocalAI.model,'gemma4:12b-mlx'])

    def test_operator_environment_override_does_not_read_an_invalid_file(self):
        self.write({'untrusted':'not used when explicitly overridden'})
        with patch.dict(os.environ,{'STUDY_LOCAL_MODELS':' qwen2.5-coder:3b, gemma4:12b-mlx '}):
            self.assertEqual(local_models(),[LocalAI.model,'qwen2.5-coder:3b','gemma4:12b-mlx'])
        with patch.dict(os.environ,{'STUDY_LOCAL_MODELS':''}):self.assertEqual(local_models(),[LocalAI.model])

    def test_invalid_server_config_fails_closed_instead_of_adding_unknown_models(self):
        for value in [{'models':'gemma4:12b-mlx'},{'models':[3]},{'models':['bad\nmodel']},
                      {'models':['bad\x00name']},{'models':['']},{'models':[], 'endpoint':'https://untrusted.test'},
                      {'models':['model:'+str(i) for i in range(9)]}]:
            with self.subTest(value=value):
                self.write(value)
                with self.assertRaises(ValueError):local_models()
        self.write({'models':['gemma4:12b-mlx']});self.path.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'600'):local_models()
