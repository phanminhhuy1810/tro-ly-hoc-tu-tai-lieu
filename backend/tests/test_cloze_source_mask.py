import hashlib
import json
import unittest
from pydantic import ValidationError
from study_backend.generation_contract import validated_generation
from study_backend.models import QUESTION_DRAFTS,grade,validate_refs

class Audit:
    def __init__(self):self.value={}
    def usage(self,value):self.value.update(value)

class ClozeSourceMaskTests(unittest.TestCase):
    def draft(self,statement='IPv4 có 32 bit.',answer='32',ref='s'):
        return {'reason':'','question':{'kind':'cloze','prompt':statement,'answer':answer,'source_refs':[ref],'explanation':'Theo câu đã trích.'}}
    def parse(self,draft,source=None,audit=None):
        return validated_generation(QUESTION_DRAFTS['cloze'],json.dumps(draft,ensure_ascii=False),audit,source or [{'id':'s','text':'Địa chỉ IPv4 có 32 bit. IPv6 có 128 bit.'}]).model_dump()['question']
    def test_masks_unique_source_answer_without_changing_key_and_records_audit(self):
        a=Audit();q=self.parse(self.draft(),audit=a)
        self.assertEqual(q['prompt'],'“IPv4 có ____ bit.”');self.assertEqual(q['answer'],'32');self.assertEqual(q['source_refs'],['s']);self.assertEqual(q['options'],[])
        self.assertTrue(grade(q,'32')['correct']);self.assertFalse(grade(q,'128')['correct'])
        self.assertEqual(a.value['cloze_source_mask_derived'],1);self.assertEqual(a.value['cloze_statement_sha256'],hashlib.sha256('IPv4 có 32 bit.'.encode()).hexdigest())
    def test_rejects_hallucinated_statement_repeated_answer_substring_and_missing_source(self):
        cases=[(self.draft('IPv4 có 64 bit.','64'),None),
               (self.draft('IPv4 có 32 bit và 32 là số bit.','32'),[{'id':'s','text':'IPv4 có 32 bit và 32 là số bit.'}]),
               (self.draft('Địa chỉ IPv4 là một định danh.','4'),[{'id':'s','text':'Địa chỉ IPv4 là một định danh.'}]),
               (self.draft(ref='foreign'),None)]
        for draft,source in cases:
            with self.subTest(draft=draft),self.assertRaises(ValueError):self.parse(draft,source)
    def test_correct_existing_blank_is_unchanged_and_multiple_blanks_still_fail(self):
        draft=self.draft('IPv4 có ____ bit.');q=self.parse(draft);self.assertEqual(q['prompt'],draft['question']['prompt'])
        with self.assertRaises(ValidationError):self.parse(self.draft('IPv4 có ____ bit và ____ byte.'))
    def test_quoted_sentence_with_layout_whitespace_and_unicode_keeps_source_and_input(self):
        source=[{'id':'s','text':'Địa chỉ IPv4\n có 32 bit.'}];raw=self.draft('Địa chỉ IPv4 có 32 bit.')
        before=json.dumps([raw,source],ensure_ascii=False);q=self.parse(raw,source);validate_refs(q,{'s'})
        self.assertEqual(q['prompt'],'“Địa chỉ IPv4 có ____ bit.”');self.assertEqual(json.dumps([raw,source],ensure_ascii=False),before)

    def test_original_quote_is_retained_when_explanation_language_is_english(self):
        from study_backend.language import validate_language
        draft=self.draft();draft['question']['explanation']='IPv4 addresses contain32 bits, as stated in the source.'
        question=self.parse(draft)
        validate_language(question,{'language':'en'})
        self.assertEqual(question['answer'],'32')
        self.assertIn('IPv4 có ____ bit.',question['prompt'])

    def test_null_prompt_constructs_question_from_one_unique_source_sentence(self):
        draft=self.draft();draft['question']['prompt']=None
        question=self.parse(draft)
        self.assertEqual(question['prompt'],'“Địa chỉ IPv4 có ____ bit.”')
        self.assertEqual(question['answer'],'32')
    def test_null_prompt_selects_first_proved_excerpt_and_preserves_ipv4_internal_dots(self):
        draft=self.draft(answer='192.168.1.64');draft['question']['prompt']=None
        question=self.parse(draft,[{'id':'s','text':'Network address is 192.168.1.64. Broadcast address is 192.168.1.127.'}])
        self.assertEqual(question['prompt'],'“Network address is ____.”')
        draft=self.draft();draft['question']['prompt']=None
        question=self.parse(draft,[{'id':'s','text':'IPv4 has 32 bits. The number 32 is the address length.'}])
        self.assertEqual(question['prompt'],'“IPv4 has ____ bits.”')

    def test_joined_pdf_words_align_without_changing_source_or_answer_and_keep_bullet_context(self):
        text='Giớithiệu\n§Địachỉvậtlý\n•do nhàsảnxuấtấnđịnh\n•VD: địachỉMAC (Media Access Control)\n§Địachỉlogic\n•do ngườidùngấnđịnh\n•VD: địachỉIP (Internet Protocol)\n5Khoa Công nghệ thông tin'
        source=[{'id':'s','text':text}];draft=self.draft(None,'địa chỉ IP (Internet Protocol)')
        before=json.dumps([source,draft],ensure_ascii=False);q=self.parse(draft,source)
        self.assertEqual(q['prompt'],'“§Địachỉlogic •do ngườidùngấnđịnh •VD: ____”')
        self.assertEqual(q['answer'],draft['question']['answer'])
        self.assertEqual(json.dumps([source,draft],ensure_ascii=False),before)
        self.assertTrue(grade(q,q['answer'])['correct'])
        self.assertFalse(grade(q,'địa chỉ MAC (Media Access Control)')['correct'])

    def test_layout_alignment_never_merges_numbers_changes_case_or_accepts_subtokens(self):
        for text,answer in [('Mã truy cập là 1 2 và 3.','12'),('Địa chỉ IPv4 có 32 bit.','4'),('Địa chỉ IPv4 có 32 bit.','ipv4'),('Kết nối internet dùng địa chỉ.','net')]:
            with self.subTest(text=text,answer=answer),self.assertRaises(ValueError):
                self.parse(self.draft(None,answer),[{'id':'s','text':text}])

    def test_unverified_candidate_is_typed_and_foreign_reference_stays_hard_failure(self):
        from study_backend.generation_contract import QuestionRejected
        with self.assertRaises(QuestionRejected) as caught:self.parse(self.draft(None,'invented answer'))
        self.assertEqual(caught.exception.details['origin'],'backend_question_validation')
        self.assertEqual(len(caught.exception.details['candidate_sha256']),64)
        with self.assertRaises(ValueError) as caught:self.parse(self.draft(None,ref='foreign'))
        self.assertNotIsInstance(caught.exception,QuestionRejected)
