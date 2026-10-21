#!/usr/bin/env python3
"""Build the portable experiment from actual PDF text, never synthetic source."""
import base64
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PDF = Path('/Users/phanminhhuy/Documents/learning resources/Hk4/tai lieu MMT/slide vn/CTT105-2-IP&subnetting_2.0.pdf')
PAGES = [8, 15, 23, 26, 27, 33]


def string(low=1, high=2000):
    return {'type': 'string', 'minLength': low, 'maxLength': high}


def array(item, low=1, high=12):
    return {'type': 'array', 'minItems': low, 'maxItems': high, 'items': item}


def obj(props):
    return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}


def build():
    from pypdf import PdfReader
    import ipaddress
    reader = PdfReader(PDF)
    fragments = [{'id': f'pdf-p{page:02d}', 'page': page, 'text': reader.pages[page-1].extract_text()} for page in PAGES]
    refs = array(string(high=30))
    section = obj({'title': string(high=200), 'text': string(high=5000), 'source_refs': refs})
    card = obj({'front': string(high=1000), 'back': string(high=3000), 'source_refs': refs})
    term = obj({'text': string(high=4000), 'source_refs': refs, 'needs_more_source': {'type': 'boolean'}})
    mcq = obj({'kind': {'type': 'string', 'const': 'mcq'}, 'prompt': string(), 'options': {**array(string(high=1000), 4, 4), 'uniqueItems': True}, 'answer': string(high=1000), 'explanation': string(high=3000), 'source_refs': refs})
    reading = obj({'title': string(high=200), 'sections': array(section, 3, 3), 'cards': array(card, 2, 2), 'mindmap': array(section, 3, 3)})
    interface = ipaddress.ip_interface('172.29.217.10/19')
    network = interface.network
    target = str(network.network_address)
    single_instruction = ("Tạo đúng một câu trắc nghiệm 4 lựa chọn, một đáp án đúng. "
        "Dựa vào bài tập trang26: 'Địa chỉ đường mạng của 172.29.217.10/19 là gì?'. "
        "Mỗi option và answer chỉ là một địa chỉ IPv4, không kèm prefix hoặc nhãn A/B/C/D. "
        "Giải thích cách dùng /19 để tìm NetID. Dùng source_refs hỗ trợ quy tắc và bài tập. "
        "Không tự đổi IP hoặc prefix. answer phải trùng nguyên văn một option.")
    workloads = [
        {'id': 'term', 'kind': 'term', 'num_predict': 384, 'schema': term,
         'instruction': 'Subnet mask là gì, và các bit 1/0 phân định NetID/HostID thế nào? Giải thích tiếng Việt trong tối đa80 từ, giữ hai thuật ngữ NetID/HostID, chỉ dùng nguồn và nêu source_refs. needs_more_source=false nếu nguồn đủ.'},
        {'id': 'mcq', 'kind': 'mcq', 'num_predict': 900, 'schema': mcq,
         'instruction': single_instruction, 'oracle': {'answer': target, 'basis': 'Python ipaddress.ip_interface(...).network.network_address'}},
        {'id': 'reading', 'kind': 'reading', 'num_predict': 2400, 'schema': reading,
         'instruction': 'Tạo bài đọc ngắn bằng tiếng Việt về IPv4 và subnetting cho người mới: đúng3 mục lý thuyết (IPv4 32bit và NetID/HostID; subnet mask/prefix; số host và nguyên tắc chia subnet), đúng2 flashcard và đúng3 nhánh mindmap. Mỗi mục120 từ trở xuống. Dùng ví dụ172.29.217.10/19 ở trang26 và giải đúng network, broadcast, sốIP tổng, sốhost hợp lệ, dải host. Giữ NetID/HostID, nguyên ngữ Classless. Chỉ dùng nguồn và tính toán suy ra; source_refs phải đúng trang.'},
    ]
    pipeline = [
        ('IPv4 có bao nhiêu bit?', '32', 'Mỗi option và answer chỉ là một số nguyên, không thêm đơn vị.'),
        ('Subnet mask có bao nhiêu byte?', '4', 'Mỗi option và answer chỉ là một số nguyên, không thêm đơn vị.'),
        ('Số bit HostID của địa chỉ172.29.217.10/19 là bao nhiêu?', str(32-network.prefixlen), 'Mỗi option và answer chỉ là một số nguyên, không thêm đơn vị.'),
        ('Địa chỉ broadcast của172.29.217.10/19 là gì?', str(network.broadcast_address), 'Mỗi option và answer chỉ là một địa chỉ IPv4, không thêm prefix.'),
        ('Số địa chỉ host hợp lệ của network chứa172.29.217.10/19 là bao nhiêu?', str(network.num_addresses-2), 'Mỗi option và answer chỉ là một số nguyên, không thêm đơn vị.'),
    ]
    for i, (question, answer, rule) in enumerate(pipeline, 1):
        workloads.append({'id': f'pipeline_mcq_{i}', 'kind': 'mcq', 'num_predict': 900, 'schema': mcq,
                          'instruction': f'Tạo đúng một câu trắc nghiệm4 lựa chọn, một đáp án đúng cho câu hỏi: {question} {rule} Không đổi dữ kiện. Giải thích ngắn gọn bằng tiếng Việt, ghi source_refs hỗ trợ quy tắc và bài tập. answer phải trùng nguyên văn một option.',
                          'oracle': {'answer': answer, 'basis': 'PDF fact or Python ipaddress; reviewed independently from model output'}})
    bundle = {'version': 1, 'source': {'filename': PDF.name, 'sha256': hashlib.sha256(PDF.read_bytes()).hexdigest(), 'page_count': len(reader.pages), 'selected_pages': PAGES, 'extraction': 'pypdf extract_text, uncorrected original text; full source audit separate'}, 'fragments': fragments, 'workloads': workloads,
              'oracle': {'ip': str(interface), 'netmask': str(network.netmask), 'network': str(network.network_address), 'broadcast': str(network.broadcast_address), 'total_addresses': network.num_addresses, 'usable_hosts': network.num_addresses-2, 'first_host': str(network.network_address+1), 'last_host': str(network.broadcast_address-1)}}
    (ROOT/'benchmark-bundle.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2))
    # Fixed mtime enables identical archive hash between builds.
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as tar:
        for filename in ['benchmark.py', 'benchmark-bundle.json']:
            data = (ROOT/filename).read_bytes()
            info = tarfile.TarInfo(filename)
            info.size, info.mtime = len(data), 0
            tar.addfile(info, io.BytesIO(data))
    encoded = base64.b64encode(gzip.compress(buffer.getvalue(), mtime=0)).decode()
    cell = '''# Paste this complete cell AFTER Ollama and qwen3.8:27b are ready.
# No ngrok or credentials are used. At most13 requests;<=180s each,<=30min total.
import base64, gzip, io, json, pathlib, subprocess, sys, tarfile, datetime
_bundle = """BUNDLE"""
_root = pathlib.Path('/kaggle/working/network-benchmark')
_root.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(gzip.decompress(base64.b64decode(_bundle))), mode='r:') as _tar:
    for _member in _tar.getmembers():
        if _member.name not in {'benchmark.py', 'benchmark-bundle.json'}:
            raise ValueError('unexpected bundle member')
        (_root / _member.name).write_bytes(_tar.extractfile(_member).read())
_out = pathlib.Path('/kaggle/working/network-benchmark-results') / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
_command = [sys.executable, str(_root/'benchmark.py'), '--model', 'qwen3.8:27b', '--output', str(_out), '--max-seconds', '1800']
_process = subprocess.run(_command, check=False)
print('BENCHMARK_EXIT', _process.returncode, flush=True)
if (_out/'report.json').exists():
    _report = json.loads((_out/'report.json').read_text())
    # Full per-token NDJSON events remain in downloadable report/call files.
    _compact = json.loads(json.dumps(_report))
    for _call in _compact['calls']:
        _call.pop('events', None)
    _raw = json.dumps(_compact, ensure_ascii=False, separators=(',', ':')).encode()
    (_out/'portable-report.json').write_bytes(_raw)
    _encoded = base64.b64encode(gzip.compress(_raw, mtime=0)).decode()
    _chunks = [_encoded[i:i+6000] for i in range(0,len(_encoded),6000)]
    print('REPORT_CHUNKS', len(_chunks), 'GZIP_BASE64', flush=True)
    for _i, _chunk in enumerate(_chunks, 1):
        print(f'REPORT_CHUNK_{_i:02d}={_chunk}', flush=True)
    import shutil
    _zip = shutil.make_archive(str(_out), 'zip', _out)
    try:
        from IPython.display import FileLink, display
        display(FileLink(_zip))
    except ImportError:
        print('DOWNLOAD', _zip)
'''.replace('BUNDLE', encoded)
    (ROOT/'kaggle-benchmark-cell.py').write_text(cell)
    print(json.dumps({'bundle_sha256': hashlib.sha256((ROOT/'benchmark-bundle.json').read_bytes()).hexdigest(), 'cell_bytes': len(cell.encode()), 'source': bundle['source']}, ensure_ascii=False))


if __name__ == '__main__':
    build()
