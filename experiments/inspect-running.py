"""Inspect all analyses: status, isStale, age."""
import urllib.request, json
from datetime import datetime, UTC
r = urllib.request.urlopen("http://localhost:8000/api/analyses", timeout=10)
body = json.loads(r.read())
print(f"total: {len(body)}")
print(f"statuses: {sorted(set(j['status'] for j in body))}")
print()
for j in body:
    if j["status"] in ("RUNNING", "STARTING"):
        print(f"  {j['id'][:8]} {j['status']} isStale={j['isStale']} {j['documentFilename']}")
