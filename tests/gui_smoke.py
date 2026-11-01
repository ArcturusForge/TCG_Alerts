"""Run under Xvfb on Linux; no storefront network access."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from tcg_alerts.core import Database, Observation
from tcg_alerts.app import App, WatchDialog

with tempfile.TemporaryDirectory() as directory:
    db = Database(Path(directory) / 'test.sqlite3')
    app = App(db, start_monitor=False)
    app.update()
    first = db.add('https://example.com/products/box', label='Riftbound box', group_name='English box', target=23000)
    db.record(first, Observation('Riftbound box', 22000, 'AUD', 'in_stock', 'fixture'))
    app.refresh()
    app.table.selection_set(str(first))
    app.selection()
    app.show_history()
    dialog = WatchDialog(app, db, app.refresh, db.watches()[0])
    app.update()
    dialog.destroy()
    for tab in app.tabs.tabs():
        app.tabs.select(tab)
        app.update()
    assert len(app.table.get_children()) == 1
    assert len(app.compare_table.get_children()) == 1
    assert len(app.alert_table.get_children()) == 1
    app.close()
print('GUI smoke passed')
