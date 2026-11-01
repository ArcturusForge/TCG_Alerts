"""User-selected OpenRift card search; catalogue artwork is never a price quote."""
import json
from urllib.parse import urlencode
from .sources import APIClient,validate_url

PROVIDER='OpenRift (community catalogue)'
DOCS='https://openrift.app/developers'


def normalize_openrift(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('printingIds'),list) or not isinstance(payload.get('printings'),dict) or not isinstance(payload.get('cards'),dict):
        raise ValueError('Catalogue response changed; local images and artwork URLs still work.')
    sets={s['id']:s for s in payload.get('sets',[]) if isinstance(s,dict) and 'id' in s}
    results=[]
    for printing_id in payload['printingIds'][:40]:
        p=payload['printings'].get(printing_id,{})
        card=payload['cards'].get(p.get('cardId'),{})
        if not card.get('name'):continue
        images=p.get('images') or [];image_id=images[0].get('imageId') if images and isinstance(images[0],dict) else None
        # imageId is an opaque path component, never an arbitrary provider URL.
        from urllib.parse import quote
        image_url='https://openrift.app/media/cards/'+quote(str(image_id),safe='')+'-400w.webp' if image_id else ''
        short=p.get('shortCode','');edition=sets.get(p.get('setId'),{})
        variant='Alternate art' if p.get('artVariant') not in (None,'normal') else 'Foil' if p.get('finish')=='foil' else 'Standard'
        language={'EN':'English','FR':'French','SC':'Chinese'}.get(p.get('language'),'Other')
        results.append(dict(id=str(printing_id),name=card['name'],title=card['name'],set_code=edition.get('slug',short.split('-')[0]),
            collector=short.split('-',1)[1] if '-' in short else '',printing=variant,language=language,image_url=image_url,
            subtitle=f"{p.get('publicCode',short)} · {variant}\n{', '.join(card.get('types',[]))} · Energy {card.get('energy') if card.get('energy') is not None else '—'}",
            fallback='RIFTBOUND',notes=f"Artwork/identity chosen from {PROVIDER}. Printing ID: {printing_id}. No price imported."))
    return results


def search(name,client=None):
    name=name.strip()
    if not 2<=len(name)<=100:raise ValueError('Enter 2–100 characters to search by card name.')
    client=client or APIClient()
    from urllib.error import HTTPError
    try:return normalize_openrift(json.loads(client.get('https://openrift.app/api/v1/search?'+urlencode(dict(q=name,limit=40)))))
    except HTTPError as e:
        if e.code==404:return []
        raise
