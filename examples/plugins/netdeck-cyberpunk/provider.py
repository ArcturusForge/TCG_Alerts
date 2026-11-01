"""Exact-name lookup used by NetDeck's public embed SDK; not fuzzy catalogue browsing."""
import json
from urllib import request
from tcg_alerts.sources import LIMIT,validate_url


class Provider:
    def search_cards(self,game,query,client):
        body=json.dumps(dict(cards=[dict(name=query,game='cyberpunk')],defaultGame='cyberpunk')).encode()
        req=request.Request('https://api.netdeck.gg/api/cards/lookup',data=body,headers={'User-Agent':'TCGAlerts/0.6 (+personal card catalogue)','Content-Type':'application/json'})
        with request.urlopen(req,timeout=15) as response:
            data=response.read(LIMIT+1)
            if len(data)>LIMIT:raise ValueError('Card lookup response exceeded limit.')
        payload=json.loads(data);rows=[]
        for result in payload.get('results',[])[:40]:
            card=result.get('card') or {}
            if result.get('status')!='found' or not card.get('id') or not card.get('name'):continue
            rows.append(dict(id=card['id'],name=card['name'],image_url=validate_url(card['image_url']) if card.get('image_url') else '',collector=str(card.get('print_number') or ''),printing='Other',language='Other'))
        return rows


def create_plugin(context):return Provider()
