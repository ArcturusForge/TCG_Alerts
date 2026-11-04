"""Calendar entries detected from news text, plus release reminders.

Only dates the publisher states in words ("launches worldwide on October 23,
2026") become entries. Publication dates are never used. Detected entries are
marked Tentative with the article as their source, and they never overwrite
an entry you edited.
"""
from __future__ import annotations
import hashlib
import re
from datetime import date, timedelta

MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
PATTERN = re.compile(
    r'\b(launch(?:es|ing)?|releas(?:es|ing|ed)|arriv(?:es|ing)|available|prerelease[s]?)\b[^.!?]{0,60}?\b'
    r'(' + '|'.join(m[:3] for m in MONTHS) + r')[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)', re.I)
REMIND_DAYS = (7, 1, 0)


def detect(text):
    """[(iso_date, kind)] for each explicit release date phrase in text."""
    found = []
    for m in PATTERN.finditer(text or ''):
        month = [x[:3] for x in MONTHS].index(m[2].lower()[:3]) + 1
        try:
            day = date(int(m[4]), month, int(m[3]))
        except ValueError:
            continue
        kind = 'Prerelease' if 'prerelease' in m[0].lower() else 'Release'
        found.append((day.isoformat(), kind))
    return list(dict.fromkeys(found))


def ingest(db, game, items, today=None):
    """Add Tentative calendar rows for dates stated in news items. Returns rows added."""
    today = today or date.today()
    added = 0
    with db.connect() as c:
        for it in items:
            for day, kind in detect(it.get('title', '') + '. ' + it.get('blurb', '')):
                if day < (today - timedelta(days=30)).isoformat():
                    continue
                key = 'auto:' + hashlib.sha1(f"{it['url']}|{day}".encode()).hexdigest()[:16]
                cur = c.execute('''INSERT OR IGNORE INTO releases(seed_key,title,game,kind,start,end,precision,window,region,status,source_url,checked,notes)
                                   VALUES(?,?,?,?,?,?,'Day','','Global / unspecified','Tentative',?,?,?)''',
                                (key, it['title'][:200], game, kind, day, day, it['url'], today.isoformat(),
                                 'Detected automatically from publisher news text. Check the article and local store availability.'))
                added += cur.rowcount
    return added


def due_reminders(db, today=None):
    """Messages for releases 7 days, 1 day and 0 days away. Each fires once."""
    today = today or date.today()
    sent = set(db.setting('release_reminders_sent', []))
    messages = []
    for r in db.releases():
        if r['status'] == 'Cancelled' or r['precision'] not in ('Day', 'Range') or not r['start']:
            continue
        days = (date.fromisoformat(r['start']) - today).days
        if days not in REMIND_DAYS:
            continue
        key = f"{r['id']}:{r['start']}:{days}"
        if key in sent:
            continue
        sent.add(key)
        when = 'today' if days == 0 else 'tomorrow' if days == 1 else f'in {days} days ({r["start"]})'
        messages.append(f"{r['game']}: {r['title']} — {r['kind'].lower()} {when}.")
    if messages:
        db.set_setting('release_reminders_sent', sorted(sent)[-500:])
    return messages
