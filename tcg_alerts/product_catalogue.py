"""Local product catalogue built from public Shopify store listings.

Instead of pasting product links one at a time, the app syncs each store's
public ``/products.json`` listing into SQLite. Users then search every synced
store at once and track an exact variant with one click.
"""
from __future__ import annotations
import json
import re
from urllib import parse

from .core import now

SCHEMA = '''
CREATE TABLE IF NOT EXISTS catalogue_products(
    id INTEGER PRIMARY KEY,
    store TEXT NOT NULL, domain TEXT NOT NULL, product_id TEXT NOT NULL,
    variant_id TEXT NOT NULL, title TEXT NOT NULL, vendor TEXT NOT NULL,
    product_type TEXT NOT NULL, tags TEXT NOT NULL, game TEXT NOT NULL,
    price INTEGER, available INTEGER, image TEXT NOT NULL, url TEXT NOT NULL,
    synced TEXT NOT NULL, UNIQUE(domain, variant_id));
CREATE INDEX IF NOT EXISTS catalogue_title ON catalogue_products(title);
CREATE TABLE IF NOT EXISTS catalogue_syncs(
    domain TEXT PRIMARY KEY, store TEXT NOT NULL, synced TEXT NOT NULL,
    products INTEGER NOT NULL, error TEXT NOT NULL);
'''

MAX_PAGES = 20  # 250 products per page, so up to 5,000 per store
GAME_WORDS = [
    ('Riftbound', r'riftbound|league of legends tcg'),
    ('Cyberpunk', r'cyberpunk'),
    ('Pokémon', r'pok[eé]mon'),
    ('Magic: The Gathering', r'magic: the gathering|\bmtg\b'),
    ('One Piece', r'one piece'),
    ('Lorcana', r'lorcana'),
    ('Flesh and Blood', r'flesh and blood|\bfab\b'),
    ('Yu-Gi-Oh!', r'yu-?gi-?oh'),
    ('Gundam', r'gundam'),
]


def ensure(db):
    with db.connect() as c:
        c.executescript(SCHEMA)


def infer_game(*texts):
    blob = ' '.join(texts).lower()
    return next((game for game, pattern in GAME_WORDS if re.search(pattern, blob)), 'Unspecified')


def price_minor(value):
    try:
        whole, _, frac = str(value).partition('.')
        return int(whole) * 100 + int((frac + '00')[:2])
    except ValueError:
        return None


def parse_page(store, base_url, payload):
    """Rows for one /products.json page. One row per variant."""
    domain = parse.urlsplit(base_url).netloc
    rows = []
    for p in payload.get('products', []):
        tags = p.get('tags', [])
        tags = ', '.join(tags) if isinstance(tags, list) else str(tags)
        game = infer_game(p.get('title', ''), p.get('vendor', ''), p.get('product_type', ''), tags)
        images = p.get('images') or []
        image = images[0].get('src', '') if images and isinstance(images[0], dict) else ''
        variants = p.get('variants') or []
        for v in variants:
            title = str(p.get('title', '')).strip()
            vt = str(v.get('title', ''))
            if vt and vt != 'Default Title' and len(variants) > 1:
                title += ' / ' + vt
            url = f"{base_url.rstrip('/')}/products/{p.get('handle')}?variant={v.get('id')}"
            rows.append(dict(store=store, domain=domain, product_id=str(p.get('id')), variant_id=str(v.get('id')),
                             title=title, vendor=str(p.get('vendor', '')), product_type=str(p.get('product_type', '')),
                             tags=tags, game=game, price=price_minor(v.get('price')),
                             available=None if v.get('available') is None else int(bool(v.get('available'))),
                             image=image, url=url))
    return rows


def sync_store(db, client, store, base_url, max_pages=MAX_PAGES):
    """Replace one store's catalogue with a fresh listing. Returns the row count."""
    ensure(db)
    domain = parse.urlsplit(base_url).netloc
    rows = []
    try:
        for page in range(1, max_pages + 1):
            payload = json.loads(client.get(f"{base_url.rstrip('/')}/products.json?limit=250&page={page}"))
            batch = parse_page(store, base_url, payload)
            rows += batch
            if len(payload.get('products', [])) < 250:
                break
    except Exception as e:
        with db.connect() as c:
            c.execute('INSERT INTO catalogue_syncs VALUES(?,?,?,?,?) ON CONFLICT(domain) DO UPDATE SET synced=excluded.synced,error=excluded.error',
                      (domain, store, now(), 0, str(e)[:300]))
        raise
    stamp = now()
    with db.connect() as c:
        c.execute('DELETE FROM catalogue_products WHERE domain=?', (domain,))
        c.executemany('INSERT OR REPLACE INTO catalogue_products(store,domain,product_id,variant_id,title,vendor,product_type,tags,game,price,available,image,url,synced) '
                      'VALUES(:store,:domain,:product_id,:variant_id,:title,:vendor,:product_type,:tags,:game,:price,:available,:image,:url,:synced)',
                      [dict(r, synced=stamp) for r in rows])
        c.execute('INSERT OR REPLACE INTO catalogue_syncs VALUES(?,?,?,?,?)', (domain, store, stamp, len(rows), ''))
    return len(rows)


def sync_all(db, client, stores):
    """stores: iterable of (name, base_url). Returns {name: count or error text}."""
    results = {}
    for name, url in stores:
        try:
            results[name] = sync_store(db, client, name, url)
        except Exception as e:
            results[name] = f'failed: {e}'
    return results


def search(db, text='', game='All games', in_stock_only=False, limit=300):
    ensure(db)
    sql, args = 'SELECT * FROM catalogue_products WHERE 1=1', []
    for word in text.split():
        sql += ' AND (title LIKE ? OR tags LIKE ? OR vendor LIKE ?)'
        args += [f'%{word}%'] * 3
    if game not in ('', 'All games'):
        sql += ' AND game=?'
        args.append(game)
    if in_stock_only:
        sql += ' AND available=1'
    sql += ' ORDER BY price IS NULL, price, title LIMIT ?'
    args.append(limit)
    with db.connect() as c:
        return [dict(r) for r in c.execute(sql, args)]


def sync_status(db):
    ensure(db)
    with db.connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM catalogue_syncs ORDER BY store')]
