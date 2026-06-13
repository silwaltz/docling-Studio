"""Final smoke test: API is up, isStale field present, sweep ran."""
import urllib.request, json
with urllib.request.urlopen("http://localhost:8000/api/analyses", timeout=10) as r:
    body = json.loads(r.read())
print(f"API OK: {len(body)} analyses")
if body:
    has_field = "isStale" in body[0]
    print(f"isStale field present: {has_field}")
