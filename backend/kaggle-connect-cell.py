# Run AFTER the bootstrap cell has Ollama and the model ready. Do not Run All to reconnect.
# Opens a password-protected ngrok tunnel to Ollama. The ngrok token comes from the
# notebook's Kaggle Secret "ngrok-api-key"; the generated password is not embedded
# in notebook source. Keep outputs private.
import base64, json, secrets, subprocess, sys
from pathlib import Path
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'pyngrok'], check=True)
from IPython.display import HTML, display
from kaggle_secrets import UserSecretsClient
from pyngrok import ngrok
try:
    ngrok.set_auth_token(UserSecretsClient().get_secret('ngrok-api-key'))
except Exception as exc:  # a re-run finds the token already saved in this session
    if 'already set' not in str(exc):
        raise
password = secrets.token_urlsafe(32)
for tunnel in ngrok.get_tunnels():
    ngrok.disconnect(tunnel.public_url)
# Current ngrok agents take the password as a basic-auth traffic policy (the old basic_auth option is rejected).
policy = {'on_http_request': [{'actions': [{'type': 'basic-auth', 'config': {'credentials': ['study:' + password]}}]}]}
tunnel = ngrok.connect(addr=11434, proto='http', traffic_policy=policy, inspect=False)
config = Path('/kaggle/working/study-kaggle-private.json')
config.write_text(json.dumps({'endpoint': tunnel.public_url, 'model': 'qwen3.8:27b', 'username': 'study', 'password': password}))
config.chmod(0o600)
print('STUDY_AUTH_READY: duong ham co mat khau da mo. Tai file ket noi ben duoi, khong gui file nay cho ai.')
display(HTML('<a download="study-kaggle-private.json" href="data:application/json;base64,' + base64.b64encode(config.read_bytes()).decode() + '">Download private backend config</a>'))
