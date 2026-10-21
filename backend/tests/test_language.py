import unittest
from study_backend.language import validate_language


class LanguageTests(unittest.TestCase):
    def test_vietnamese_question_or_option_is_not_accepted_as_english(self):
        for value in [{'prompt':'Nếu còn 6 bit host, có bao nhiêu địa chỉ?'}, {'options':['64 địa chỉ','32 địa chỉ']}, {'cards':[{'front':'How many?','back':'Phần host còn 6 bit.'}]}]:
            with self.subTest(value=value),self.assertRaises(ValueError):validate_language(value,{'language':'en'})

    def test_original_terms_and_quotes_are_preserved_without_translating_source(self):
        validate_language({'prompt':'What does "địa chỉ mạng" mean?','text':'Translate the term địa chỉ mạng.','back':'64'}, {'language':'en','terms_to_keep':['địa chỉ mạng']})
        validate_language({'text':'Địa chỉ mạng là địa chỉ đầu của subnet.'},{'language':'source'})
        validate_language({'text':'Café has an accent; x² remains mathematical notation.'},{'language':'en'})
