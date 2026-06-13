"""Smoke test VLM-direct on Doc2 (1 page, smallest)."""
import json, time, urllib.request

def post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=60).read())

docs = json.load(open(r"C:\Users\silwa\Projects\docling-Studio\experiments\docs_full.json"))
doc2 = next(d for d in docs if "Doc2" in d["filename"])
print(f"Triggering VLM-direct on {doc2['filename']} (id={doc2['doc_id']})")

t0 = time.time()
r = post("http://localhost:3000/api/analyses", {
    "documentId": doc2["doc_id"],
    "pipelineOptions": {
        "forceVlmPipeline": True,
        "vlmBackend": "ollama",
        "vlmOutputMode": "markdown",
        "vlmImageScale": 2.0,
    },
})
aid = r["id"]
print(f"  analysis_id={aid}, trigger took {time.time()-t0:.1f}s")

t1 = time.time()
last_status = None
while time.time() - t1 < 300:
    a = get(f"http://localhost:3000/api/analyses/{aid}")
    if a["status"] != last_status:
        print(f"  status={a['status']} progress={a.get('progressCurrent')}/{a.get('progressTotal')} elapsed={time.time()-t1:.0f}s")
        last_status = a["status"]
    if a["status"] in ("COMPLETED", "FAILED"):
        break
    time.sleep(3)

print(f"\nFinal: status={a['status']}, total={time.time()-t0:.1f}s")
if a["status"] == "COMPLETED":
    md = a.get("contentMarkdown") or ""
    print(f"Markdown: {len(md)} chars")
    print("--- first 800 chars ---")
    print(md[:800])
    print("---")
else:
    print(f"Error: {a.get('errorMessage')}")
