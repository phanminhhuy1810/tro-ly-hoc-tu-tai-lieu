"""Transport contracts exercise real parsers, not a real model or API key."""
import asyncio
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from study_backend.ai import LocalAI
from study_backend.gemini import GeminiAI, ProviderError
from study_backend.generation_contract import generation_schema, validated_generation, QuestionRejected
from study_backend.models import QUESTION_DRAFTS, ChatReply, SourceReferenceError


SOURCE = [{'id': 'ref', 'text': 'A /26 block has 64 addresses and 62 usable hosts.'}]
CLOZE = {'question': {'kind': 'cloze', 'prompt': 'A /26 block has ____ usable hosts.',
                     'answer': '62', 'explanation': 'Two addresses are network and broadcast.',
                     'source_refs': ['ref']}, 'reason': ''}


class Progress:
    def __init__(self):self.fallbacks=0
    def usage(self, value):pass
    def chunk(self, value):pass
    def fallback(self):self.fallbacks+=1


class GenerationContractTests(unittest.TestCase):
    def test_null_reason_beside_a_valid_question_does_not_change_question_or_answer(self):
        draft={**deepcopy(CLOZE),'reason':None}
        class Audit(Progress):
            def __init__(self):super().__init__();self.values={}
            def usage(self,value):self.values.update(value)
        audit=Audit();value=validated_generation(QUESTION_DRAFTS['cloze'],json.dumps(draft),audit,SOURCE).model_dump()
        self.assertEqual(value['reason'],'')
        self.assertEqual(value['question']['prompt'],CLOZE['question']['prompt'])
        self.assertEqual(value['question']['answer'],CLOZE['question']['answer'])
        self.assertEqual(audit.values['question_empty_reason_normalized'],1)

    def test_nullable_reason_does_not_accept_unexplained_decline_or_bad_question_fields(self):
        for reason in [None,'',True]:
            with self.subTest(reason=reason),self.assertRaises(ValidationError):
                validated_generation(QUESTION_DRAFTS['cloze'],json.dumps({'question':None,'reason':reason}),fragments=SOURCE)
        draft={**deepcopy(CLOZE),'reason':None};draft['question']['options']=[]
        with self.assertRaises(ValidationError):validated_generation(QUESTION_DRAFTS['cloze'],json.dumps(draft),fragments=SOURCE)

    def test_mcq_unmatched_key_or_duplicate_choices_are_rejected_without_inventing_key(self):
        base={'kind':'mcq','prompt':'How many usable hosts?','options':['62','64','128'],
              'answer':'A','explanation':'From source','source_refs':['ref']}
        for question in [base,{**base,'options':['62','62','64'],'answer':'62'}]:
            before=deepcopy(question)
            with self.subTest(question=question),self.assertRaises(QuestionRejected) as caught:
                validated_generation(QUESTION_DRAFTS['mcq'],json.dumps({'question':question,'reason':''}),fragments=SOURCE)
            self.assertEqual(caught.exception.code,'MCQ_KEY_OR_CHOICES_INVALID')
            self.assertEqual(question,before)
            self.assertEqual(caught.exception.details['source_refs'],['ref'])

    def test_foreign_reference_is_still_hard_error_even_for_invalid_mcq_key(self):
        draft={'question':{'kind':'mcq','prompt':'Pick one','options':['62','64','128'],'answer':'A',
                          'explanation':'Invalid','source_refs':['outside']},'reason':None}
        with self.assertRaises(SourceReferenceError):
            validated_generation(QUESTION_DRAFTS['mcq'],json.dumps(draft),fragments=SOURCE)

    def test_typed_question_keeps_exact_text_and_domain_defaults_without_choice_payloads(self):
        wire = generation_schema(QUESTION_DRAFTS['cloze'])
        props = next(v['properties'] for v in wire.model_json_schema()['$defs'].values() if 'prompt' in v.get('properties', {}))
        self.assertEqual(set(props), {'kind', 'prompt', 'answer', 'explanation', 'source_refs'})
        value = validated_generation(QUESTION_DRAFTS['cloze'], json.dumps(CLOZE)).model_dump()
        self.assertEqual(value['question']['answer'], CLOZE['question']['answer'])
        self.assertEqual(value['question']['prompt'], CLOZE['question']['prompt'])
        self.assertEqual(value['question']['source_refs'], ['ref'])
        self.assertEqual(value['question']['options'], [])
        self.assertEqual(value['question']['left'], [])
        self.assertIs(generation_schema(ChatReply), ChatReply)

    def test_unexpected_generated_fields_are_rejected_even_if_empty_not_removed_to_pass(self):
        for field, content in [('left', ['62']), ('left', []), ('options', []), ('rubric', []), ('difficulty_basis', 'known_from_source')]:
            value = deepcopy(CLOZE);value['question'][field]=content
            with self.subTest(field=field,content=content),self.assertRaises(ValidationError):
                validated_generation(QUESTION_DRAFTS['cloze'],json.dumps(value))

    def test_domain_guards_still_reject_bad_blanks_keys_and_equivalent_choices(self):
        cases = [
            ('cloze', {**CLOZE['question'], 'prompt': '____ and ____'}),
            ('mcq', {'kind':'mcq','prompt':'Pick one','options':['32 bit','4 byte'],'answer':'32 bit'}),
            ('matching', {'kind':'matching','prompt':'Match','options':['64','127'],'left':['Network','Broadcast'],'answer':[0,0]}),
            ('ordering', {'kind':'ordering','prompt':'Arrange','options':['first','second'],'answer':[False,1]}),
            ('short_answer', {'kind':'short_answer','prompt':'Explain','answer':'Source reference','rubric':[]}),
        ]
        for kind,q in cases:
            q={'explanation':'From source','source_refs':['ref'],**q}
            with self.subTest(kind=kind),self.assertRaises(ValidationError):
                validated_generation(QUESTION_DRAFTS[kind],json.dumps({'question':q,'reason':''}))

    def test_null_question_still_needs_missing_source_reason(self):
        schema = QUESTION_DRAFTS['ordering']
        value=validated_generation(schema,json.dumps({'question':None,'reason':'The source contains no ordered steps.'}))
        self.assertIsNone(value.question)
        with self.assertRaises(ValidationError):validated_generation(schema,'{"question":null,"reason":""}')

    def test_legacy_partial_dto_remains_valid_and_new_output_has_same_stored_shape(self):
        old=deepcopy(CLOZE);old['question'].update(options=[],left=[],rubric=[])
        # Old partials/history use the domain contract, not the new model wire.
        before=QUESTION_DRAFTS['cloze'].model_validate(old).model_dump()
        after=validated_generation(QUESTION_DRAFTS['cloze'],json.dumps(CLOZE)).model_dump()
        self.assertEqual(before,after)

    def test_ordering_key_is_derived_from_exact_cited_steps_and_logged(self):
        fragments=[{'id':'ref','text':'Procedure: (1) read the prefix; (2) calculate host bits; (3) identify the block.'}]
        draft={'question':{'kind':'ordering','prompt':'Arrange the source steps',
                          'options':['identify the block','read the prefix','calculate host bits'],
                          'explanation':'The source lists the steps in order.','source_refs':['ref']},'reason':''}
        class Audit(Progress):
            def usage(self,value):self.values=value
        audit=Audit();value=validated_generation(QUESTION_DRAFTS['ordering'],json.dumps(draft),audit,fragments).model_dump()
        self.assertEqual(value['question']['answer'],[1,2,0])
        self.assertEqual(audit.values['ordering_answer_method'],'explicit_scoped_source_steps_v2')
        self.assertEqual(value['question']['options'],draft['question']['options'])
        wrong={**draft,'question':{**draft['question'],'answer':[0,1,2]}}
        with self.assertRaises(ValidationError):validated_generation(QUESTION_DRAFTS['ordering'],json.dumps(wrong),fragments=fragments)

    def test_ordering_without_pinned_or_uniquely_matching_source_stays_rejected(self):
        draft={'question':{'kind':'ordering','prompt':'Arrange',
                          'options':['read the prefix','calculate host bits'],
                          'explanation':'From the source.','source_refs':['ref']},'reason':''}
        for source in [None,[{'id':'other','text':'Step 1: read the prefix; Step 2: calculate host bits'}],
                       [{'id':'ref','text':'1. Network address\n2. Broadcast address'}],
                       [{'id':'ref','text':'Step 1: read the prefix; Step 2: read the prefix; Step 3: calculate host bits'}]]:
            with self.subTest(source=source),self.assertRaises(ValueError):
                validated_generation(QUESTION_DRAFTS['ordering'],json.dumps(draft),fragments=source)

    def test_ordering_hides_only_leading_step_labels_retaining_ip_and_original_words(self):
        fragments=[{'id':'ref','text':'Procedure: (1) read IPv4 192.168.1.70/26; (2) calculate the 6 host bits.'}]
        draft={'question':{'kind':'ordering','prompt':'Arrange the steps','options':[
            '2. calculate the 6 host bits','"1. read IPv4 192.168.1.70/26"'],
            'explanation':'Use the source order.','source_refs':['ref']},'reason':''}
        class Audit(Progress):
            def usage(self,value):self.values=value
        progress=Audit();result=validated_generation(QUESTION_DRAFTS['ordering'],json.dumps(draft),progress,fragments).model_dump()
        self.assertEqual(result['question']['answer'],[1,0])
        self.assertEqual(result['question']['options'],['calculate the 6 host bits','"read IPv4 192.168.1.70/26"'])
        self.assertEqual(progress.values['ordering_step_labels_removed'],2)
        self.assertEqual(len(progress.values['ordering_model_options_sha256']),64)

    def test_local_native_stream_uses_small_wire_then_validates_source_without_retrying_bad_output(self):
        async def scenario():
            for value, accepted in [(CLOZE,True),({**CLOZE,'question':{**CLOZE['question'],'left':['62']}},False),
                                    ({**CLOZE,'question':{**CLOZE['question'],'source_refs':['other-source']}},False)]:
                requests=[];progress=Progress()
                def transport(request):
                    body=json.loads(request.content);requests.append(body)
                    if 'format' in body:
                        props=next(v['properties'] for v in body['format']['$defs'].values() if 'prompt' in v.get('properties',{}))
                        self.assertNotIn('left',props);self.assertNotIn('options',props)
                        return httpx.Response(501,json={'error':'structured output is unavailable'})
                    packets=[{'message':{'content':json.dumps(value)},'done':False},
                             {'message':{'content':''},'done':True,'done_reason':'stop'}]
                    return httpx.Response(200,content='\n'.join(json.dumps(p) for p in packets))
                class Adapter(LocalAI):
                    async def status(self):return {'ready':True}
                    def client(self,timeout):return httpx.AsyncClient(transport=httpx.MockTransport(transport),timeout=timeout)
                if accepted:
                    result=await Adapter().generate_stream(QUESTION_DRAFTS['cloze'],'One cloze',SOURCE,progress)
                    self.assertEqual(result['question']['answer'],'62')
                else:
                    with self.assertRaises(ValueError):await Adapter().generate_stream(QUESTION_DRAFTS['cloze'],'One cloze',SOURCE,progress)
                self.assertEqual(len(requests),2);self.assertEqual(progress.fallbacks,1)
        asyncio.run(scenario())

    def test_gemini_uses_same_wire_and_rejects_extra_fields_in_one_request(self):
        async def scenario():
            client_type=httpx.AsyncClient
            for value,accepted in [(CLOZE,True),({**CLOZE,'question':{**CLOZE['question'],'left':[]}},False)]:
                requests=[]
                def handler(request):
                    body=json.loads(request.content);requests.append(body)
                    wire=body['generationConfig']['responseJsonSchema']
                    props=next(v['properties'] for v in wire['$defs'].values() if 'prompt' in v.get('properties',{}))
                    self.assertNotIn('options',props);self.assertNotIn('left',props)
                    return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(value)}]}}]})
                def client(*args,**kwargs):return client_type(*args,**kwargs,transport=httpx.MockTransport(handler))
                with patch('study_backend.gemini.httpx.AsyncClient',client):
                    ai=GeminiAI(api_key='fixture-not-a-real-key',enabled=True)
                    if accepted:
                        output=await ai.generate(QUESTION_DRAFTS['cloze'],'One cloze',SOURCE)
                        self.assertEqual(output['question']['answer'],'62');self.assertEqual(output['question']['options'],[])
                    else:
                        with self.assertRaises(ProviderError):await ai.generate(QUESTION_DRAFTS['cloze'],'One cloze',SOURCE)
                self.assertEqual(len(requests),1)
        asyncio.run(scenario())
