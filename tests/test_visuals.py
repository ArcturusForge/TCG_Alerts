import unittest
import json,os,queue,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock
from PIL import Image
try:
    from tcg_alerts.visuals import ImageService
except ModuleNotFoundError as e:  # Tk missing on headless CI
    raise unittest.SkipTest(f'Tk unavailable: {e}')
from tcg_alerts.card_catalogue import normalize_openrift,search
from tcg_alerts.news import PublisherPage,attach_publisher_images,feed_items
from tcg_alerts.core import Database,Observation
from tcg_alerts.decks import DeckStore
from tcg_alerts.deck_charts import breakdown
from tcg_alerts.onboarding import restore_copy


class VisualTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def deliver(self,service,events):
        kind,payload=events.get(timeout=3);self.assertEqual(kind,'visual_image');service.receive(*payload)
    def test_cache_deduplicates_requests_and_keeps_last_image_offline(self):
        events=queue.Queue();loader=Mock(return_value=Image.new('RGB',(90,130),'navy'));service=ImageService(self.root/'art',events,loader=loader,ttl=0)
        received=[]
        try:
            service.request('https://images.example/card','',lambda *v:received.append(v))
            service.request('https://images.example/card','',lambda *v:received.append(v))
            self.deliver(service,events);self.assertEqual(loader.call_count,1);self.assertEqual(len(received),2)
            # Windows file timestamps can be slightly ahead of time.time(); even a future mtime must not bypass expiry.
            cache=next((self.root/'art').glob('*.png'));future=time.time()+60;os.utime(cache,(future,future))
            loader.side_effect=OSError('offline')
            service.request('https://images.example/card','',lambda *v:received.append(v));self.deliver(service,events)
            self.assertIsNotNone(received[-1][0]);self.assertIn('unavailable',received[-1][1])
            before=loader.call_count;service.request('https://images.example/card','',lambda *v:received.append(v));self.assertEqual(loader.call_count,before)
        finally:service.close()
    def test_disk_cache_reused_by_next_session_and_local_file_identity_changes(self):
        events=queue.Queue();loader=Mock(return_value=Image.new('RGB',(90,130)));service=ImageService(self.root/'art',events,loader=loader)
        service.request('https://images.example/card','',lambda *v:None);self.deliver(service,events);service.close()
        cache=next((self.root/'art').glob('*.png'));past=time.time()-60;os.utime(cache,(past,past))
        second=ImageService(self.root/'art',events,loader=Mock(side_effect=OSError('offline')));received=[]
        try:
            second.request('https://images.example/card','',lambda *v:received.append(v));self.deliver(second,events)
            self.assertIsNotNone(received[0][0]);second.loader.assert_not_called()
            file=self.root/'card.png';file.write_bytes(b'a');key=second.key('',str(file));file.write_bytes(b'longer')
            self.assertNotEqual(key,second.key('',str(file)))
        finally:second.close()
    def test_catalogue_printing_identity_and_no_price_import(self):
        payload=dict(printingIds=['p'],printings={'p':dict(cardId='c',shortCode='RAD-042',language='EN',finish='foil',images=[dict(imageId='image-1')],setId='s')},cards={'c':dict(name='Orianna',types=['unit'],energy=3)},sets=[dict(id='s',slug='RAD')])
        row=normalize_openrift(payload)[0]
        self.assertEqual((row['collector'],row['printing'],row['language']),('042','Foil','English'));self.assertIn('/image-1-400w.webp',row['image_url']);self.assertNotIn('manual_price',row)
        with self.assertRaises(ValueError):normalize_openrift({'wrong':[]})
        with self.assertRaises(ValueError):search('x',Mock())
    def test_news_images_match_article_url_and_preserve_on_text_only_refresh(self):
        source=dict(url='https://playriftbound.com/en-us/news/',adapter='riftbound')
        url='https://playriftbound.com/en-us/news/announcements/set'
        parser=PublisherPage(source);parser.feed('<a href="'+url+'"><img src="data:image/svg+xml,placeholder"><h2>New set</h2></a>')
        self.assertFalse(parser.items[url]['image_url'])
        payload=dict(media=dict(url='https://images.example/story.jpg'),action=dict(payload=dict(url=url)))
        attach_publisher_images('<script type="application/json">'+json.dumps(payload)+'</script>',parser.items,source)
        self.assertEqual(parser.items[url]['image_url'],'https://images.example/story.jpg')
        db=Database(self.root/'news.db');source_id=db.news_sources()[0]['id'];db.save_news(source_id,list(parser.items.values()),0)
        db.save_news(source_id,[dict(url=url,title='Updated title')],0);self.assertEqual(db.news()[0]['image_url'],'https://images.example/story.jpg')
        self.assertEqual(Database(db.path).rows('PRAGMA user_version')[0]['user_version'],5)
    def test_feed_thumbnail_and_reject_non_https_art(self):
        source=dict(url='https://publisher.example/rss')
        data='<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>Set</title><link>https://publisher.example/story</link><media:thumbnail url="https://images.example/set.jpg"/></item></channel></rss>'
        self.assertEqual(feed_items(data,source)[0]['image_url'],'https://images.example/set.jpg')
        self.assertEqual(feed_items(data.replace('https://images.example/set.jpg','file:///etc/passwd'),source)[0]['image_url'],'')
    def test_cost_graph_excludes_unknown_prices_and_uses_required_copies(self):
        db=Database(self.root/'deck.db');store=DeckStore(db);deck=store.save_deck('Test','Riftbound')
        store.import_rows(deck,[dict(name='Priced',quantity=3,owned=2,manual_price=500,reference_checked='2026-11-02'),dict(name='Unknown',quantity=2)])
        result=breakdown(store.report(deck));self.assertEqual(result['costs'][0][1],1500);self.assertEqual(result['unpriced'],2);self.assertEqual(result['sections'],[('Main',5)])
    def test_restore_preserves_original_and_rejects_unrelated_database(self):
        db=Database(self.root/'original.db');db.add('https://shop.example/products/test')
        copy=restore_copy(db.path,self.root/'restores');Database(copy).add('https://other.example/products/new')
        self.assertEqual(len(Database(db.path).watches()),1);self.assertEqual(len(Database(copy).watches()),2)
        bad=self.root/'bad.db';bad.write_text('not sqlite')
        with self.assertRaises(Exception):restore_copy(bad,self.root/'restores')
        self.assertEqual(len(list((self.root/'restores').glob('*.sqlite3'))),1)
