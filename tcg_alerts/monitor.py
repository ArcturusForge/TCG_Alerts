"""One serial worker: bounded traffic and no GUI calls from background threads."""
import queue
import threading
import time
import random
from .sources import Client, fetch


class Monitor:
    def __init__(self, db, interval=900, fetcher=fetch):
        self.db = db
        self.interval = max(300, interval)
        self.fetcher = fetcher
        self.events = queue.Queue()
        self.wake = threading.Event()
        self.stop_event = threading.Event()
        self.client = Client()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='store-monitor')
        self.thread.start()

    def check_now(self):
        # Deliberately respects next_due, including rate-limit backoff.
        self.wake.set()

    def close(self):
        self.stop_event.set()
        self.wake.set()

    def cycle(self):
        for w in self.db.watches():
            if self.stop_event.is_set():
                break
            if not w['enabled'] or w['next_due'] > time.time():
                continue
            self.events.put(('status', f"Checking {w['label'] or w['url']}"))
            try:
                obs = self.fetcher(w['url'], self.client)
                due = time.time() + self.interval + random.uniform(0, 30)
                alerts = self.db.record(w['id'], obs, due)
                for kind, message in alerts:
                    self.events.put(('alert', message))
                self.events.put(('updated', w['id']))
            except Exception as e:
                delay = min(86400, self.interval * 2 ** min(w['failures'] + 1, 6))
                message = f'{type(e).__name__}: {e}'
                self.db.fail(w['id'], message, time.time() + delay)
                self.events.put(('error', message))
        self.events.put(('idle', 'Monitoring • next due checks run automatically'))

    def run(self):
        while not self.stop_event.is_set():
            self.cycle()
            self.wake.wait(15)
            self.wake.clear()
