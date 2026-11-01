import hashlib,json,tempfile,unittest,zipfile,queue
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.error import HTTPError
from urllib.request import Request
from tcg_alerts.updates import version,extract,Releases,install_version,ReleaseRedirect,UpdateCoordinator
from tcg_alerts.browser_helper import BrowserHelper
from tcg_alerts.sources import Client
from tcg_alerts.core import Database,Observation
from tcg_alerts.decks import DeckStore
from tcg_alerts.deck_alerts import evaluate


class UpdateTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def archive(self,files):
        path=self.root/'package.zip'
        with zipfile.ZipFile(path,'w') as out:
            for name,content in files:out.writestr(name,content)
        return path
    def test_versions_and_malicious_archives(self):
        self.assertGreater(version('v0.10.0'),version('0.9.0'))
        for value in ('latest','1.0','1.0.0-rc1','v1.0.0/../../bad'):
            with self.assertRaises(ValueError):version(value)
        for name in ('../outside.txt','/absolute.txt','C:/escape.exe','folder/../../bad'):
            with self.assertRaises(ValueError):extract(self.archive([(name,'bad')]),self.root/'out')
        self.assertFalse((self.root/'outside.txt').exists())
        with self.assertRaises(ValueError):extract(self.archive([('file','12345')]),self.root/'small',max_size=4)
    def test_checked_download_rejects_tampering_and_keeps_existing_file(self):
        asset=dict(id=1,size=5,url='https://api.github.com/repos/owner/repo/releases/assets/1',digest='sha256:'+hashlib.sha256(b'valid').hexdigest())
        client=Releases(token='test');client.open=Mock(return_value=BytesIO(b'wrong'));destination=self.root/'download.zip';destination.write_bytes(b'previous')
        with self.assertRaises(ValueError):client.download('owner/repo',asset,destination)
        self.assertEqual(destination.read_bytes(),b'previous');self.assertFalse(destination.with_suffix('.partial').exists())
        client.open=Mock(return_value=BytesIO(b'valid'));client.download('owner/repo',asset,destination);self.assertEqual(destination.read_bytes(),b'valid')
    def test_release_redirect_does_not_forward_credentials(self):
        req=Request('https://api.github.com/asset',headers={'Authorization':'Bearer secret'})
        redirected=ReleaseRedirect().redirect_request(req,None,302,'',{},'https://release-assets.githubusercontent.com/file')
        self.assertIsNone(redirected.get_header('Authorization'))
        with self.assertRaises(ValueError):ReleaseRedirect().redirect_request(req,None,302,'',{},'http://github.com/file')
    def test_version_install_is_atomic_on_failed_validation(self):
        archive=self.archive([('provider.py','broken')]);client=Mock(download=Mock(return_value=archive))
        with self.assertRaises(ValueError):install_version(client,'owner/repo',dict(tag_name='v1.0.0'),dict(name='plugin.zip',digest='sha256:x'),self.root/'versions',lambda p:(_ for _ in ()).throw(ValueError('missing manifest')))
        self.assertFalse((self.root/'versions/v1.0.0').exists());self.assertFalse(list((self.root/'versions').glob('.stage-*')))
    def test_plugin_update_retains_data_and_backup_and_rejects_scope_expansion(self):
        from tcg_alerts.plugins import PluginRegistry
        db=Database(self.root/'data.db');registry=PluginRegistry(self.root/'plugins',db)
        folder=registry.directory/'example';folder.mkdir()
        m=dict(api_version=1,id='example',name='Example',version='1.0.0',kind='catalogue-json',games=['Game'],api_url='https://cards.example/',fields={'id':'id','name':'name'},update=dict(repository='owner/repo',asset='plugin.zip'))
        (folder/'plugin.json').write_text(json.dumps(m));(folder/'data').mkdir();(folder/'data/user.txt').write_text('keep');registry.reload()
        app=Mock(db=db,plugins=registry);coordinator=UpdateCoordinator(app)
        new=dict(m,version='1.1.0');archive=self.archive([('plugin.json',json.dumps(new))])
        client=Mock();client.latest.return_value=dict(tag_name='v1.1.0',assets=[dict(name='plugin.zip',digest='sha256:fixture')]);client.download.return_value=archive
        with patch('tcg_alerts.updates.Releases',return_value=client):
            coordinator.update_plugins()
        self.assertEqual(json.loads((folder/'plugin.json').read_text())['version'],'1.1.0');self.assertEqual((folder/'data/user.txt').read_text(),'keep')
        registry.reload();self.assertEqual(len(registry.entries),1);self.assertTrue(folder.with_name('example.previous').exists())
        # Repeated checks use the installed version, not a stale loaded manifest.
        app.plugins=registry
        with patch('tcg_alerts.updates.Releases',return_value=client):self.assertEqual(coordinator.update_plugins(),[])
    def test_failed_python_update_recovers_previous_version_and_remembers_failure(self):
        from tcg_alerts.plugins import PluginRegistry
        db=Database(self.root/'rollback.db');registry=PluginRegistry(self.root/'rollback_plugins',db)
        current=registry.directory/'reader';old=registry.directory/'reader.previous';current.mkdir();old.mkdir()
        manifest=dict(api_version=1,id='reader',name='Reader',version='1.1.0',kind='python',games=['Game'],capabilities=['catalogue'])
        (current/'plugin.json').write_text(json.dumps(manifest));(current/'provider.py').write_text('raise RuntimeError("new plugin fails")')
        (old/'plugin.json').write_text(json.dumps(dict(manifest,version='1.0.0')))
        (old/'provider.py').write_text('class Provider:\n def search_cards(self,game,query,client):return []\ndef create_plugin(context):return Provider()\n')
        db.set_setting('enabled_plugins',['reader']);registry.reload()
        self.assertEqual(len(registry.active),1);self.assertEqual(registry.entries[0]['version'],'1.0.0');self.assertEqual(db.setting('failed_plugin_updates')['reader'],'1.1.0')

    def test_browser_fallback_keeps_robot_policy_and_skips_rate_limit(self):
        helper=Mock();helper.solve.return_value='<html>product</html>';client=Client(spacing=0,browser_helper=helper)
        def raw(url):
            if url.endswith('/robots.txt'):return 'User-agent: *\nAllow: /'
            raise HTTPError(url,403,'blocked',{},None)
        client.raw=Mock(side_effect=raw);self.assertEqual(client.get('https://store.example/product'),'<html>product</html>');helper.solve.assert_called_once()
        helper.reset_mock();client.raw=Mock(side_effect=HTTPError('https://store.example/product',429,'rate limited',{},None))
        with self.assertRaises(HTTPError):client.get('https://store.example/product')
        helper.solve.assert_not_called()
        denied=Client(browser_helper=helper);denied.raw=Mock(return_value='User-agent: *\nDisallow: /')
        with self.assertRaises(ValueError):denied.get('https://store.example/product')
        helper.solve.assert_not_called()
    def test_budget_requires_all_missing_prices_and_deduplicates_transitions(self):
        db=Database(self.root/'budget.db');store=DeckStore(db);deck=store.save_deck('Deck','Riftbound')
        w=db.add('https://store.example/products/card',game='Riftbound');db.record(w,Observation('Card',500,'AUD','in_stock','Fixture'))
        store.save_entry(deck,dict(name='Card',quantity=3,owned=1,watch_id=w,listing_confirmed=True))
        db.set_setting('deck_budget_'+str(deck),dict(enabled=True,currency='AUD',amount=1000,active=False))
        self.assertEqual(len(evaluate(db)),1);self.assertEqual(evaluate(db),[])
        db.fail(w,'offline',0);self.assertEqual(evaluate(db),[])
        db.record(w,Observation('Card',450,'AUD','in_stock','Fixture'));self.assertEqual(len(evaluate(db)),1)
        store.save_entry(deck,dict(name='Unpriced',quantity=1));self.assertEqual(evaluate(db),[])
