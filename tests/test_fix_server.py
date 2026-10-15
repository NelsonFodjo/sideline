"""Regressions for the MCP server core and config fixes (docs/BUGS.md, MCP-01..22 and CFG-01/02/03).

Raw sockets where the bug lives below what urllib can show: a hung read, a body
parsed as the next request, a connection that never ends.
"""

import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from conftest import make_ctx

from sideline import audit, envfile
from sideline.app import resolve_listener, tool_runner
from simulator.host import local_url as _local_url
from sideline.config import Config, ConfigError
from sideline.mcp import registry
from sideline.mcp import server as mcp_server
from sideline.mcp.errors import InvalidParams
from sideline.mcp.schema import validate

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SEEN = {}


def runner(question, listener_id, tz=None, cut=None, name=None):
    SEEN.update(question=question, tz=tz, cut=cut, name=name)
    if question == "explode":
        raise RuntimeError("boom")
    return {"text": "answer", "generated_by": "nova", "tool_results": []}


def _start(origins, agent=None):
    srv = mcp_server.serve("127.0.0.1", 0, tool_runner(make_ctx(start_minute=40)), resolve_listener,
                           origins, agent_runner=agent)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def raw(port, data, wait=3.0):
    """Send bytes; return everything the server sends until it closes (or `wait` passes)."""
    s = socket.create_connection(("127.0.0.1", port), timeout=wait)
    s.sendall(data)
    out, deadline = b"", time.time() + wait
    try:
        while time.time() < deadline:
            chunk = s.recv(65536)
            if not chunk:
                return out, True              # closed by the server
            out += chunk
    except socket.timeout:
        pass
    finally:
        s.close()
    return out, False


def http(port, method, path, body=None, headers=None):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data, h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            text = r.read()
            return r.status, (json.loads(text) if text else None), r.headers
    except urllib.error.HTTPError as e:
        text = e.read()
        try:
            doc = json.loads(text) if text else None
        except ValueError:
            doc = None
        return e.code, doc, e.headers


