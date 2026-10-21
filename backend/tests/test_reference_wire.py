import asyncio
import copy
import json
import unittest

import httpx

from study_backend.ai import LocalAI
from study_backend.generation_contract import QuestionRejected, generation_schema
from study_backend.models import ChatReply, LessonReading, QUESTION_DRAFTS, SourceReferenceError
from study_backend.reference_wire import ReferenceWire
from study_backend.gemini import GeminiAI


class ReferenceWireTests(unittest.TestCase):
    def setUp(self):
        self.fragments=[{'id':f'9e4fd21e3d03413c98be56a868494c36:2:{i}',
                         'text':'IPv4 has 32 bits.' if i==0 else 'A /26 block contains 64 addresses.'} for i in range(6)]
        self.wire=ReferenceWire(self.fragments)

    def test_one_based_aliases_restore_exact_zero_based_ids_without_repairing_unknowns(self):
        value={'text':'Keep the variable R1 and literal text unchanged.','source_refs':['R1','R6'],'needs_more_source':False}
        restored=self.wire.validated(ChatReply,json.dumps(value)).model_dump()
        self.assertEqual(restored['source_refs'],[self.fragments[0]['id'],self.fragments[5]['id']])
        self.assertEqual(restored['text'],value['text'])
        for unknown in ['R0','R7','r1','R01','9e4fd21e3d03413c98be56a868494c36:2:6','other-source:2:0']:
            with self.subTest(unknown=unknown),self.assertRaises(SourceReferenceError):
                self.wire.validated(ChatReply,json.dumps({**value,'source_refs':[unknown]}))
        self.assertEqual(self.wire.validated(ChatReply,json.dumps({**value,'source_refs':[self.fragments[0]['id']]})).source_refs,[self.fragments[0]['id']])

    def test_reading_refs_in_sections_cards_and_mindmap_all_restore_before_domain_validation(self):
        reading={'title':'IP','sections':[{'title':'IPv4','text':'32 bits.','source_refs':['R1']}],
                 'cards':[{'front':'How many bits?','back':'32','source_refs':['R1']}],
                 'mindmap':[{'title':'/26','text':'64 addresses','source_refs':['R2']}]}
        value=self.wire.validated(LessonReading,json.dumps(reading)).model_dump()
        self.assertEqual(value['sections'][0]['source_refs'],[self.fragments[0]['id']])
        self.assertEqual(value['cards'][0]['source_refs'],[self.fragments[0]['id']])
        self.assertEqual(value['mindmap'][0]['source_refs'],[self.fragments[1]['id']])
        self.assertEqual(value['cards'][0]['back'],'32')

    def test_cloze_still_uses_original_text_and_rejection_details_keep_real_ids(self):
        value={'question':{'kind':'cloze','prompt':None,'answer':'32','explanation':'IPv4 has 32 bits.','source_refs':['R1']},'reason':''}
        question=self.wire.validated(QUESTION_DRAFTS['cloze'],json.dumps(value)).question
        self.assertIn('____',question.prompt);self.assertEqual(question.answer,'32')
        self.assertEqual(question.source_refs,[self.fragments[0]['id']])
        value['question']['answer']='128'
        with self.assertRaises(QuestionRejected) as caught:self.wire.validated(QUESTION_DRAFTS['cloze'],json.dumps(value))
        self.assertEqual(caught.exception.details['source_refs'],[self.fragments[0]['id']])

    def test_ordering_key_is_derived_from_source_after_alias_decoding(self):
        wire=ReferenceWire([{'id':'source:2:0','text':'Procedure: (1) read the prefix; (2) calculate host bits.'}])
        value={'question':{'kind':'ordering','prompt':'Arrange the steps','options':['calculate host bits','read the prefix'],
                          'explanation':'Follow the source order.','source_refs':['R1']},'reason':''}
        question=wire.validated(QUESTION_DRAFTS['ordering'],json.dumps(value)).question
        self.assertEqual(question.answer,[1,0]);self.assertEqual(question.source_refs,['source:2:0'])

    def test_request_schema_enum_does_not_mutate_cached_schema_or_allow_an_extra_label(self):
        original=generation_schema(LessonReading).model_json_schema();before=copy.deepcopy(original)
        encoded=self.wire.schema(original)
        arrays=[]
        def find(value):
            if isinstance(value,dict):
                if 'source_refs' in value.get('properties',{}):arrays.append(value['properties']['source_refs'])
                for child in value.values():find(child)
            elif isinstance(value,list):
                for child in value:find(child)
        find(encoded)
        self.assertTrue(arrays)
        self.assertTrue(all(x['items']['enum']==['R1','R2','R3','R4','R5','R6'] for x in arrays))
        self.assertEqual(original,before)
        self.assertEqual(generation_schema(LessonReading).model_json_schema(),before)

    def test_instruction_id_replacement_is_token_exact_and_never_changes_source_text(self):
        fragments=[{'id':'a:2:1','text':'R1 is a variable; a:2:1 is literal source text.'},{'id':'a:2:10','text':'Second.'}]
        wire=ReferenceWire(fragments)
        encoded=wire.instruction(json.dumps({'valid':['a:2:1','a:2:10'],'outside':'a:2:11'}))
        self.assertIn('"valid": ["R1", "R2"]',encoded);self.assertIn('a:2:11',encoded)
        self.assertEqual(wire.fragments[0]['text'],fragments[0]['text'])
        self.assertEqual(fragments[0]['id'],'a:2:1')

    def test_local_adapter_sends_aliases_and_returns_only_persistable_real_ids(self):
        captured=[]
        def handle(request):
            payload=json.loads(request.content);captured.append(payload)
            content={'text':'IPv4 has 32 bits.','source_refs':['R1'],'needs_more_source':False}
            return httpx.Response(200,json={'message':{'content':json.dumps(content)},'done_reason':'stop'})
        class Local(LocalAI):
            async def status(self):return {'ready':True}
            def client(self,timeout):return httpx.AsyncClient(transport=httpx.MockTransport(handle))
        value=asyncio.run(Local().generate(ChatReply,'Explain '+self.fragments[0]['id'],self.fragments))
        self.assertEqual(value['source_refs'],[self.fragments[0]['id']])
        self.assertIn('"id": "R1"',captured[0]['messages'][1]['content'])
        self.assertNotIn(self.fragments[0]['id'],captured[0]['messages'][1]['content'])
        self.assertEqual(captured[0]['format']['properties']['source_refs']['items']['enum'],['R1','R2','R3','R4','R5','R6'])
        self.assertEqual(len(captured),1)

    def test_gemini_uses_the_same_request_labels_and_restores_original_ids(self):
        captured=[]
        def handle(request):
            captured.append(json.loads(request.content))
            content={'text':'A /26 has 64 addresses.','source_refs':['R2'],'needs_more_source':False}
            return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(content)}]}}]})
        class Gemini(GeminiAI):
            def client(self,timeout):return httpx.AsyncClient(transport=httpx.MockTransport(handle))
        value=asyncio.run(Gemini(api_key='development-test',enabled=True).generate(ChatReply,'Explain the block',self.fragments))
        self.assertEqual(value['source_refs'],[self.fragments[1]['id']])
        self.assertIn('"id": "R2"',captured[0]['contents'][0]['parts'][0]['text'])
        self.assertEqual(captured[0]['generationConfig']['responseJsonSchema']['properties']['source_refs']['items']['enum'],['R1','R2','R3','R4','R5','R6'])
