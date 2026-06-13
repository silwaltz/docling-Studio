"""Check the fake-stale job's isStale flag."""
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/api/analyses", timeout=10) as r:
    body = json.loads(r.read())
for j in body:
    if j["id"] == "fake-stale-job-001":
        print(f"status={j['status']} isStale={j['isStale']} createdAt={j['createdAt']}")
        break
else:
    print("NOT FOUND in API")
