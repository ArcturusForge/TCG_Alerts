import tempfile,unittest,json,queue,sys
from pathlib import Path
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from types import SimpleNamespace
from tcg_alerts.core import Database,Observation
from tcg_alerts.commerce import quote,postcode
from tcg_alerts.releases import validate,icalendar,upcoming
from tcg_alerts.sources import variant_options,product_endpoints
from tcg_alerts.desktop import Desktop

class CommerceTests(unittest.TestCase):
    def w(self,**changes):return {**dict(price=20000,currency='AUD',shipping=None,shipping_postcode='',shipping_country='Australia',pack_count=24,pickup='Unspecified',store_id=1),**changes}
    def r(self,**changes):return {**dict(store_id=1,country='Australia',postcode='',currency='AUD',flat=1000,free_over=25000,source_url='https://store.example/shipping',checked='2026-11-01'),**changes}
    def test_unknown_cost_not_free(self):
        self.assertIsNone(quote(self.w(),destination='3000')['total'])
        self.assertIsNone(quote(self.w(),destination='3000')['per_pack'])
    def test_exact_postcode_beats_country_rule(self):self.assertEqual(quote(self.w(),[self.r(),self.r(postcode='3000',flat=500)],destination='3000')['shipping'],500)
    def test_currency_and_store_are_not_mixed(self):
        self.assertIsNone(quote(self.w(),[self.r(currency='USD')])['total'])
        self.assertIsNone(quote(self.w(),[self.r(store_id=99)])['total'])
    def test_free_threshold_and_decimal_pack_cost(self):
        q=quote(self.w(price=25000),[self.r()],destination='3000')
        self.assertEqual(q['shipping'],0);self.assertEqual(q['per_pack'],Decimal(25000)/24)
        self.assertIsNone(quote(self.w(),[self.r(flat=None)],destination='3000')['total'])
        self.assertIsNone(quote(self.w(pack_count=None),[self.r()])['per_pack'])
    def test_fixed_shipping_destination_is_exact(self):
        self.assertEqual(quote(self.w(shipping=700))['total'],20700)
        self.assertIsNone(quote(self.w(shipping=700),destination='3000')['total'])
        self.assertEqual(quote(self.w(shipping=700,shipping_postcode='3000'),destination='3000')['shipping'],700)
    def test_pickup_requires_policy_and_explicit_no_overrides_store(self):
        self.assertIsNone(quote(self.w(),mode='Pickup')['total'])
        self.assertEqual(quote(self.w(),mode='Pickup',store={'pickup':'Yes'})['shipping'],0)
        self.assertIsNone(quote(self.w(pickup='No'),mode='Pickup',store={'pickup':'Yes'})['total'])
    def test_au_postcode_preserves_zeroes(self):
        self.assertEqual(postcode('0800'),'0800')
        with self.assertRaises(ValueError):postcode('800')

class StorageTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.db';self.db=Database(self.path)
    def tearDown(self):self.tmp.cleanup()
    def test_seed_idempotence_and_location_inheritance(self):
        self.db.add('https://onlypackstcg.com.au/products/box')
        self.assertEqual(self.db.watches()[0]['state'],'Victoria')
        self.assertIsNotNone(self.db.watches()[0]['store_id'])
        Database(self.path)
        self.assertEqual(len(self.db.stores()),6);self.assertEqual(len(self.db.releases()),4)
    def test_existing_location_is_not_overwritten(self):
        self.db.add('https://onlypackstcg.com.au/products/box',country='Australia',state='New South Wales')
        self.assertEqual(self.db.watches()[0]['state'],'New South Wales')
        self.db.apply_store(self.db.watches()[0]['store_id'])
        self.assertEqual(self.db.watches()[0]['state'],'Victoria')
    def test_rule_upsert_and_validation(self):
        s=self.db.stores()[0]['id'];v=dict(country='Australia',postcode='3000',currency='AUD',flat=1000,free_over=None,source_url='https://store.example/shipping')
        self.db.save_rule(s,v);v['flat']=500;self.db.save_rule(s,v)
        self.assertEqual(len(self.db.rules(s)),1);self.assertEqual(self.db.rules(s)[0]['flat'],500)
        self.db.delete_rule(self.db.rules(s)[0]['id']);self.assertFalse(self.db.rules(s))
        v['flat']=None
        with self.assertRaises(ValueError):self.db.save_rule(s,v)
    def test_v2_upgrade_preserves_observations_and_shipping(self):
        a=self.db.add('https://store.example/products/box',shipping=700)
        self.db.record(a,Observation('Box',20000,'AUD','in_stock','fixture'))
        with self.db.connect() as c:
            for name in ('store_id','pack_count','shipping_postcode','shipping_country','pickup'):c.execute('ALTER TABLE watches DROP COLUMN '+name)
            c.execute('DROP TABLE shipping_rules');c.execute('DROP TABLE stores');c.execute('DROP TABLE releases');c.execute('DROP TABLE settings');c.execute('PRAGMA user_version=2')
        db=Database(self.path)
        self.assertEqual(db.watches()[0]['shipping'],700);self.assertEqual(db.watches()[0]['shipping_postcode'],'');self.assertEqual(len(db.history(a)),1)
    def test_invalid_units_rejected(self):
        with self.assertRaises(ValueError):self.db.add('https://store.example/products/box',pack_count=0)
        a=self.db.add('https://store.example/products/box',pack_count=24)
        with self.assertRaises(ValueError):self.db.update(a,pack_count=-1)
    def test_preferences_and_calendar_edits_persist(self):
        self.db.set_setting('close_to_tray',True);self.assertTrue(Database(self.path).setting('close_to_tray'))
        r=self.db.releases()[0];r['notes']='Changed note';self.db.save_release(r,r['id'])
        self.assertEqual(Database(self.path).releases()[0]['notes'],'Changed note')
    def test_future_schema_is_not_downgraded(self):
        with self.db.connect() as c:c.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):Database(self.path)

