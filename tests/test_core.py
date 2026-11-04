import tempfile
import unittest
from pathlib import Path
from tcg_alerts.core import Database, Observation, money
from tcg_alerts.monitor import Monitor


def obs(price=20000, stock='in_stock', currency='AUD'):
    return Observation('Riftbound / English / box of 24', price, currency, stock, 'fixture')


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / 'data.sqlite3')
        self.id = self.db.add('https://shop.example/products/box', target=22000)

    def tearDown(self):
        self.temp.cleanup()

    def test_target_transition_not_repeated(self):
        self.assertEqual(self.db.record(self.id, obs())[0][0], 'price')
        self.assertEqual(self.db.record(self.id, obs()), [])
        self.db.record(self.id, obs(23000))
        self.assertEqual(len(self.db.record(self.id, obs())), 1)

    def test_initial_check_not_restock(self):
        self.db.update(self.id, target=None)
        self.assertEqual(self.db.record(self.id, obs()), [])
        self.db.record(self.id, obs(stock='out_of_stock'))
        self.assertEqual(self.db.record(self.id, obs())[0][0], 'restock')

    def test_failure_does_not_corrupt_stock_or_repeat_alert(self):
        self.db.record(self.id, obs())
        self.db.fail(self.id, 'timeout', 123)
        row = self.db.watches()[0]
        self.assertEqual(row['stock'], 'in_stock')
        self.assertEqual(row['price'], 20000)
        self.assertEqual(self.db.record(self.id, obs()), [])
        self.assertIsNone(self.db.watches()[0]['error'])

    def test_confirmed_restock_survives_failure(self):
        self.db.record(self.id, obs(stock='out_of_stock'))
        self.db.fail(self.id, 'timeout', 0)
        self.assertEqual({a[0] for a in self.db.record(self.id, obs())}, {'restock', 'price'})

    def test_preorder_unknown_and_unavailable_do_not_hit_price(self):
        for stock in ['preorder', 'unknown', 'out_of_stock']:
            self.assertEqual(self.db.record(self.id, obs(stock=stock)), [])

    def test_shipping_in_target(self):
        self.db.update(self.id, shipping=2500)
        self.assertEqual(self.db.record(self.id, obs()), [])
        self.assertEqual(len(self.db.record(self.id, obs(19000))), 1)

    def test_currency_change_rejected(self):
        self.db.record(self.id, obs())
        with self.assertRaisesRegex(ValueError, 'CURRENCY'):
            self.db.record(self.id, obs(currency='USD'))
        self.assertEqual(self.db.watches()[0]['currency'], 'AUD')
        self.assertEqual(len(self.db.history(self.id)), 1)

    def test_pause_and_delete_during_check(self):
        self.db.update(self.id, enabled=False)
        self.assertEqual(self.db.record(self.id, obs()), [])
        self.db.delete(self.id)
        self.assertEqual(self.db.record(self.id, obs()), [])

    def test_backoff_and_resume_persist(self):
        def broken(url, client):
            raise TimeoutError('fixture')
        m = Monitor(self.db, interval=300, fetcher=broken)
        m.cycle()
        self.assertEqual(self.db.watches()[0]['failures'], 1)
        m.cycle()
        self.assertEqual(self.db.watches()[0]['failures'], 1)
        self.assertEqual(len(self.db.history(self.id)), 0)

    def test_backup_and_duplicate_watch(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add('https://shop.example/products/box')
        target = Path(self.temp.name) / 'backup.db'
        self.db.backup(target)
        self.assertEqual(len(Database(target).watches()), 1)

    def test_money(self):
        self.assertEqual(money('219.99'), 21999)
        for bad in ['NaN', 'Infinity', '-1', '1.001', 'abc']:
            with self.assertRaises(ValueError):
                money(bad)

    def test_backup_onto_itself_rejected(self):
        with self.assertRaises(ValueError):
            self.db.backup(self.db.path)


class MoneyInputTests(__import__('unittest').TestCase):
    def test_accepts_symbols_and_thousands(self):
        from tcg_alerts.core import money
        self.assertEqual(money('$1,299.50'), 129950)
        self.assertEqual(money(' A$ 45 '), 4500)
        self.assertEqual(money('12.5'), 1250)

    def test_rejects_ambiguous(self):
        from tcg_alerts.core import money
        for bad in ('12,50', '1,2,3', '-5', '1.234', 'abc'):
            with self.assertRaises(ValueError):
                money(bad)


class LinuxNotifyTests(__import__('unittest').TestCase):
    def test_notify_send_used_off_windows(self):
        from unittest import mock
        from tcg_alerts import desktop
        d = desktop.Desktop(None)
        with mock.patch.object(desktop.sys, 'platform', 'linux'), \
             mock.patch.object(desktop.shutil, 'which', return_value='/usr/bin/notify-send'), \
             mock.patch.object(desktop.subprocess, 'Popen') as popen:
            self.assertTrue(d.notify('Price drop'))
            self.assertEqual(popen.call_args[0][0][-1], 'Price drop')
        with mock.patch.object(desktop.sys, 'platform', 'linux'), mock.patch.object(desktop.shutil, 'which', return_value=None):
            self.assertFalse(d.notify('x'))
            self.assertIn('notify-send', d.error)
