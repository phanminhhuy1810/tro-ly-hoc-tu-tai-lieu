"""Operator-only setup for the free AI pool; keys are typed privately, never as CLI arguments."""
import argparse
import getpass
import json
import os
import tempfile

import httpx

from study_backend.free_apis import PRESETS, config_path, members_of


def check(name, key):
    """A call that spends no generation quota and only shows whether the key is accepted."""
    preset = PRESETS[name]
    if not preset['check']:
        return 'chưa kiểm tra trước được; sẽ thử khi tạo bài'
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False, headers={'Authorization': 'Bearer ' + key}) as client:
        response = client.get(preset['base_url'] + preset['check'])
    if response.status_code in (401, 403):
        raise ValueError(preset['label'] + ' từ chối key này; cấu hình cũ được giữ.')
    return 'key dùng được' if response.status_code == 200 else f'chưa xác nhận được (mã {response.status_code}), vẫn lưu'


def main():
    parser = argparse.ArgumentParser(description='Lưu key các API AI miễn phí (Groq, Cerebras, OpenRouter, Mistral, GitHub Models, NVIDIA) cho backend.')
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--default', dest='default', action='store_true', default=None, help='Dùng nhóm AI miễn phí làm mặc định cho người học chưa tự chọn model.')
    choice.add_argument('--not-default', dest='default', action='store_false', help='Chỉ thêm vào danh sách model, không làm mặc định.')
    args = parser.parse_args()
    target = config_path()
    old = json.loads(target.read_text()) if target.exists() else {}
    kept = {m.get('provider'): m for m in old.get('members', [])}
    members = []
    print('Dán key từng nơi (ẩn khi gõ). Enter để giữ key cũ hoặc bỏ qua nơi đó. Thứ tự dưới đây là thứ tự thử.')
    for name, preset in PRESETS.items():
        key = getpass.getpass(f"{preset['label']} (lấy key ở {preset['keys_at']}): ").strip()
        if key:
            print('  ' + check(name, key))
            members.append({'provider': name, 'api_key': key, 'models': preset['models']})
        elif name in kept:
            members.append(kept[name])
            print('  giữ key cũ')
    if not members:
        raise ValueError('Chưa có key nào.')
    value = {'enabled': True, 'default': old.get('default', False) if args.default is None else args.default, 'members': members}
    members_of(value)
    target.parent.mkdir(exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, prefix='.free-apis-', delete=False) as output:
            temporary = output.name
            os.fchmod(output.fileno(), 0o600)
            json.dump(value, output)
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    print(f"Đã lưu {len(members)} nơi vào cấu hình riêng quyền 600; key không được in ra hay gửi tới trình duyệt.")
    print('Làm mặc định cho người học mới: ' + ('có' if value['default'] else 'không (chọn “AI miễn phí · nhiều nguồn” trong Cài đặt)'))
    print('Khởi động lại backend (./run.sh) để dùng cấu hình mới. Dữ liệu học giữ nguyên.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, httpx.HTTPError) as exc:
        raise SystemExit('Chưa lưu cấu hình AI miễn phí: ' + str(exc) + ' Không cần gửi key vào chat.')
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('Đã hủy; chưa lưu cấu hình mới.')
