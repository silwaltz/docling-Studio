"""Quick live API smoke: GET /api/analyses should return [] (empty after container restart)."""
import urllib.request, json
req = urllib.request.Request("http://localhost:8000/api/analyses", method="GET")
with urllib.request.urlopen(req, timeout=10) as r:
    body = json.loads(r.read())
print("status:", r.status)
print("analyses:", json.dumps(body, indent=2)[:500])
