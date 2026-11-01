"""Persistent, single-user watchlists. Money is stored in integer minor units."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import os
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def money(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d.quantize(Decimal('.01')) != d:
            raise ValueError('Use a non-negative amount with at most two decimal places.')
        return int(d * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid money amount.') from None


def data_dir():
    root = os.environ.get('LOCALAPPDATA') if os.name == 'nt' else os.environ.get('XDG_DATA_HOME')
    return Path(root or Path.home() / '.local' / 'share') / 'TCGAlerts'


@dataclass(frozen=True)
class Observation:
    title: str
    price: int
    currency: str
    stock: str  # in_stock, out_of_stock, preorder, unknown
    source: str
    variant: str = ''

    def __post_init__(self):
        if not self.title or not isinstance(self.price, int) or isinstance(self.price, bool) or self.price < 0:
            raise ValueError('PARSE: Invalid title or price.')
        if len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
            raise ValueError('CURRENCY: Currency must be a three-letter ISO code.')
        if self.currency in {'JPY', 'KRW', 'BHD', 'KWD', 'OMR', 'CLP', 'VND'}:
            raise ValueError('CURRENCY: MVP supports two-decimal currencies only.')
        if self.stock not in {'in_stock', 'out_of_stock', 'preorder', 'unknown'}:
            raise ValueError('PARSE: Invalid availability.')


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS watches (
                    id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL DEFAULT '', group_name TEXT NOT NULL DEFAULT '',
                    target INTEGER, restock INTEGER NOT NULL DEFAULT 1,
                    shipping INTEGER, enabled INTEGER NOT NULL DEFAULT 1,
                    title TEXT, currency TEXT, price INTEGER, stock TEXT,
                    source TEXT, checked TEXT, attempted TEXT, error TEXT,
                    failures INTEGER NOT NULL DEFAULT 0, next_due REAL NOT NULL DEFAULT 0,
                    price_active INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY, watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
                    at TEXT NOT NULL, price INTEGER NOT NULL, currency TEXT NOT NULL,
                    stock TEXT NOT NULL, source TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS history_watch ON observations(watch_id, id);
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY, watch_id INTEGER REFERENCES watches(id) ON DELETE SET NULL,
                    at TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL);
            ''')
            # Idempotent additive migration: preserve every v0.1 watch and observation.
            columns = {r['name'] for r in c.execute('PRAGMA table_info(watches)')}
            for name in ('game', 'country', 'state'):
                if name not in columns:
                    c.execute(f"ALTER TABLE watches ADD COLUMN {name} TEXT NOT NULL DEFAULT 'Unspecified'")
            c.executescript('''
                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY, watch_id INTEGER REFERENCES watches(id) ON DELETE SET NULL,
                    at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
                CREATE INDEX IF NOT EXISTS activity_watch ON activity(watch_id, at);
                CREATE TABLE IF NOT EXISTS news_sources (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
                    game TEXT NOT NULL, adapter TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                    checked TEXT, error TEXT, next_due REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS news_items (
                    id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES news_sources(id) ON DELETE CASCADE,
                    url TEXT NOT NULL UNIQUE, title TEXT NOT NULL, published TEXT, first_seen TEXT NOT NULL,
                    topic TEXT NOT NULL DEFAULT 'News');
                PRAGMA user_version=2;
            ''')
            for name, url, game, adapter in (
                ('Riftbound official', 'https://playriftbound.com/en-us/news/', 'Riftbound', 'riftbound'),
                ('Cyberpunk official', 'https://cyberpunktcg.com/blog', 'Cyberpunk', 'cyberpunk')):
                c.execute('INSERT OR IGNORE INTO news_sources(name,url,game,adapter) VALUES(?,?,?,?)', (name,url,game,adapter))

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            with c:
                yield c
        finally:
            c.close()

    def rows(self, query, args=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(query, args)]

    def watches(self):
        return self.rows('SELECT * FROM watches ORDER BY id DESC')

    def add(self, url, label='', group_name='', target=None, shipping=None, restock=True, game='Unspecified', country='Unspecified', state='Unspecified'):
        from .sources import validate_url
        url = validate_url(url)
        from .catalog import metadata
        game, country, state = metadata(game, country, state)
        if target is not None and (not isinstance(target, int) or target < 0):
            raise ValueError('Invalid target.')
        if shipping is not None and (not isinstance(shipping, int) or shipping < 0):
            raise ValueError('Invalid shipping.')
        with self.connect() as c:
            return c.execute('INSERT INTO watches(url,label,group_name,target,shipping,restock,game,country,state) VALUES(?,?,?,?,?,?,?,?,?)',
                             (url, label, group_name, target, shipping, int(restock), game, country, state)).lastrowid

    def update(self, watch_id, **fields):
        allowed = {'label', 'group_name', 'target', 'shipping', 'restock', 'enabled', 'game', 'country', 'state'}
        if not fields or not set(fields) <= allowed:
            raise ValueError('Invalid fields.')
        for key in ('target', 'shipping'):
            if fields.get(key) is not None and (not isinstance(fields[key], int) or fields[key] < 0):
                raise ValueError('Invalid money amount.')
        if set(fields) & {'game', 'country', 'state'}:
            from .catalog import metadata
            old = self.rows('SELECT * FROM watches WHERE id=?', (watch_id,))
            if not old:
                raise ValueError('Watch no longer exists.')
            values = metadata(*(fields.get(k, old[0][k]) for k in ('game', 'country', 'state')))
            fields.update(zip(('game', 'country', 'state'), values))
        with self.connect() as c:
            assignments = ','.join(k + '=?' for k in fields)
            c.execute(f'UPDATE watches SET {assignments},price_active=0,next_due=0 WHERE id=?', (*fields.values(), watch_id))

    def delete(self, watch_id):
        with self.connect() as c:
            c.execute('DELETE FROM watches WHERE id=?', (watch_id,))

    def record(self, watch_id, obs, due=0):
        """Persist observation and alert transitions atomically. First check is not a restock."""
        alerts = []
        at = now()
        with self.connect() as c:
            old = c.execute('SELECT * FROM watches WHERE id=?', (watch_id,)).fetchone()
            if not old or not old['enabled']:
                return []
            if old['currency'] and old['currency'] != obs.currency:
                raise ValueError('CURRENCY: Currency changed; verify the listing before resuming.')
            # Targets are item price unless a known shipping amount is supplied.
            cost = obs.price + (old['shipping'] or 0)
            active = obs.stock == 'in_stock' and old['target'] is not None and cost <= old['target']
            title = old['label'] or obs.title
            if active and not old['price_active']:
                basis = 'delivered' if old['shipping'] is not None else 'item only; shipping unknown'
                alerts.append(('price', f'{title}: {obs.currency} {cost / 100:.2f} ({basis}) meets target.'))
            if old['restock'] and old['stock'] == 'out_of_stock' and obs.stock == 'in_stock':
                alerts.append(('restock', f'{title}: back in stock at {obs.currency} {obs.price / 100:.2f}.'))
            c.execute('INSERT INTO observations(watch_id,at,price,currency,stock,source) VALUES(?,?,?,?,?,?)',
                      (watch_id, at, obs.price, obs.currency, obs.stock, obs.source))
            c.execute('''UPDATE watches SET title=?,currency=?,price=?,stock=?,source=?,checked=?,attempted=?,
                         error=NULL,failures=0,next_due=?,price_active=? WHERE id=?''',
                      (obs.title, obs.currency, obs.price, obs.stock, obs.source, at, at, due, int(active), watch_id))
            c.execute('INSERT INTO activity(watch_id,at,kind) VALUES(?,?,?)', (watch_id, at, 'check_ok'))
            for kind, message in alerts:
                c.execute('INSERT INTO alerts(watch_id,at,kind,message) VALUES(?,?,?,?)', (watch_id, at, kind, message))
        return alerts

    def fail(self, watch_id, error, due):
        # Deliberately retain last successful stock and price.
        with self.connect() as c:
            c.execute('UPDATE watches SET error=?,attempted=?,failures=failures+1,next_due=? WHERE id=?',
                      (str(error)[:600], now(), due, watch_id))
            if c.execute('SELECT id FROM watches WHERE id=?', (watch_id,)).fetchone():
                c.execute('INSERT INTO activity(watch_id,at,kind,detail) VALUES(?,?,?,?)', (watch_id, now(), 'check_failed', str(error)[:600]))

    def history(self, watch_id):
        return self.rows('SELECT * FROM observations WHERE watch_id=? ORDER BY id DESC LIMIT 1000', (watch_id,))

    def alerts(self):
        return self.rows('SELECT * FROM alerts ORDER BY id DESC LIMIT 500')

    def backup(self, destination):
        if Path(destination).resolve() == self.path.resolve():
            raise ValueError('Choose a backup path different from the active database.')
        with self.connect() as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)


    def log_open(self, watch_id):
        with self.connect() as c:
            if c.execute('SELECT id FROM watches WHERE id=?', (watch_id,)).fetchone():
                c.execute('INSERT INTO activity(watch_id,at,kind) VALUES(?,?,?)', (watch_id, now(), 'store_open'))

    def add_news_source(self, name, url, game='Unspecified'):
        from .sources import validate_url
        from .catalog import metadata
        if not name.strip():
            raise ValueError('Enter a source name.')
        game = metadata(game)[0]
        with self.connect() as c:
            return c.execute('INSERT INTO news_sources(name,url,game,adapter) VALUES(?,?,?,?)', (name.strip()[:120], validate_url(url), game, 'feed')).lastrowid

    def news_sources(self):
        return self.rows('SELECT * FROM news_sources ORDER BY id')

    def set_news_enabled(self, source_id, enabled):
        with self.connect() as c:
            c.execute('UPDATE news_sources SET enabled=? WHERE id=?', (int(enabled), source_id))

    def save_news(self, source_id, items, due):
        with self.connect() as c:
            for item in items:
                c.execute('''INSERT INTO news_items(source_id,url,title,published,first_seen,topic) VALUES(?,?,?,?,?,?)
                             ON CONFLICT(url) DO UPDATE SET title=excluded.title,published=COALESCE(excluded.published,news_items.published),topic=excluded.topic''',
                          (source_id, item['url'], item['title'], item.get('published'), now(), item.get('topic', 'News')))
            c.execute('UPDATE news_sources SET checked=?,error=NULL,next_due=? WHERE id=?', (now(), due, source_id))

    def fail_news(self, source_id, message, due):
        with self.connect() as c:
            c.execute('UPDATE news_sources SET error=?,next_due=? WHERE id=?', (str(message)[:600], due, source_id))

    def news(self):
        return self.rows('''SELECT n.*,s.name AS source_name,s.game,s.checked,s.error,s.enabled FROM news_items n
                            JOIN news_sources s ON s.id=n.source_id WHERE s.enabled=1
                            ORDER BY COALESCE(n.published,n.first_seen) DESC LIMIT 500''')
