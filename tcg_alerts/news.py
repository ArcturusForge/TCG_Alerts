"""Headline-only publisher board and RSS/Atom reader. No inferred release dates."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
import re
import threading
import time
import xml.etree.ElementTree as ET
from .sources import Client, validate_url


def published(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value.strip())
        except (ValueError, TypeError, OverflowError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds')


def topic(title):
    if re.search(r'errata|rules|patch notes|clarification', title, re.I):
        return 'Rules'
    if re.search(r'announc|release|launch|booster|new set|set (?:two|three|\d)|overview', title, re.I):
        return 'Release / announcement'
    if re.search(r'tournament|regional|play|event|championship', title, re.I):
        return 'Events / play'
    return 'News'


def item(title, url, date=None):
    return {'title': ' '.join(title.split())[:400], 'url': validate_url(url), 'published': published(date), 'topic': topic(title)}


class PublisherPage(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.current = None
        self.heading_tag = None
        self.items = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            url = urljoin(self.source['url'], attrs.get('href', ''))
            p = urlsplit(url)
            pattern = r'^/en-us/news/[^/]+/[^/]+/?$' if self.source['adapter'] == 'riftbound' else r'^/blog/[^/]+/?$'
            if p.scheme == 'https' and p.netloc == urlsplit(self.source['url']).netloc and re.match(pattern, p.path):
                self.current = {'url': url.split('#')[0], 'title': [], 'all': [], 'date': None, 'fallback': attrs.get('aria-label', '')}
        if self.current:
            if tag in ('h2', 'h3') or attrs.get('data-testid') == 'card-title':
                self.heading_tag = tag
            if tag == 'time':
                self.current['date'] = attrs.get('datetime') or self.current['date']

    def handle_data(self, data):
        if self.current:
            self.current['all'].append(data)
            if self.heading_tag:
                self.current['title'].append(data)

    def handle_endtag(self, tag):
        if tag == self.heading_tag:
            self.heading_tag = None
        if tag == 'a' and self.current:
            c = self.current
            title = ''.join(c['title']).strip() or c['fallback']
            date = c['date']
            if not date and self.source['adapter'] == 'cyberpunk':
                # This is a publication date on the article card, never a release date.
                m = re.search(r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{1,2}),\s+(\d{4})\b', ' '.join(c['all']), re.I)
                if m:
                    month = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].index(m[1].lower()) + 1
                    try:
                        date = datetime(int(m[3]), month, int(m[2]), tzinfo=timezone.utc).isoformat()
                    except ValueError:
                        pass
            if title:
                self.items[c['url']] = item(title, c['url'], date)
            self.current = None
            self.heading_tag = None


def feed_items(text, source):
    if '<!doctype' in text.lower() or '<!entity' in text.lower():
        raise ValueError('FEED: DTD/entity declarations are not accepted.')
    root = ET.fromstring(text)
    if root.tag.rsplit('}', 1)[-1].lower() not in ('rss', 'feed', 'rdf'):
        raise ValueError('FEED: URL did not return RSS or Atom.')
    results = {}
    for entry in root.iter():
        if entry.tag.rsplit('}', 1)[-1] not in ('item', 'entry'):
            continue
        fields = {}
        url = None
        for child in entry:
            tag = child.tag.rsplit('}', 1)[-1]
            fields[tag] = ''.join(child.itertext()).strip()
            if tag == 'link' and child.get('rel', 'alternate') == 'alternate':
                url = child.get('href') or fields[tag]
        title = fields.get('title')
        if not title or not url:
            continue
        try:
            result = item(title, urljoin(source['url'], url), fields.get('published') or fields.get('pubDate') or fields.get('date') or fields.get('updated'))
        except ValueError:
            continue
        previous = results.get(result['url'])
        if previous and not result['published']:
            result['published'] = previous['published']
        results[result['url']] = result
        if len(results) >= 150:
            break
    return list(results.values())


def fetch_news(source, client):
    text = client.get(source['url'])
    if source['adapter'] == 'feed':
        return feed_items(text, source)
    parser = PublisherPage(source)
    parser.feed(text)
    if not parser.items:
        raise ValueError('NEWS: Publisher page returned no recognizable headlines; cached items retained.')
    return list(parser.items.values())[:100]


class NewsMonitor:
    def __init__(self, db, events, fetcher=fetch_news):
        self.db, self.events, self.fetcher = db, events, fetcher
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.client = Client()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='publisher-news')
        self.thread.start()

    def refresh(self):
        # Existing source cooldowns are respected; newly added feeds are due immediately.
        self.wake.set()

    def close(self):
        self.stop_event.set()
        self.wake.set()

    def cycle(self):
        for source in self.db.news_sources():
            if self.stop_event.is_set():
                break
            if not source['enabled'] or source['next_due'] > time.time():
                continue
            try:
                items = self.fetcher(source, self.client)
                self.db.save_news(source['id'], items, time.time() + 3600)
            except Exception as e:
                self.db.fail_news(source['id'], str(e), time.time() + 7200)
            self.events.put(('news_updated', None))

    def run(self):
        while not self.stop_event.is_set():
            self.cycle()
            self.wake.wait(30)
            self.wake.clear()
