"""Versioned provider plugins outside the executable. Manifests are read without executing code."""
import importlib.util
import json
from pathlib import Path
import re
import threading
from urllib.parse import urlencode,urlsplit,urlunsplit,parse_qsl
from .sources import Client,APIClient,fetch as builtin_fetch,validate_url
from .core import Observation
from .card_catalogue import search as openrift_search

API_VERSION=1


def get_path(value,path,default=None):
    if not path:return value
    try:
        for key in path.split('.'):
            value=value[int(key)] if isinstance(value,list) else value[key]
        return value
    except (KeyError,IndexError,TypeError,ValueError):return default


def validate_manifest(value):
    if not isinstance(value,dict) or value.get('api_version')!=API_VERSION:raise ValueError('Unsupported plugin API version.')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,63}',str(value.get('id',''))):raise ValueError('Plugin id must use lowercase letters, digits, _ or -.')
    if value['id']=='openrift':raise ValueError('The built-in OpenRift id is reserved.')
    if not isinstance(value.get('name'),str) or not value['name'].strip() or len(value['name'])>100:raise ValueError('Plugin needs a short display name.')
    if value.get('kind') not in ('catalogue-json','python'):raise ValueError('Plugin kind must be catalogue-json or python.')
    games=value.get('games')
    if not isinstance(games,list) or not games or len(games)>40 or any(not isinstance(g,str) or not g or len(g)>80 for g in games):raise ValueError('Plugin needs a list of game names (or *).')
    if value['kind']=='catalogue-json':
        validate_url(value.get('api_url',''))
        fields=value.get('fields')
        if not isinstance(fields,dict) or not {'id','name'}<=fields.keys() or any(not isinstance(v,str) or len(v)>200 for v in fields.values()):raise ValueError('JSON catalogue needs id/name field paths.')
        if not isinstance(value.get('image_suffix',''),str) or len(value.get('image_suffix',''))>200:raise ValueError('Invalid image suffix.')
        if not isinstance(value.get('results_path',''),str):raise ValueError('Invalid results path.')
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_-]{0,39}',value.get('query_parameter','q')):raise ValueError('Invalid query parameter.')
    else:
        if value.get('module','provider.py')!='provider.py':raise ValueError('Python plugins use provider.py in their own folder.')
        caps=value.get('capabilities',[])
        if not isinstance(caps,list) or not caps or any(c not in ('catalogue','store') for c in caps):raise ValueError('Declare catalogue and/or store capabilities.')
        if 'store' in caps:
            hosts=value.get('hosts',[])
            if not isinstance(hosts,list) or not hosts or any(not isinstance(h,str) or not re.fullmatch(r'[a-z0-9.-]+',h) or '.' not in h for h in hosts):raise ValueError('Store plugins declare exact host names.')
    return dict(value)


def json_cards(manifest,query,game,client=None):
    client=client or APIClient();p=urlsplit(manifest['api_url']);params=dict(parse_qsl(p.query));params[manifest.get('query_parameter','q')]=query
    if manifest.get('game_parameter'):params[manifest['game_parameter']]=game
    payload=json.loads(client.get(urlunsplit((p.scheme,p.netloc,p.path,urlencode(params),''))))
    rows=get_path(payload,manifest.get('results_path',''))
    if not isinstance(rows,list):raise ValueError('Plugin results path no longer returns a list.')
    result=[]
    for row in rows[:40]:
        fields={key:get_path(row,path) for key,path in manifest['fields'].items()}
        if fields.get('id') is None or not fields.get('name'):continue
        image=fields.get('image_url') or ''
        if image:image=str(image)+str(manifest.get('image_suffix',''))
        try:image=validate_url(image) if image else ''
        except (ValueError,TypeError):image=''
        result.append(dict(id=str(fields['id']),title=str(fields['name'])[:240],name=str(fields['name'])[:240],image_url=image,
            set_code=str(fields.get('set_code') or ''),collector=str(fields.get('collector') or ''),
            printing=str(fields.get('printing') or 'Other'),language=str(fields.get('language') or 'Other'),
            subtitle=f"{fields.get('set_code') or game} · #{fields.get('collector') or '?'}\n{manifest['name']}",fallback=game.upper(),
            notes=f"Catalogue identity/artwork from {manifest['name']}. Source ID: {fields['id']}. No price imported."))
    return result


