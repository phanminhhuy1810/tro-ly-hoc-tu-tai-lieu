"""Export only the self-authored subnet dev trial; never export auth tokens."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
db = sqlite3.connect((ROOT / "backend/runtime/study.sqlite3").as_uri() + "?mode=ro", uri=True)
db.row_factory = sqlite3.Row
sources = [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY created_at DESC")]
source = next(row for row in sources if json.loads(row["metadata_json"])["name"] == "subnet-dev.txt")
owner, source_id = source["owner_id"], source["id"]
plans = [dict(row) for row in db.execute("SELECT * FROM plans WHERE source_id=? AND owner_id=?", (source_id, owner))]
plan_ids = {plan["id"] for plan in plans}
revisions = [dict(row) for row in db.execute("SELECT * FROM course_revisions ORDER BY revision") if row["plan_id"] in plan_ids]
course_ids = {row["course_id"] for row in revisions}
jobs = []
for row in db.execute("SELECT * FROM jobs WHERE owner_id=? ORDER BY created_at", (owner,)):
    payload = json.loads(row["payload_json"])
    only_trial_owner = not any(x["owner_id"] == owner and x["id"] != source_id for x in sources)
    if payload.get("plan_id") not in plan_ids and payload.get("course_id") not in course_ids and not (only_trial_owner and row["task"] in {"lesson", "correction", "chat"}):
        continue
    jobs.append({"id": row["id"], "task": row["task"], "status": row["status"], "attempts": row["attempts"], "created_at": row["created_at"], "updated_at": row["updated_at"], "seconds": round((datetime.fromisoformat(row["updated_at"]) - datetime.fromisoformat(row["created_at"])).total_seconds(), 3), "resume_job_id": payload.get("resume_job_id"), "saved_reading": "reading" in json.loads(row["partial_json"]), "saved_question_types": list(json.loads(row["partial_json"]).get("questions", {})), "error": json.loads(row["error_json"]) if row["error_json"] else None, "chat_result": json.loads(row["result_json"]) if row["task"] == "chat" and row["result_json"] else None})
original = (ROOT / "backend/runtime/sources" / source_id).read_bytes()
assert original == (ROOT / "experiments/02-local-ai/fixtures/subnet-dev.txt").read_bytes(), "Only the exact self-authored dev fixture may be exported"
report = {
    "verified_at": datetime.now(timezone.utc).isoformat(),
    "scope": "Self-authored subnet-dev.txt uploaded via browser; not Huy's school document, final benchmark, or independent user evaluation.",
    "model": "qwen3.5:9b", "provider": "ollama_local", "runner": "mlx",
    "source": {"id": source_id, "metadata": json.loads(source["metadata_json"]), "original_sha256_now": hashlib.sha256(original).hexdigest(), "original_text": original.decode("utf-8")},
    "extractions": [{"revision": row["revision"], "reviewed": bool(row["reviewed_at"]), "fragments": json.loads(row["content_json"])} for row in db.execute("SELECT * FROM extraction_revisions WHERE source_id=? ORDER BY revision", (source_id,))],
    "plans": [{"id": row["id"], "status": row["status"], "preferences": json.loads(row["preferences_json"]), "outline": json.loads(row["outline_json"])} for row in plans],
    "course_revisions": [{"course_id": row["course_id"], "revision": row["revision"], "content": json.loads(row["content_json"])} for row in revisions],
    "jobs": jobs,
    "attempts": [{"id": row["id"], "revision": row["course_revision"], "status": row["status"], "result": json.loads(row["result_json"]) if row["result_json"] else None, "items": json.loads(row["items_json"])} for row in db.execute("SELECT * FROM study_sessions WHERE owner_id=?", (owner,)) if row["course_id"] in course_ids],
    "corrections": [{"base_revision": row["base_revision"], "status": row["status"], "request": row["request"], "scope": json.loads(row["scope_json"]), "before": json.loads(row["content_json"])["before"], "after": json.loads(row["content_json"])["after"]} for row in db.execute("SELECT * FROM revision_proposals WHERE owner_id=?", (owner,)) if row["course_id"] in course_ids],
    "chat": [{"role": row["role"], "revision": row["revision"], "text": row["content"], "source_refs": json.loads(row["refs_json"])} for row in db.execute("SELECT * FROM chat_messages WHERE owner_id=? ORDER BY created_at", (owner,)) if row["course_id"] in course_ids],
}
assert report["source"]["metadata"]["sha256"] == report["source"]["original_sha256_now"]
target = ROOT / "backend/evidence/subnet-local-trial.json"
target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"report": str(target), "jobs": [{k: j[k] for k in ["task", "status", "seconds"]} for j in jobs], "revisions": [r["revision"] for r in report["course_revisions"]], "results": [a["result"] for a in report["attempts"]]}, ensure_ascii=False))
