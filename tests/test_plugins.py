import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from tcg_alerts.plugins import PluginRegistry,validate_manifest,json_cards
from tcg_alerts.core import Database,Observation


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=Database(self.root/'data.db');self.registry=PluginRegistry(self.root/'plugins',self.db)
    def tearDown(self):self.tmp.cleanup()
    def manifest(self,**changes):return dict(api_version=1,id='custom-game',name='Custom TCG catalogue',kind='catalogue-json',games=['A new TCG'],api_url='https://cards.example/search',query_parameter='name',results_path='data.cards',fields=dict(id='key',name='title',image_url='art.url'),**changes)
    def install(self,manifest,code=None):
        folder=self.registry.directory/manifest['id'];folder.mkdir(exist_ok=True);(folder/'plugin.json').write_text(json.dumps(manifest))
        if code:(folder/'provider.py').write_text(code)
        self.registry.reload();return folder
    def test_json_provider_adds_an_arbitrary_game_without_recompile(self):
        self.install(self.manifest());self.assertEqual(self.registry.providers('A new TCG'),[])
        self.registry.enable('custom-game',True);self.assertIn('A new TCG',self.registry.games())
        self.assertEqual(self.registry.providers('A new TCG')[0]['id'],'custom-game')
        client=Mock();client.get.return_value=json.dumps(dict(data=dict(cards=[dict(key='001',title='New hero',art=dict(url='https://img.example/card.webp'),price=999)])))
        rows=json_cards(self.manifest(),'Hero & Me','A new TCG',client)
        self.assertIn('name=Hero+%26+Me',client.get.call_args[0][0]);self.assertEqual(rows[0]['name'],'New hero');self.assertNotIn('manual_price',rows[0])
        self.registry.enable('custom-game',False);self.assertEqual(self.registry.providers('A new TCG'),[])
    def test_python_plugin_not_executed_until_enabled_and_reload_isolated(self):
        marker=self.root/'executed'
        manifest=dict(api_version=1,id='reader',name='Reader',kind='python',games=['*'],capabilities=['store'],hosts=['store.example'])
        code=f"from pathlib import Path\nPath({str(marker)!r}).write_text('yes')\nfrom tcg_alerts.core import Observation\nclass Provider:\n def fetch_product(self,url,client):return Observation('Plugin card',123,'AUD','in_stock','Test')\ndef create_plugin(context):return Provider()\n"
        folder=self.install(manifest,code);self.assertFalse(marker.exists());self.registry.enable('reader',True);self.assertTrue(marker.exists())
        result=self.registry.fetch('https://store.example/card',Mock());self.assertEqual(result.price,123);self.assertIn('Reader',result.source)
        with patch('tcg_alerts.plugins.builtin_fetch',return_value='fallback') as fallback:
            self.assertEqual(self.registry.fetch('https://other.example/card',Mock()),'fallback');fallback.assert_called_once()
        (folder/'provider.py').write_text('raise RuntimeError("broken provider")');self.registry.reload()
        self.assertEqual(self.registry.active,());self.assertIn('broken provider',self.registry.entries[0]['error'])
    def test_invalid_manifests_and_bad_payloads_are_rejected(self):
        for change in ({'api_version':99},{'id':'../bad'},{'api_url':'file:///secret'},{'fields':{'name':'title'}}):
            manifest=self.manifest();manifest.update(change)
            with self.assertRaises(ValueError):validate_manifest(manifest)
        with self.assertRaises(ValueError):json_cards(self.manifest(),'hero','A new TCG',Mock(get=Mock(return_value='{}')))
    def test_invalid_plugin_does_not_block_builtin_game(self):
        folder=self.registry.directory/'bad';folder.mkdir();(folder/'plugin.json').write_text('{broken')
        self.registry.reload();self.assertTrue(self.registry.entries[0]['error']);self.assertEqual(self.registry.providers('Riftbound')[0]['id'],'openrift')
