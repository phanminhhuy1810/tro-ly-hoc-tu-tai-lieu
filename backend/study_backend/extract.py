"""Read bounded text with real locations; keep OCR warnings separate."""

from io import BytesIO
from pathlib import Path
import re
from .ocr import IMAGE_TYPES, recognize
from .pdf_content import MAX_PDF_PAGES, MAX_OCR_PAGES, visual_signals

from .source_limits import MAX_BYTES, MAX_FRAGMENTS, MAX_TEXT
from .sequences import numbered_sequences
SUPPORTED = {".txt", ".md", ".docx", ".pdf", ".pptx"} | IMAGE_TYPES


def explicit_sequence(fragments):
    """Conservative gate: numbered steps, not a bare list of concepts."""
    return bool(numbered_sequences(fragments))


def extract(filename: str, data: bytes, ocr=True):
    suffix = Path(filename).suffix.lower()
    if not data or len(data) > MAX_BYTES:
        raise ValueError("File rỗng hoặc lớn hơn giới hạn 50 MiB.")
    if suffix not in SUPPORTED:
        raise ValueError("Hỗ trợ TXT, Markdown, DOCX, PDF, PPTX và ảnh PNG/JPEG/WebP/TIFF/BMP/HEIC.")
    if suffix in IMAGE_TYPES:
        if not ocr:
            raise ValueError("OCR chưa cấu hình trong bộ thử này.")
        return recognize(filename, data)
    fragments = []
    warnings = []
    used = 0

    def add(text, locator):
        nonlocal used
        text = text.strip()
        if not text:
            return
        # Bound the stored prefix, rather than dropping a whole long paragraph.
        for offset in range(0, len(text), 2400):
            remaining = MAX_TEXT - used
            if len(fragments) >= MAX_FRAGMENTS or remaining <= 0:
                warnings.append("Nguồn vượt giới hạn trích xuất; phần còn lại chưa được đọc. File gốc vẫn được giữ.")
                break
            part = text[offset:offset + min(2400, remaining)]
            fragments.append({"text": part, "locator": {**locator, "character_start": offset}})
            used += len(part)
            if remaining < min(2400, len(text)-offset):
                warnings.append("Nguồn vượt giới hạn trích xuất; phần còn lại chưa được đọc. File gốc vẫn được giữ.")
                break

    if suffix in {".txt", ".md"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Văn bản cần UTF-8; chưa đoán bảng mã hoặc bỏ ký tự lỗi.") from exc
        for line, text in enumerate(text.splitlines(), 1):
            add(text, {"type": "line", "line": line})
    elif suffix in {'.docx','.pptx'}:
        from .office_inputs import read_with_ocr
        office_fragments, office_warnings = read_with_ocr(filename, data, ocr, recognize)
        warnings.extend(office_warnings)
        for fragment in office_fragments:
            before = len(fragments)
            add(fragment['text'], fragment['locator'])
            for created in fragments[before:]:
                created.update({k:v for k,v in fragment.items() if k not in {'text','locator'}})
    elif suffix == ".pdf":
        from pypdf import PdfReader
        if not data.startswith(b"%PDF-"):
            raise ValueError("Nội dung không phải PDF hợp lệ.")
        doc = PdfReader(BytesIO(data))
        if doc.is_encrypted:
            raise ValueError("PDF có mật khẩu; chưa hỗ trợ mở khóa.")
        missing, mixed = set(), set()
        for i, page in enumerate(doc.pages[:MAX_PDF_PAGES], 1):
            text = page.extract_text() or ""
            signals = visual_signals(page)
            if not text.strip():
                warnings.append(f"Trang {i} chưa có chữ trích được; có thể là scan, cần OCR.")
                missing.add(i)
            if signals.get('raster_regions'):
                mixed.add(i)
                signals['raster_ocr'] = 'not_read'
                warnings.append(f'Trang {i} có vùng ảnh lớn; chữ trích từ PDF có thể bỏ sót nội dung trong ảnh. Cần đối chiếu cả bảng/công thức.')
            if signals.get('vector_paths'):
                warnings.append(f'Trang {i} có nhiều nét vẽ; bản chữ không giữ được mũi tên, quan hệ hoặc bố cục sơ đồ. Đối chiếu trang gốc.')
            if signals.get('analysis_incomplete'):
                warnings.append(f'Trang {i} chưa phân tích hết vùng hình; đối chiếu trang gốc, không coi bản chữ là đầy đủ.')
            add(text, {"type": "page", "page": i, "page_index_base": 1, **({'visual_review': signals} if signals else {})})
        if len(doc.pages) > MAX_PDF_PAGES:
            warnings.append("Chỉ đọc 1000 trang đầu trong lượt này.")
        selected = sorted(missing)[:MAX_OCR_PAGES]
        selected += [p for p in sorted(mixed - missing) if p not in selected][:MAX_OCR_PAGES-len(selected)]
        if len(missing | mixed) > len(selected):
            warnings.append('OCR chỉ xử lý tối đa 20 trang được chọn trong một lượt; một số vùng ảnh còn chưa đọc. Dùng đọc lại theo trang hoặc chia nguồn.')
        if selected and ocr:
            try:
                scanned, ocr_warnings = recognize(filename, data, pages=selected)
                scanned = [f for f in scanned if f["locator"]["page"] in selected]
                recovered = set()
                for fragment in scanned:
                    before = len(fragments)
                    page_number = fragment['locator']['page']
                    add(fragment["text"], {**fragment["locator"], 'extraction_method': 'ocr_supplement', 'layout_unverified': True})
                    for f in fragments[before:]:
                        f.update(needs_review=True, recognizer_score=fragment.get("recognizer_score"),
                                 provenance={'kind': 'ocr_supplement', 'reason': 'no_text' if page_number in missing else 'mixed_page'})
                        recovered.add(page_number)
                for fragment in fragments:
                    if fragment['locator'].get('visual_review') and fragment['locator']['page'] in recovered:
                        fragment['locator']['visual_review']['raster_ocr'] = 'added_unverified'
                for page_number in selected:
                    if page_number not in recovered: warnings.append(f'Trang {page_number} chưa thêm được bản OCR; vùng ảnh còn cần đọc lại hoặc nhập tay.')
                fragments.sort(key=lambda f: f["locator"]["page"])
                warnings.extend(ocr_warnings)
            except ValueError as exc:
                warnings.append(str(exc))
        warnings.append("PDF: chữ/công thức/sơ đồ cần đối chiếu trang gốc; trích được chữ chưa chứng minh bố cục đúng.")
    if not fragments:
        raise ValueError("Chưa trích được chữ. Cần OCR hoặc cung cấp văn bản; chưa thể tạo bài từ file này.")
    return fragments, list(dict.fromkeys(warnings))
