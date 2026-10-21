"""Install a private connection download. Never print credentials or response bodies."""
import asyncio
import json
import os
from pathlib import Path
import sys

import httpx

from study_backend.ai import KaggleAI


async def install(path):
    ai = KaggleAI(json.loads(path.read_text()))
    async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False) as client:
        response = await client.get(ai.endpoint + '/api/tags', headers={'ngrok-skip-browser-warning': 'study-backend'})
        if response.status_code != 401:
            raise ValueError('Tunnel chưa chặn truy cập không xác thực; chưa nối dữ liệu học.')
    if not (await ai.status())['ready']:
        raise ValueError('Chưa xác thực được model; kiểm tra phiên Kaggle hoặc tải lại file kết nối mới nhất.')
    target = Path(__file__).resolve().parent / 'runtime/kaggle-private.json'
    target.parent.mkdir(exist_ok=True)
    path.chmod(0o600)
    if path.resolve() != target.resolve():
        if target.exists():
            target.replace(target.with_suffix('.previous.json'))
        os.replace(path, target)
    print('Kaggle authenticated, model ready:', ai.model)
    print('Private configuration installed. Start: sh backend/run-kaggle.sh')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: .venv/bin/python backend/configure-kaggle.py /path/to/study-kaggle-private.json')
    try:
        asyncio.run(install(Path(sys.argv[1]).expanduser()))
    except (ValueError, OSError, httpx.HTTPError):
        raise SystemExit('Chưa cài cấu hình: kiểm tra file riêng, xác thực tunnel và phiên Kaggle; không cần gửi mật khẩu vào chat.')
