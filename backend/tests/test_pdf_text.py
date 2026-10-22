"""Slide PDFs whose plain text lost word gaps (real case: IPv4 lecture, page 5)."""
import unittest
from unittest.mock import patch

from pypdf import PageObject

from study_backend.extract import extract
from study_backend.pdf_text import repair_page_text, respace, tidy_bullets
from test_pdf_recovery import pdf_bytes

PLAIN = 'Giớithiệu\nqĐịachỉmạng(identifier):\n§địnhdanhcủa1 node mạng\n§Địachỉlogic\n•do ngườidùngấnđịnh\n•VD: địachỉIP (Internet Protocol)'
LAYOUT = (' Giới     thiệu\n\n  q   Địa   chỉ   mạng      (identifier):\n       §  định   danh    của   1 node mạng\n'
          '       §  Địa  chỉ  logic\n            • do người   dùng   ấn định\n            • VD: địa  chỉ IP (Internet Protocol)')


class RespaceTest(unittest.TestCase):
    def test_glued_vietnamese_is_split_only_into_words_the_layout_pass_saw(self):
        fixed = respace(PLAIN, LAYOUT)
        self.assertIn('Giới thiệu', fixed)
        self.assertIn('q Địa chỉ mạng (identifier):', fixed)
        self.assertIn('§ định danh của 1 node mạng', fixed)
        self.assertIn('người dùng ấn định', fixed)

    def test_ascii_and_unknown_tokens_are_left_alone(self):
        self.assertEqual(respace('Subnetmask 255.255.255.0', 'Subnet mask 255.255.255.0'), 'Subnetmask 255.255.255.0')
        self.assertEqual(respace('nghiêngngả', 'nghiêng'), 'nghiêngngả')
        self.assertEqual(respace('Địachỉ', ''), 'Địachỉ')


class BulletTest(unittest.TestCase):
    def test_wingdings_bullets_become_bullets(self):
        self.assertEqual(tidy_bullets('q Địa chỉ\n§ định danh\n•do người dùng\nØ Bước 1'), '• Địa chỉ\n• định danh\n• do người dùng\n• Bước 1')

    def test_real_words_and_section_references_are_kept(self):
        text = 'quy tắc chia mạng\n§ 5 Điều khoản\nØresund\nq = 5'
        self.assertEqual(tidy_bullets(text), text)


class RepairPageTest(unittest.TestCase):
    def test_layout_pass_runs_only_when_words_look_glued(self):
        def unexpected():
            raise AssertionError('layout pass for a clean page')
        self.assertEqual(repair_page_text('Native text on page 1', unexpected), 'Native text on page 1')
        self.assertTrue(repair_page_text(PLAIN, lambda: LAYOUT).startswith('Giới thiệu\n• Địa chỉ mạng'))

    def test_failed_layout_pass_keeps_the_plain_reading(self):
        def broken():
            raise ValueError('layout failed')
        self.assertIn('Giớithiệu', repair_page_text(PLAIN, broken))

    def test_extract_stores_the_repaired_text_for_pdf_pages(self):
        original = PageObject.extract_text

        def fake(page, *args, **kwargs):
            if 'Native text on page 1' not in original(page):
                return original(page, *args, **kwargs)
            return LAYOUT if kwargs.get('extraction_mode') == 'layout' else PLAIN

        with patch.object(PageObject, 'extract_text', fake):
            fragments, _ = extract('slides.pdf', pdf_bytes(count=2, images=()), ocr=False)
        first = next(f for f in fragments if f['locator']['page'] == 1)
        self.assertIn('• Địa chỉ logic', first['text'])
        self.assertIn('• do người dùng ấn định', first['text'])
        self.assertIn('Native text on page 2', next(f for f in fragments if f['locator']['page'] == 2)['text'])


if __name__ == '__main__':
    unittest.main()
