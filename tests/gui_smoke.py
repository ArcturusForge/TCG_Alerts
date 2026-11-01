"""Run under Xvfb on Linux; no storefront network access."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from tcg_alerts.core import Database, Observation
from tcg_alerts.app import App, WatchDialog
from tcg_alerts.panels import NewsSources
from tcg_alerts.additions import Rules,VariantPicker,delivery_editor
from tcg_alerts.decks_ui import CardEditor,ListImport
from tcg_alerts.decks import parse_list
from unittest.mock import patch

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
    app.reset_filters()
    db.update(first,pack_count=24,shipping=1000,shipping_postcode='3000')
    app.compare_page.destination.set('3000');app.compare_page.refresh()
    assert app.compare_table.item(str(first),'values')[-1]=='9.58'
    app.directory_page.refresh()
    assert len(app.directory_page.table.get_children())==6
    app.directory_page.table.selection_set(str(db.stores()[0]['id']))
    app.directory_page.discover()
    assert app.tabs.select()==str(app.discovery_page)
    app.directory_page.edit(True)
    app.calendar_page.view.set('All entries');app.calendar_page.refresh()
    assert len(app.calendar_page.table.get_children())==4
    app.calendar_page.table.selection_set(str(db.releases()[0]['id']));app.calendar_page.edit(True)
    rules=Rules(app,db.stores()[0]);rules.add()
    delivery_editor(app,db.rows('SELECT * FROM watches WHERE id=?',(first,))[0])
    chosen=[]
    picker=VariantPicker(app,'https://fixture.example/products/box',chosen.append)
    picker.receive(picker.url.get(),[dict(title='Box',currency='AUD',price=20000,stock='in_stock',id='42',url='https://fixture.example/products/box?variant=42')],None)
    picker.table.selection_set('42');picker.select()
    assert chosen[0]['url'].endswith('?variant=42')
    with patch.object(app.desktop,'available',return_value=True):
        app.close_to_tray.set(True);app.request_close()
        assert app.winfo_exists() and app.state()=='withdrawn'
        app.deiconify();app.close_to_tray.set(False)
    with patch.object(app.desktop,'available',return_value=False):assert not app.minimize_to_tray()
    app.update()
    page=app.decks_page
    deck=page.store.save_deck('GUI fixture deck','Riftbound','AUD')
    page.store.import_rows(deck,parse_list('[Main]\n3 Fixture Card\n[Sideboard]\n1 Other Card'))
    page.refresh(deck)
    assert len(page.table.get_children())==2
    row=page.store.report(deck)['lines'][0]
    page.table.selection_set(str(row['id']));page.select()
    editor=CardEditor(page,row)
    editor.vars['manual_price'].set('5.00');editor.vars['reference_checked'].set('2026-11-02')
    editor.vars['owned'].set('1');editor.save()
    assert page.store.report(deck)['summary']['reference_subtotal']==1500
    page.store.snapshot(deck);page.history()
    importer=ListImport(page);importer.text.insert('1.0','2 New Fixture Card');importer.save()
    assert len(page.store.report(deck)['lines'])==3
    # Changing printing resets confirmation rather than reusing consent for another card variant.
    row=page.store.report(deck)['lines'][0]
    editor=CardEditor(page,row);editor.confirm.set(True);editor.vars['printing'].set('Foil')
    assert not editor.confirm.get() and not editor.vars['manual_price'].get();editor.destroy()
    page.table.selection_set(str(row['id']));page.select()
    from PIL import Image
    page.art_received(row['id'],page._art_token,Image.new('RGB',(180,250),'navy'),None)
    app.update()
    assert page.photo is not None
    old_token=page._art_token
    other=page.store.save_deck('Empty GUI deck','Riftbound');page.refresh(other)
    page.art_received(row['id'],old_token,Image.new('RGB',(180,250),'red'),None)
    assert page.art is None
    app.update()
    app.close()
print('GUI smoke passed')
