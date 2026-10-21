# Run AFTER your existing Ollama/model/ngrok setup. Do not Run All to reconnect.
# The generated password is not embedded in notebook source. Keep outputs private.
from pyngrok import ngrok
import base64
import json
from pathlib import Path
import secrets
from IPython.display import HTML, display

password = secrets.token_urlsafe(32)
for tunnel in ngrok.get_tunnels():
    ngrok.disconnect(tunnel.public_url)
tunnel = ngrok.connect(addr=11434, proto='http', basic_auth=['study:' + password], inspect=False)
config = Path('/kaggle/working/study-kaggle-private.json')
config.write_text(json.dumps({'endpoint': tunnel.public_url, 'model': 'qwen3.8:27b',
                             'username': 'study', 'password': password}))
config.chmod(0o600)
print('STUDY_AUTH_READY', tunnel.public_url)
print('Download for backend only. Do not publish notebook outputs or send this file in chat.')
display(HTML('<a download="study-kaggle-private.json" href="data:application/json;base64,' +
             base64.b64encode(config.read_bytes()).decode() + '">Download private backend config</a>'))
