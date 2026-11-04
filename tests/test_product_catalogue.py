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


class DueTests(CatalogueTests):
    def test_due_rules(self):
        import time
        stores = [('Shop', 'https://shop.example')]
        self.assertEqual(pc.due_stores(self.db, stores), stores)
        pc.sync_store(self.db, FakeClient([page(1)]), 'Shop', 'https://shop.example')
        self.assertEqual(pc.due_stores(self.db, stores), [])
        self.assertEqual(pc.due_stores(self.db, stores, clock=time.time() + 13 * 3600), stores)


class DeckMatchTests(CatalogueTests):
    def test_match_and_link(self):
        from tcg_alerts.decks import DeckStore
        singles = {'products': [
            {'id': 1, 'handle': 'jinx', 'title': 'Jinx, Loose Cannon - Riftbound Single', 'vendor': '', 'product_type': '', 'tags': [], 'images': [],
             'variants': [{'id': 11, 'title': 'Default Title', 'price': '4.50', 'available': True}]},
            {'id': 2, 'handle': 'jinx2', 'title': 'Jinx, Loose Cannon (Foil) - Riftbound', 'vendor': '', 'product_type': '', 'tags': [], 'images': [],
             'variants': [{'id': 22, 'title': 'Default Title', 'price': '2.00', 'available': False}]},
            {'id': 3, 'handle': 'vi', 'title': 'Vi - Riftbound', 'vendor': '', 'product_type': '', 'tags': [], 'images': [],
             'variants': [{'id': 33, 'title': 'Default Title', 'price': '1.00', 'available': True}]}]}
        pc.sync_store(self.db, FakeClient([singles]), 'Shop', 'https://shop.example')
        store = DeckStore(self.db)
        deck = store.save_deck('Clockwork', 'Riftbound')
        jinx = store.save_entry(deck, dict(name='Jinx, Loose Cannon', quantity=3, owned=1))
        store.save_entry(deck, dict(name='Owned Card', quantity=1, owned=1))
        m = pc.deck_matches(self.db, deck)
        self.assertEqual([x['entry']['id'] for x in m], [jinx])
        self.assertEqual(m[0]['candidates'][0]['price'], 450)  # in stock first, though dearer
        pc.link_entry(self.db, deck, jinx, m[0]['candidates'][0], 'Riftbound')
        self.assertEqual(pc.deck_matches(self.db, deck), [])
        line = [l for l in store.report(deck)['lines'] if l['id'] == jinx][0]
        self.assertTrue(line['listing_url'].endswith('?variant=11'))
