"""Run under Xvfb on Linux; no storefront network access."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from tcg_alerts.core import Database, Observation
from tcg_alerts.app import App, WatchDialog
from tcg_alerts.panels import NewsSources

with tempfile.TemporaryDirectory() as directory:
    db = Database(Path(directory) / 'test.sqlite3')
    app = App(db, start_monitor=False)
    app.update()
    first = db.add('https://example.com/products/box', label='Riftbound box', group_name='English box', target=23000,game='Riftbound',country='Australia',state='Victoria')
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
    second=db.add('https://other.example/products/box',label='Cyberpunk box',game='Cyberpunk',country='Australia',state='New South Wales')
    app.country_filter.set('Australia')
    app.state_filter.set('Victoria')
    app.game_filter.set('Riftbound')
    app.refresh()
    assert len(app.table.get_children()) == 1
    app.game_filter.set('Cyberpunk')
    app.refresh()
    assert len(app.table.get_children()) == 0
    app.analytics_page.metric.set('Checks per UTC day')
    app.analytics_page.refresh()  # empty geographic/game scope must render an empty state
    app.reset_filters()
    for mode in ('Item price','Checks per UTC day','Store-link opens per UTC day'):
        app.analytics_page.metric.set(mode)
        app.analytics_page.refresh()
        app.analytics_page.evidence()
        app.update()
    source=app.db.news_sources()[0]
    app.db.save_news(source['id'],[{'url':'https://playriftbound.com/en-us/news/announcements/test','title':'Fixture news','published':'2026-11-01T00:00:00+00:00','topic':'News'}],0)
    app.news_page.refresh()
    assert len(app.news_page.table.get_children()) == 1
    app.game_filter.set('Cyberpunk')
    app.news_page.refresh()
    assert len(app.news_page.table.get_children()) == 0
    sources=NewsSources(app)
    app.update()
    sources.destroy()
    app.close()
print('GUI smoke passed')
