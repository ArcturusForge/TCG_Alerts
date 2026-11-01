from pathlib import Path
from datetime import datetime,timezone,timedelta
from io import BytesIO
import json,tempfile,unittest
from tcg_alerts.core import Database,Observation,now
from tcg_alerts.decks import DeckStore,parse_list
from tcg_alerts.card_images import decode,ImageRedirect
from urllib.request import Request

class DeckTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'decks.db';self.db=Database(self.path);self.store=DeckStore(self.db);self.deck=self.store.save_deck('Clockwork','Riftbound','AUD')
    def tearDown(self):self.tmp.cleanup()
    def card(self,**changes):return {**dict(name='Card',quantity=3,owned=1,section='Main',printing='Standard',manual_price=500,reference_checked='2026-11-02',reference_source='User evidence'),**changes}
    def watch(self,currency='AUD',stock='in_stock',game='Riftbound'):
        w=self.db.add('https://store.example/products/'+str(len(self.db.watches())),game=game)
        self.db.record(w,Observation('Card',600,currency,stock,'fixture'));return w
    def test_parse_sections_quantities_and_names(self):
        rows=parse_list('# comment\n[Legend]\n1 Example — Legend\nMain:\n3x Ball\nCard x2\n2 Alpha // Beta')
        self.assertEqual([(r['name'],r['quantity'],r['section']) for r in rows],[('Example — Legend',1,'Legend'),('Ball',3,'Main'),('Card',2,'Main'),('Alpha // Beta',2,'Main')])
        for text in ('Unknown name','0 Card','[Main]'):
            with self.assertRaises(ValueError):parse_list(text)
    def test_unknowns_never_become_zero_complete_deck(self):
        self.store.save_entry(self.deck,self.card());self.store.save_entry(self.deck,self.card(name='Unknown',manual_price=None))
        s=self.store.report(self.deck)['summary']
        self.assertEqual((s['required'],s['missing'],s['reference_subtotal'],s['reference_copies']),(6,4,1500,3))
        self.assertEqual((s['missing_reference_subtotal'],s['missing_reference_copies']),(1000,2))
        self.assertEqual(s['missing_ask_copies'],0)
    def test_fresh_asking_offer_is_distinct_from_manual_reference(self):
        w=self.watch();self.store.save_entry(self.deck,self.card(watch_id=w,listing_confirmed=True))
        r=self.store.report(self.deck);s=r['summary']
        self.assertEqual(s['reference_subtotal'],1500);self.assertEqual(s['missing_ask_subtotal'],1200)
        self.assertEqual(r['lines'][0]['reference_basis'],'Manual reference: User evidence')
    def test_stale_failed_out_of_stock_and_paused_not_buying_offers(self):
        w=self.watch();self.store.save_entry(self.deck,self.card(manual_price=None,watch_id=w,listing_confirmed=True))
        r=self.store.report(self.deck,clock=datetime.now(timezone.utc)+timedelta(hours=1))
        self.assertEqual(r['summary']['reference_subtotal'],1800);self.assertEqual(r['summary']['reference_old_copies'],3);self.assertEqual(r['summary']['missing_ask_copies'],0)
        self.db.fail(w,'Timeout',0);self.assertIsNone(self.store.report(self.deck)['lines'][0]['fresh_ask'])
        self.db.record(w,Observation('Card',600,'AUD','out_of_stock','fixture'));self.assertIsNone(self.store.report(self.deck)['lines'][0]['fresh_ask'])
        self.db.update(w,enabled=False);self.assertIsNone(self.store.report(self.deck)['lines'][0]['fresh_ask'])
    def test_currency_mismatch_is_not_converted(self):
        w=self.watch(currency='USD');self.store.save_entry(self.deck,self.card(manual_price=None,watch_id=w,listing_confirmed=True))
        s=self.store.report(self.deck)['summary'];self.assertEqual(s['reference_copies'],0);self.assertEqual(s['missing_ask_copies'],0)
    def test_link_confirmation_and_game_are_checked(self):
        w=self.watch()
        with self.assertRaises(ValueError):self.store.save_entry(self.deck,self.card(watch_id=w))
        other=self.watch(game='Cyberpunk')
        with self.assertRaises(ValueError):self.store.save_entry(self.deck,self.card(watch_id=other,listing_confirmed=True))
    def test_deleting_watch_preserves_card_and_manual_reference(self):
        w=self.watch();self.store.save_entry(self.deck,self.card(watch_id=w,listing_confirmed=True));self.db.delete(w)
        r=self.store.report(self.deck);self.assertIsNone(r['lines'][0]['watch_id']);self.assertEqual(r['summary']['reference_subtotal'],1500)
    def test_owned_above_required_clamps_missing(self):
        self.store.save_entry(self.deck,self.card(owned=10));s=self.store.report(self.deck)['summary']
        self.assertEqual(s['owned'],3);self.assertEqual(s['missing'],0)
    def test_explicit_zero_price_is_priced(self):
        self.store.save_entry(self.deck,self.card(manual_price=0));s=self.store.report(self.deck)['summary'];self.assertEqual(s['reference_copies'],3);self.assertEqual(s['reference_subtotal'],0)
    def test_atomic_import_no_partial_changes_on_invalid_row(self):
        with self.assertRaises(ValueError):self.store.import_rows(self.deck,[self.card(),self.card(name='Bad',quantity=0)])
        self.assertEqual(self.store.report(self.deck)['lines'],[])
    def test_currency_and_game_lock_and_clone(self):
        self.store.save_entry(self.deck,self.card())
        with self.assertRaises(ValueError):self.store.save_deck('Clockwork','Riftbound','USD',deck_id=self.deck)
        with self.assertRaises(ValueError):self.store.save_deck('Clockwork','Cyberpunk','AUD',deck_id=self.deck)
        clone=self.store.clone(self.deck);self.assertEqual(self.store.report(clone)['summary']['required'],3)
        self.store.delete_deck(self.deck);self.assertEqual(len(self.store.report(clone)['lines']),1)
    def test_snapshot_preserves_evidence_and_coverage(self):
        row=self.store.save_entry(self.deck,self.card());self.store.snapshot(self.deck)
        self.store.save_entry(self.deck,self.card(manual_price=1000),row)
        snap=self.store.snapshots(self.deck)[0]
        self.assertEqual(json.loads(snap['summary'])['reference_subtotal'],1500)
        self.assertEqual(json.loads(snap['evidence'])[0]['reference'],500)
        self.assertNotIn('image_path',json.loads(snap['evidence'])[0])
    def test_csv_roundtrip_does_not_trust_external_watch_ids_or_local_paths(self):
        w=self.watch();self.store.save_entry(self.deck,self.card(name='Name, comma',watch_id=w,listing_confirmed=True,image_url='https://images.example/card.png'))
        text=self.store.csv_export(self.deck);other=self.store.save_deck('Other','Riftbound')
        self.store.csv_import(other,text);line=self.store.report(other)['lines'][0]
        self.assertEqual(line['name'],'Name, comma');self.assertEqual(line['manual_price'],500);self.assertIsNone(line['watch_id']);self.assertEqual(line['image_path'],'')
        with self.assertRaises(ValueError):self.store.csv_import(other,'name,quantity,currency\nCard,2,USD\n')
        with self.assertRaises(ValueError):self.store.csv_import(other,'name,name,quantity\nA,B,2\n')
    def test_export_defuses_spreadsheet_formulas(self):
        self.store.save_entry(self.deck,self.card(name='=2+2'))
        self.assertIn("'=2+2",self.store.csv_export(self.deck))
    def test_upgrade_v3_preserves_all_prior_data_and_adds_decks(self):
        w=self.watch()
        with self.db.connect() as c:
            c.execute('DROP TABLE deck_snapshots');c.execute('DROP TABLE deck_entries');c.execute('DROP TABLE decks');c.execute('PRAGMA user_version=3')
        db=Database(self.path);self.assertEqual(len(db.history(w)),1);self.assertEqual(len(db.stores()),6);self.assertEqual(db.rows('PRAGMA user_version')[0]['user_version'],4)
        self.assertEqual(DeckStore(db).decks(),[])
    def test_invalid_identity_quantity_art_url_and_reference_date(self):
        for bad in ({'quantity':-1},{'owned':-1},{'name':''},{'image_url':'file:///tmp/private.png'},{'reference_checked':''}):
            with self.assertRaises(ValueError):self.store.save_entry(self.deck,self.card(**bad))

class ArtworkTests(unittest.TestCase):
    def test_preview_valid_image_and_invalid_bytes(self):
        from PIL import Image,UnidentifiedImageError
        image=Image.new('RGB',(744,1039),'navy');out=BytesIO();image.save(out,format='PNG')
        preview=decode(out.getvalue());self.assertLessEqual(preview.width,240);self.assertLessEqual(preview.height,330)
        with self.assertRaises(UnidentifiedImageError):decode(b'not an image')
    def test_image_size_limit_and_https_redirect(self):
        with self.assertRaises(ValueError):decode(b'X'*(8*1024*1024+1))
        redirect=ImageRedirect()
        with self.assertRaises(ValueError):redirect.redirect_request(Request('https://images.example/card'),None,302,'',{},'http://images.example/card')
