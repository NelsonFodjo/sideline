"""MCP server over Streamable HTTP. Spec revision 2025-11-25.

Alexa+ is the MCP *client*. This module is the *server*. We never do
speech recognition, never choose the wording the listener hears, never
render the screen. We expose tools and hold state. Everything else in
this repository exists to make these tools answerable.

Transport, per the 2025-11-25 revision:

    POST   /mcp    one JSON-RPC 2.0 request, notification or response
    GET    /mcp    optional SSE stream for server-initiated messages
    DELETE /mcp    terminate the session

Implementation notes that matter:

  * `Mcp-Session-Id` is issued on a successful initialize and required
    afterwards: no header is HTTP 400, an unknown one HTTP 404, which
    tells the client to re-initialize rather than retry forever.
  * `Origin` is validated on every request, as a full origin (scheme,
    host and port). Without this an MCP server bound to localhost is
    trivially reachable from any page the user has open - the
    DNS-rebinding problem the spec warns about. No Origin (Alexa+, curl)
    passes: it is not a browser.
  * `MCP-Protocol-Version` is checked when a client sends it (an
    unsupported one is HTTP 400) and echoed on responses.
  * Notifications and client responses get HTTP 202 and no body. Getting
    this wrong makes clients hang waiting for a response that is not
    coming. JSON-RPC batches are refused: MCP removed them in 2025-06-18.
  * Every body is read through one guard: Content-Length must be a plain
    non-negative integer under the route's cap, and every error response
    closes the connection, so an unread body can never be parsed as the
    next request.

Zero third-party dependencies. See docs/ARCHITECTURE.md for why.
"""

import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .. import audit
from ..providers.base import ProviderUnavailable
from .errors import (ERROR_SPOKEN, InvalidParams, InvalidRequest, MethodNotFound, ParseError,
                     RpcError, ToolError)
from .registry import by_name, public_tools
from .schema import validate

LOG = logging.getLogger("sideline.mcp")

PROTOCOL_VERSION = "2025-11-25"
# What a client may put in MCP-Protocol-Version: only what initialize negotiates.
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION,)
SERVER_INFO = {"name": "sideline", "version": "1.0.0",
               "title": "Sideline - live sport for listeners"}

# A session ends after this long without a request, and the table never holds more than MAX_SESSIONS
# (the least recently used goes first; its client gets 404 and re-initializes).
SESSION_IDLE_SECONDS = 60 * 60 * 6
MAX_SESSIONS = 1000

# Bodies. A JSON-RPC message is small; a spoken question is seconds of audio and a sentence of text.
MCP_MAX_BODY_BYTES = 1024 * 1024
CHAT_MAX_BODY_BYTES = 16 * 1024
VOICE_MAX_AUDIO_BYTES = 12 * 1024 * 1024
VOICE_MAX_TEXT_BYTES = 16 * 1024

# One thread per connection: a socket that stops sending or reading is dropped after this long.
SOCKET_TIMEOUT_SECONDS = 30
# The optional event stream pins a thread while it is open, so there are few, and none for long.
MAX_EVENT_STREAMS = 8
EVENT_STREAM_SECONDS = 300
EVENT_STREAM_TICK_SECONDS = 15

# The listener context that rides along with a question.
MAX_TZ_OFFSET_MINUTES = 840                     # UTC-14:00 .. UTC+14:00
MAX_INTERRUPTED_CHARS = 300
_TZ_NAME = re.compile(r"[A-Za-z_]+(/[A-Za-z_+\-0-9]+){0,2}")
_TZ_OFFSET = re.compile(r"[+-]?[0-9]{1,4}")
_CONTENT_LENGTH = re.compile(r"[0-9]{1,15}")

SIMULATOR_ROUTES = ("/", "/simulator", "/simulator/", "/index.html", "/simulator/index.html")

# Set per request from the X-Sideline-Agent header (see simulator/mcp_client.py, an optional add-on): the voice
# agent asks tools for facts, not for model-written paragraphs.
_REQUEST = threading.local()


