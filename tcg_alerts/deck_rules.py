"""Deck construction checks. Riftbound is built in; other games report nothing.

Riftbound (Core Rules): main deck 40 cards including the Chosen Champion,
12 runes, 3 unique battlefields, 1 Champion Legend, at most 3 copies of a
card across main deck and sideboard, and a sideboard of up to 10 cards for
best-of-three. Check the current tournament rules before an event.
"""
from collections import Counter

RIFTBOUND = dict(main=40, runes=12, battlefields=3, legend=1, champion=1, copies=3, sideboard_max=10)


def check(game, entries):
    """[(level, message)] where level is 'error' or 'ok'. entries need name, section, quantity."""
    if game != 'Riftbound':
        return []
    r = RIFTBOUND
    by = Counter()
    for e in entries:
        by[e['section']] += e['quantity']
    problems = []
    main = by['Main'] + by['Champion']  # the Chosen Champion counts toward the 40
    if main != r['main']:
        problems.append(f"Main deck has {main} cards (with Champion); it needs exactly {r['main']}.")
    if by['Champion'] != r['champion']:
        problems.append(f"Choose exactly one Chosen Champion (found {by['Champion']}).")
    if by['Legend'] != r['legend']:
        problems.append(f"Choose exactly one Champion Legend (found {by['Legend']}).")
    if by['Runes'] != r['runes']:
        problems.append(f"Rune deck has {by['Runes']} cards; it needs exactly {r['runes']}.")
    fields = [e for e in entries if e['section'] == 'Battlefields']
    if by['Battlefields'] != r['battlefields'] or any(e['quantity'] > 1 for e in fields):
        problems.append(f"Bring {r['battlefields']} different battlefields (found {by['Battlefields']}).")
    if by['Sideboard'] > r['sideboard_max']:
        problems.append(f"Sideboard has {by['Sideboard']} cards; the maximum is {r['sideboard_max']}.")
    copies = Counter()
    for e in entries:
        if e['section'] in ('Main', 'Champion', 'Sideboard'):
            copies[e['name'].strip().casefold()] += e['quantity']
    names = {e['name'].strip().casefold(): e['name'] for e in entries}
    for key, n in sorted(copies.items()):
        if n > r['copies']:
            problems.append(f"{names[key]}: {n} copies across main deck and sideboard; the limit is {r['copies']}.")
    return [('error', p) for p in problems] or [('ok', 'Deck meets Riftbound construction rules.')]
