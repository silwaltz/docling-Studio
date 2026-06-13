"""Refresh docs_full.json with current DB state.
Outputs only doc_id + filename + page_count. (No completed analyses to read.)
"""
import sqlite3, json
c = sqlite3.connect('/app/data/docling_studio.db')
c.row_factory = sqlite3.Row
rows = c.execute("SELECT id, filename, page_count FROM documents ORDER BY filename").fetchall()
out = []
for r in rows:
    out.append({
        "doc_id": r["id"],
        "filename": r["filename"],
        "page_count": r["page_count"],
        "md_chars": 0,
        "md": "",
    })
print(f"Found {len(out)} docs")
with open('/tmp/docs_full.json', 'w') as f:
    json.dump(out, f)
print("Wrote /tmp/docs_full.json")
for d in out:
    print(f"  {d['doc_id']}  {d['filename']}")
