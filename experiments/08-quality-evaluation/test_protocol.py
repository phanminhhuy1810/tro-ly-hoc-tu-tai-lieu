import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from oracles import polynomial_integral, verify_facts
import run_http


class OracleTests(unittest.TestCase):
    def test_integral_uses_both_bounds_and_retains_fraction(self):
        self.assertEqual(polynomial_integral([0,0,0,1],[2,4]),Fraction(60))
        self.assertEqual(polynomial_integral([0,0,1],[1,0]),Fraction(-1,3))

    def test_wrong_fixture_gold_is_rejected(self):
        with self.assertRaises(AssertionError):
            verify_facts({'oracle':'chain_power','inner_slope':3,'inner_intercept':1,
                          'power':4,'at':0,'coefficient':4,'value_at':4})
        with self.assertRaises(AssertionError):
            verify_facts({'oracle':'longest_prefix','routes':[['10.0.0.0/8','A'],['10.1.0.0/16','B']],
                          'destinations':{'10.1.2.3':'A'}})

    def test_concept_labels_never_receive_a_computed_pass(self):
        result=verify_facts({'oracle':'concept_table','relations':{'invented':'unverified'}})
        self.assertEqual(result['verification'],'agent_source_crosscheck_only_needs_independent_review')
        self.assertNotIn('passed',result)

    def test_ordinary_subnet_formula_not_applied_to_31(self):
        with self.assertRaises(ValueError):verify_facts({'oracle':'ipv4','input':'10.0.0.0/31'})


class FrozenDatasetTests(unittest.TestCase):
    def test_split_hashes_balance_and_no_cross_split_ids(self):
        splits={name:run_http.load_frozen(name)[1] for name in ('dev','final')}
        self.assertFalse({c['id'] for c in splits['dev']} & {c['id'] for c in splits['final']})
        for cases in splits.values():
            self.assertEqual(sorted([c['subject'] for c in cases]).count('Mạng máy tính'),2)
            self.assertEqual(len({c['subject'] for c in cases}),3)
            self.assertTrue(all(c['question_count']==8 for c in cases))

    def test_tampered_source_cannot_be_run_as_frozen(self):
        with TemporaryDirectory() as tmp:
            dest=Path(tmp)
            for name in ('freeze.json','dev.json'):(dest/name).write_bytes((run_http.HERE/name).read_bytes())
            d=json.loads((dest/'dev.json').read_text());d['cases'][0]['text']+=' changed'
            (dest/'dev.json').write_text(json.dumps(d))
            with patch.object(run_http,'HERE',dest),self.assertRaisesRegex(ValueError,'Frozen split changed'):
                run_http.load_frozen('dev')


class RoundtripTests(unittest.TestCase):
    def test_successful_chapter_checkpoint_is_not_counted_as_a_published_lesson_or_practice(self):
        item={'case_id':'dev-case','course_id':'course','unit_id':'unit'};calls=[]
        chapter={'complete':False,'covered_fragments':7,'total_fragments':21}
        def call(client,method,path,body=None,headers=None):
            calls.append((method,path))
            if path.endswith('/editor'):return {'revision':1,'content':{'units':[{'data':None}]}}
            return {}
        job={'status':'succeeded','result':{'continuation_required':True},'partial':{'chapter_context':chapter}}
        with patch.object(run_http,'request',call):run_http.capture_outcome(None,item,job)
        self.assertEqual(item['outcome_kind'],'chapter_continuation_required')
        self.assertEqual(item['published_question_count'],0)
        self.assertEqual(item['chapter_context'],chapter)
        self.assertFalse(any('/sessions' in path for _,path in calls))

    def test_session_ids_are_not_assumed_to_exist_on_domain_questions(self):
        question={'kind':'mcq','prompt':'A question','answer':'correct'}
        item={'case_id':'dev-case','course_id':'course','unit_id':'unit'}
        session={'id':'sid','questions':[{'id':'server-item','kind':'mcq','prompt':'A question'}]}
        calls=[]
        def call(client,method,path,body=None,headers=None):
            calls.append((method,path,body,headers))
            if path.endswith('/editor'):return {'revision':2,'content':{'units':[{'data':{'questions':[question]}}]}}
            if path=='/wallet':return {'balance':0}
            if path.endswith('/sessions'):return session
            return {'ok':True}
        with patch.object(run_http,'request',call):run_http.capture_outcome(None,item,{'status':'succeeded'})
        answer=next(c for c in calls if c[1].endswith('/answers'))
        self.assertEqual(answer[2],{'item_id':'server-item','answer':'correct'})
        self.assertTrue(item['outcome_captured'])

    def test_observation_reuses_existing_session_after_harness_interruption(self):
        item={'case_id':'dev-case','course_id':'course','unit_id':'unit','session_id':'existing'}
        calls=[]
        def call(client,method,path,body=None,headers=None):
            calls.append((method,path))
            if path.endswith('/editor'):return {'revision':2,'content':{'units':[{'data':{'questions':[]}}]}}
            if path=='/sessions/existing':return {'id':'existing','questions':[]}
            return {}
        with patch.object(run_http,'request',call):run_http.capture_outcome(None,item,{'status':'succeeded'})
        self.assertIn(('GET','/sessions/existing'),calls)
        self.assertNotIn(('POST','/courses/course/sessions'),calls)


if __name__=='__main__':unittest.main()