def init(port, params=None):
    return http(port, "POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                       "params": {"protocolVersion": "2025-11-25"} if params is None else params})


def rpc(port, sid, method, params=None, mid=2, extra=None):
    h = {"Mcp-Session-Id": sid} if sid else {}
    h.update(extra or {})
    msg = {"jsonrpc": "2.0", "id": mid, "method": method}
    if params is not None:
        msg["params"] = params
    return http(port, "POST", "/mcp", msg, h)


def check_body_guard(port):
    # MCP-01: a negative, non-numeric or oversized Content-Length is refused at once, and closed.
    for path in ("/mcp", "/agent/chat", "/voice/tts", "/voice/stt"):
        for bad in ("-1", "abc", "1_0", "+5"):
            out, closed = raw(port, ("POST %s HTTP/1.1\r\nHost: x\r\nContent-Length: %s\r\n\r\n" % (path, bad)).encode())
            assert out.startswith(b"HTTP/1.1 400"), (path, bad, out[:80])
            assert closed, "the connection is closed after an early error (%s %s)" % (path, bad)
    out, closed = raw(port, b"POST /mcp HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n" % (2 * 1024 * 1024))
    assert out.startswith(b"HTTP/1.1 413") and closed, out[:80]
    out, closed = raw(port, b"POST /mcp HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n")
    assert out.startswith(b"HTTP/1.1 411") and closed, out[:80]
    print("ok  MCP-01 Content-Length -1 / non-numeric / oversized / chunked: 400/413/411 at once, connection closed")

    # MCP-02: a request hidden in the body of a refused request is never run.
    hidden = b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n"
    for path in (b"/mcp", b"/agent/chat", b"/voice/tts", b"/voice/stt"):
        req = (b"POST " + path + b" HTTP/1.1\r\nHost: x\r\nOrigin: https://evil.example\r\n"
               b"Content-Length: %d\r\n\r\n" % len(hidden)) + hidden
        out, closed = raw(port, req)
        assert out.startswith(b"HTTP/1.1 403") and closed, out[:80]
        assert out.count(b"HTTP/1.1 ") == 1 and b'"ok": true' not in out, "smuggled request answered: %r" % out
    # ...and a body sent with a GET is not taken for the next request either
    out, closed = raw(port, b"GET /health HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n" % len(hidden) + hidden)
    assert out.count(b"HTTP/1.1 200") == 1 and closed, out
    print("ok  MCP-02 a request smuggled in the body of a refused (or GET) request is never parsed")


def check_origins(port):
    # MCP-03: scheme, host and port all count.
    own = "http://127.0.0.1:%d" % port
    assert init(port)[0] == 200, "no Origin (Alexa+) is allowed"
    code, _, hdr = http(port, "POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, {"Origin": own})
    assert code == 200 and hdr["Access-Control-Allow-Origin"] == own, code
    assert http(port, "POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                {"Origin": "http://localhost:%d" % port})[0] == 200
    for bad in ("http://localhost:31337", "https://127.0.0.1:%d" % port, "http://127.0.0.1",
                "null", "http://127.0.0.1.evil.example:%d" % port, "garbage"):
        code, _, hdr = http(port, "POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, {"Origin": bad})
        assert code == 403 and "Access-Control-Allow-Origin" not in hdr, (bad, code)
    print("ok  MCP-03 Origin compared as scheme+host+port: other localhost ports and https are refused")

    keys, anyone = mcp_server.allowed_origin_keys(["localhost", "https://judge.example:8443", "*x"], "127.0.0.1", 9000)
    assert ("http", "localhost", 9000) in keys and ("https", "judge.example", 8443) in keys and not anyone
    assert ("http", "127.0.0.1", 9000) in keys, "the bound address is the simulator's own origin"
    assert mcp_server.origin_key("https://judge.example") == ("https", "judge.example", 443)
    print("ok  SIDELINE_ALLOWED_ORIGINS takes full origins or bare hosts (on this port)")


def check_sessions_and_versions(port):
    code, doc, hdr = init(port)
    sid = hdr["Mcp-Session-Id"]

    # MCP-07: required after initialize
    code, doc, _ = rpc(port, None, "tools/list")
    assert code == 400 and doc["error"]["code"] == -32600, (code, doc)
    assert rpc(port, "nope", "tools/list")[0] == 404
    assert rpc(port, sid, "tools/list")[0] == 200
    print("ok  MCP-07 no Mcp-Session-Id after initialize -> 400; unknown -> 404")

    # MCP-08: MCP-Protocol-Version checked when present
    assert rpc(port, sid, "ping", extra={"MCP-Protocol-Version": "2025-11-25"})[0] == 200
    assert rpc(port, sid, "ping", extra={"MCP-Protocol-Version": "1999-01-01"})[0] == 400
    print("ok  MCP-08 unsupported MCP-Protocol-Version -> 400; the negotiated one and none pass")

    # MCP-20: the query string is not part of the route
    code, doc, _ = http(port, "POST", "/mcp?x=1", {"jsonrpc": "2.0", "id": 3, "method": "ping"}, {"Mcp-Session-Id": sid})
    assert code == 200 and doc["result"] == {}, code
    assert http(port, "GET", "/health?x=1")[0] == 200
    print("ok  MCP-20 /mcp?x=1 and /health?x=1 route normally")

    # MCP-16: invalid messages are 400; a client response is 202
    for bad in (5, {"id": 4, "method": "ping"}, {"jsonrpc": "2.0", "id": None, "method": "ping"},
                {"jsonrpc": "2.0", "id": True, "method": "ping"}, {"jsonrpc": "2.0"}):
        code, doc, _ = http(port, "POST", "/mcp", bad, {"Mcp-Session-Id": sid})
        assert code == 400 and doc["error"]["code"] == -32600, (bad, code, doc)
    code, doc, _ = http(port, "POST", "/mcp", {"jsonrpc": "2.0", "id": 9, "result": {}}, {"Mcp-Session-Id": sid})
    assert code == 202 and doc is None, code
    assert http(port, "POST", "/mcp", {"jsonrpc": "2.0", "method": "notifications/cancelled"},
                {"Mcp-Session-Id": sid})[0] == 202
    print("ok  MCP-16 5, no jsonrpc, null/boolean id -> 400 -32600; a client response -> 202")

    # MCP-17: batches refused
    code, doc, hdr = http(port, "POST", "/mcp", [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])
    assert code == 400 and not hdr.get("Mcp-Session-Id"), code
    print("ok  MCP-17 JSON-RPC batches -> 400")

    # MCP-18: non-object params -> -32602, and a failed initialize mints no session
    before = len(srv_sessions)
    code, doc, hdr = init(port, params=[])
    assert doc["error"]["code"] == -32602 and not hdr.get("Mcp-Session-Id"), doc
    code, doc, _ = rpc(port, sid, "tools/call", params="x")
    assert doc["error"]["code"] == -32602, doc
    # MCP-05: neither does a notification-style initialize
    code, _, hdr = http(port, "POST", "/mcp", {"jsonrpc": "2.0", "method": "initialize"})
    assert code == 400 and not hdr.get("Mcp-Session-Id")
    assert len(srv_sessions) == before, "no session for a failed or notification initialize"
    print("ok  MCP-18 non-object params -> -32602; MCP-05 failed/notification initialize mints no session")

    # MCP-19: DELETE checks Origin, needs a session, 404 for an unknown one
    assert http(port, "DELETE", "/mcp", headers={"Mcp-Session-Id": sid, "Origin": "https://evil.example"})[0] == 403
    assert http(port, "DELETE", "/mcp")[0] == 400
    assert http(port, "DELETE", "/mcp", headers={"Mcp-Session-Id": "nope"})[0] == 404
    assert http(port, "DELETE", "/mcp", headers={"Mcp-Session-Id": sid})[0] == 204
    assert http(port, "DELETE", "/mcp", headers={"Mcp-Session-Id": sid})[0] == 404
    code, _, hdr = http(port, "OPTIONS", "/mcp", headers={"Origin": "http://127.0.0.1:%d" % port})
    assert code == 204 and "DELETE" in hdr["Access-Control-Allow-Methods"], hdr
    for h in ("X-Interrupted", "X-Tz-Offset", "X-Tz-Name", "X-Run-Agent", "X-Audio-Type", "X-Sideline-Agent"):
        assert h in hdr["Access-Control-Allow-Headers"], h
    print("ok  MCP-19 DELETE: 403 foreign origin, 400 no session, 404 unknown; preflight lists DELETE and X-*")


def check_session_table():
    # MCP-05: capped, swept, and expiry counts from the last request, not from creation.
    s = mcp_server.Sessions(idle_seconds=100, limit=3)
    ids = [s.create() for _ in range(5)]
    assert len(s) == 3 and not s.touch(ids[0]) and s.touch(ids[4]), "the least recently used go first"
    s._s[ids[4]]["created"] -= 10 ** 6                 # old, but active
    assert s.touch(ids[4]), "an active session does not die of age"
    s._s[ids[3]]["seen"] -= 101                        # idle
    assert not s.known(ids[3]) and not s.touch(ids[3])
    s._s[ids[2]]["seen"] -= 101
    s.create()
    assert ids[2] not in s._s, "expired sessions are swept on create"
    print("ok  MCP-05 session table capped, swept on create, expiry from last use")


def check_event_stream(port):
    # MCP-04 / MCP-06: GET /mcp needs a session, ends with EOF, and the streams are capped.
    out, closed = raw(port, b"GET /mcp HTTP/1.1\r\nHost: x\r\n\r\n")
    assert out.startswith(b"HTTP/1.1 400") and closed, out[:60]
    sid = init(port)[2]["Mcp-Session-Id"].encode()
    old = mcp_server.EVENT_STREAM_SECONDS
    mcp_server.EVENT_STREAM_SECONDS = 0.5
    try:
        out, closed = raw(port, b"GET /mcp HTTP/1.1\r\nHost: x\r\nMcp-Session-Id: " + sid + b"\r\n\r\n", wait=5)
    finally:
        mcp_server.EVENT_STREAM_SECONDS = old
    assert out.startswith(b"HTTP/1.1 200") and b"text/event-stream" in out and b": keepalive" in out, out[:200]
    assert b"Connection: close" in out and closed, "the client sees the end of the stream"
    assert mcp_server.Handler.timeout and mcp_server.Handler.timeout <= 60, "idle sockets do not pin threads"

    # an idle keep-alive connection is dropped by the socket timeout
    old_t = mcp_server.Handler.timeout
    mcp_server.Handler.timeout = 0.5
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        t0 = time.time()
        assert s.recv(10) == b"" and time.time() - t0 < 4, "idle connection closed by the server"
        s.close()
    finally:
        mcp_server.Handler.timeout = old_t
    print("ok  MCP-04/06 SSE needs a session, closes the connection when it ends; idle sockets time out")


def check_tools(port):
    sid = init(port)[2]["Mcp-Session-Id"]
    code, doc, _ = init(port)
    caps = doc["result"]["capabilities"]
    assert caps == {"tools": {"listChanged": False}}, caps
    # MCP-22
    info, text = doc["result"]["serverInfo"], doc["result"]["instructions"]
    assert "football" not in info["title"].lower() and "basketball" in text and "hockey" in text, (info, text)
    print("ok  MCP-14 no experimental.mcpApps claim; MCP-22 title and instructions are sport-neutral")

    tools = rpc(port, sid, "tools/list")[1]["result"]["tools"]
    assert not any("_meta" in t for t in tools), "no tool points at an MCP Apps resource"
    rpc(port, sid, "tools/call", {"name": "follow_match", "arguments": {"team": "Arsenal"}})
    res = rpc(port, sid, "tools/call", {"name": "get_match_state", "arguments": {}})[1]["result"]
    assert "ui" not in res["_meta"] and res["_meta"]["sideline"]["ui"]["home"], res["_meta"]
    print("ok  MCP-14 tool definitions carry no _meta.ui; card data is under _meta.sideline.ui")

    # MCP-11: fixture ids as numbers or digit strings
    fx = registry.by_name("get_match_state")["inputSchema"]
    for good in ({"fixture_id": 1208341}, {"fixture_id": "1208341"}, {"fixture_id": "401915417"}):
        validate(good, fx)
    for bad in ({"fixture_id": "abc"}, {"fixture_id": 0}, {"fixture_id": "0"}, {"fixture_id": True},
                {"fixture_id": "12 34"}, {"fixture_id": 1.5}):
        try:
            validate(bad, fx)
        except InvalidParams:
            continue
        raise AssertionError("accepted %r" % bad)
    print("ok  MCP-11 fixture_id accepts an integer or a digit string, nothing else")

    # MCP-10: maxItems
    fav = registry.by_name("set_favourites")["inputSchema"]
    try:
        validate({"teams": ["T%d" % i for i in range(50)]}, fav)
        raise AssertionError("50 favourites accepted")
    except InvalidParams:
        pass
    code, doc, _ = rpc(port, sid, "tools/call", {"name": "set_favourites",
                                                 "arguments": {"teams": ["T%d" % i for i in range(50)]}})
    assert doc["result"]["isError"] and doc["result"]["structuredContent"]["reason"] == "invalid_arguments", doc
    print("ok  MCP-10 maxItems is enforced (set_favourites with 50 teams refused)")

    # MCP-15: a tool hidden from tools/list does not answer tools/call
    registry.limit_to({"fixtures"})
    try:
        assert registry.by_name("get_lineups") is None and registry.by_name("get_match_state")
        code, doc, _ = rpc(port, sid, "tools/call", {"name": "get_lineups", "arguments": {}})
        assert doc["error"]["code"] == -32602, doc
    finally:
        registry.limit_to(None)
    print("ok  MCP-15 by_name honours available(): hidden tools cannot be called")


def check_agent_context(port):
    from simulator import voice
    logging.getLogger("sideline.mcp").setLevel(logging.CRITICAL)   # the failures below are on purpose
    real = voice.transcribe
    voice.transcribe = lambda audio, mime, hint="": {"provider": "test", "text": SEEN.get("next", "score?")}
    try:
        def stt(headers):
            h = {"X-Run-Agent": "1", "X-Audio-Type": "audio/pcm;rate=16000"}
            h.update(headers)
            return http(port, "POST", "/voice/stt", b"\0" * 32, h)

        # MCP-12: same validation as /agent/chat, X-Interrupted percent-decoded, tz_name passed through
        code, doc, _ = stt({"X-Tz-Offset": "2000", "X-Interrupted": "x" * 5000, "X-Tz-Name": "../etc/passwd"})
        assert code == 200 and doc["chat"]["text"] == "answer"
        assert SEEN["tz"] is None and len(SEEN["cut"]) == 300 and SEEN["name"] is None, SEEN
        stt({"X-Tz-Offset": "-300", "X-Tz-Name": "America%2FNew_York",
             "X-Interrupted": "Arsenal%E2%80%99s%20goal%20%E2%80%94%20Saka"})
        assert SEEN["tz"] == -300 and SEEN["name"] == "America/New_York", SEEN
        assert SEEN["cut"] == "Arsenal’s goal — Saka", SEEN
        http(port, "POST", "/agent/chat", {"text": "hi", "tz_offset_minutes": 241,
                                           "interrupted": "half%20time", "tz_name": "Indian/Mauritius"})
        assert (SEEN["tz"], SEEN["cut"], SEEN["name"]) == (241, "half time", "Indian/Mauritius"), SEEN
        print("ok  MCP-12 STT path: X-Tz-Offset capped at +-840, X-Interrupted percent-decoded and capped, X-Tz-Name passed")

        # MCP-21: an agent failure on the speech path is reported, not swallowed
        SEEN["next"] = "explode"
        code, doc, _ = stt({})
        assert code == 200 and "chat" not in doc and doc["chat_error"] == "Nova agent request failed", doc
        print("ok  MCP-21 agent failure after STT returns chat_error")
        # VO-26 (server side): a failing hint does not drop the connection; TTS text must be a string
        srv_ref.voice_hint = lambda _l: 1 / 0
        SEEN["next"] = "score?"
        assert stt({})[0] == 200
        assert http(port, "POST", "/voice/tts", {"text": 123})[0] == 400
        print("ok  a failing speech hint is ignored; non-string TTS text -> 400")
    finally:
        voice.transcribe = real
        srv_ref.voice_hint = None


def check_config():
    # MCP-13
    assert _local_url(("0.0.0.0", 8765)) == "http://127.0.0.1:8765/mcp"
    assert _local_url(("192.168.1.20", 8765)) == "http://192.168.1.20:8765/mcp"
    assert _local_url(("::", 8765)) == "http://[::1]:8765/mcp"
    print("ok  MCP-13 the agent bridge dials the bound address (loopback for 0.0.0.0)")

    # CFG-01
    saved = {k: os.environ.get(k) for k in ("SIDELINE_PORT", "SIDELINE_POLL_SECONDS", "SIDELINE_STATE")}
    try:
        os.environ.update(SIDELINE_PORT="eighty", SIDELINE_POLL_SECONDS="0", SIDELINE_STATE="postgres")
        c = Config()
        assert c.port == 8765 and c.poll_seconds == 30 and c.state == "memory"
        try:
            c.check()
            raise AssertionError("bad settings accepted")
        except ConfigError as e:
            for name in ("SIDELINE_PORT", "SIDELINE_POLL_SECONDS", "SIDELINE_STATE"):
                assert name in str(e), e
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    env = dict(os.environ, SIDELINE_PORT="eighty", SIDELINE_LOG_DIR="off", PYTHONPATH=ROOT)
    r = subprocess.run([sys.executable, "-m", "sideline"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode != 0 and "SIDELINE_PORT" in r.stderr and "Traceback" not in r.stderr, r.stderr
    print("ok  CFG-01 bad SIDELINE_PORT/POLL_SECONDS/STATE: one readable ConfigError, no traceback")

    # CFG-02
    d = tempfile.mkdtemp()
    for name in ("sideline-2026-13-40.log", "calls-2026-02-30.jsonl", "sideline-2000-01-01.log", "notes.txt"):
        open(os.path.join(d, name), "w").close()
    try:
        assert audit.setup(d, 14)
        assert sorted(os.listdir(d)) == ["calls-2026-02-30.jsonl", "notes.txt", "sideline-2026-13-40.log"]
    finally:
        audit.setup("off")
    print("ok  CFG-02 an oddly named file in logs/ does not stop the server; old logs are still pruned")

    # CFG-03
    assert envfile.parse('A="abc" # note\nB=\'x # y\'\nC=plain # c\n') == {"A": "abc", "B": "x # y", "C": "plain"}
    print("ok  CFG-03 KEY=\"abc\" # note -> abc")


srv_sessions = None
srv_ref = None


def check_auth(srv, port):
    """SIDELINE_AUTH_TOKEN: off by default; when set, every route but /health needs `Authorization: Bearer <token>`."""
    assert init(port)[0] == 200, "no token configured: open, as before"
    srv.auth_token = "t" * 20
    try:
        good = {"Authorization": "Bearer " + "t" * 20}
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        code, _, hdr = http(port, "POST", "/mcp", body)
        assert code == 401 and hdr.get("WWW-Authenticate", "").startswith("Bearer"), (code, hdr)
        for bad in ("Bearer nope", "Bearer " + "t" * 19, "Basic " + "t" * 20, "t" * 20, ""):
            assert http(port, "POST", "/mcp", body, {"Authorization": bad})[0] == 401, bad
        assert http(port, "POST", "/mcp", body, good)[0] == 200
        for method, path in (("GET", "/mcp"), ("DELETE", "/mcp"), ("POST", "/agent/chat"), ("POST", "/voice/tts"),
                             ("GET", "/voice/capabilities")):
            assert http(port, method, path, None)[0] == 401, (method, path)
        assert http(port, "GET", "/health", None)[0] == 200, "/health stays open for a load balancer"
        print("ok  SIDELINE_AUTH_TOKEN: a bearer token is required on /mcp, /agent and /voice, never on /health")
    finally:
        srv.auth_token = ""

    from sideline.config import Config
    os.environ["SIDELINE_AUTH_TOKEN"] = "short"
    try:
        assert any("SIDELINE_AUTH_TOKEN" in e for e in Config().errors), "a short token is refused at startup"
    finally:
        del os.environ["SIDELINE_AUTH_TOKEN"]
    print("ok  a token shorter than 16 characters stops the server from starting")


def main():
    global srv_sessions, srv_ref
    check_session_table()
    check_config()
    srv, port = _start(["localhost", "127.0.0.1"], agent=runner)
    srv_sessions, srv_ref = srv.sessions, srv
    try:
        check_body_guard(port)
        check_origins(port)
        check_auth(srv, port)
        check_sessions_and_versions(port)
        check_event_stream(port)
        check_tools(port)
        check_agent_context(port)
    finally:
        srv.shutdown()
        srv.server_close()
    print("\nserver fixes: all good")


if __name__ == "__main__":
    main()
