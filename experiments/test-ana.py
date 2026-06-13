import urllib.request, json
# Test POST /api/analyses
body = json.dumps({"documentId": "12757426-a8d6-4f9c-aa9b-81c4ce16eb2d", "pipelineOptions": {"forceVlmPipeline": True, "vlmBackend": "ollama", "vlmOutputMode": "markdown"}}).encode("utf-8")
req = urllib.request.Request("http://localhost:3000/api/analyses", data=body, headers={"Content-Type": "application/json"}, method="POST")
try:
    r = urllib.request.urlopen(req, timeout=30)
    print(f"POST /api/analyses -> {r.status}: {r.read()[:500].decode()}")
except urllib.error.HTTPError as e:
    print(f"POST /api/analyses -> HTTP {e.code}: {e.read()[:500].decode()}")
