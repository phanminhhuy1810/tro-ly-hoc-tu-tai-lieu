"""On-device OCR through macOS Vision; originals never leave this machine."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from .pdf_content import MAX_PDF_PAGES, MAX_OCR_PAGES, MAX_IMAGE_FRAMES

ROOT = Path(__file__).resolve().parents[2]
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".heic"}
_build_lock = threading.Lock()


def binary():
    if sys.platform != "darwin":
        raise ValueError("OCR local hiện dùng macOS Vision; máy này cần cấu hình bộ OCR tương thích trước.")
    source = Path(__file__).with_name("vision_ocr.swift")
    executable = ROOT / "backend/runtime/vision-ocr"
    with _build_lock:
        import fcntl
        executable.parent.mkdir(parents=True, exist_ok=True)
        with (executable.parent / "vision-build.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if executable.exists() and executable.stat().st_mtime >= source.stat().st_mtime:
                return executable
            swift = shutil.which("swiftc")
            if not swift:
                raise ValueError("Chưa có Swift compiler cho OCR local. Nguồn gốc vẫn được giữ, có thể dán văn bản.")
            module_cache = ROOT / "backend/runtime/vision-modules"
            module_cache.mkdir(parents=True, exist_ok=True)
            temporary = executable.with_name("vision-ocr." + str(os.getpid()) + ".tmp")
            try:
                subprocess.run([swift, "-module-cache-path", str(module_cache), str(source), "-o", str(temporary)], check=True, capture_output=True, timeout=45)
                temporary.replace(executable)
            except (subprocess.SubprocessError, OSError) as exc:
                raise ValueError("Bộ OCR local chưa khởi động được; giữ file gốc để thử lại hoặc dán văn bản.") from exc
            finally:
                temporary.unlink(missing_ok=True)
    return executable


def selected_result(raw, pages, timed_out=False):
    """Keep completed native OCR pages if a later page exceeds the deadline."""
    packets = []
    for line in raw.splitlines():
        try: packets.append(json.loads(line))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if not timed_out: raise
    if len(packets) == 1 and 'fragments' in packets[0] and packets[0].get('kind') != 'page':
        return packets[0]  # Also accepts the nonstream native/test adapter format.
    if not packets or len(packets) > MAX_OCR_PAGES + 1:
        raise ValueError('OCR chưa trả bản trích hợp lệ cho các trang được chọn.')
    result = {'fragments': [], 'warnings': [], 'engine': packets[0].get('engine', 'macOS_Vision'), 'revision': packets[0].get('revision')}
    received = set()
    complete = False
    for packet in packets:
        if packet.get('kind') == 'page':
            page = packet.get('page')
            if complete or page not in pages or page in received or any(f['locator'].get('page') != page for f in packet['fragments']):
                raise ValueError('OCR trả trang không khớp phạm vi yêu cầu; chưa dùng dữ liệu này.')
            received.add(page); result['fragments'].extend(packet['fragments'])
        elif packet.get('kind') == 'complete':
            complete = True; result['warnings'].extend(packet.get('warnings', []))
    if timed_out or not complete:
        result['warnings'].append('OCR dừng trước khi hoàn tất; đã giữ các trang đọc xong. Trang chưa đọc cần chọn riêng hoặc chia nguồn, không tự thử lại.')
    for page in pages:
        if page not in received: result['warnings'].append(f'Trang {page} chưa hoàn tất OCR trong lượt này.')
    return result


def recognize(filename, data, pages=None, timeout_seconds=40):
    if type(timeout_seconds) not in {int,float} or not .05<=timeout_seconds<=40:
        raise ValueError('Thời hạn OCR cần từ 0,05 đến 40 giây.')
    is_pdf = Path(filename).suffix.lower() == '.pdf'
    if pages is not None and (not is_pdf or not isinstance(pages, list) or
            not 1 <= len(pages) <= MAX_OCR_PAGES or
            any(type(p) is not int or not 1 <= p <= MAX_PDF_PAGES for p in pages) or len(set(pages)) != len(pages)):
        raise ValueError('Chọn tối đa 20 trang PDF khác nhau trong phạm vi 1–1000.')
    executable = binary()
    tmp = ROOT / "backend/runtime/ocr-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    file_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=tmp, delete=False) as file:
            file.write(data); file_path = file.name
        command = [str(executable), 'pdf-pages' if pages is not None else 'pdf' if is_pdf else 'image', file_path]
        if pages is not None: command.append(','.join(map(str, pages)))
        timed_out = False
        try:
            process = subprocess.run(command, capture_output=True, timeout=timeout_seconds)
            output = process.stdout
        except subprocess.TimeoutExpired as exc:
            if pages is None or not exc.stdout: raise
            timed_out = True; output = exc.stdout
        if len(output) > 2_000_000:
            raise ValueError("OCR trả quá nhiều nội dung cho một lượt; cần chia nguồn.")
        result = selected_result(output, pages, timed_out) if pages is not None else json.loads(output)
        if (not timed_out and process.returncode) or result.get("error"):
            raise ValueError("OCR chưa đọc được nguồn: " + result.get("error", "lỗi bộ nhận dạng"))
        fragments = result["fragments"]
        if not fragments:
            raise ValueError("OCR chưa nhận ra chữ; đối chiếu ảnh rõ hơn hoặc dán phần văn bản cần học.")
        if is_pdf:
            # Keep observations with geometry, but cite one bounded page instead
            # of treating every bit/cell as an independent source fragment.
            grouped = {}
            for fragment in fragments:
                grouped.setdefault(fragment['locator']['page'], []).append(fragment)
            compact = []
            for page, observations in grouped.items():
                if len(observations) > 2000:
                    raise ValueError('Trang OCR có quá nhiều vùng chữ; cần chia nguồn để đối chiếu.')
                compact.append({'text': '\n'.join(f['text'] for f in observations),
                    'locator': {**{k:v for k,v in observations[0]['locator'].items() if k != 'bounds'},
                                'location_scope': 'full_page', 'layout_unverified': True,
                                'ocr_observations': [{'text':f['text'], 'bounds':f['locator'].get('bounds'),
                                                      'recognizer_score':f.get('recognizer_score')} for f in observations]},
                    'recognizer_score': min(f.get('recognizer_score', 0) for f in observations)})
            fragments = compact
        if len(fragments) > 400 or sum(len(f["text"]) for f in fragments) > 120_000:
            raise ValueError("OCR vượt giới hạn bản trích; chia nguồn để không mất phần đọc.")
        for f in fragments:
            f["locator"]["ocr_engine"] = result["engine"]
            f["locator"]["ocr_revision"] = result["revision"]
            f["locator"]["image_orientation"] = "exif_normalized"
            f["needs_review"] = True
            # This is the recognizer's score, not a guarantee of mathematical
            # or semantic accuracy. Every OCR fragment requires source review.
        return fragments, result["warnings"]
    except subprocess.TimeoutExpired as exc:
        raise ValueError("OCR quá thời gian 40 giây; file gốc vẫn còn để chia nguồn/thử lại.") from exc
    except (json.JSONDecodeError, KeyError) as exc:
        raise ValueError("Bộ OCR chưa trả bản trích hợp lệ; không dùng dữ liệu này để tạo bài.") from exc
    finally:
        if file_path:
            os.unlink(file_path)


def render_page(filename, data, page=1):
    """One bounded, EXIF-normalized raster for review/vision; no UI capture."""
    suffix = Path(filename).suffix.lower()
    if suffix != ".pdf" and suffix not in IMAGE_TYPES:
        raise ValueError("Đọc lại bằng vision dùng một trang PDF hoặc một ảnh/khung ảnh.")
    limit = MAX_PDF_PAGES if suffix == '.pdf' else MAX_IMAGE_FRAMES
    if type(page) is not int or not 1 <= page <= limit:
        raise ValueError(f'Trang/khung ảnh cần trong phạm vi 1–{limit}.')
    executable = binary()
    tmp = ROOT / "backend/runtime/ocr-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=tmp) as folder:
            input_path, output_path = Path(folder)/"original", Path(folder)/"page.png"
            input_path.write_bytes(data)
            process = subprocess.run([str(executable), "render", "pdf" if suffix == ".pdf" else "image", str(input_path), str(page), str(output_path)], capture_output=True, timeout=25)
            result = json.loads(process.stdout)
            if process.returncode or result.get("error"):
                raise ValueError("Chưa dựng được trang để đối chiếu: " + result.get("error", "render error"))
            value = output_path.read_bytes()
            if len(value) > 8*1024*1024:
                raise ValueError("Ảnh trang vượt giới hạn vision; cần chia nguồn.")
            return value, result
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        raise ValueError("Chưa dựng được trang để đối chiếu; bản gốc còn nguyên.") from exc
