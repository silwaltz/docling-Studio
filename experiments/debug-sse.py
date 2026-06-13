"""Debug: dump raw SSE bytes from chat endpoint."""
import json, urllib.request
from pathlib import Path

with open(Path(__file__).parent / "docs_full.json") as f:
    docs = json.load(f)
doc2 = next(d for d in docs if "Doc2" in d["filename"])

body = json.dumps({"messages": [{"role": "user", "content": "Extrait toutes les adresses, noms de sociétés, informations de transport et descriptions des marchandises au format JSON."}]}).encode("utf-8")
req = urllib.request.Request(
    f"http://localhost:3000/api/documents/{doc2['doc_id']}/chat",
    data=body, headers={"Content-Type": "application/json"}, method="POST",
)
print("Sending request...")
with urllib.request.urlopen(req, timeout=300) as resp:
    print(f"Status: {resp.status}, headers:")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
    print()
    print("Reading body byte by byte...")
    chunks = []
    while True:
        chunk = resp.read(1024)
        if not chunk:
            break
        chunks.append(chunk)
    print(f"Total chunks: {len(chunks)}, total bytes: {sum(len(c) for c in chunks)}")
    if chunks:
        full = b"".join(chunks)
        print(f"\nFirst 2000 bytes raw:")
        print(full[:2000].decode("utf-8", errors="replace"))
        print(f"\n...last 1000 bytes raw:")
        print(full[-1000:].decode("utf-8", errors="replace"))
