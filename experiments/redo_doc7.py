"""Re-trigger VLM + Ask for Doc7 only (got malformed output first time)."""
import json, time, urllib.request, re
from pathlib import Path

def post(url, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=60).read())

docs = json.load(open(r"C:\Users\silwa\Projects\docling-Studio\experiments\docs_full.json"))
doc7 = next(d for d in docs if d["filename"] == "NR Doc7-BL.pdf")
print(f"Re-triggering VLM for {doc7['filename']} (id={doc7['doc_id']})")

# New analysis
r = post("http://localhost:3000/api/analyses", {
    "documentId": doc7["doc_id"],
    "pipelineOptions": {
        "forceVlmPipeline": True,
        "vlmBackend": "ollama",
        "vlmOutputMode": "markdown",
        "vlmImageScale": 2.0,
    },
})
aid = r["id"]
print(f"  analysis: {aid}")
t0 = time.time()
while time.time() - t0 < 300:
    a = get(f"http://localhost:3000/api/analyses/{aid}")
    if a["status"] in ("COMPLETED", "FAILED"):
        break
    time.sleep(3)
print(f"  completed in {time.time()-t0:.1f}s: {a['status']}")
md = a.get("contentMarkdown") or ""
print(f"  markdown: {len(md)} chars")
# Save the markdown
out_md = Path(r"C:\Users\silwa\Projects\docling-Studio\extracted-json\vlm__4df0e88f__NR_Doc7-BL.md")
out_md.write_text(md, encoding="utf-8")
print(f"  saved: {out_md.name}")

# Now ask
print("\nRunning Ask...")
body = json.dumps({"messages": [{"role": "user", "content": "Extrait toutes les adresses, noms de sociétés, informations de transport et descriptions des marchandises au format JSON."}], "model": "gemma4:e4b-it-qat"}).encode("utf-8")
req = urllib.request.Request(f"http://localhost:3000/api/documents/{doc7['doc_id']}/chat", data=body, headers={"Content-Type": "application/json"}, method="POST")
full_text = ""
with urllib.request.urlopen(req, timeout=600) as resp:
    buf = ""
    while True:
        chunk = resp.read(4096)
        if not chunk:
            break
        buf += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buf:
            frame, buf = buf.split("\n\n", 1)
            for line in frame.splitlines():
                if line.startswith("data: "):
                    try:
                        ev = json.loads(line[6:])
                        if "delta" in ev:
                            full_text += ev["delta"]
                    except Exception:
                        pass
print(f"Ask: {len(full_text)} chars")
# Save
out_raw = Path(r"C:\Users\silwa\Projects\docling-Studio\extracted-json\vlm_ask__4df0e88f__NR_Doc7-BL.pdf.raw.txt")
out_raw.write_text(full_text, encoding="utf-8")
print(f"  saved: {out_raw.name}")
print()
print("--- first 1000 chars ---")
print(full_text[:1000])
