"""Small self-authored OCR development probe, not a held-out benchmark."""
import json
from pathlib import Path
import subprocess
import sys
import time
import unicodedata
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from study_backend.ocr import binary
from study_backend.extract import extract

HERE = Path(__file__).resolve().parent
FONT = ROOT / 'frontend/assets/fonts/Nunito-Variable.ttf'
MATH_FONT = Path('/System/Library/Fonts/Supplemental/STIXGeneral.otf')
CASES = {
    'networking': [
        'Mạng máy tính: IPv4 và subnet mask',
        'IPv4 có 32 bit. Prefix /26 dành 26 bit cho network.',
        'Phần host còn 6 bit: 2^6 = 64 địa chỉ.',
        'Subnet của 192.168.1.70/26 nằm trong block 64 - 127.',
        'Network: 192.168.1.64. Broadcast: 192.168.1.127.',
        'Host dùng được: 192.168.1.65 đến 192.168.1.126.',
        'Số host dùng được: 64 - 2 = 62.',
    ],
    'psychology': [
        'Tâm lý học đại cương: trí nhớ',
        'Trí nhớ gồm mã hóa, lưu trữ và truy hồi thông tin.',
        'Mã hóa là biến đổi thông tin để có thể lưu trữ.',
        'Truy hồi là lấy lại thông tin đã được lưu.',
        'Ví dụ: tự nhắc lại kiến thức sau khi đọc.',
    ],
    'calculus': [
        'Vi tích phân: đạo hàm và tích phân',
        'f(x) = x² + 3x',
        "f′(x) = 2x + 3",
        '∫ x² dx = x³/3 + C',
        'Giá trị tích phân xác định cần xét hai cận.',
    ],
}


def normalized(text):
    return ' '.join(unicodedata.normalize('NFC', text).split())


def cer(expected, actual):
    expected, actual = normalized(expected), normalized(actual)
    previous = list(range(len(actual)+1))
    for i, left in enumerate(expected, 1):
        row = [i]
        for j, right in enumerate(actual, 1):
            row.append(min(row[-1]+1, previous[j]+1, previous[j-1]+(left != right)))
        previous = row
    return {'edit_distance': previous[-1], 'reference_characters': len(expected), 'cer': round(previous[-1]/len(expected), 4)}


def fixtures():
    font = ImageFont.truetype(str(FONT), 38)
    maths = ImageFont.truetype(str(MATH_FONT), 50)
    for name, lines in CASES.items():
        image = Image.new('RGB', (1500, 720), 'white')
        draw = ImageDraw.Draw(image)
        for i, line in enumerate(lines):
            draw.text((65, 55+i*80), line, font=maths if name == 'calculus' and 1 <= i <= 3 else font, fill='black')
        image.save(HERE/'fixtures'/f'{name}.png')
        image.save(HERE/'fixtures'/f'{name}-scan.pdf', 'PDF', resolution=180)
        (HERE/'fixtures'/f'{name}.txt').write_text('\n'.join(lines)+'\n')
    # Deliberately two-dimensional notation for manual semantic comparison.
    image = Image.new('RGB', (1000, 400), 'white')
    draw = ImageDraw.Draw(image)
    small = ImageFont.truetype(str(MATH_FONT), 32)
    large = ImageFont.truetype(str(MATH_FONT), 80)
    draw.text((60, 155), '∫', font=large, fill='black')
    draw.text((108, 134), '1', font=small, fill='black')
    draw.text((96, 235), '0', font=small, fill='black')
    draw.text((143, 165), 'x² dx =', font=large, fill='black')
    draw.text((485, 135), '1', font=large, fill='black')
    draw.line((458, 215, 556, 215), fill='black', width=3)
    draw.text((485, 220), '3', font=large, fill='black')
    image.save(HERE/'fixtures'/'calculus-layout.png')
    (HERE/'fixtures'/'calculus-layout.txt').write_text(r'\int_0^1 x^2\,dx = \frac{1}{3}'+'\n')


def main():
    fixtures()
    native = binary()
    baseline = ROOT/'backend/runtime/vision-ocr-baseline-en'
    report = {'purpose': 'self-authored clean printed development probe; not user documents or held-out/human benchmark',
              'human_review': False, 'language_change': 'English-only baseline -> supported Vietnamese locale plus English',
              'normalization': 'NFC; whitespace collapse; case, punctuation and math symbols preserved', 'cases': []}
    for case, lines in CASES.items():
        name = f'{case}.png'; expected = '\n'.join(lines)
        value = {'name': name, 'expected': expected, 'runs': []}
        for label, executable in [('baseline_en', baseline), ('vi_en', native)]:
            if not executable.exists(): continue
            start = time.monotonic()
            result = subprocess.run([str(executable), 'image', str(HERE/'fixtures'/name)], capture_output=True, check=True, timeout=40)
            raw = json.loads(result.stdout)
            text = '\n'.join(f['text'] for f in raw['fragments'])
            value['runs'].append({'label': label, 'elapsed_seconds': round(time.monotonic()-start,3), 'text': text,
                                  **cer(expected, text), 'fragments': raw['fragments'], 'warnings': raw['warnings']})
        pdf = HERE/'fixtures'/f'{case}-scan.pdf'
        fragments, warnings = extract(pdf.name, pdf.read_bytes())
        value['pdf_scan'] = {'text': '\n'.join(f['text'] for f in fragments), 'fragments': fragments, 'warnings': warnings}
        value['pdf_scan'].update(cer(expected, value['pdf_scan']['text']))
        report['cases'].append(value)
    raw = subprocess.run([str(native), 'image', str(HERE/'fixtures'/'calculus-layout.png')], capture_output=True, check=True, timeout=40)
    report['two_dimensional_math'] = {'expected_latex': r'\int_0^1 x^2\,dx = \frac{1}{3}', 'raw': json.loads(raw.stdout), 'automatically_proven_semantically_correct': False}
    destination = HERE/'results'/'native-vision-dev.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    for case in report['cases']:
        print(case['name'], [(r['label'], r['cer']) for r in case['runs']], 'scan_pdf_cer', case['pdf_scan']['cer'])
    print('layout_math:', [f['text'] for f in report['two_dimensional_math']['raw']['fragments']])
    print('report:', destination)

if __name__ == '__main__': main()
