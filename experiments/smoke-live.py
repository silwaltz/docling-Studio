"""Smoke test: call chat for Doc2 and dump the response."""
import json, urllib.request
from pathlib import Path

with open(Path(__file__).parent / "docs_full.json") as f:
    docs = json.load(f)
doc2 = next(d for d in docs if "Doc2" in d["filename"])
print(f"Smoke test on {doc2['filename']} (id={doc2['doc_id']})")

body = json.dumps({"messages": [{"role": "user", "content": "Extrait toutes les adresses, noms de sociétés, informations de transport et descriptions des marchandises au format JSON."}], "model": "gemma4:e4b-it-qat"}).encode("utf-8")
req = urllib.request.Request(
    f"http://localhost:3000/api/documents/{doc2['doc_id']}/chat",
    data=body, headers={"Content-Type": "application/json"}, method="POST",
)
with urllib.request.urlopen(req, timeout=300) as resp:
    buf = ""
    text = ""
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
                            text += ev["delta"]
                        if "done" in ev and ev.get("done"):
                            print(f"Model: {ev.get('model')}, tokens: {ev.get('total_tokens')}")
                    except Exception:
                        pass
print(f"\nFull response ({len(text)} chars):\n{text}")
