import os
import sqlite3

dbs = sorted(os.listdir('data/spider/database'))
for db in dbs:
    p = f'data/spider/database/{db}/{db}.sqlite'
    if os.path.exists(p):
        conn = sqlite3.connect(p)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tbls = [r[0] for r in c.fetchall()]
        print(f"{db}: {tbls}")
        conn.close()

