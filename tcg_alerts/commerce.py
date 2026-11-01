"""One-unit delivery estimates. Money is in minor units; unknown stays unknown."""
from decimal import Decimal
from urllib.parse import urlsplit


def domain(url):
    return (urlsplit(url).hostname or '').lower().removeprefix('www.')


def postcode(value, country='Australia'):
    value=value.strip().upper()
    if country=='Australia' and value and (len(value)!=4 or not value.isdigit()):
        raise ValueError('Australian postcodes need four digits, including leading zeroes.')
    if len(value)>16:raise ValueError('Postcode is too long.')
    return value


def validate_delivery(fields):
    values=dict(fields)
    if 'pack_count' in values and values['pack_count'] is not None:
        p=values['pack_count']
        if not isinstance(p,int) or isinstance(p,bool) or not 1<=p<=100000:
            raise ValueError('Pack count must be a positive whole number.')
    if values.get('pickup','Unspecified') not in ('Unspecified','Yes','No'):
        raise ValueError('Invalid pickup option.')
    if 'shipping_postcode' in values:
        values['shipping_postcode']=postcode(values['shipping_postcode'],values.get('shipping_country','Australia'))
    return values


def quote(watch, rules=(), country='Australia', destination='', mode='Delivery', store=None):
    destination=postcode(destination,country)
    shipping=None;basis='Shipping unknown for this destination';source=''
    price=watch.get('price')
    if price is None:return dict(shipping=None,total=None,per_pack=None,basis='No observed item price',source='')
    if mode=='Pickup':
        pickup=watch.get('pickup','Unspecified')
        if pickup=='Unspecified' and store:pickup=store.get('pickup','Unspecified')
        if pickup=='Yes':shipping,basis,source=0,'Pickup estimate; confirm item eligibility/readiness',(store or {}).get('source_url','')
        else:basis='Pickup not confirmed' if pickup!='No' else 'Pickup unavailable'
    elif mode=='Delivery':
        if watch.get('shipping') is not None and watch.get('shipping_postcode','')==destination and watch.get('shipping_country','Australia')==country:
            shipping,basis,source=watch['shipping'],'User-entered listing quote',watch.get('url','')
        else:
            candidates=[r for r in rules if r['store_id']==watch.get('store_id') and r['country']==country and r['currency']==watch.get('currency') and r['postcode'] in ('',destination)]
            exact=[r for r in candidates if destination and r['postcode']==destination]
            selected=exact or [r for r in candidates if not r['postcode']]
            if len(selected)==1:
                r=selected[0];shipping=0 if r['free_over'] is not None and price>=r['free_over'] else r['flat']
                basis,source='Store rule estimate • entered '+r['checked'],r['source_url']
            elif len(selected)>1:basis='Conflicting rules; no estimate applied'
    else:raise ValueError('Choose Delivery or Pickup.')
    total=price+shipping if shipping is not None else None
    packs=watch.get('pack_count')
    return dict(shipping=shipping,total=total,per_pack=Decimal(total)/packs if total is not None and packs else None,basis=basis,source=source)
