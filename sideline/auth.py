"""Bearer-token authentication for the MCP endpoint. Standard library,
plus the `cryptography` package only if you verify RS256 tokens.

WHY THIS EXISTS

Listener state is keyed on one id. Without authentication every caller
is the same listener, so one person's catch-up window would be another's.
Alexa+ account linking (OAuth 2.1) hands us a bearer token; this module
verifies it and returns its `sub` claim as the listener id.

WHAT ALEXA+ ACTUALLY REQUIRES (developer.amazon.com, MCP QuickStart and
"Account Linking for MCP Add-ons", read 2026-10-12)

  * Unauthenticated requests get 401 (or 403) WITHOUT a WWW-Authenticate
    header. The QuickStart lists WWW-Authenticate in 401 responses as not
    yet supported, so sending one is a deviation, and we do not. This
    differs from the generic MCP spec, which expects it.
  * Protected Resource Metadata (RFC 9728) at
    /.well-known/oauth-protected-resource: `resource` (must exactly
    match the URL in your add-on manifest), `authorization_servers`
    (Alexa uses only the first) and `scopes_supported`.
  * The authorization server, not this server, must do OAuth 2.1 code
    flow with PKCE S256, issue refresh tokens, use static client
    registration (no DCR), and publish
    /.well-known/oauth-authorization-server with
    code_challenge_methods_supported containing S256.
  * Bearer token in the Authorization header only, never the query.
  * Account linking is optional; it is needed here only because listener
    state is per person.
Nothing in Alexa's published docs says tokens carry an `aud` claim or a
`sub` claim. We require `sub` (it is the listener id) and enforce `aud`
only if you configure SIDELINE_AUTH_AUDIENCE.

MODES (SIDELINE_AUTH)

  off       default. No tokens required. Listener identity comes from the
            X-Sideline-Listener header, else one shared id. Fine for the
            local demo and the simulator; unsafe for several real people.
  required  every /mcp request needs a valid bearer token.

WHAT IS VERIFIED

  signature   RS256 (keys from SIDELINE_AUTH_JWKS_URL, cached) or HS256
              (shared secret, SIDELINE_AUTH_HS256_SECRET - for tests).
              Anything else, including alg=none, is rejected.
  exp / nbf   with 60 s of clock skew.
  iss         must equal SIDELINE_AUTH_ISSUER.
  aud         must contain SIDELINE_AUTH_AUDIENCE, if that is set.
  sub         must be present; it becomes the listener id.

Not here: issuing tokens, the login page, client registration. Those are
the authorization server's job; this server is only the resource server.
"""

import base64
import json
import logging
import hmac
import hashlib
import time
import urllib.request

LOG = logging.getLogger("sideline.auth")

SKEW = 60
JWKS_TTL = 3600


class AuthError(Exception):
    """Token missing or invalid. `reason` is for logs, never for the caller."""

    def __init__(self, reason, status=401):
        Exception.__init__(self, reason)
        self.reason = reason
        self.status = status


def _b64(seg):
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def _int(seg):
    return int.from_bytes(_b64(seg), "big")


class Authenticator:
    def __init__(self, issuer, resource, audience="", jwks_url="", hs256_secret="",
                 scopes=(), fetch=None):
        if not issuer or not resource:
            raise ValueError("SIDELINE_AUTH=required needs SIDELINE_AUTH_ISSUER "
                             "and SIDELINE_PUBLIC_URL (the canonical https URL "
                             "of this server's /mcp, as in the add-on manifest)")
        if not jwks_url and not hs256_secret:
            raise ValueError("SIDELINE_AUTH=required needs SIDELINE_AUTH_JWKS_URL "
                             "(RS256) or SIDELINE_AUTH_HS256_SECRET")
        self.issuer = issuer
        self.resource = resource
        self.audience = audience          # "" = do not check `aud`
        self.jwks_url = jwks_url
        self.secret = hs256_secret.encode() if hs256_secret else b""
        self.scopes = list(scopes)
        self._fetch = fetch or self._http_get_json
        self._jwks = None
        self._jwks_at = 0.0

    # ------------------------------------------------------ discovery
    def protected_resource_metadata(self):
        doc = {"resource": self.resource,
               "authorization_servers": [self.issuer],
               "bearer_methods_supported": ["header"]}
        if self.scopes:
            doc["scopes_supported"] = self.scopes
        return doc

    # --------------------------------------------------------- verify
    def authenticate(self, headers):
        """Returns the listener id (`sub`) or raises AuthError."""
        auth = headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            raise AuthError("no bearer token")
        return self.verify(auth[7:].strip())["sub"]

    def verify(self, token):
        try:
            h64, p64, s64 = token.split(".")
            header = json.loads(_b64(h64))
            claims = json.loads(_b64(p64))
            sig = _b64(s64)
        except (ValueError, TypeError):
            raise AuthError("malformed token")
        signed = (h64 + "." + p64).encode()
        alg = header.get("alg")

        if alg == "HS256" and self.secret:
            want = hmac.new(self.secret, signed, hashlib.sha256).digest()
            if not hmac.compare_digest(want, sig):
                raise AuthError("bad signature")
        elif alg == "RS256" and self.jwks_url:
            self._verify_rs256(header.get("kid"), signed, sig)
        else:
            raise AuthError("unsupported alg %r" % alg)

        now = time.time()
        if "exp" not in claims or now > float(claims["exp"]) + SKEW:
            raise AuthError("expired")
        if "nbf" in claims and now < float(claims["nbf"]) - SKEW:
            raise AuthError("not yet valid")
        if claims.get("iss") != self.issuer:
            raise AuthError("wrong issuer")
        if self.audience:
            aud = claims.get("aud")
            auds = aud if isinstance(aud, list) else [aud]
            if self.audience not in auds:
                raise AuthError("wrong audience")
        if not claims.get("sub"):
            raise AuthError("no subject")
        return claims

    def _verify_rs256(self, kid, signed, sig):
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding, rsa
            from cryptography.exceptions import InvalidSignature
        except ImportError:
            raise AuthError("RS256 needs `pip install cryptography`", 500)
        key = self._key_for(kid)
        if key is None:
            raise AuthError("unknown signing key")
        pub = rsa.RSAPublicNumbers(_int(key["e"]), _int(key["n"])).public_key()
        try:
            pub.verify(sig, signed, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            raise AuthError("bad signature")

    def _key_for(self, kid):
        for refresh in (False, True):
            if refresh or self._jwks is None or time.time() - self._jwks_at > JWKS_TTL:
                try:
                    self._jwks = self._fetch(self.jwks_url)
                    self._jwks_at = time.time()
                except Exception as e:                         # noqa: BLE001
                    LOG.warning("could not fetch JWKS: %s", e)
                    if self._jwks is None:
                        raise AuthError("signing keys unavailable", 503)
            for k in self._jwks.get("keys", []):
                if k.get("kty") == "RSA" and (kid is None or k.get("kid") == kid):
                    return k
            # kid not found: keys may have rotated, refetch once.
        return None

    @staticmethod
    def _http_get_json(url):
        with urllib.request.urlopen(url, timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))


def build(cfg):
    """Authenticator when SIDELINE_AUTH=required, else None."""
    if cfg.auth != "required":
        return None
    return Authenticator(cfg.auth_issuer, cfg.public_url,
                         audience=cfg.auth_audience,
                         jwks_url=cfg.auth_jwks_url,
                         hs256_secret=cfg.auth_hs256_secret,
                         scopes=[x for x in cfg.auth_scopes.replace(",", " ").split() if x])
