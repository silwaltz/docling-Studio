"""Smoke test: trigger VLM-direct in json mode for Doc2, see what content_markdown looks like."""
import json, time, urllib.request

def post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=60).read())

docs = json.load(open(r"C:\Users\silwa\Projects\docling-Studio\experiments\docs_full.json"))
doc2 = next(d for d in docs if "Doc2" in d["filename"])
print(f"Triggering VLM-direct (json mode) on {doc2['filename']} (id={doc2['doc_id']})")

t0 = time.time()
r = post("http://localhost:3000/api/analyses", {
    "documentId": doc2["doc_id"],
    "pipelineOptions": {
        "forceVlmPipeline": True,
        "vlmBackend": "ollama",
        "vlmOutputMode": "json",  # NEW: ask qwen3-vl to produce JSON
        "vlmImageScale": 2.0,
    },
})
aid = r["id"]
print(f"  analysis_id={aid}")

t1 = time.time()
while time.time() - t1 < 300:
    a = get(f"http://localhost:3000/api/analyses/{aid}")
    if a["status"] in ("COMPLETED", "FAILED"):
        break
    time.sleep(3)

print(f"  status: {a['status']} ({time.time()-t0:.1f}s)")
if a["status"] == "COMPLETED":
    md = a.get("contentMarkdown") or ""
    cj = a.get("contentJson") or ""
    print(f"  content_markdown: {len(md)} chars")
    print(f"  content_json: {len(cj)} chars")
    print()
    print("--- content_markdown (first 800 chars) ---")
    print(md[:800])
    print("---")
    print("--- content_json (first 1200 chars) ---")
    print(cj[:1200])
    print("---")
else:
    print(f"  error: {a.get('errorMessage')}")
