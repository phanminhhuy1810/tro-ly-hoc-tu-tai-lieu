"""Proved subnet conflicts must never be repaired into an apparent model pass."""
import copy
import ipaddress
import json
from pathlib import Path
import unittest

from study_backend.models import QUESTION_DRAFTS
from study_backend.subnet_reasoning import calculations, instruction, check_question, SubnetClaimError
import test_chapter_context as chapter_fixtures
from test_slice import SliceFixture


def bad_questions():
    root=Path(__file__).resolve().parents[2]
    report=json.loads((root/'experiments/09-chapter-first/results/network-local.json').read_text())
    return next(u['data']['questions'] for u in report['course_snapshot']['content']['units'] if u['id']==report['unit_id'])


class SubnetReasoningTests(unittest.TestCase):
    def test_real_v22_correct_key_with_wrong_octet_explanation_is_rejected_without_mutation(self):
        root=Path(__file__).resolve().parents[2]
        trial=json.loads((root/'experiments/10-source-support/results/network-local-v22-resume.json').read_text())
        unit=next(u for u in trial['course_snapshot']['content']['units'] if u['id']==trial['unit_id'])
        question=next(q for q in unit['data']['questions'] if q['kind']=='mcq');before=copy.deepcopy(question)
        self.assertIn('172.100.96.0',question['answer'])
        with self.assertRaises(SubnetClaimError):check_question(question)
        self.assertEqual(question,before)
        fixed=copy.deepcopy(question)
        fixed['explanation']=fixed['explanation'].replace('2 octet đầu và 1 bit','2 octet đầu và 3 bit')
        check_question(fixed)

    def test_correct_bit_counts_and_decomposition_for_all_ipv4_prefixes(self):
        for prefix in range(33):
            with self.subTest(prefix=prefix):
                fact=calculations(f'10.12.7.201/{prefix}')[0]
                self.assertEqual(fact['network_full_octets']*8+fact['network_remainder_bits'],prefix)
                self.assertEqual(fact['boundary_octet'],prefix//8+1 if prefix%8 else None)
                question={'prompt':f'Với10.12.7.201/{prefix}, xét cấu trúc bit.', 'answer':'Đối chiếu',
                          'explanation':f'Network ID có {prefix} bits. HostID có {32-prefix} bits. '
                          f'{prefix} bits bao phủ {prefix//8} octet đầu và {prefix%8} bit của octet tiếp theo.'}
                check_question(question)
                wrong=copy.deepcopy(question);wrong['explanation']=f'HostID có {33-prefix} bits.'
                with self.assertRaises(SubnetClaimError):check_question(wrong)

    def test_network_and_host_bit_blank_keys_are_checked_without_treating_host_count_as_bits(self):
        for label,answer in [('HostID','13'),('NetID','19')]:
            question={'prompt':f'Với172.100.112.4/19, {label} có ____ bits.','answer':answer,'explanation':''}
            check_question(question)
            with self.assertRaises(SubnetClaimError):check_question({**question,'answer':str(int(answer)+1)})
        check_question({'prompt':'Với172.100.112.4/19, số host hợp lệ là ____.','answer':'8190','explanation':''})

    def test_bit_distractors_negations_and_a_different_explanatory_prefix_are_not_positive_claims(self):
        question={'prompt':'Với172.100.112.4/19, chọn mô tả bit đúng.','answer':'HostID có 13 bits.',
                  'options':['HostID có 13 bits.','HostID có 12 bits.'], 'explanation':'Không phải HostID có12bits. Với prefix /24, HostID có8bits.'}
        check_question(question)
        question['explanation']='19 bits cover 2 full octets and 1 bit.'
        with self.assertRaises(SubnetClaimError):check_question(question)

    def test_same_three_real_model_outputs_are_rejected_without_changing_any_answer(self):
        questions=bad_questions();before=copy.deepcopy(questions)
        for q in questions:
            with self.subTest(kind=q['kind']):
                with self.assertRaises(SubnetClaimError):check_question(q)
        self.assertEqual(questions,before)

    def test_program_computes_cross_octet_network_and_hosts_not_first_three_octets(self):
        fact=calculations('Cho 172.100.112.4 / 19.')[0]
        self.assertEqual((fact['network'],fact['broadcast'],fact['subnet_mask'],fact['usable_hosts']),
                         ('172.100.96.0','172.100.127.255','255.255.224.0',8190))
        for raw in ['10.3.4.5/27','192.168.1.0/31','192.168.1.9/32']:
            oracle=ipaddress.ip_interface(raw);fact=calculations(raw)[0];hosts=list(oracle.network.hosts())
            self.assertEqual((fact['usable_hosts'],fact['first_host'],fact['last_host']),(len(hosts),str(hosts[0]),str(hosts[-1])))
        self.assertEqual(calculations('999.1.1.1/24 192.168.1.1/99'),[])

    def test_wrong_distractors_are_allowed_but_stem_key_explanation_are_checked(self):
        question=copy.deepcopy(bad_questions()[0])
        question['options'][0]='Network: 172.100.96.0, Broadcast: 172.100.127.255'
        question['answer']=question['options'][0]
        question['explanation']='Network ID là 172.100.96.0. Broadcast là 172.100.127.255.'
        check_question(question)
        question['explanation']='Network ID là 172.100.112.0.'
        with self.assertRaises(SubnetClaimError):check_question(question)

    def test_explicit_host_count_and_host_bit_blank_are_not_confused(self):
        q={'kind':'cloze','prompt':'Với IP 172.100.112.4/19, số host hợp lệ là ____.','answer':'8190','explanation':''}
        check_question(q)
        with self.assertRaises(SubnetClaimError):check_question({**q,'answer':'8192'})
        check_question({**q,'prompt':'Với 172.100.112.4/19, HostID có ____ bits.','answer':'13'})

    def test_ambiguous_multi_cidr_is_not_guessed_and_computed_context_keeps_real_source_binding(self):
        check_question({'prompt':'So sánh 10.1.1.1/24 và 172.100.112.4/19.','answer':'Network: 10.1.1.0','explanation':''})
        value=instruction([{'id':'ref-actual','text':'Bài tập 172.100.112.4/19.'}])
        self.assertIn('172.100.96.0',value);self.assertIn('ref-actual',value)
        self.assertIn('DO BACKEND KIỂM TRA',value)
        self.assertEqual(instruction([{'id':'x','text':'IPv4 có 32 bits.'}]),'')
        other=instruction([{'id':'ref-27','text':'10.3.4.5/27'}])
        self.assertNotIn('Prefix /19',other)
        self.assertIn('"network_remainder_bits": 3',other)

    def test_deliberately_wrong_work_in_error_analysis_is_not_treated_as_an_asserted_key(self):
        question={'kind':'short_answer','prompt':'Với 172.100.112.4/19, bạn An tính sai: network là 172.100.112.0. Hãy giải thích sai lầm này.',
                  'answer':'Bạn An bỏ qua các bit network nằm trong octet thứ ba.','explanation':'Cần dùng subnet mask với prefix, network đúng là 172.100.96.0.'}
        check_question(question)


class SubnetPipelineTests(SliceFixture):
    draft=chapter_fixtures.ChapterContextTests.draft
    generate=chapter_fixtures.ChapterContextTests.generate
    def test_bad_subnet_candidate_isolated_while_other_questions_keep_their_answers(self):
        course,plan,source=self.draft(paragraphs=2)
        prefs={**plan['preferences'],'question_types':['mcq','cloze'],'question_count':2}
        prefs.pop('extraction_revision');prefs['expected_extraction_revision']=source['revision']
        fresh=self.client.post('/api/plans/from-source-sections',json=prefs).json()
        cid=self.client.post(f"/api/plans/{fresh['id']}/approve",json={'expected_revision':1}).json()['course_id']
        original=self.provider.generate;wrong=bad_questions()[0];seen=[]
        async def broken(schema,instruction,fragments):
            if schema is QUESTION_DRAFTS['mcq']:
                seen.append(schema)
                candidate={**copy.deepcopy(wrong),'source_refs':[fragments[0]['id']]}
                candidate.pop('difficulty');candidate.pop('difficulty_basis')
                return {'question':candidate,'reason':''}
            return await original(schema,instruction,fragments)
        self.provider.generate=broken
        response=self.generate({'id':cid,'revision':1});self.job(response)
        job=self.client.get('/api/jobs/'+response.json()['job_id']).json()
        self.assertEqual(job['partial']['question_rejections']['mcq']['code'],'SUBNET_DERIVATION_MISMATCH')
        unit=self.client.get(f'/api/courses/{cid}/editor').json()['content']['units'][0]
        self.assertEqual([q['kind'] for q in unit['data']['questions']],['cloze'])
        self.assertEqual(unit['data']['questions'][0]['answer'],'62')
        self.assertEqual(len(seen),1);self.assertTrue(unit['generation']['chapter_context']['complete'])
