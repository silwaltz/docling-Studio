import sqlite3
c = sqlite3.connect('/app/data/docling_studio.db')
print("statuses:", list(c.execute("SELECT status, COUNT(*) FROM analysis_jobs GROUP BY status").fetchall()))
print("doc count:", c.execute("SELECT COUNT(*) FROM documents").fetchone())
for row in c.execute("SELECT id, filename, page_count FROM documents ORDER BY filename").fetchall():
    print(row)
