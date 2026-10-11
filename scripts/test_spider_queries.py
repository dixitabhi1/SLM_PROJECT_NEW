import sqlite3

def q(db, sql):
    c = sqlite3.connect(f'data/spider/database/{db}/{db}.sqlite').cursor()
    c.execute(sql)
    return c.fetchone()[0]

print('tvshow Share > 3.0:', q('tvshow', 'SELECT count(*) FROM TV_series WHERE Share > 3.0'))
print('battle_death killed > 2:', q('battle_death', 'SELECT count(*) FROM death WHERE killed > 2'))
