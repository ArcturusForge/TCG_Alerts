"""Private deck plans with exact-printing notes and source-aware price subtotals."""
from __future__ import annotations
import csv
import io
import json
import re
from datetime import date,datetime,timezone
from .core import now, money
from .sources import validate_url
from .catalog import metadata

CURRENCIES=('AUD','USD','NZD','CAD','EUR','GBP')
ENTRY_FIELDS=('name','section','quantity','owned','set_code','collector','printing','language','condition','manual_price','reference_source','reference_checked','image_url','notes','watch_id','listing_confirmed')
CSV_FIELDS=('name','quantity','owned','section','set_code','collector','printing','language','condition','reference_price','currency','reference_source','reference_checked','image_url','notes','watch_url')


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS decks(id INTEGER PRIMARY KEY,name TEXT NOT NULL,game TEXT NOT NULL,currency TEXT NOT NULL,notes TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS deck_entries(
        id INTEGER PRIMARY KEY,deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
        name TEXT NOT NULL,section TEXT NOT NULL,quantity INTEGER NOT NULL,owned INTEGER NOT NULL,
        set_code TEXT NOT NULL,collector TEXT NOT NULL,printing TEXT NOT NULL,language TEXT NOT NULL,condition TEXT NOT NULL,
        manual_price INTEGER,reference_source TEXT NOT NULL,reference_checked TEXT NOT NULL,image_url TEXT NOT NULL,
        image_path TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL,watch_id INTEGER REFERENCES watches(id) ON DELETE SET NULL,
        listing_confirmed INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS deck_snapshots(id INTEGER PRIMARY KEY,deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,at TEXT NOT NULL,currency TEXT NOT NULL,summary TEXT NOT NULL,evidence TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS deck_entry_parent ON deck_entries(deck_id);
    PRAGMA user_version=4;
    ''')


def parse_list(text):
    if len(text.encode('utf-8'))>1024*1024:raise ValueError('Deck list is too large (1 MB limit).')
    section='Main';rows=[]
    for number,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if not line or line.startswith(('#','//')):continue
        if line.startswith('[') and line.endswith(']'):
            section=line[1:-1].strip()
            if not section or len(section)>80:raise ValueError(f'Line {number}: invalid section.')
            continue
        if line.endswith(':') and line[:-1].casefold() in ('main','main deck','sideboard','legend','champion','runes','battlefields','other'):
            section=line[:-1];continue
        m=re.fullmatch(r'(\d+)\s*[xX]?\s+(.+)',line)
        if m:quantity,name=int(m[1]),m[2].strip()
        else:
            m=re.fullmatch(r'(.+?)\s+[xX](\d+)',line)
            if not m:raise ValueError(f'Line {number}: use “3 Card Name”, “3x Card Name” or “[Section]”.')
            name,quantity=m[1].strip(),int(m[2])
        if not 1<=quantity<=10000 or not name:raise ValueError(f'Line {number}: invalid card/quantity.')
        rows.append(dict(name=name,quantity=quantity,section=section))
        if len(rows)>1000:raise ValueError('Maximum 1,000 deck rows per import.')
    if not rows:raise ValueError('No cards found.')
    return rows


def entry_values(fields):
    defaults=dict(name='',section='Main',quantity=1,owned=0,set_code='',collector='',printing='Standard',language='English',condition='Near mint',manual_price=None,reference_source='',reference_checked='',image_url='',notes='',watch_id=None,listing_confirmed=False)
    v={k:fields.get(k,default) for k,default in defaults.items()}
    for k in ('name','section','set_code','collector','printing','language','condition','reference_source','reference_checked','image_url','notes'):
        v[k]=str(v[k] or '').strip()
    if not v['name'] or len(v['name'])>240:raise ValueError('Enter a card name (maximum 240 characters).')
    if any(len(v[k])>240 for k in ('section','set_code','collector','printing','language','condition')):raise ValueError('Card identity fields are too long.')
    if len(v['notes'])>4000 or len(v['reference_source'])>2048 or len(v['image_url'])>4096:raise ValueError('Notes or URLs are too long.')
    for key,lo,hi in [('quantity',1,10000),('owned',0,1000000)]:
        if not isinstance(v[key],int) or isinstance(v[key],bool) or not lo<=v[key]<=hi:raise ValueError(f'{key.title()} must be a whole number between {lo} and {hi}.')
    if v['manual_price'] is not None:
        if not isinstance(v['manual_price'],int) or isinstance(v['manual_price'],bool) or v['manual_price']<0:raise ValueError('Invalid reference amount.')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v['reference_checked']):raise ValueError('A manual reference price needs its YYYY-MM-DD source date.')
        date.fromisoformat(v['reference_checked'])
        v['reference_source']=v['reference_source'] or 'User entered'
    if v['image_url']:v['image_url']=validate_url(v['image_url'])
    if v['watch_id'] is not None:
        if not isinstance(v['watch_id'],int) or isinstance(v['watch_id'],bool) or v['watch_id']<1:raise ValueError('Invalid watch selection.')
        if not v['listing_confirmed']:raise ValueError('Confirm the linked listing is ONE copy of this printing, language and condition.')
    v['listing_confirmed']=int(bool(v['listing_confirmed']))
    return v


class DeckStore:
    def __init__(self,db):self.db=db
    def decks(self):return self.db.rows('SELECT * FROM decks ORDER BY updated DESC,id DESC')
    def deck(self,deck_id):
        rows=self.db.rows('SELECT * FROM decks WHERE id=?',(deck_id,))
        if not rows:raise ValueError('Deck no longer exists.')
        return rows[0]
    def save_deck(self,name,game,currency='AUD',notes='',deck_id=None):
        name=name.strip();game=metadata(game=game)[0]
        if not name or len(name)>160:raise ValueError('Enter a deck name (maximum 160 characters).')
        if currency not in CURRENCIES:raise ValueError('Choose a supported two-decimal currency.')
        if len(notes)>4000:raise ValueError('Deck notes are too long.')
        with self.db.connect() as c:
            if deck_id:
                old=c.execute('SELECT * FROM decks WHERE id=?',(deck_id,)).fetchone()
                if not old:raise ValueError('Deck no longer exists.')
                if c.execute('SELECT 1 FROM deck_entries WHERE deck_id=?',(deck_id,)).fetchone() and (old['currency']!=currency or old['game']!=game):raise ValueError('Game/currency are locked once cards exist. Create a new deck instead; no currency conversion is assumed.')
                c.execute('UPDATE decks SET name=?,game=?,currency=?,notes=?,updated=? WHERE id=?',(name,game,currency,notes.strip(),now(),deck_id));return deck_id
            return c.execute('INSERT INTO decks(name,game,currency,notes,created,updated) VALUES(?,?,?,?,?,?)',(name,game,currency,notes.strip(),now(),now())).lastrowid
    def _validate_link(self,c,deck_id,v):
        if v['watch_id'] is None:return
        w=c.execute('SELECT * FROM watches WHERE id=?',(v['watch_id'],)).fetchone()
        d=c.execute('SELECT * FROM decks WHERE id=?',(deck_id,)).fetchone()
        if not w:raise ValueError('Linked watch no longer exists.')
        if w['game'] not in ('Unspecified',d['game']):raise ValueError('That watch is tagged for a different game.')
    def _insert(self,c,deck_id,v):
        self._validate_link(c,deck_id,v)
        return c.execute('INSERT INTO deck_entries(deck_id,'+','.join(ENTRY_FIELDS)+') VALUES('+','.join('?' for _ in range(len(ENTRY_FIELDS)+1))+')',(deck_id,*(v[k] for k in ENTRY_FIELDS))).lastrowid
    def save_entry(self,deck_id,fields,entry_id=None):
        v=entry_values(fields)
        with self.db.connect() as c:
            if not c.execute('SELECT id FROM decks WHERE id=?',(deck_id,)).fetchone():raise ValueError('Deck no longer exists.')
            if entry_id:
                old=c.execute('SELECT * FROM deck_entries WHERE id=? AND deck_id=?',(entry_id,deck_id)).fetchone()
                if not old:raise ValueError('Card row no longer exists.')
                self._validate_link(c,deck_id,v)
                c.execute('UPDATE deck_entries SET '+','.join(k+'=?' for k in ENTRY_FIELDS)+',image_path=? WHERE id=?',(*(v[k] for k in ENTRY_FIELDS),old['image_path'] if old['image_url']==v['image_url'] else '',entry_id))
            else:
                if c.execute('SELECT COUNT(*) FROM deck_entries WHERE deck_id=?',(deck_id,)).fetchone()[0]>=1000:raise ValueError('A deck can contain at most 1,000 rows.')
                entry_id=self._insert(c,deck_id,v)
            c.execute('UPDATE decks SET updated=? WHERE id=?',(now(),deck_id))
        return entry_id
    def import_rows(self,deck_id,rows):
        if not 1<=len(rows)<=1000:raise ValueError('Import between 1 and 1,000 rows.')
        values=[entry_values(r) for r in rows]
        with self.db.connect() as c:
            if not c.execute('SELECT id FROM decks WHERE id=?',(deck_id,)).fetchone():raise ValueError('Deck no longer exists.')
            if c.execute('SELECT COUNT(*) FROM deck_entries WHERE deck_id=?',(deck_id,)).fetchone()[0]+len(values)>1000:raise ValueError('A deck can contain at most 1,000 rows.')
            for v in values:self._insert(c,deck_id,v)
            c.execute('UPDATE decks SET updated=? WHERE id=?',(now(),deck_id))
        return len(values)
    def remove_entry(self,deck_id,entry_id):
        with self.db.connect() as c:
            c.execute('DELETE FROM deck_entries WHERE id=? AND deck_id=?',(entry_id,deck_id));c.execute('UPDATE decks SET updated=? WHERE id=?',(now(),deck_id))
    def delete_deck(self,deck_id):
        with self.db.connect() as c:c.execute('DELETE FROM decks WHERE id=?',(deck_id,))
    def clone(self,deck_id):
        d=self.deck(deck_id)
        with self.db.connect() as c:
            new=c.execute('INSERT INTO decks(name,game,currency,notes,created,updated) VALUES(?,?,?,?,?,?)',(d['name']+' (copy)',d['game'],d['currency'],d['notes'],now(),now())).lastrowid
            rows=c.execute('SELECT * FROM deck_entries WHERE deck_id=? ORDER BY id',(deck_id,)).fetchall()
            for row in rows:
                v=dict(row);new_row=self._insert(c,new,v)
                c.execute('UPDATE deck_entries SET image_path=? WHERE id=?',(row['image_path'],new_row))
        return new
    def local_image(self,entry_id,path):
        with self.db.connect() as c:c.execute('UPDATE deck_entries SET image_path=? WHERE id=?',(str(path),entry_id))
    def report(self,deck_id,clock=None):
        d=self.deck(deck_id);clock=clock or datetime.now(timezone.utc)
        rows=self.db.rows('''SELECT e.*,w.url AS listing_url,w.title AS listing_title,w.price AS ask,w.currency AS ask_currency,w.stock,w.checked AS price_checked,w.error AS check_error,w.enabled,w.game AS listing_game
                            FROM deck_entries e LEFT JOIN watches w ON w.id=e.watch_id WHERE e.deck_id=? ORDER BY e.section,e.id''',(deck_id,))
        summary=dict(required=0,owned=0,missing=0,reference_subtotal=0,reference_copies=0,missing_reference_subtotal=0,missing_reference_copies=0,missing_ask_subtotal=0,missing_ask_copies=0,reference_old_copies=0)
        lines=[]
        for r in rows:
            q=r['quantity'];owned=min(q,r['owned']);missing=max(0,q-r['owned']);summary['required']+=q;summary['owned']+=owned;summary['missing']+=missing
            linked=bool(r['watch_id'] and r['listing_confirmed'] and r['listing_game'] in ('Unspecified',d['game']))
            ask_ok=linked and r['ask'] is not None and r['ask_currency']==d['currency']
            fresh=False
            if r['price_checked']:
                try:fresh=0<=(clock-datetime.fromisoformat(r['price_checked'])).total_seconds()<=1800
                except (ValueError,TypeError):pass
            reference=r['manual_price'];basis='Manual reference: '+(r['reference_source'] or 'User entered') if reference is not None else 'Unpriced'
            if reference is None and ask_ok:
                reference=r['ask'];basis='Last observed asking price'
                if not fresh or r['check_error'] or not r['enabled']:summary['reference_old_copies']+=q;basis+=' (stale/failed/paused)'
            offer=bool(ask_ok and fresh and not r['check_error'] and r['enabled'] and r['stock']=='in_stock')
            reason='Fresh ask; quantity not verified' if offer else 'No linked listing' if not linked else 'Currency mismatch' if r['ask_currency'] and r['ask_currency']!=d['currency'] else 'No fresh in-stock offer'
            if reference is not None:
                summary['reference_subtotal']+=reference*q;summary['reference_copies']+=q;summary['missing_reference_subtotal']+=reference*missing;summary['missing_reference_copies']+=missing
            if offer:summary['missing_ask_subtotal']+=r['ask']*missing;summary['missing_ask_copies']+=missing
            lines.append({**r,'missing':missing,'reference':reference,'reference_line':reference*q if reference is not None else None,'reference_basis':basis,'fresh_ask':r['ask'] if offer else None,'missing_ask':r['ask']*missing if offer else None,'offer_status':reason})
        return dict(deck=d,summary=summary,lines=lines,at=clock.isoformat(timespec='seconds'))
    def snapshot(self,deck_id):
        r=self.report(deck_id)
        # Local paths are not required to reproduce price arithmetic.
        evidence=[{k:v for k,v in line.items() if k not in ('image_path','image_url')} for line in r['lines']]
        with self.db.connect() as c:return c.execute('INSERT INTO deck_snapshots(deck_id,at,currency,summary,evidence) VALUES(?,?,?,?,?)',(deck_id,r['at'],r['deck']['currency'],json.dumps(r['summary']),json.dumps(evidence))).lastrowid
    def snapshots(self,deck_id):return self.db.rows('SELECT * FROM deck_snapshots WHERE deck_id=? ORDER BY id DESC LIMIT 500',(deck_id,))
    def csv_export(self,deck_id):
        r=self.report(deck_id);out=io.StringIO(newline='');w=csv.DictWriter(out,fieldnames=CSV_FIELDS);w.writeheader()
        for line in r['lines']:
            v={k:line.get(k,'') for k in CSV_FIELDS};v['reference_price']=f"{line['manual_price']/100:.2f}" if line['manual_price'] is not None else '';v['currency']=r['deck']['currency'];v['watch_url']=line['listing_url'] or ''
            # Escape spreadsheet formulas in text fields. Numeric quantities remain numeric.
            v={k:("'"+value if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r')) else value) for k,value in v.items()};w.writerow(v)
        return out.getvalue()
    def csv_import(self,deck_id,text):
        if len(text.encode('utf-8'))>2*1024*1024:raise ValueError('CSV is too large (2 MB limit).')
        d=self.deck(deck_id);reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')),strict=True)
        if reader.fieldnames and len(set(reader.fieldnames))!=len(reader.fieldnames):raise ValueError('CSV has duplicate column names.')
        if not reader.fieldnames or not {'name','quantity'}<=set(reader.fieldnames):raise ValueError('CSV needs name and quantity columns.')
        rows=[]
        for number,row in enumerate(reader,2):
            if len(rows)>=1000:raise ValueError('Maximum 1,000 imported rows.')
            try:
                if row.get('currency') and row['currency']!=d['currency']:raise ValueError('CSV currency differs from the deck; no conversion is assumed.')
                value={k:row[k] for k in ('name','section','set_code','collector','printing','language','condition','reference_source','reference_checked','image_url','notes') if row.get(k) is not None}
                value.update(quantity=int(row['quantity']),owned=int(row.get('owned') or 0),manual_price=money(row['reference_price']) if row.get('reference_price') else None)
                rows.append(value)
            except (ValueError,TypeError) as e:raise ValueError(f'CSV row {number}: {e}') from None
        # Store-specific watch links are deliberately not trusted/imported from a CSV.
        return self.import_rows(deck_id,rows)
