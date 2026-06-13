"""Smoke-test the stuck-job recovery sweep.

We can't `sqlite3` in the container, so we use the live API + a tiny
script that injects a fake "stale RUNNING" row, then bounce the
container, then read the log to confirm `recovered=1`.
"""
import subprocess
import urllib.request
import json

from datetime import datetime, timedelta, UTC

# Step 1: confirm no RUNNING jobs
req = urllib.request.Request("http://localhost:8000/api/analyses")
with urllib.request.urlopen(req, timeout=10) as r:
    body = json.loads(r.read())
running = [j for j in body if j["status"] in ("RUNNING", "STARTING")]
print(f"BEFORE: {len(running)} RUNNING/STARTING jobs")
assert not running, "preconditions failed: there shouldn't be any stuck jobs"

# Step 2: inject a fake stale job directly into the DB via the repo.
# We use docker exec to run a python one-liner that imports the repo
# and inserts a row. The repo's `insert()` method is the same one the
# service uses, so this simulates exactly what the production code path
# does.
inject = """
docker exec docling-studio-document-parser-1 python -c '
import asyncio
from datetime import datetime, timedelta, UTC
from domain.models import AnalysisJob, AnalysisStatus
from persistence.analysis_repo import SqliteAnalysisRepository
from persistence.document_repo import SqliteDocumentRepository
from domain.value_objects import DocumentLifecycleState

async def main():
    doc = SqliteDocumentRepository()
    ar = SqliteAnalysisRepository()
    # Reuse one of the existing docs to keep the foreign key happy.
    d = await doc.find_all()
    if not d:
        print("no docs in db; cannot insert")
        return
    j = AnalysisJob(id="fake-stale-job-001", document_id=d[0].id)
    j.status = AnalysisStatus.RUNNING
    j.created_at = datetime.now(UTC) - timedelta(hours=2)
    await ar.insert(j)
    print("injected fake-stale-job-001 (2h old)")

asyncio.run(main())
'
"""

result = subprocess.run(
    inject, shell=True, capture_output=True, text=True
)
print("inject stdout:", result.stdout.strip())
print("inject stderr:", result.stderr.strip()[:300])

# Step 3: confirm the fake job is in the DB and reports isStale=True.
req = urllib.request.Request("http://localhost:8000/api/analyses")
with urllib.request.urlopen(req, timeout=10) as r:
    body = json.loads(r.read())
stale = [j for j in body if j["id"] == "fake-stale-job-001"]
assert stale, "fake job not found in API list"
print(
    f"  fake-stale-job-001 status={stale[0]['status']} isStale={stale[0]['isStale']}"
)
assert stale[0]["isStale"] is True, "fake job should be marked isStale=True"

print("\nSTEP: now bounce the container to trigger the recovery sweep")
