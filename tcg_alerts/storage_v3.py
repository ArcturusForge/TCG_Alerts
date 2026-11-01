"""Additive v3 tables; separate from price observations and alert semantics."""
from .commerce import domain
from .seed_data import STORES,RELEASES


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS stores(id INTEGER PRIMARY KEY,name TEXT NOT NULL,url TEXT NOT NULL,domain TEXT UNIQUE NOT NULL,country TEXT NOT NULL,state TEXT NOT NULL,address TEXT NOT NULL,source_url TEXT NOT NULL,checked TEXT NOT NULL,catalog_url TEXT NOT NULL,support TEXT NOT NULL,pickup TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS shipping_rules(id INTEGER PRIMARY KEY,store_id INTEGER NOT NULL REFERENCES stores(id),country TEXT NOT NULL,postcode TEXT NOT NULL,currency TEXT NOT NULL,flat INTEGER,free_over INTEGER,source_url TEXT NOT NULL,checked TEXT NOT NULL,UNIQUE(store_id,country,postcode,currency));
    CREATE TABLE IF NOT EXISTS releases(id INTEGER PRIMARY KEY,seed_key TEXT UNIQUE,title TEXT NOT NULL,game TEXT NOT NULL,kind TEXT NOT NULL,start TEXT,end TEXT,precision TEXT NOT NULL,window TEXT NOT NULL,region TEXT NOT NULL,status TEXT NOT NULL,source_url TEXT NOT NULL,checked TEXT NOT NULL,notes TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    ''')
    columns={r['name'] for r in c.execute('PRAGMA table_info(watches)')}
    for name,definition in [('store_id','INTEGER REFERENCES stores(id)'),('pack_count','INTEGER'),('shipping_postcode',"TEXT NOT NULL DEFAULT ''"),('shipping_country',"TEXT NOT NULL DEFAULT 'Australia'"),('pickup',"TEXT NOT NULL DEFAULT 'Unspecified'")]:
        if name not in columns:c.execute(f'ALTER TABLE watches ADD COLUMN {name} {definition}')
    for name,url,address,source,catalog,support,pickup in STORES:
        c.execute('INSERT OR IGNORE INTO stores(name,url,domain,country,state,address,source_url,checked,catalog_url,support,pickup) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(name,url,domain(url),'Australia','Victoria',address,source,'2026-11-01',catalog,support,pickup))
    for key,title,game,kind,start,end,precision,window,source,notes in RELEASES:
        c.execute('INSERT OR IGNORE INTO releases(seed_key,title,game,kind,start,end,precision,window,region,status,source_url,checked,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(key,title,game,kind,start,end,precision,window,'Global / unspecified','Confirmed',source,'2026-11-01',notes))
    for row in c.execute('SELECT id,url FROM watches WHERE store_id IS NULL').fetchall():
        found=c.execute('SELECT id FROM stores WHERE domain=?',(domain(row['url']),)).fetchone()
        if found:c.execute('UPDATE watches SET store_id=? WHERE id=?',(found['id'],row['id']))
    c.execute('PRAGMA user_version=3')
