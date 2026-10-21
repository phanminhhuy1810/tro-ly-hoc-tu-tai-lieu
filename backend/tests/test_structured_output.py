import asyncio
import json
import unittest

import httpx
from pydantic import ValidationError

from study_backend.ai import LocalAI
from study_backend.models import ChatReply,QUESTION_DRAFTS,ClozeQuestion,ShortQuestion,McqQuestion,MatchingQuestion,OrderingQuestion
from study_backend.structured_output import validated_json,without_trailing_commas


class Progress:
    def __init__(self):self.values={};self.fallbacks=0
    def usage(self,value):self.values.update(value)
    def chunk(self,text):pass
    def fallback(self):self.fallbacks+=1


class StructuredOutputTests(unittest.TestCase):
    def test_generation_wire_schema_expresses_question_shape_rules_before_calling_a_model(self):
        # A model following the schema must not be invited to generate payloads
        # that the domain validator already forbids (the real Gemma cloze failure).
        for schema in [ClozeQuestion,ShortQuestion]:
            properties=schema.model_json_schema()['properties']
            self.assertEqual(properties['options']['maxItems'],0)
            self.assertEqual(properties['left']['maxItems'],0)
        for schema in [McqQuestion,OrderingQuestion]:
            properties=schema.model_json_schema()['properties']
            self.assertEqual(properties['left']['maxItems'],0)
            self.assertGreaterEqual(properties['options']['minItems'],2)
        self.assertGreaterEqual(MatchingQuestion.model_json_schema()['properties']['left']['minItems'],2)
        self.assertGreaterEqual(ShortQuestion.model_json_schema()['properties']['rubric']['minItems'],1)

    def test_only_structural_commas_change_and_quoted_escaped_text_stays_exact(self):
        raw='{"text":"literal ,] and ,} plus escaped \\\" ,] and slash \\\\","source_refs":["ref,]",],"needs_more_source":false,}'
        progress=Progress();value=validated_json(ChatReply,raw,progress)
        self.assertEqual(value.source_refs,['ref,]']);self.assertIn('literal ,] and ,}',value.text)
        self.assertIn('escaped " ,]',value.text);self.assertEqual(progress.values['json_trailing_commas_removed'],2)
        self.assertNotEqual(progress.values['raw_json_sha256'],progress.values['normalized_json_sha256'])

    def test_invalid_values_and_incomplete_or_executable_text_are_still_rejected(self):
        for raw in ['{"text":,}', '{"text":"unfinished,}', '{"text":"ok",,"source_refs":[],}',
                    'run({"text":"x",})','{"text":"ok","source_refs":[],"needs_more_source":"not a boolean",}',
                    '{"text":"ok","source_refs":[],"needs_more_source":false,"unknown":1,}']:
            with self.subTest(raw=raw),self.assertRaises(ValidationError):validated_json(ChatReply,raw)
        question={'question':{'kind':'mcq','prompt':'Pick one','options':['32 bit','4 byte'],'answer':'32 bit','explanation':'Test','source_refs':['ref']},'reason':''}
        raw=json.dumps(question)[:-1]+',}'
        with self.assertRaises(ValidationError):validated_json(QUESTION_DRAFTS['mcq'],raw)

    def test_normalization_has_a_size_and_change_bound(self):
        raw='"'+('x'*200_001)+'",}'
        self.assertEqual(without_trailing_commas(raw),(raw,0))
        raw='['+','.join('[0,]' for _ in range(65))+']'
        self.assertEqual(without_trailing_commas(raw),(raw,0))

    def test_real_adapter_validates_after_one_protocol_fallback_without_an_extra_model_call(self):
        async def scenario():
            requests=[];progress=Progress()
            def transport(request):
                body=json.loads(request.content);requests.append(body)
                if 'format' in body:return httpx.Response(501,json={'error':'structured output is unavailable'})
                text='{"text":"64 địa chỉ, 62 host","source_refs":["ref",],"needs_more_source":false,}'
                packets=[{'message':{'content':text},'done':False},{'message':{'content':''},'done':True,'done_reason':'stop','eval_count':20}]
                return httpx.Response(200,content='\n'.join(json.dumps(p) for p in packets))
            class Adapter(LocalAI):
                async def status(self):return {'ready':True}
                def client(self,timeout):return httpx.AsyncClient(transport=httpx.MockTransport(transport),timeout=timeout)
            output=await Adapter().generate_stream(ChatReply,'Explain',[{'id':'ref','text':'64 addresses,62 hosts','locator':{}}],progress)
            self.assertEqual(output['source_refs'],['ref']);self.assertEqual(len(requests),2)
            self.assertEqual(progress.fallbacks,1);self.assertEqual(progress.values['json_trailing_commas_removed'],2)
        asyncio.run(scenario())
