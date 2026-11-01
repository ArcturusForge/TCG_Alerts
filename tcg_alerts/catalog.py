"""Explicit catalog tags. Store location is independent of currency or delivery area."""
GAMES = ('Unspecified', 'Riftbound', 'Cyberpunk', 'Pokémon', 'Magic: The Gathering', 'One Piece', 'Gundam', 'Flesh and Blood', 'Lorcana', 'Yu-Gi-Oh!', 'Other')
COUNTRIES = ('Unspecified', 'Australia', 'New Zealand', 'United States', 'Canada', 'United Kingdom', 'Other')
AU_STATES = ('Victoria', 'New South Wales', 'Queensland', 'South Australia', 'Western Australia', 'Tasmania', 'Australian Capital Territory', 'Northern Territory')


def metadata(game='Unspecified', country='Unspecified', state='Unspecified'):
    game = game.strip() or 'Unspecified'
    country = country.strip() or 'Unspecified'
    state = state.strip() or 'Unspecified'
    if any(len(v) > 80 for v in (game, country, state)):
        raise ValueError('Keep catalog tags under 80 characters.')
    aliases = {'au': 'Australia', 'aus': 'Australia', 'us': 'United States', 'usa': 'United States', 'nz': 'New Zealand', 'uk': 'United Kingdom'}
    country = aliases.get(country.lower(), next((c for c in COUNTRIES if c.lower() == country.lower()), country))
    states = dict(zip(('vic', 'nsw', 'qld', 'sa', 'wa', 'tas', 'act', 'nt'), AU_STATES))
    state = states.get(state.lower(), next((s for s in AU_STATES if s.lower() == state.lower()), state))
    if state in AU_STATES and country != 'Australia':
        raise ValueError('An Australian state requires country Australia.')
    game = next((g for g in GAMES if g.casefold() == game.casefold()), game)
    return game, country, state


def matches(watch, game='All games', country='All countries', state='All states'):
    return (game == 'All games' or watch.get('game', 'Unspecified') == game) and (country == 'All countries' or watch.get('country', 'Unspecified') == country) and (state == 'All states' or watch.get('state', 'Unspecified') == state)
