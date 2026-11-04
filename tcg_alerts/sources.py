"""Conservative public storefront adapters; no login or cart writes; optional browser rendering for public pages."""
from __future__ import annotations
from .tls import https_handler
import http.cookiejar
import json
import re
import time
from html.parser import HTMLParser
from urllib import request, parse, robotparser, error
from .core import Observation, money

AGENT = 'TCGAlerts/0.6 (+https://github.com/ArcturusForge/TCG_Alerts)'
LIMIT = 4 * 1024 * 1024


def validate_url(url):
    p = parse.urlsplit(url.strip())
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('URL: Enter an HTTPS product URL without credentials or a custom port.')
    return parse.urlunsplit((p.scheme, p.netloc.lower(), p.path or '/', p.query, ''))


class SameOrigin(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if parse.urlsplit(req.full_url).netloc != parse.urlsplit(newurl).netloc or parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('REDIRECT: Cross-store redirects need a new watch URL.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, spacing=2.0, browser_helper=None):
        self.opener = request.build_opener(https_handler(), SameOrigin(), request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.robots = {}
        self.last = {}
        self.spacing = spacing
        self.cooldowns = {}
        self.browser_helper = browser_helper

    def raw(self, url):
        host = parse.urlsplit(url).netloc
        if self.cooldowns.get(host, 0) > time.monotonic():
            raise ValueError('RATE_LIMIT: Store is cooling down after a failed request.')
        delay = self.spacing - (time.monotonic() - self.last.get(host, 0))
        if delay > 0:
            time.sleep(delay)
        self.last[host] = time.monotonic()
        accept = 'application/json' if parse.urlsplit(url).path.endswith(('.js', '.json')) else 'text/html,application/xhtml+xml,text/plain;q=0.8'
        req = request.Request(url, headers={'User-Agent': AGENT, 'Accept': accept})
        try:
            response = self.opener.open(req, timeout=15)
        except error.HTTPError as e:
            if e.code in (429, 503):
                retry = e.headers.get('Retry-After', '') if e.headers else ''
                try:
                    from email.utils import parsedate_to_datetime
                    seconds = int(retry) if retry.isdigit() else parsedate_to_datetime(retry).timestamp() - time.time()
                except (ValueError, TypeError, OverflowError):
                    seconds = 1800
                self.cooldowns[host] = time.monotonic() + max(300, seconds)
            raise
        with response as r:
            content = r.read(LIMIT + 1)
            if len(content) > LIMIT:
                raise ValueError('SIZE: Store response exceeded 4 MB.')
            return content.decode('utf-8-sig')

    def get(self, url):
        p = parse.urlsplit(validate_url(url))
        origin = f'{p.scheme}://{p.netloc}'
        cached = self.robots.get(origin)
        if cached is None or time.monotonic() - cached[0] > 3600:
            rp = robotparser.RobotFileParser(origin + '/robots.txt')
            try:
                rp.parse(self.raw(origin + '/robots.txt').splitlines())
            except error.HTTPError as e:
                if e.code in (404, 410):
                    rp.parse([])
                else:
                    raise ValueError(f'ROBOTS: Cannot verify crawl permission (HTTP {e.code}).') from e
            self.robots[origin] = (time.monotonic(), rp)
        rp = self.robots[origin][1]
        if not rp.can_fetch(AGENT, url):
            raise ValueError('ROBOTS: Store disallows automated access to this path.')
        crawl_delay = rp.crawl_delay(AGENT)
        if crawl_delay:
            delay = crawl_delay - (time.monotonic() - self.last.get(p.netloc, 0))
            if delay > 0:
                time.sleep(min(delay, 120))
            if delay > 120:
                raise ValueError('ROBOTS: Crawl delay too long for an interactive check.')
        try:
            text=self.raw(url)
        except error.HTTPError as e:
            if e.code==403 and self.browser_helper:return self.browser_helper.solve(url)
            raise
        if self.browser_helper:
            from .browser_helper import challenge
            if challenge(text):return self.browser_helper.solve(url)
        return text


class APIClient(Client):
    """Documented machine APIs use their API contract rather than HTML crawler rules."""
    def get(self,url):
        return self.raw(validate_url(url))


class StructuredData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.parts = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type', '').lower() == 'application/ld+json':
            self.capture = True
            self.parts = []

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.capture:
            self.capture = False
            try:
                self.documents.append(json.loads(''.join(self.parts)))
            except ValueError:
                pass


def nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from nodes(item)
    elif isinstance(value, dict):
        yield value
        for key in ('@graph', 'mainEntity'):
            if key in value:
                yield from nodes(value[key])


def jsonld(text):
    parser = StructuredData()
    parser.feed(text)
    products = []
    for node in nodes(parser.documents):
        types = node.get('@type', [])
        if isinstance(types, str):
            types = [types]
        if 'Product' in types:
            products.append(node)
    if len(products) != 1:
        raise ValueError('PARSE: Expected one Product in JSON-LD; use an exact product page.')
    p = products[0]
    offers = p.get('offers', [])
    if isinstance(offers, dict):
        offers = [offers]
    if len(offers) != 1 or offers[0].get('@type') == 'AggregateOffer':
        raise ValueError('VARIANT: Multiple or aggregated offers cannot safely identify one price.')
    offer = offers[0]
    availability = str(offer.get('availability', '')).rsplit('/', 1)[-1]
    stock = {'InStock': 'in_stock', 'OutOfStock': 'out_of_stock', 'SoldOut': 'out_of_stock',
             'PreOrder': 'preorder', 'PreSale': 'preorder'}.get(availability, 'unknown')
    return Observation(str(p.get('name', '')), money(offer.get('price')), str(offer.get('priceCurrency', '')), stock, 'JSON-LD')


def shopify(product, currency, variant_id=None):
    variants = product.get('variants', [])
    if variant_id:
        variants = [v for v in variants if str(v.get('id')) == variant_id]
    if len(variants) != 1:
        choices = ', '.join(f"{v.get('title')}: ?variant={v.get('id')}" for v in variants[:8])
        raise ValueError('VARIANT: Choose an exact variant in the store URL. ' + choices)
    v = variants[0]
    price = v.get('price')
    if not isinstance(price, int) or isinstance(price, bool):
        raise ValueError('PRICE: Shopify price is not integer minor units.')
    available = v.get('available')
    stock = 'in_stock' if available is True else 'out_of_stock' if available is False else 'unknown'
    title = str(product.get('title', ''))
    variant = str(v.get('title', ''))
    if variant and variant != 'Default Title':
        title += ' / ' + variant
    # A purchasable preorder is not the same as physical stock. Conservatively suppress alerts.
    if re.search(r'pre[\s-]?order|pre[\s-]?sale', title, re.I) and stock == 'in_stock':
        stock = 'preorder'
    return Observation(title, price, currency, stock, 'Shopify Ajax', str(v.get('id', '')))


def fetch(url, client):
    p = parse.urlsplit(url)
    match = re.search(r'^(.*?/)?products/([^/]+?)(?:\.js)?/?$', p.path.lstrip('/'))
    if match:
        # Product paths are characteristic but not proof of Shopify. A 404 can fall back to JSON-LD.
        base,cart_url=product_endpoints(url)
        try:
            product = json.loads(client.get(base+'.js'))
        except error.HTTPError as e:
            if e.code != 404:
                raise
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(product, dict) and 'variants' in product:
                cart=json.loads(client.get(cart_url))
                currency = cart.get('currency', '')
                variant_id = parse.parse_qs(p.query).get('variant', [None])[0]
                return shopify(product, currency, variant_id)
    return jsonld(client.get(url))


class ProductLinks(HTMLParser):
    """One page of Shopify-style product links; no whole-store crawling."""
    def __init__(self, page_url):
        super().__init__()
        self.page_url = page_url
        self.links = {}
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href', '')
        u = parse.urlsplit(parse.urljoin(self.page_url, href))
        if u.netloc != parse.urlsplit(self.page_url).netloc or u.scheme != 'https':
            return
        match = re.search(r'/(?:collections/[^/]+/)?products/([^/]+)/?$', u.path)
        if not match:
            return
        # Keep locale but remove collection prefixes and tracking query parameters.
        prefix = u.path.split('/collections/', 1)[0] if '/collections/' in u.path else u.path.split('/products/', 1)[0]
        url = f'https://{u.netloc}{prefix}/products/{match.group(1)}'
        self.current = url
        self.links.setdefault(url, '')

    def handle_data(self, text):
        if self.current:
            self.links[self.current] += ' ' + text.strip()

    def handle_endtag(self, tag):
        if tag == 'a':
            self.current = None


def discover(url, client):
    url = validate_url(url)
    parser = ProductLinks(url)
    parser.feed(client.get(url))
    return [(u, ' '.join(title.split()) or parse.unquote(u.rsplit('/', 1)[-1])) for u, title in list(parser.links.items())[:100]]


def product_endpoints(url):
    p=parse.urlsplit(validate_url(url));parts=p.path.strip('/').split('/');pos=len(parts)-2
    if pos<0 or parts[pos]!='products':raise ValueError('Paste an exact Shopify product URL.')
    before=parts[:pos]
    if 'collections' in before:before=before[:before.index('collections')]
    locale='/'+('/'.join(before)) if before else ''
    base='https://'+p.netloc+locale
    return base+'/products/'+parts[-1].removesuffix('.js'),base+'/cart.js'


def variant_options(url,client):
    base,cart=product_endpoints(url)
    product=json.loads(client.get(base+'.js'));currency=json.loads(client.get(cart)).get('currency','')
    options=[]
    for v in product.get('variants',[]):
        o=shopify(product,currency,str(v['id']))
        query=[(k,value) for k,value in parse.parse_qsl(parse.urlsplit(url).query) if k!='variant']+[('variant',str(v['id']))]
        options.append(dict(title=o.title,price=o.price,currency=o.currency,stock=o.stock,id=str(v['id']),url=base+'?'+parse.urlencode(query)))
    if not options:raise ValueError('No recognizable Shopify variants. Use the store’s exact product URL directly.')
    return options