class Sessions:
    """In-memory session table.

    Sessions hold no listener data - that lives in the state store and is
    keyed by the listener id, so a dropped session never
    loses a match or a last_told_at. This table only tracks liveness.
    """

    def __init__(self, idle_seconds=SESSION_IDLE_SECONDS, limit=MAX_SESSIONS):
        self._s = {}
        self._lock = threading.Lock()
        self.idle_seconds = idle_seconds
        self.limit = limit

    def __len__(self):
        with self._lock:
            return len(self._s)

    def _sweep(self, now):
        # Caller holds the lock.
        for sid in [k for k, v in self._s.items() if now - v["seen"] > self.idle_seconds]:
            del self._s[sid]

    def create(self):
        sid = secrets.token_hex(16)
        now = time.time()
        with self._lock:
            self._sweep(now)
            while len(self._s) >= self.limit:
                del self._s[min(self._s, key=lambda k: self._s[k]["seen"])]
            self._s[sid] = {"created": now, "seen": now}
        return sid

    def touch(self, sid):
        now = time.time()
        with self._lock:
            s = self._s.get(sid)
            if not s:
                return False
            if now - s["seen"] > self.idle_seconds:
                del self._s[sid]
                return False
            s["seen"] = now
            return True

    def known(self, sid):
        """Is the session still open? Does not count as activity."""
        with self._lock:
            s = self._s.get(sid)
            return bool(s) and time.time() - s["seen"] <= self.idle_seconds

    def drop(self, sid):
        with self._lock:
            return self._s.pop(sid, None) is not None


class Dispatcher:
    """Maps JSON-RPC methods onto our handlers."""

    def __init__(self, tool_runner, sessions):
        self.run_tool = tool_runner
        self.sessions = sessions

    def handle(self, msg, listener_id):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            raise InvalidRequest("not a JSON-RPC 2.0 message")

        method = msg.get("method")
        if not isinstance(method, str):
            raise InvalidRequest("missing method")
        params = msg.get("params")
        if params is None:
            params = {}
        elif not isinstance(params, dict):
            raise InvalidParams("params must be an object")

        if method == "initialize":
            return self._initialize(params)
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": public_tools()}
        if method == "tools/call":
            return self._call(params, listener_id)

        raise MethodNotFound("unknown method: %s" % method)

    def _initialize(self, params):
        asked = params.get("protocolVersion")
        if asked and asked != PROTOCOL_VERSION:
            # We advertise what we actually speak and let the client
            # decide. Silently pretending to match is worse.
            LOG.info("client asked for protocol %s, we speak %s", asked, PROTOCOL_VERSION)
        return {
            "protocolVersion": PROTOCOL_VERSION,
            # Tools only. No resources, prompts or UI resources are served, so none are declared.
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": (
                "Sideline answers questions about live sport - football (soccer), "
                "basketball, American football, baseball and ice hockey - for a "
                "listener who cannot see the screen. Prefer what_did_i_miss "
                "when the listener asks what HAPPENED, and get_match_state "
                "when they ask what the score IS. Read answers back plainly: "
                "this listener is following the game by ear and a long "
                "preamble costs them the next thing that happens."
            ),
        }

    def _call(self, params, listener_id):
        name = params.get("name")
        args = params.get("arguments")
        if args is None:
            args = {}
        if not isinstance(name, str):
            raise InvalidParams("tools/call needs a tool name")
        spec = by_name(name)
        if not spec:
            raise InvalidParams("no such tool: %s" % name)
        if not isinstance(args, dict):
            raise InvalidParams("arguments must be an object")

        try:
            validate(args, spec["inputSchema"])
        except InvalidParams as e:
            # Bad arguments are the tool call's failure, not the protocol's (MCP 2025-11-25): a result the model can
            # read and correct, instead of an error object most clients never show it.
            LOG.info("tool %s: invalid arguments: %s", name, e)
            audit.record("tool", tool=name, args=args, ok=False, reason="invalid_arguments", problem=str(e)[:200],
                         listener=listener_id, via="agent" if getattr(_REQUEST, "agent", False) else "client")
            return {
                "content": [{"type": "text", "text": "The arguments were not valid: %s. Check the tool's input schema "
                                                     "and call it again." % e}],
                "structuredContent": {"reason": "invalid_arguments", "problem": str(e)},
                "isError": True,
            }

        started = time.time()
        try:
            if getattr(_REQUEST, "agent", False):
                result = self.run_tool(name, args, listener_id, agent=True)
            else:
                result = self.run_tool(name, args, listener_id)
        except ProviderUnavailable as e:
            # The data feed refused or is down (bad key, quota, plan, network).
            # A listener cannot act on a protocol error; they can on this.
            LOG.warning("tool %s: data feed unavailable: %s", name, e)
            audit.record("tool", tool=name, args=args, ok=False, reason="provider_unavailable", problem=str(e),
                         ms=round((time.time() - started) * 1000), listener=listener_id,
                         via="agent" if getattr(_REQUEST, "agent", False) else "client")
            return {
                "content": [{"type": "text", "text": ERROR_SPOKEN}],
                "structuredContent": {"reason": "provider_unavailable",
                                      "problem": str(e)},
                "isError": True,
            }
        except ToolError as e:
            # Not a protocol failure. Hand the model something it can say.
            LOG.info("tool %s declined: %s", name, e.spoken)
            audit.record("tool", tool=name, args=args, ok=False, reason=(e.detail or {}).get("reason"),
                         spoken=e.spoken, ms=round((time.time() - started) * 1000), listener=listener_id,
                         via="agent" if getattr(_REQUEST, "agent", False) else "client")
            return {
                "content": [{"type": "text", "text": e.spoken}],
                "structuredContent": e.detail,
                "isError": True,
            }
        except RpcError:
            raise
        except Exception as e:                           # noqa: BLE001 - a crash in a tool is the tool's, not the protocol's
            LOG.exception("tool %s failed: %s", name, e)
            audit.record("tool", tool=name, args=args, ok=False, reason="tool_error", problem=str(e)[:200],
                         ms=round((time.time() - started) * 1000), listener=listener_id,
                         via="agent" if getattr(_REQUEST, "agent", False) else "client")
            return {
                "content": [{"type": "text", "text": ERROR_SPOKEN}],
                "structuredContent": {"reason": "tool_error", "problem": type(e).__name__},
                "isError": True,
            }
        took = (time.time() - started) * 1000
        LOG.info("tool %s ok in %.0fms", name, took)
        audit.record("tool", tool=name, args=args, ok=True, ms=round(took), listener=listener_id,
                     spoken=result[0], via="agent" if getattr(_REQUEST, "agent", False) else "client")

        # Every tool returns (spoken_text, structured, ui_payload).
        spoken, structured, ui = result
        out = {
            "content": [{"type": "text", "text": spoken}],
            "structuredContent": structured,
        }
        # Our own namespace: the card data the simulator can draw. It is not an MCP Apps
        # resource (none is served), so it does not use that extension's `ui` key.
        meta = {"tool": name, "took_ms": round(took)}
        if ui:
            meta["ui"] = ui
        out["_meta"] = {"sideline": meta}
        return out


