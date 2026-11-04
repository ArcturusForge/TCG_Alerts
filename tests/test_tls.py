import ssl, unittest
from unittest import mock
from tcg_alerts import tls


class TLSTests(unittest.TestCase):
    def test_context_verifies(self):
        ctx = tls.context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_env_bundle_first_and_missing_ignored(self):
        with mock.patch.dict('os.environ', {'SSL_CERT_FILE': '/nope.pem'}):
            self.assertNotIn('/nope.pem', tls.ca_sources())

    def test_diagnostics(self):
        self.assertIn('loaded_certificates', tls.diagnostics())


if __name__ == '__main__':
    unittest.main()
