"""Authentication: the thing that stops one listener hearing another's
catch-up. Tokens are minted here with a throwaway key, so the verifier is
exercised against real signatures, not mocks of itself."""

import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request

from conftest import make_ctx

from sideline.auth import AuthError, Authenticator
from sideline.mcp import server as mcp_server
from sideline.tools import REGISTRY

ISS = "https://idp.example.test/pool"
AUD = "https://sideline.example.test/mcp"
SECRET = "test-secret-not-for-production"


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def hs256(claims, secret=SECRET, alg="HS256"):
    h = b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    p = b64(json.dumps(claims).encode())
    sig = hmac.new(secret.encode(), (h + "." + p).encode(), hashlib.sha256).digest()
    return h + "." + p + "." + b64(sig)


def good(**over):
    c = {"iss": ISS, "aud": AUD, "sub": "listener-42", "exp": time.time() + 600}
    c.update(over)
    return c


def rejects(auth, token, why):
    try:
        auth.verify(token)
    except AuthError as e:
        assert why in e.reason, (why, e.reason)
        return
    raise AssertionError("accepted a token that should fail: " + why)


def main():
    a = Authenticator(ISS, AUD, audience=AUD, hs256_secret=SECRET)

    assert a.verify(hs256(good()))["sub"] == "listener-42"
    print("ok  valid HS256 token accepted, sub becomes the listener id")

    rejects(a, hs256(good(), secret="wrong"), "signature")
    rejects(a, hs256(good(exp=time.time() - 3600)), "expired")
    rejects(a, hs256(good(iss="https://evil.test")), "issuer")
    rejects(a, hs256(good(aud="https://other.test/mcp")), "audience")
    rejects(a, hs256(good(sub="")), "subject")
    rejects(a, hs256(good(nbf=time.time() + 3600)), "not yet")
    rejects(a, "not.a.token", "malformed")
    # alg=none is the classic bypass
    h = b64(json.dumps({"alg": "none"}).encode())
    rejects(a, h + "." + b64(json.dumps(good()).encode()) + ".", "unsupported")
    print("ok  bad signature, expired, wrong iss/aud, no sub, nbf, malformed, alg=none all rejected")

    assert Authenticator(ISS, AUD, audience=AUD, hs256_secret=SECRET).verify(
        hs256(good(aud=["x", AUD])))["sub"]
    print("ok  aud may be a list")

    # Alexa's docs do not say tokens carry `aud`, so it is opt-in.
    lenient = Authenticator(ISS, AUD, hs256_secret=SECRET)
    c = good()
    c.pop("aud")
    assert lenient.verify(hs256(c))["sub"] == "listener-42"
    rejects(Authenticator(ISS, AUD, audience=AUD, hs256_secret=SECRET), hs256(c), "audience")
    print("ok  `aud` is only enforced when SIDELINE_AUTH_AUDIENCE is set")

    # ---- RS256 against a JWKS, if cryptography is here
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
    except ImportError:
        print("skip  RS256 (pip install cryptography to run)")
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nums = key.public_key().public_numbers()

        def i2b(n):
            return b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))

        jwks = {"keys": [{"kty": "RSA", "kid": "k1", "n": i2b(nums.n), "e": i2b(nums.e)}]}
        fetches = []

        def fetch(url):
            fetches.append(url)
            return jwks

        def rs(claims, kid="k1"):
            h = b64(json.dumps({"alg": "RS256", "kid": kid}).encode())
            p = b64(json.dumps(claims).encode())
            sig = key.sign((h + "." + p).encode(), padding.PKCS1v15(), hashes.SHA256())
            return h + "." + p + "." + b64(sig)

        r = Authenticator(ISS, AUD, audience=AUD, jwks_url="https://idp.example.test/jwks", fetch=fetch)
        assert r.verify(rs(good()))["sub"] == "listener-42"
        r.verify(rs(good()))
        assert len(fetches) == 1
        print("ok  RS256 verified against JWKS; keys cached, not refetched per call")

        tampered = rs(good()).rsplit(".", 1)[0] + "." + b64(b"x" * 256)
        rejects(r, tampered, "signature")
        rejects(r, rs(good(), kid="unknown"), "unknown signing key")
        print("ok  RS256 tampered signature and unknown kid rejected")

    # ---- over HTTP
    ctx = make_ctx(start_minute=40)

    def run_tool(name, args, listener):
        return REGISTRY[name](ctx, args, listener)

    port = 8793
    srv = mcp_server.serve("127.0.0.1", port, run_tool, lambda h: "shared", ["*"],
                           authenticator=Authenticator(ISS, AUD, audience=AUD, hs256_secret=SECRET,
                                                       scopes=["sideline.read"]))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    base = "http://127.0.0.1:%d" % port
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()

    def post(token=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + "/mcp", data=body, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    code, headers, _ = post()
    assert code == 401, code
    assert "WWW-Authenticate" not in headers, headers
    print("ok  no token -> 401 WITHOUT WWW-Authenticate (Alexa+'s QuickStart requires that)")

    assert post("garbage")[0] == 401
    assert post(hs256(good(), secret="wrong"))[0] == 401
    assert post(hs256(good()))[0] == 200
    print("ok  bad token -> 401, good token -> 200")

    with urllib.request.urlopen(base + "/.well-known/oauth-protected-resource") as r:
        meta = json.loads(r.read())
    assert meta["resource"] == AUD and meta["authorization_servers"] == [ISS]
    assert meta["scopes_supported"] == ["sideline.read"]
    print("ok  RFC 9728 protected-resource metadata served, no token needed")

    # two tokens, two listeners: the whole point
    seen = []
    srv.dispatcher.run_tool = lambda n, a, l: (seen.append(l) or ("", {}, None))
    for sub in ("alice", "bob"):
        call = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                           "params": {"name": "get_match_state", "arguments": {}}}).encode()
        req = urllib.request.Request(base + "/mcp", data=call, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + hs256(good(sub=sub))})
        urllib.request.urlopen(req, timeout=3).read()
    assert seen == ["alice", "bob"], seen
    print("ok  the listener id is the token's sub, not a header the caller chose")

    srv.shutdown()

    # constructing it badly is an error, not a silently open server
    for kw in ({"issuer": "", "resource": AUD, "hs256_secret": "s"},
               {"issuer": ISS, "resource": AUD}):
        try:
            Authenticator(**kw)
        except ValueError:
            continue
        raise AssertionError("misconfigured authenticator was accepted")
    print("ok  required mode with missing config refuses to start")

    print("\nauth: all good")


if __name__ == "__main__":
    main()
