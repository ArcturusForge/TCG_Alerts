from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import queue
import sqlite3
import tempfile
import unittest

from tcg_alerts.core import Database, Observation
from tcg_alerts.catalog import metadata, matches
from tcg_alerts.analytics import report
from tcg_alerts.news import PublisherPage, feed_items, published, NewsMonitor


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'data.db'
        self.db = Database(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_v1_migration_retains_data_and_is_repeatable(self):
        old = Path(self.temp.name) / 'v1.db'
        # Real v1 schema without the metadata columns, as it existed in the previous executable.
        with sqlite3.connect(old) as c:
            c.executescript('''CREATE TABLE watches (
                id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE,label TEXT NOT NULL DEFAULT '',group_name TEXT NOT NULL DEFAULT '',
                target INTEGER, restock INTEGER NOT NULL DEFAULT 1,shipping INTEGER,enabled INTEGER NOT NULL DEFAULT 1,
                title TEXT,currency TEXT,price INTEGER,stock TEXT,source TEXT,checked TEXT,attempted TEXT,error TEXT,
                failures INTEGER NOT NULL DEFAULT 0,next_due REAL NOT NULL DEFAULT 0,price_active INTEGER NOT NULL DEFAULT 0);
                INSERT INTO watches(id,url,label,target) VALUES(7,'https://store.example/products/box','Existing watch',20000);
                PRAGMA user_version=1;''')
        c.close()
        upgraded = Database(old)
        w = upgraded.watches()[0]
        self.assertEqual((w['id'], w['label'], w['target']), (7,'Existing watch',20000))
        self.assertEqual(w['country'], 'Unspecified')
        Database(old)
        self.assertEqual(len(upgraded.news_sources()),2)
        self.assertEqual(upgraded.rows('PRAGMA user_version')[0]['user_version'],3)

    def test_tags_and_hierarchical_filter(self):
        a=self.db.add('https://a.example/products/box',game='riftbound',country='au',state='vic')
        self.db.add('https://b.example/products/box',game='Cyberpunk',country='Australia',state='New South Wales')
        self.db.add('https://c.example/products/box')
        scoped=[w for w in self.db.watches() if matches(w,'Riftbound','Australia','Victoria')]
        self.assertEqual([w['id'] for w in scoped],[a])
        self.assertEqual(len([w for w in self.db.watches() if matches(w,country='Australia')]),2)
        with self.assertRaises(ValueError):
            metadata('Riftbound','Canada','Victoria')

    def test_edit_location_never_guesses_from_currency(self):
        a=self.db.add('https://a.example/products/box')
        self.db.record(a,Observation('Riftbound box',20000,'AUD','in_stock','fixture'))
        self.assertEqual(self.db.watches()[0]['country'],'Unspecified')
        self.db.update(a,game='Cyberpunk',country='Australia',state='vic')
        self.assertEqual(self.db.watches()[0]['state'],'Victoria')
        with self.assertRaises(ValueError):
            self.db.update(a,country='Canada')
        self.assertEqual(len(self.db.history(a)),1)

    def test_analytics_counts_real_events_filters_and_window(self):
        a=self.db.add('https://a.example/products/box',game='Riftbound')
        b=self.db.add('https://b.example/products/box',game='Cyberpunk')
        self.db.record(a,Observation('A',20000,'AUD','in_stock','fixture'))
        self.db.record(a,Observation('A',19000,'AUD','out_of_stock','fixture'))
        self.db.record(b,Observation('B',10000,'USD','in_stock','fixture'))
        self.db.fail(a,'fixture timeout',0)
        self.db.log_open(a)
        r=report(self.db,[a],a,7)
        self.assertEqual([p['price'] for p in r['prices']],[20000,19000])
        self.assertEqual({p['currency'] for p in r['prices']},{'AUD'})
        self.assertEqual(sum(d['check_ok'] for d in r['daily']),2)
        self.assertEqual(sum(d['check_failed'] for d in r['daily']),1)
        self.assertEqual(sum(d['store_open'] for d in r['daily']),1)
        self.assertEqual(len(report(self.db,[b],a,7)['prices']),0)
        self.assertEqual(len(report(self.db,[a],a,7,clock=datetime.now(timezone.utc)+timedelta(days=10))['prices']),0)
        self.assertEqual(report(self.db,[],a)['daily'],[])

    def test_no_historical_traffic_from_old_observations(self):
        a=self.db.add('https://a.example/products/box')
        with self.db.connect() as c:
            c.execute("INSERT INTO observations(watch_id,at,price,currency,stock,source) VALUES(?,datetime('now'),20000,'AUD','in_stock','legacy')",(a,))
        self.assertEqual(sum(d['store_open'] for d in report(self.db,[a],a)['daily']),0)

    def test_news_cache_deduplication_and_failure_retains_items(self):
        source=self.db.news_sources()[0]
        items=[{'url':'https://playriftbound.com/en-us/news/announcements/example','title':'Set announcement','published':'2026-11-01T00:00:00+00:00','topic':'Release / announcement'}]
        self.db.save_news(source['id'],items,0)
        self.db.save_news(source['id'],items,0)
        self.db.fail_news(source['id'],'offline',123)
        self.assertEqual(len(self.db.news()),1)
        self.assertEqual(self.db.news()[0]['error'],'offline')
        self.db.set_news_enabled(source['id'],False)
        self.assertEqual(self.db.news(),[])
        self.assertEqual(len(self.db.rows('SELECT * FROM news_items')),1)

    def test_news_monitor_respects_cooldowns(self):
        calls=[]
        monitor=NewsMonitor(self.db,queue.Queue(),fetcher=lambda s,c: calls.append(s['id']) or [])
        monitor.cycle()
        monitor.cycle()
        self.assertEqual(len(calls),2)


class NewsParserTests(unittest.TestCase):
    def test_riftbound_headline_and_publication_only(self):
        parser=PublisherPage({'url':'https://playriftbound.com/en-us/news/','adapter':'riftbound'})
        parser.feed('''<a href="/en-us/news/announcements/next-set" aria-label="Next set"><time dateTime="2026-10-27T16:00:00Z"></time><div data-testid="card-title">Next set announced</div><p>Release date 2027-02-01</p></a>''')
        value=list(parser.items.values())[0]
        self.assertEqual(value['title'],'Next set announced')
        self.assertEqual(value['published'],'2026-10-27T16:00:00+00:00')
        self.assertNotIn('2027',json.dumps(value))

    def test_cyberpunk_date_from_card(self):
        parser=PublisherPage({'url':'https://cyberpunktcg.com/blog','adapter':'cyberpunk'})
        parser.feed('''<a href="/blog/set-2"><h3>Set Two &amp; Beyond</h3><p>Spring 2027 release window</p><span>OCT 20, 2026</span></a>''')
        value=list(parser.items.values())[0]
        self.assertEqual(value['title'],'Set Two & Beyond')
        self.assertEqual(value['published'][:10],'2026-10-20')

    def test_rss_dedup_dates_and_unsafe_links(self):
        xml='''<rss><channel><item><title>New TCG announced</title><link>https://publisher.example/new</link><pubDate>Sun, 01 Nov 2026 10:00:00 GMT</pubDate></item><item><title>Duplicate</title><link>https://publisher.example/new</link></item><item><title>Unsafe</title><link>javascript:alert(1)</link></item></channel></rss>'''
        result=feed_items(xml,{'url':'https://publisher.example/feed'})
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['published'], '2026-11-01T10:00:00+00:00')
        with self.assertRaises(ValueError):
            feed_items('<!DOCTYPE x><rss/>',{'url':'https://publisher.example/feed'})
        with self.assertRaises(ValueError):
            feed_items('<html/>',{'url':'https://publisher.example/feed'})

    def test_atom_namespace_and_missing_date(self):
        xml='''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>New series</title><link rel="alternate" href="/new"/><updated>2026-11-01T11:00:00Z</updated></entry></feed>'''
        value=feed_items(xml,{'url':'https://publisher.example/feed'})[0]
        self.assertEqual(value['url'],'https://publisher.example/new')
        self.assertEqual(value['published'],'2026-11-01T11:00:00+00:00')
        self.assertIsNone(published('unconfirmed'))
