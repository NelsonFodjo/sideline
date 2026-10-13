"""TLS context for outbound HTTPS. Always verifies; never disables.

python.org builds of Python on macOS ship without a CA bundle until
"Install Certificates.command" has been run, so every HTTPS call fails
with CERTIFICATE_VERIFY_FAILED even though the server is fine. A live
data feed is useless if that is the first thing a judge sees, so when the
default context has no CAs (it already honours SSL_CERT_FILE when set) we look
for a real bundle: certifi if installed, then the usual system locations.
"""

import os
import ssl

_SYSTEM_BUNDLES = ("/etc/ssl/cert.pem",                    # macOS
                   "/etc/ssl/certs/ca-certificates.crt",   # Debian, Ubuntu
                   "/etc/pki/tls/certs/ca-bundle.crt")     # RHEL, Amazon Linux


def _has_default_cas():
    p = ssl.get_default_verify_paths()
    return any(x and os.path.exists(x) for x in (p.cafile, p.capath))


def context():
    ctx = ssl.create_default_context()
    if _has_default_cas():
        return ctx
    candidates = []
    try:
        import certifi
        candidates.append(certifi.where())
    except ImportError:
        pass
    candidates.extend(_SYSTEM_BUNDLES)
    for path in candidates:
        if path and os.path.exists(path):
            return ssl.create_default_context(cafile=path)
    return ctx
