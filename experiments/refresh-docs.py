"""Re-collect the current document list and (re)build experiments/docs_full.json.

The container's volume mount keeps the SQLite DB across restarts, but
on some rebuilds the doc_ids are regenerated. This script fetches the
fresh `/api/documents` list and writes it back so the experiment
scripts use up-to-date ids.
"""
import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "docs_full.json"
with urllib.request.urlopen("http://localhost:8000/api/documents", timeout=10) as r:
    docs = json.loads(r.read())
out = [
    {"doc_id": d["id"], "filename": d["filename"], "page_count": d.get("pageCount", "?")}
    for d in docs
]
OUT.write_text(json.dumps(out, indent=2))
print(f"wrote {OUT} with {len(out)} docs")
for d in out:
    print(f"  {d['filename']:60s} pages={d['page_count']:>3} id={d['doc_id'][:8]}")
