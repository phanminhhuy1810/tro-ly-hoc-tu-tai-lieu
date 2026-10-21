"""Operator-only setup; the key is entered privately, never as a CLI argument."""
import argparse
import getpass
import json
import os
from pathlib import Path
import tempfile

import httpx

from study_backend.gemini import GeminiAI


def main():
    parser = argparse.ArgumentParser(description='Lưu key Gemini riêng cho backend; không tự bật billing.')
    parser.add_argument('--model', action='append', help='Tên model được cho phép; có thể lặp. Mặc định gemini-2.5-flash.')
    parser.add_argument('--enable', action='store_true', help='Cho phép sinh nội dung bằng key này. Chỉ dùng sau khi tự kiểm tra billing/quota của project.')
    args = parser.parse_args()
    models = list(dict.fromkeys(args.model or ['gemini-2.5-flash']))
    if not 1 <= len(models) <= 8:
        raise ValueError('Chọn 1–8 model.')
    key = getpass.getpass('Gemini API key (ẩn khi gõ): ').strip()
    if not key:
        raise ValueError('Chưa nhập key.')
    for model in models:
        ai = GeminiAI(model, api_key=key, enabled=False)
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False,
                          headers={'x-goog-api-key': key}) as client:
            response = client.get(ai.endpoint + '/models/' + model)
            if response.status_code != 200 or 'generateContent' not in response.json().get('supportedGenerationMethods', []):
                raise ValueError('Chưa xác thực được model; cấu hình cũ được giữ. Kiểm tra model/key phía Google.')
    target = Path(__file__).resolve().parent / 'runtime/gemini-private.json'
    target.parent.mkdir(exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, prefix='.gemini-', delete=False) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o600)
            json.dump({'api_key': key, 'enabled': args.enable, 'models': models}, output)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print('Đã lưu cấu hình riêng quyền 600; không gửi key ra trình duyệt hoặc in key.')
    print('Gọi sinh nội dung: ' + ('được cho phép' if args.enable else 'đang tắt'))
    print('Model access kiểm tra được; quota/billing và chất lượng sinh chưa được chứng minh bằng model-list.')
    print('Khởi động lại backend để dùng cấu hình mới. Dữ liệu học giữ nguyên.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, httpx.HTTPError):
        raise SystemExit('Chưa cài cấu hình Gemini; dữ liệu/cấu hình cũ giữ nguyên. Không cần gửi key vào chat.')
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('Đã hủy; chưa lưu cấu hình mới.')
