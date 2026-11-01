"""Observed listing metrics and local activity, never estimated retailer traffic."""
from collections import defaultdict
from datetime import datetime, timezone, timedelta


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def report(db, watch_ids, watch_id=None, days=30, clock=None):
    if days not in (7, 30, 90):
        raise ValueError('Choose a 7, 30 or 90 day window.')
    clock = clock or datetime.now(timezone.utc)
    since = clock - timedelta(days=days)
    ids = set(watch_ids)
    # SQL scope prevents pulling unrelated watches; cap is explicit in UI/evidence.
    if not ids:
        return {'prices': [], 'activity': [], 'daily': [], 'since': since, 'until': clock, 'capped': False}
    placeholders = ','.join('?' for _ in ids)
    args = tuple(sorted(ids))
    events = db.rows(f'SELECT * FROM activity WHERE watch_id IN ({placeholders}) AND at>=? AND at<=? ORDER BY at DESC,id DESC LIMIT 10001', (*args, since.isoformat(), clock.isoformat()))
    prices = []
    if watch_id in ids:
        prices = db.rows('SELECT * FROM observations WHERE watch_id=? AND at>=? AND at<=? ORDER BY at DESC,id DESC LIMIT 10001', (watch_id, since.isoformat(), clock.isoformat()))
    capped = len(events) > 10000 or len(prices) > 10000
    events, prices = events[:10000], prices[:10000]
    buckets = defaultdict(lambda: {'check_ok': 0, 'check_failed': 0, 'store_open': 0})
    for event in events:
        key = timestamp(event['at']).date().isoformat()
        if event['kind'] in buckets[key]:
            buckets[key][event['kind']] += 1
    # Include partial first/last UTC calendar days and zero-activity days explicitly.
    daily = []
    day = since.date()
    while day <= clock.date():
        key = day.isoformat()
        daily.append({'day': key, **buckets[key]})
        day += timedelta(days=1)
    return {'prices': list(reversed(prices)), 'activity': events, 'daily': daily, 'since': since, 'until': clock, 'capped': capped}