class CalendarTests(unittest.TestCase):
    def entry(self,**changes):return {**dict(id=1,title='Release, edition; launch',game='Cyberpunk',kind='Release',start='2026-11-06',end='2026-11-06',precision='Day',window='',region='Global / unspecified',status='Confirmed',source_url='https://publisher.example/release',checked='2026-11-01',notes='Source note'),**changes}
    def test_window_never_becomes_an_exact_date(self):
        w=validate(self.entry(start='',end='',precision='Window',window='Spring 2027'))
        self.assertIsNone(w['start']);self.assertTrue(upcoming(w,date(2026,11,1)))
        with self.assertRaises(ValueError):validate(self.entry(precision='Window',window='Spring 2027'))
    def test_ics_inclusive_range_and_unknown_dates_skipped(self):
        text,count,skipped=icalendar([self.entry(),self.entry(id=2,start=None,end=None,precision='Window',window='Spring 2027')])
        self.assertEqual((count,skipped),(1,1));self.assertIn('DTEND;VALUE=DATE:20261107',text);self.assertNotIn('Spring 2027',text);self.assertIn(r'SUMMARY:Release\, edition\; launch',text)
        for line in text.split('\r\n'):self.assertLessEqual(len(line.encode()),75)
    def test_bad_dates_and_cancelled(self):
        with self.assertRaises(ValueError):validate(self.entry(precision='Range',end='2026-11-01'))
        self.assertFalse(upcoming(self.entry(status='Cancelled'),date(2026,11,1)))

class VariantTests(unittest.TestCase):
    def test_exact_variant_url_currency_and_collection_route(self):
        calls=[]
        class C:
            def get(self,url):
                calls.append(url)
                return json.dumps({'currency':'AUD'} if url.endswith('cart.js') else {'title':'Product','variants':[{'id':1,'title':'Pack','price':1000,'available':True},{'id':2,'title':'Box','price':20000,'available':False}]})
        options=variant_options('https://store.example/en/collections/boxes/products/product?variant=1',C())
        self.assertEqual(calls,['https://store.example/en/products/product.js','https://store.example/en/cart.js'])
        self.assertEqual(options[1]['url'],'https://store.example/en/products/product?variant=2');self.assertEqual(options[1]['price'],20000)
        self.assertEqual(product_endpoints('https://store.example/collections/products/products/box')[0],'https://store.example/products/box')

class DesktopTests(unittest.TestCase):
    def test_lifecycle_callback_queue_and_notification(self):
        class Icon:
            def __init__(self,name,image,title,menu):self.visible=False;self.menu=menu
            def run_detached(self,setup):setup(self)
            def notify(self,*args):pass
            def stop(self):self.visible=False
        fake=SimpleNamespace(Icon=Icon,Menu=lambda *items:items,MenuItem=lambda title,action,**kw:action)
        drawing=SimpleNamespace(rounded_rectangle=lambda *a,**kw:None,line=lambda *a,**kw:None)
        pillow=SimpleNamespace(Image=SimpleNamespace(new=lambda *a,**kw:object()),ImageDraw=SimpleNamespace(Draw=lambda image:drawing))
        with patch('tcg_alerts.desktop.sys.platform','win32'),patch.dict(sys.modules,{'pystray':fake,'PIL':pillow}):
            q=queue.Queue();d=Desktop(q);d.start();self.assertTrue(d.available());self.assertTrue(d.notify('Test'));d.icon.menu[0](d.icon,None);self.assertEqual(q.get(),('desktop_action','show'));d.stop();self.assertFalse(d.available())
    def test_unsupported_platform_never_hides(self):
        with patch('tcg_alerts.desktop.sys.platform','linux'):
            d=Desktop(queue.Queue());d.start();self.assertFalse(d.available());self.assertFalse(d.notify('Test'))