def message_kind(msg):
    """'request', 'notification' or 'response' for a well-formed JSON-RPC 2.0 message; None otherwise."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return None
    if "method" in msg:
        if not isinstance(msg["method"], str):
            return None
        if "id" not in msg:
            return "notification"
        mid = msg["id"]                             # MCP: a string or a number, never null
        return "request" if isinstance(mid, (str, int)) and not isinstance(mid, bool) else None
    if "id" in msg and ("result" in msg) != ("error" in msg):
        return "response"
    return None


def _usable_id(msg):
    mid = msg.get("id") if isinstance(msg, dict) else None
    return mid if isinstance(mid, (str, int)) and not isinstance(mid, bool) else None


def tz_offset(value):
    """Minutes east of UTC from an int or a header string; None unless within +-14 hours."""
    if isinstance(value, str):
        value = value.strip()
        value = int(value) if _TZ_OFFSET.fullmatch(value) else None
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if -MAX_TZ_OFFSET_MINUTES <= value <= MAX_TZ_OFFSET_MINUTES else None


def tz_name(value):
    """An IANA zone name such as 'Indian/Mauritius' (percent-encoding allowed); None otherwise."""
    if not isinstance(value, str) or len(value) > 200:
        return None
    value = unquote(value).strip()
    return value if _TZ_NAME.fullmatch(value) else None


def interrupted(value):
    """What the listener cut off, percent-encoded or plain: one line, at most 300 characters."""
    if not isinstance(value, str):
        return None
    text = " ".join(unquote(value).split())[:MAX_INTERRUPTED_CHARS].strip()
    return text or None


def _optional(name):
    """A module from the simulator add-on, or None when this checkout does not have it. The MCP server itself needs
    nothing outside the `sideline` package."""
    try:
        import importlib
        return importlib.import_module("simulator." + name)
    except ImportError:
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "sideline/1.0"
    protocol_version = "HTTP/1.1"
    timeout = SOCKET_TIMEOUT_SECONDS

    # ---------------------------------------------------------- helpers
    def _route(self):
        # A query string is not part of the route.
        return urlparse(self.path).path

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True  # non-browser client; Alexa+ sends none
        return self.server.origin_allowed(origin)

    def _unauthorized(self):
        """True (after answering 401) when a token is required and this request does not carry it.

        Off unless SIDELINE_AUTH_TOKEN is set. A static bearer token is not OAuth: it keeps a public deployment from
        being open, and it is what a client with a header field (Claude, the MCP Inspector, a gateway) can send today."""
        token = self.server.auth_token
        if not token:
            return False
        given = (self.headers.get("Authorization") or "").strip()
        if given[:7].lower() == "bearer " and hmac.compare_digest(given[7:].strip().encode("utf-8"),
                                                                    token.encode("utf-8")):
            return False
        self._send(401, {"error": "unauthorized"}, {"WWW-Authenticate": 'Bearer realm="sideline"'})
        return True

    def _protocol_ok(self):
        asked = self.headers.get("MCP-Protocol-Version")
        return asked is None or asked.strip() in SUPPORTED_PROTOCOL_VERSIONS

    def _send(self, code, payload=None, headers=None):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
        origin = self.headers.get("Origin")
        if origin and self._origin_ok():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id, MCP-Protocol-Version")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if code >= 400:
            # An error may leave the body unread. Closing is the only way to make sure it is
            # never parsed as the next request (that is how a smuggled request got past Origin).
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_body(self, limit):
        """The request body, or None once an error has been sent. The one way any route reads a body."""
        if self.headers.get("Transfer-Encoding"):
            self._send(411, {"error": "send the body with a Content-Length"})
            return None
        lengths = {v.strip() for v in self.headers.get_all("Content-Length") or []}
        if len(lengths) > 1:
            self._send(400, {"error": "bad Content-Length"})
            return None
        raw = lengths.pop() if lengths else "0"
        if not _CONTENT_LENGTH.fullmatch(raw):
            self._send(400, {"error": "bad Content-Length"})
            return None
        length = int(raw)
        if length > limit:
            self._send(413, {"error": "request is too large"})
            return None
        try:
            body = self.rfile.read(length) if length else b""
        except OSError:                             # the socket timed out mid-body
            self.close_connection = True
            return None
        if len(body) != length:                     # the client hung up mid-body
            self.close_connection = True
            return None
        return body

    def _no_body(self):
        """GET, DELETE and OPTIONS take no body; one that came anyway must not become a request."""
        if self.headers.get("Transfer-Encoding") or (self.headers.get("Content-Length") or "0").strip() != "0":
            self.close_connection = True

    def _listener(self):
        """Who is asking: the `X-Sideline-Listener` header, else one shared id.

        There is no account linking (Alexa+'s add-on tooling is partner-only,
        so participants cannot exercise it). That makes this a single-listener
        server: the id is the only thing keying listener state, so do not expose
        it to more than one real person.
        """
        return self.server.resolve_listener(self.headers)

    def _rpc_error(self, err, msg_id=None, http=200):
        self._send(http, {"jsonrpc": "2.0", "id": msg_id, "error": err.to_json()})

    def log_message(self, fmt, *args):
        LOG.debug("%s - %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------- verbs
    def _serve_simulator(self):
        """The voice simulator, served by the server it talks to.

        A page opened from disk (file://) sends `Origin: null`, which the
        Origin allow-list correctly refuses on /mcp, so the simulator could
        not even initialize. Served from here it is same-origin
        (http://127.0.0.1:<port>), the allow-list stays strict, and
        nothing has to be opened up for the string "null".
        """
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        try:
            with open(os.path.join(root, "simulator", "index.html"), "rb") as fh:
                body = fh.read()
        except OSError:
            return self._send(404, {"error": "simulator not found in this checkout"})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _session_error(self):
        """Checks shared by every /mcp request after initialize. Sends the error and returns True on failure."""
        if not self._protocol_ok():
            self._rpc_error(InvalidRequest("unsupported MCP-Protocol-Version; this server speaks %s"
                                           % PROTOCOL_VERSION), None, 400)
            return True
        sid = self.headers.get("Mcp-Session-Id")
        if not sid:
            self._rpc_error(InvalidRequest("Mcp-Session-Id is required after initialize"), None, 400)
            return True
        if not self.server.sessions.touch(sid):
            self._send(404, {"error": "unknown session"})
            return True
        return False

    def do_GET(self):
        self._no_body()
        route = self._route()
        if route in SIMULATOR_ROUTES:
            return self._serve_simulator()
        if route == "/health":
            return self._send(200, {"ok": True, "protocol": PROTOCOL_VERSION,
                                    "tools": len(public_tools())})
        if route == "/voice/capabilities":
            if not self._origin_ok():
                return self._send(403, {"error": "origin not allowed"})
            if self._unauthorized():
                return None
            # Simulator support, not part of the MCP surface. The browser
            # asks once at load whether to post audio here or fall back
            # to its own engine. See simulator/voice.py.
            voice = _optional("voice")
            if voice is None:
                return self._send(404, {"error": "not found"})
            capabilities = voice.capabilities
            # Setup hints name credentials and install commands: for the
            # developer's console and CLI check, never for a listener's
            # screen, so they are not sent to the page at all.
            public = {k: v for k, v in capabilities().items() if not k.endswith("_hint")}
            return self._send(200, public)
        if route.rstrip("/") != "/mcp":
            return self._send(404, {"error": "not found"})
        if not self._origin_ok():
            return self._send(403, {"error": "origin not allowed"})
        if self._unauthorized():
            return None
        if self._session_error():
            return None
        sid = self.headers.get("Mcp-Session-Id")

        # Optional SSE channel. We hold it open but currently push nothing:
        # Alexa+ owns the turn model, so the server cannot make the device
        # speak first. Kept open and correct so that if the platform ever
        # allows server-initiated messages, the "goal just went in"
        # notification has somewhere to go. See docs/PRODUCT_FEEDBACK.md.
        # Each stream pins a thread, so there are at most MAX_EVENT_STREAMS, each ends after
        # EVENT_STREAM_SECONDS (the client reconnects), and the connection closes with it.
        if not self.server.event_streams.acquire(blocking=False):
            return self._send(429, {"error": "too many open event streams"}, {"Retry-After": "60"})
        try:
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
            origin = self.headers.get("Origin")
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            deadline = time.time() + EVENT_STREAM_SECONDS
            while time.time() < deadline and self.server.sessions.known(sid):
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(min(EVENT_STREAM_TICK_SECONDS, max(0.0, deadline - time.time())))
        except OSError:                              # the client went away, or stopped reading
            pass
        finally:
            self.server.event_streams.release()
        return None

    def do_DELETE(self):
        self._no_body()
        if self._route().rstrip("/") != "/mcp":
            return self._send(404, {"error": "not found"})
        if not self._origin_ok():
            return self._send(403, {"error": "origin not allowed"})
        if self._unauthorized():
            return None
        if not self._protocol_ok():
            return self._rpc_error(InvalidRequest("unsupported MCP-Protocol-Version"), None, 400)
        sid = self.headers.get("Mcp-Session-Id")
        if not sid:
            return self._rpc_error(InvalidRequest("Mcp-Session-Id is required"), None, 400)
        if not self.server.sessions.drop(sid):
            return self._send(404, {"error": "unknown session"})
        return self._send(204)

    def do_OPTIONS(self):
        # CORS preflight. Only an allowed origin gets the headers; the simulator is
        # same-origin and never needs one.
        self._no_body()
        if not self._origin_ok():
            return self._send(403, {"error": "origin not allowed"})
        self.send_response(204)
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Accept, Last-Event-ID, Mcp-Session-Id, MCP-Protocol-Version, "
                         "X-Sideline-Listener, X-Sideline-Agent, X-Audio-Type, X-Run-Agent, "
                         "X-Tz-Offset, X-Tz-Name, X-Interrupted")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id, MCP-Protocol-Version")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()
        return None

    def _voice(self, route):
        """/voice/stt and /voice/tts. Simulator only, same-origin like /mcp: a page on another
        origin must not be able to spend this server's speech credits."""
        voice = _optional("voice")
        if voice is None or route not in ("/voice/stt", "/voice/tts"):
            return self._send(404, {"error": "not found"})
        if not self._origin_ok():
            return self._send(403, {"error": "origin not allowed"})
        raw = self._read_body(VOICE_MAX_AUDIO_BYTES if route == "/voice/stt" else VOICE_MAX_TEXT_BYTES)
        if raw is None:
            return None

        if route == "/voice/stt":
            mime = self.headers.get("X-Audio-Type") or "audio/webm"
            hint = ""
            listener_id = self._listener()
            hinter = getattr(self.server, "voice_hint", None)
            if hinter:
                try:
                    hint = hinter(listener_id) or ""
                except Exception:                    # noqa: BLE001 - a hint is optional
                    LOG.exception("speech hint failed; transcribing without one")
            out = voice.transcribe(raw, mime, hint)
            if not out:
                return self._send(503, {"error": "no speech provider configured"})
            LOG.info("stt (%s): %s", out["provider"], out["text"][:60])
            audit.record("stt", provider=out["provider"], heard=out["text"], bytes=len(raw))
            question = (out.get("text") or "").strip()
            if self.headers.get("X-Run-Agent") == "1" and question and getattr(self.server, "agent_runner", None):
                # The same listener context /agent/chat takes, from headers (X-Interrupted and
                # X-Tz-Name percent-encoded), validated the same way.
                result, failure = self._run_agent(
                    question, listener_id,
                    tz_offset(self.headers.get("X-Tz-Offset")),
                    interrupted(self.headers.get("X-Interrupted")),
                    tz_name(self.headers.get("X-Tz-Name")))
                if failure:
                    out["chat_error"] = failure[1]
                else:
                    out["chat"] = result
            return self._send(200, out)

        try:
            doc = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._send(400, {"error": "bad body"})
        text = doc.get("text", "") if isinstance(doc, dict) else None
        if not isinstance(text, str):
            return self._send(400, {"error": "text must be a string"})
        out = voice.synthesize(text)
        if not out:
            return self._send(503, {"error": "no voice provider configured"})
        return self._send(200, out)

    def do_POST(self):
        route = self._route()
        if route.startswith("/voice/"):
            if self._unauthorized():
                return None
            return self._voice(route)
        if route == "/agent/chat":
            if not self._origin_ok():
                return self._send(403, {"error": "origin not allowed"})
            if self._unauthorized():
                return None
            return self._agent_chat(self._listener())
        if route.rstrip("/") != "/mcp":
            return self._send(404, {"error": "not found"})
        if not self._origin_ok():
            return self._send(403, {"error": "origin not allowed"})
        if self._unauthorized():
            return None

        raw = self._read_body(MCP_MAX_BODY_BYTES)
        if raw is None:
            return None
        if not raw:
            return self._rpc_error(InvalidRequest("empty body"), None, 400)
        try:
            msg = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self._rpc_error(ParseError("could not parse JSON"), None, 400)

        if isinstance(msg, list):
            return self._rpc_error(InvalidRequest(
                "JSON-RPC batches are not supported (removed from MCP in 2025-06-18); send one message per POST"),
                None, 400)
        kind = message_kind(msg)
        if kind is None:
            return self._rpc_error(InvalidRequest(
                "not a JSON-RPC 2.0 request, notification or response"), _usable_id(msg), 400)

        is_init = msg.get("method") == "initialize"
        if is_init and kind != "request":
            return self._rpc_error(InvalidRequest("initialize must be a request with an id"), None, 400)
        if not is_init and self._session_error():
            return None
        if kind == "response":
            return self._send(202)                  # we send no requests, so there is nothing to match it to

        listener_id = self._listener()
        _REQUEST.agent = self.headers.get("X-Sideline-Agent") == "1"
        result = self._one(msg, listener_id)
        if kind == "notification":
            return self._send(202)

        extra = {}
        if is_init and "result" in result:
            # Minted only for an initialize that succeeded.
            extra["Mcp-Session-Id"] = self.server.sessions.create()
        return self._send(200, result, extra)

    def _run_agent(self, question, listener_id, tz, cut, name):
        """Runs the agent and audits it. (result, None), or (None, (http status, error text))."""
        asked_at = time.time()
        try:
            result = self.server.agent_runner(question, listener_id, tz, cut, name)
        except Exception as e:                           # noqa: BLE001
            AgentUnavailable = getattr(_optional("agent"), "AgentUnavailable", ())
            audit.record("agent", question=question, ok=False, error=str(e) or type(e).__name__,
                         ms=round((time.time() - asked_at) * 1000), listener=listener_id)
            if isinstance(e, AgentUnavailable):
                LOG.warning("Nova agent unavailable: %s", e)
                return None, (503, "Nova agent unavailable")
            LOG.exception("Nova agent request failed")
            return None, (500, "Nova agent request failed")
        audit.record("agent", question=question, ok=True, answer=result.get("text"),
                     tools=[t.get("name") for t in result.get("tool_results") or []],
                     generated_by=result.get("generated_by"), understood=result.get("understood"),
                     ms=round((time.time() - asked_at) * 1000), listener=listener_id)
        return result, None

    def _agent_chat(self, listener_id):
        """Simulator endpoint: Nova selects and runs tools from the MCP registry."""
        if not self.server.agent_runner:
            return self._send(503, {"error": "Nova agent is not configured"})
        raw = self._read_body(CHAT_MAX_BODY_BYTES)
        if raw is None:
            return None
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return self._send(400, {"error": "invalid JSON"})
        question = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            return self._send(400, {
                "error": "text must be a non-empty string of at most 1000 characters"
            })
        cut = interrupted(payload.get("interrupted"))
        if cut is None:
            cut = interrupted(self.headers.get("X-Interrupted"))
        result, failure = self._run_agent(question.strip(), listener_id,
                                          tz_offset(payload.get("tz_offset_minutes")), cut,
                                          tz_name(payload.get("tz_name")))
        if failure:
            return self._send(failure[0], {"error": failure[1]})
        return self._send(200, result)

    def _one(self, msg, listener_id):
        msg_id = msg.get("id") if isinstance(msg, dict) else None
        try:
            payload = self.server.dispatcher.handle(msg, listener_id)
        except RpcError as e:
            if msg_id is None:
                return None
            return {"jsonrpc": "2.0", "id": msg_id, "error": e.to_json()}
        except Exception as e:                       # noqa: BLE001
            LOG.exception("unhandled error")
            if msg_id is None:
                return None
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32603, "message": "internal error",
                              "data": {"type": type(e).__name__}}}
        if msg_id is None:
            return None                              # notification
        return {"jsonrpc": "2.0", "id": msg_id, "result": payload}