class PluginRegistry:
    def __init__(self,directory,db):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True);self.db=db
        self.lock=threading.RLock();self.active=();self.entries=[];self.reload()

    def reload(self):
        entries=[];active=[];seen=set()
        enabled=self.db.setting('enabled_plugins',[])
        for path in sorted(self.directory.glob('*/plugin.json'))[:100]:
            record={'path':str(path),'enabled':False,'error':''}
            try:
                if path.stat().st_size>64000:raise ValueError('Manifest exceeds 64 KB.')
                m=validate_manifest(json.loads(path.read_text(encoding='utf-8')));record.update(m)
                if m['id'] in seen:raise ValueError('Duplicate plugin id.')
                seen.add(m['id']);record['enabled']=m['id'] in enabled
                provider=None
                if record['enabled'] and m['kind']=='python':
                    file=path.parent/'provider.py'
                    if not file.is_file() or file.resolve().parent!=path.parent.resolve():raise ValueError('Missing provider.py inside plugin folder.')
                    spec=importlib.util.spec_from_file_location('tcg_provider_'+m['id'],file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                    data=path.parent/'data';data.mkdir(exist_ok=True)
                    provider=module.create_plugin(dict(api_version=API_VERSION,data_dir=str(data)))
                    for capability,method in (('catalogue','search_cards'),('store','fetch_product')):
                        if capability in m['capabilities'] and not callable(getattr(provider,method,None)):raise ValueError('Plugin is missing '+method)
                if record['enabled']:active.append((m,provider))
            except Exception as e:record['error']=str(e)[:350];record['enabled']=False
            entries.append(record)
        with self.lock:self.entries=entries;self.active=tuple(active)

    def enable(self,plugin_id,enabled):
        ids=set(self.db.setting('enabled_plugins',[]))
        if enabled:ids.add(plugin_id)
        else:ids.discard(plugin_id)
        self.db.set_setting('enabled_plugins',sorted(ids));self.reload()

    def games(self):return sorted({g for m,_ in self.active for g in m['games'] if g!='*'})

    def providers(self,game):
        providers=[dict(id='openrift',name='OpenRift (community catalogue)')] if game=='Riftbound' else []
        for m,_ in self.active:
            if (game in m['games'] or '*' in m['games']) and (m['kind']=='catalogue-json' or 'catalogue' in m.get('capabilities',[])):
                providers.append(dict(id=m['id'],name=m['name']))
        return providers

    def search(self,provider_id,game,query):
        if not 2<=len(query.strip())<=100:raise ValueError('Search needs 2–100 characters.')
        if provider_id=='openrift':
            if game!='Riftbound':raise ValueError('OpenRift only supports Riftbound.')
            return openrift_search(query)
        for m,provider in self.active:
            if m['id']==provider_id and (game in m['games'] or '*' in m['games']):
                rows=json_cards(m,query,game) if m['kind']=='catalogue-json' else provider.search_cards(game,query,APIClient())
                if not isinstance(rows,list):raise ValueError('Plugin must return a list of card candidates.')
                # External code candidates pass through the same canonical sanitization as JSON providers.
                if m['kind']=='python':
                    mapping={k:k for k in ('id','name','image_url','set_code','collector','printing','language')}
                    fake=type('Payload',(),{'get':lambda self,url:json.dumps(rows[:40])})()
                    return json_cards(dict(m,api_url='https://plugin.invalid/',fields=mapping,results_path=''),query,game,fake)
                return rows
        raise ValueError('Catalogue plugin is unavailable or disabled. Reload plugins and search again.')

    def fetch(self,url,client):
        host=urlsplit(validate_url(url)).hostname
        for m,provider in self.active:
            if m['kind']=='python' and 'store' in m.get('capabilities',[]) and host in m['hosts']:
                result=provider.fetch_product(url,client)
                if result is None:continue
                if not isinstance(result,Observation):raise ValueError('Store plugin must return an Observation or None.')
                return Observation(result.title,result.price,result.currency,result.stock,m['name']+' · '+result.source,result.variant)
        return builtin_fetch(url,client)
