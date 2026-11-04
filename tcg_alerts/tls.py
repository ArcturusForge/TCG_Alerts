"""Verified TLS contexts that work in packaged Linux builds.

Frozen executables carry an OpenSSL whose default CA path often does not
exist on the user's distro, which shows up as CERTIFICATE_VERIFY_FAILED.
We keep verification on and add trust anchors from the system bundle,
SSL_CERT_FILE, and certifi when installed.
"""
from __future__ import annotations
import os
import ssl
from functools import lru_cache
from urllib import request

LINUX_BUNDLES = (
    '/etc/ssl/certs/ca-certificates.crt',  # Debian/Ubuntu/Arch
    '/etc/pki/tls/certs/ca-bundle.crt',  # Fedora/RHEL
    '/etc/ssl/ca-bundle.pem',  # openSUSE
    '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
    '/etc/ssl/cert.pem',  # Alpine/macOS
)


def ca_sources():
    found = []
    env = os.environ.get('SSL_CERT_FILE')
    if env and os.path.isfile(env):
        found.append(env)
    found += [p for p in LINUX_BUNDLES if os.path.isfile(p)]
    try:
        import certifi
        found.append(certifi.where())
    except ImportError:
        pass
    return list(dict.fromkeys(found))


@lru_cache(maxsize=1)
def context():
    ctx = ssl.create_default_context()
    for path in ca_sources():
        try:
            ctx.load_verify_locations(cafile=path)
        except (OSError, ssl.SSLError):
            continue
    return ctx


def https_handler():
    return request.HTTPSHandler(context=context())


def diagnostics():
    paths = ssl.get_default_verify_paths()
    return {'openssl': ssl.OPENSSL_VERSION, 'default_cafile': paths.cafile,
            'extra_bundles': ca_sources(), 'loaded_certificates': context().cert_store_stats().get('x509_ca', 0)}


def probe(url, timeout=10):
    """Open a TLS connection to url's host and return '' or a readable reason."""
    import socket
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname
    try:
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            with context().wrap_socket(raw, server_hostname=host):
                return ''
    except ssl.SSLCertVerificationError as e:
        return f'{host}: certificate rejected ({e.verify_message or e.reason})'
    except (OSError, ssl.SSLError) as e:
        return f'{host}: {e}'


def report(urls):
    d = diagnostics()
    lines = [f"OpenSSL: {d['openssl']}", f"Default CA file: {d['default_cafile']}",
             f"Extra CA bundles: {', '.join(d['extra_bundles']) or 'none found'}",
             f"Trusted root certificates loaded: {d['loaded_certificates']}", '']
    for url in dict.fromkeys(urls):
        lines.append(probe(url) or f'{url}: OK')
    return '\n'.join(lines)
