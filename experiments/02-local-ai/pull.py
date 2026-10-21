"""Pull a local model and show sparse progress without terminal control codes."""

import argparse
import json
import time
import urllib.request


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("model", nargs="?", default="qwen3.5:9b")
args = parser.parse_args()
if args.model.endswith(":cloud"):
    raise SystemExit("This helper only downloads local models.")
req = urllib.request.Request(
    "http://127.0.0.1:11434/api/pull",
    data=json.dumps({"model": args.model, "stream": True}).encode(),
    headers={"Content-Type": "application/json"},
)
last_time = 0
last_status = ""
started = time.monotonic()
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=900) as response:
    for line in response:
        message = json.loads(line)
        if "error" in message:
            raise SystemExit(message["error"])
        status = message.get("status", "")
        now = time.monotonic()
        if now - last_time >= 20 or status != last_status:
            total = message.get("total", 0)
            completed = message.get("completed", 0)
            info = {"status": status, "elapsed_seconds": round(now - started)}
            if total:
                info.update(
                    percent=round(completed / total * 100, 1),
                    downloaded_gb=round(completed / 1e9, 2),
                    total_gb=round(total / 1e9, 2),
                )
            print(json.dumps(info), flush=True)
            last_time = now
            last_status = status
if last_status != "success":
    raise SystemExit("Pull ended without success; retry to resume.")
print("Download complete", flush=True)
