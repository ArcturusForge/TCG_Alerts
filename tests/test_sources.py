import json
import unittest
from urllib.error import HTTPError
from tcg_alerts.sources import shopify, jsonld, fetch, validate_url


class ParserTests(unittest.TestCase):
    def product(self):
        return {'title': 'Box', 'variants': [{'id': 1, 'title': 'Default Title', 'price': 21999, 'available': False}]}

    def test_shopify_cents_and_stock(self):
        o = shopify(self.product(), 'AUD')
        self.assertEqual(o.price, 21999)
        self.assertEqual(o.stock, 'out_of_stock')

    def test_no_cheapest_variant_guess(self):
        p = self.product()
        p['variants'].append({'id': 2, 'title': 'Case', 'price': 120000, 'available': True})
        with self.assertRaisesRegex(ValueError, 'VARIANT'):
            shopify(p, 'AUD')
        self.assertEqual(shopify(p, 'AUD', '2').price, 120000)
        with self.assertRaisesRegex(ValueError, 'VARIANT'):
            shopify(p, 'AUD', '99')

    def test_currency_required_and_integer_cents(self):
        with self.assertRaisesRegex(ValueError, 'CURRENCY'):
            shopify(self.product(), '')
        p = self.product()
        p['variants'][0]['price'] = '219.99'
        with self.assertRaisesRegex(ValueError, 'PRICE'):
            shopify(p, 'AUD')

    def test_preorder(self):
        p = self.product()
        p['title'] = 'PRE-ORDER Box'
        p['variants'][0]['available'] = True
        self.assertEqual(shopify(p, 'AUD').stock, 'preorder')

    def markup(self, offer=None):
        p = {'@type': 'Product', 'name': 'Booster Box', 'offers': offer or {'@type': 'Offer', 'price': '200.50', 'priceCurrency': 'AUD', 'availability': 'https://schema.org/InStock'}}
        return '<script type="application/ld+json">' + json.dumps({'@graph': [p]}) + '</script>'

    def test_graph_jsonld(self):
        o = jsonld(self.markup())
        self.assertEqual(o.price, 20050)
        self.assertEqual(o.stock, 'in_stock')

    def test_unknown_availability_not_guessed(self):
        text = self.markup().replace('InStock', 'LimitedAvailability')
        self.assertEqual(jsonld(text).stock, 'unknown')

    def test_aggregate_rejected(self):
        with self.assertRaisesRegex(ValueError, 'VARIANT'):
            jsonld(self.markup({'@type': 'AggregateOffer', 'lowPrice': '1', 'highPrice': '100'}))

    def test_product_currency_and_variant_fetch(self):
        calls = []
        p = self.product()
        class Fake:
            def get(self, url):
                calls.append(url)
                return json.dumps({'currency': 'AUD'} if url.endswith('/cart.js') else p)
        o = fetch('https://store.example/en/products/box?variant=1', Fake())
        self.assertEqual(o.currency, 'AUD')
        self.assertEqual(calls, ['https://store.example/en/products/box.js', 'https://store.example/en/cart.js'])

    def test_404_fallback_but_rate_limit_not_bypassed(self):
        text = self.markup()
        class Fake:
            def __init__(self, code):
                self.code = code
            def get(self, url):
                if url.endswith('.js'):
                    raise HTTPError(url, self.code, 'fixture', {}, None)
                return text
        self.assertEqual(fetch('https://store.example/products/box', Fake(404)).price, 20050)
        with self.assertRaises(HTTPError):
            fetch('https://store.example/products/box', Fake(429))

    def test_url(self):
        self.assertEqual(validate_url('https://STORE.example/products/box#top'), 'https://store.example/products/box')
        for url in ['http://store.example', 'file:///tmp/test', 'https://user:pass@store.example', 'https://store.example:8080']:
            with self.assertRaises(ValueError):
                validate_url(url)


class DiscoveryTests(unittest.TestCase):
    def test_links_are_same_store_unique_and_collection_prefix_removed(self):
        from tcg_alerts.sources import discover
        class Fake:
            def get(self, url):
                return '''<a href="/collections/riftbound/products/box?x=1">Box</a>
                <a href="/products/box">Box again</a>
                <a href="https://other.example/products/fake">Other</a>
                <a href="/pages/about">About</a>'''
        result = discover('https://store.example/collections/riftbound', Fake())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'https://store.example/products/box')


class NetworkPolicyTests(unittest.TestCase):
    def test_disallowed_path_not_fetched(self):
        from tcg_alerts.sources import Client
        c = Client(spacing=0)
        calls = []
        def raw(url):
            calls.append(url)
            return 'User-agent: *\nDisallow: /products/'
        c.raw = raw
        with self.assertRaisesRegex(ValueError, 'ROBOTS'):
            c.get('https://store.example/products/box')
        self.assertEqual(calls, ['https://store.example/robots.txt'])

    def test_robots_failure_stops_product_request(self):
        from tcg_alerts.sources import Client
        c = Client(spacing=0)
        calls = []
        def raw(url):
            calls.append(url)
            raise HTTPError(url, 503, 'offline', {}, None)
        c.raw = raw
        with self.assertRaisesRegex(ValueError, 'ROBOTS'):
            c.get('https://store.example/products/box')
        self.assertEqual(len(calls), 1)

    def test_404_robots_allows_and_caches(self):
        from tcg_alerts.sources import Client
        c = Client(spacing=0)
        calls = []
        def raw(url):
            calls.append(url)
            if url.endswith('robots.txt'):
                raise HTTPError(url, 404, 'missing', {}, None)
            return 'ok'
        c.raw = raw
        self.assertEqual(c.get('https://store.example/a'), 'ok')
        self.assertEqual(c.get('https://store.example/b'), 'ok')
        self.assertEqual(len(calls), 3)

    def test_rate_limit_cooldown_honors_retry_after(self):
        from tcg_alerts.sources import Client
        import time
        c = Client(spacing=0)
        class Opener:
            def open(self, req, timeout):
                raise HTTPError(req.full_url, 429, 'slow', {'Retry-After': '7200'}, None)
        c.opener = Opener()
        with self.assertRaises(HTTPError):
            c.raw('https://store.example/products/box')
        self.assertGreater(c.cooldowns['store.example'], time.monotonic() + 7100)
        with self.assertRaisesRegex(ValueError, 'RATE_LIMIT'):
            c.raw('https://store.example/products/other')
