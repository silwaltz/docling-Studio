import sqlite3
c = sqlite3.connect('/app/data/docling_studio.db')
print("tables:", [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
print("\nanalysis_jobs schema:")
for r in c.execute("PRAGMA table_info(analysis_jobs)").fetchall():
    print(" ", r)
print("\nanalysis_jobs count:", c.execute("SELECT COUNT(*) FROM analysis_jobs").fetchone())
print("\nfirst 5 analysis_jobs:")
for r in c.execute("SELECT id, document_id, status FROM analysis_jobs LIMIT 5").fetchall():
    print(" ", r)
