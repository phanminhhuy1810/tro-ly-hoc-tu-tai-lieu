"""Paste as ONE new Kaggle code cell. No secrets, tunnels, or public listener."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

BOOT_START = time.monotonic()
BOOT_DEADLINE = BOOT_START + 1800
MODEL = 'qwen3.8:27b'
ROOT = Path('/kaggle/working/network-benchmark-results')
ROOT.mkdir(exist_ok=True)

def run(args, timeout=300):
    completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, timeout=timeout, check=False)
    print(completed.stdout[-6000:], flush=True)
    completed.check_returncode()
    return completed.stdout

gpu = run(['nvidia-smi', '--query-gpu=index,name,memory.total,driver_version', '--format=csv'])
if gpu.count('Tesla T4') < 2:
    raise RuntimeError('Expected two T4 GPUs; stop before downloading the model.')
if not shutil.which('ollama'):
    if not shutil.which('zstd'):
        run(['sudo', 'apt-get', 'update'], 300)
        run(['sudo', 'apt-get', 'install', '-y', 'zstd'], 300)
    run(['curl', '-fsSL', '--max-time', '120', 'https://ollama.com/install.sh', '-o', '/tmp/study-ollama-install.sh'], 150)
    run(['sh', '/tmp/study-ollama-install.sh'], 600)

env = dict(os.environ, OLLAMA_HOST='127.0.0.1:11434', OLLAMA_NO_CLOUD='1',
           CUDA_VISIBLE_DEVICES='0,1', OLLAMA_NUM_PARALLEL='1',
           OLLAMA_CONTEXT_LENGTH='16384', OLLAMA_KEEP_ALIVE='5m',
           OLLAMA_FLASH_ATTENTION='1', OLLAMA_KV_CACHE_TYPE='q8_0')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    with opener.open('http://127.0.0.1:11434' + path, timeout=5) as response:
        return json.load(response)

try:
    get('/api/version')
except Exception:
    log = (ROOT/'ollama-server.log').open('a')
    study_ollama_process = subprocess.Popen(['ollama', 'serve'], env=env, stdout=log, stderr=log)
    for _ in range(30):
        try:
            get('/api/version')
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError('Ollama did not start; inspect ollama-server.log.')

print('OLLAMA_VERSION', get('/api/version'), flush=True)
last_bucket = None
payload = json.dumps({'model': MODEL, 'stream': True}).encode()
request = urllib.request.Request('http://127.0.0.1:11434/api/pull', data=payload,
                                 headers={'Content-Type':'application/json'})
pull_start = time.monotonic()
with opener.open(request, timeout=90) as response:
    for line in response:
        if time.monotonic() > BOOT_DEADLINE:
            raise TimeoutError('Bootstrap exceeded 30 minutes; stop session.')
        value = json.loads(line)
        if value.get('error'):
            raise RuntimeError(value['error'])
        total, done = value.get('total', 0), value.get('completed', 0)
        bucket = (value.get('digest','')[:12], int(done*10/total) if total else value.get('status'))
        if bucket != last_bucket:
            print('PULL', value.get('status'), int(100*done/total) if total else '', flush=True)
            last_bucket = bucket

tags = get('/api/tags')
if MODEL not in {m['name'] for m in tags['models']}:
    raise RuntimeError('Downloaded tag not found; do not substitute another model silently.')
metadata = {'model': MODEL, 'gpu_inventory': gpu, 'ollama_version': get('/api/version'),
            'models': tags['models'], 'pull_wall_seconds': round(time.monotonic()-pull_start,3),
            'bootstrap_wall_seconds': round(time.monotonic()-BOOT_START,3),
            'listener':'127.0.0.1:11434', 'tunnel':False, 'secret_access':False}
(ROOT/'bootstrap.json').write_text(json.dumps(metadata, indent=2))
print('BOOTSTRAP_READY', json.dumps(metadata), flush=True)