_DEFAULT_PORTS = {"http": 80, "https": 443}
_ANY_HOST = ("", "0.0.0.0", "::")


def origin_key(origin):
    """(scheme, host, port) of a browser Origin, or None for 'null' or anything malformed."""
    try:
        u = urlparse(origin.strip())
        port = u.port
    except (ValueError, AttributeError):
        return None
    scheme, host = (u.scheme or "").lower(), (u.hostname or "").lower()
    if scheme not in _DEFAULT_PORTS or not host or u.path not in ("", "/") or u.query or u.username:
        return None
    return scheme, host, port or _DEFAULT_PORTS[scheme]


def allowed_origin_keys(entries, host, port):
    """The allow-list as full origins.

    An entry is either a full origin (`https://judge.example:8443`) or, as before, a bare host
    name, which means that host on this server's own port over http (`localhost` ->
    http://localhost:<port>). A specific bound address is always allowed, so the simulator page
    works when it is served from a LAN address. `*` allows any origin.
    """
    keys, any_origin = set(), False
    for entry in entries:
        entry = entry.strip()
        if entry == "*":
            any_origin = True
        elif "://" in entry:
            key = origin_key(entry)
            if key:
                keys.add(key)
            else:
                LOG.warning("ignoring malformed allowed origin %r", entry)
        elif entry:
            keys.add(("http", entry.lower().strip("[]"), port))
    if host not in _ANY_HOST:
        keys.add(("http", host.lower(), port))
    return keys, any_origin


class McpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, tool_runner, resolve_listener, allowed_origins,
                 agent_runner=None):
        ThreadingHTTPServer.__init__(self, addr, Handler)
        self.agent_runner = agent_runner
        self.auth_token = ""                       # set by the app from SIDELINE_AUTH_TOKEN; empty means no check
        self.sessions = Sessions()
        self.dispatcher = Dispatcher(tool_runner, self.sessions)
        self.resolve_listener = resolve_listener
        self.allowed_origins, self.any_origin = allowed_origin_keys(
            allowed_origins, self.server_address[0], self.server_address[1])
        self.event_streams = threading.BoundedSemaphore(MAX_EVENT_STREAMS)

    def origin_allowed(self, origin):
        if self.any_origin:
            return True
        key = origin_key(origin)
        return key is not None and key in self.allowed_origins


def serve(host, port, tool_runner, resolve_listener, allowed_origins, agent_runner=None):
    srv = McpServer((host, port), tool_runner, resolve_listener, allowed_origins,
                    agent_runner)
    LOG.info("MCP endpoint on http://%s:%d/mcp (spec %s)", host, port, PROTOCOL_VERSION)
    return srv
