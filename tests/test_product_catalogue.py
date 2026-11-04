import json, tempfile, unittest
from pathlib import Path
from tcg_alerts.core import Database
from tcg_alerts import product_catalogue as pc


def page(n):
    return {'products': [{'id': i, 'handle': f'p{i}', 'title': f'Riftbound Origins Booster Box {i}', 'vendor': 'Riot', 'product_type': 'Sealed',
                          'tags': ['TCG'], 'images': [{'src': 'https://x/i.png'}],
                          'variants': [{'id': 1000 + i, 'title': 'Default Title', 'price': '199.95', 'available': i % 2 == 0}]} for i in range(n)]}


class FakeClient:
    def __init__(self, pages): self.pages, self.urls = pages, []
    def get(self, url):
        self.urls.append(url)
        n = int(url.rsplit('page=', 1)[1])
        return json.dumps(self.pages[n - 1] if n <= len(self.pages) else {'products': []})


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / 'a.sqlite3')

    def tearDown(self): self.tmp.cleanup()

    def test_sync_paginates_and_search(self):
        client = FakeClient([page(250), page(3)])
        self.assertEqual(pc.sync_store(self.db, client, 'Shop', 'https://shop.example'), 253)
        self.assertEqual(len(client.urls), 2)
        rows = pc.search(self.db, 'booster box', game='Riftbound', in_stock_only=True)
        self.assertTrue(rows and all(r['available'] == 1 for r in rows))
        self.assertEqual(rows[0]['price'], 19995)
        self.assertIn('?variant=', rows[0]['url'])

    def test_resync_replaces_and_failure_recorded(self):
        pc.sync_store(self.db, FakeClient([page(5)]), 'Shop', 'https://shop.example')
        pc.sync_store(self.db, FakeClient([page(2)]), 'Shop', 'https://shop.example')
        self.assertEqual(len(pc.search(self.db)), 2)
        class Broken:
            def get(self, url): raise ValueError('ROBOTS: no')
        self.assertIn('failed', pc.sync_all(self.db, Broken(), [('Bad', 'https://bad.example')])['Bad'])
        self.assertIn('ROBOTS', [s for s in pc.sync_status(self.db) if s['store'] == 'Bad'][0]['error'])

    def test_infer_game(self):
        self.assertEqual(pc.infer_game('Pokemon Scarlet ETB'), 'Pokémon')
        self.assertEqual(pc.infer_game('Plain dice'), 'Unspecified')


if __name__ == '__main__':
    unittest.main()
