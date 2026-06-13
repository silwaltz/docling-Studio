import sqlite3
c = sqlite3.connect('/app/data/docling_studio.db')
for r in c.execute("SELECT id, filename FROM documents WHERE filename LIKE 'NR Doc2%' OR filename LIKE '%Doc2%'").fetchall():
    print(r)
