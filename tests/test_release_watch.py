import tempfile, unittest
from datetime import date
from pathlib import Path
from tcg_alerts.core import Database
from tcg_alerts import release_watch as rw


class ReleaseWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.db = Database(Path(self.tmp.name) / 'a.sqlite3')

    def tearDown(self): self.tmp.cleanup()

    def test_detect_only_stated_release_dates(self):
        self.assertEqual(rw.detect('Spiritforged launches worldwide on October 23, 2026'), [('2026-10-23', 'Release')])
        self.assertEqual(rw.detect('Prerelease events Feb 13th 2027'), [('2027-02-13', 'Prerelease')])
        self.assertEqual(rw.detect('Posted October 23, 2026'), [])
        self.assertEqual(rw.detect('Launches in Spring 2027'), [])

    def test_ingest_dedupes_and_reminds_once(self):
        items = [{'title': 'New set', 'url': 'https://playriftbound.com/en-us/news/a/b', 'blurb': 'It releases on December 4, 2026.'}]
        today = date(2026, 11, 27)
        self.assertEqual(rw.ingest(self.db, 'Riftbound', items, today), 1)
        self.assertEqual(rw.ingest(self.db, 'Riftbound', items, today), 0)
        msgs = rw.due_reminders(self.db, today)
        self.assertTrue(any('New set' in m and 'in 7 days' in m for m in msgs))
        self.assertFalse(any('New set' in m for m in rw.due_reminders(self.db, today)))


if __name__ == '__main__':
    unittest.main()
