"""MCP server over Streamable HTTP. Spec revision 2025-11-25.

Alexa+ is the MCP *client*. This module is the *server*. We never do
speech recognition, never choose the wording the listener hears, never
render the screen. We expose tools and hold state. Everything else in
this repository exists to make these tools answerable.

Transport, per the 2025-11-25 revision:

    POST   /mcp    JSON-RPC 2.0 request or notification
    GET    /mcp    optional SSE stream for server-initiated messages
    DELETE /mcp    terminate the session

Implementation notes that matter:

  * `Mcp-Session-Id` is issued on initialize and required afterwards.
    An unknown session gets HTTP 404, which tells the client to
    re-initialize rather than retry forever.
  * `Origin` is validated on every request. Without this an MCP server
    bound to localhost is trivially reachable from any page the user
    has open - the DNS-rebinding problem the spec warns about.
  * `MCP-Protocol-Version` is echoed on responses so a client can tell
    which revision it is actually talking to.
  * Notifications (no `id`) get HTTP 202 and no body. Getting this wrong
    makes clients hang waiting for a response that is not coming.

Zero third-party dependencies. See docs/ARCHITECTURE.md for why.
"""

import json
import logging
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from ..providers.base import ProviderUnavailable
from .errors import (InvalidParams, InvalidRequest, MethodNotFound, ParseError,
                     RpcError, ToolError)
from .registry import by_name, public_tools
from .schema import validate

LOG = logging.getLogger("sideline.mcp")

PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {"name": "sideline", "version": "1.0.0",
               "title": "Sideline - live football for listeners"}

SESSION_TTL_SECONDS = 60 * 60 * 6

# Set per request from the X-Sideline-Agent header (see mcp/client.py): the voice
# agent asks tools for facts, not for model-written paragraphs.
_REQUEST = threading.local()


class Sessions:
    """In-memory session table.

    Sessions hold no listener data - that lives in the state store and is
    keyed by the listener id, so a dropped session never
    loses a match or a last_told_at. This table only tracks liveness.
    """

    def __init__(self):
        self._s = {}
        self._lock = threading.Lock()

    def create(self):
        sid = secrets.token_hex(16)
        with self._lock:
            self._s[sid] = {"created": time.time(), "seen": time.time()}
        return sid

    def touch(self, sid):
        with self._lock:
            s = self._s.get(sid)
            if not s:
                return False
            if time.time() - s["created"] > SESSION_TTL_SECONDS:
                del self._s[sid]
                return False
            s["seen"] = time.time()
            return True

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
        params = msg.get("params") or {}

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
            "capabilities": {
                "tools": {"listChanged": False},
                # Declared so Alexa+ knows it may render our cards on
                # screened devices. See registry.py `_meta.ui`.
                "experimental": {"mcpApps": {"version": "1"}},
            },
            "serverInfo": SERVER_INFO,
            "instructions": (
                "Sideline answers questions about a live football match for a "
                "listener who cannot see the screen. Prefer what_did_i_miss "
                "when the listener asks what HAPPENED, and get_match_state "
                "when they ask what the score IS. Read answers back plainly: "
                "this listener is following the match by ear and a long "
                "preamble costs them the next thing on the pitch."
            ),
        }

    def _call(self, params, listener_id):
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(name, str):
            raise InvalidParams("tools/call needs a tool name")
        spec = by_name(name)
        if not spec:
            raise InvalidParams("no such tool: %s" % name)
        if not isinstance(args, dict):
            raise InvalidParams("arguments must be an object")

        validate(args, spec["inputSchema"])

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
            return {
                "content": [{"type": "text", "text":
                             "I can't get that from the match data right now."}],
                "structuredContent": {"reason": "provider_unavailable",
                                      "problem": str(e)},
                "isError": True,
            }
        except ToolError as e:
            # Not a protocol failure. Hand the model something it can say.
            LOG.info("tool %s declined: %s", name, e.spoken)
            return {
                "content": [{"type": "text", "text": e.spoken}],
                "structuredContent": e.detail,
                "isError": True,
            }
        took = (time.time() - started) * 1000
        LOG.info("tool %s ok in %.0fms", name, took)

        # Every tool returns (spoken_text, structured, ui_payload).
        spoken, structured, ui = result
        out = {
            "content": [{"type": "text", "text": spoken}],
            "structuredContent": structured,
        }
        meta = {"sideline": {"tool": name, "took_ms": round(took)}}
        if ui and spec.get("_meta", {}).get("ui"):
            meta["ui"] = {"uri": spec["_meta"]["ui"], "data": ui}
        out["_meta"] = meta
        return out


class Handler(BaseHTTPRequestHandler):
    server_version = "sideline/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------- helpers
    def _origin_ok(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True  # non-browser client; Alexa+ sends none
        allowed = self.server.allowed_origins
        if "*" in allowed:
            return True
        host = urlparse(origin).hostname or ""
        return host in allowed

    def _send(self, code, payload=None, headers=None):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id, MCP-Protocol-Version")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

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

    def do_GET(self):
        # A query string is not part of the route.
        if urlparse(self.path).path in ("/", "/simulator", "/simulator/", "/index.html"):
            return self._serve_simulator()
        if self.path == "/health":
            return self._send(200, {"ok": True, "protocol": PROTOCOL_VERSION,
                                    "tools": len(public_tools())})
        if self.path == "/voice/capabilities":
            # Simulator support, not part of the MCP surface. The browser
            # asks once at load whether to post audio here or fall back
            # to its own engine. See sideline/voice.py.
            from ..voice import capabilities
            # Setup hints name credentials and install commands: for the
            # developer's console and CLI check, never for a listener's
            # screen, so they are not sent to the page at all.
            public = {k: v for k, v in capabilities().items() if not k.endswith("_hint")}
            return self._send(200, public, {"Access-Control-Allow-Origin": "*"})
        if self.path.rstrip("/") != "/mcp":
            return self._send(404, {"error": "not found"})
        if not self._origin_ok():
            return self._send(403, {"error": "origin not allowed"})

        sid = self.headers.get("Mcp-Session-Id")
        if sid and not self.server.sessions.touch(sid):
            return self._send(404, {"error": "unknown session"})

        # Optional SSE channel. We hold it open but currently push nothing:
        # Alexa+ owns the turn model, so the server cannot make the device
        # speak first. Kept open and correct so that if the platform ever
        # allows server-initiated messages, the "goal just went in"
        # notification has somewhere to go. See docs/PRODUCT_FEEDBACK.md.
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("MCP-Protocol-Version", PROTOCOL_VERSION)
        self.end_headers()
        try:
            deadline = time.time() + 300
            while time.time() < deadline:
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(15)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_DELETE(self):
        if self.path.rstrip("/") != "/mcp":
            return self._send(404, {"error": "not found"})
        sid = self.headers.get("Mcp-Session-Id")
        if sid:
            self.server.sessions.drop(sid)
        return self._send(204)

    def do_OPTIONS(self):
        # The simulator is opened as a file:// page, so every request to
        # it is cross-origin. Only the voice endpoints are opened up;
        # /mcp keeps its Origin allow-list.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Mcp-Session-Id")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _voice(self):
        """/voice/stt and /voice/tts. Simulator only."""
        from .. import voice
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        cors = {"Access-Control-Allow-Origin": "*"}

        if self.path == "/voice/stt":
            mime = self.headers.get("X-Audio-Type") or "audio/webm"
            hint = ""
            hinter = getattr(self.server, "voice_hint", None)
            if hinter:
                hint = hinter(self.server.resolve_listener(self.headers))
            out = voice.transcribe(raw, mime, hint)
            if not out:
                return self._send(503, {"error": "no speech provider configured"}, cors)
            LOG.info("stt (%s): %s", out["provider"], out["text"][:60])
            return self._send(200, out, cors)

        if self.path == "/voice/tts":
            try:
                text = json.loads(raw.decode("utf-8")).get("text", "")
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"error": "bad body"}, cors)
            out = voice.synthesize(text)
            if not out:
                return self._send(503, {"error": "no voice provider configured"}, cors)
            return self._send(200, out, cors)

        return self._send(404, {"error": "not found"}, cors)

    def do_POST(self):
        if self.path.startswith("/voice/"):
            return self._voice()
        if self.path == "/agent/chat":
            if not self._origin_ok():
                return self._send(403, {"error": "origin not allowed"})
            return self._agent_chat(self._listener())
        if self.path.rstrip("/") != "/mcp":
            return self._send(404, {"error": "not found"})
        if not self._origin_ok():
            return self._send(403, {"error": "origin not allowed"})
        listener_id = self._listener()
        _REQUEST.agent = self.headers.get("X-Sideline-Agent") == "1"

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            msg = json.loads(raw.decode("utf-8")) if raw else None
        except (ValueError, UnicodeDecodeError):
            return self._rpc_error(ParseError("could not parse JSON"), None, 400)

        if msg is None:
            return self._rpc_error(InvalidRequest("empty body"), None, 400)

        is_init = isinstance(msg, dict) and msg.get("method") == "initialize"
        sid = self.headers.get("Mcp-Session-Id")
        extra = {}

        if is_init:
            sid = self.server.sessions.create()
            extra["Mcp-Session-Id"] = sid
        elif sid:
            if not self.server.sessions.touch(sid):
                return self._send(404, {"error": "unknown session"})
        # A client that never initializes still works for tools/list; that
        # makes `curl` debugging and MCP Inspector sane. Alexa+ always
        # initializes first.

        # Batches are legal JSON-RPC. Alexa+ does not currently send them,
        # but a conforming server should accept them.
        if isinstance(msg, list):
            out = []
            for m in msg:
                r = self._one(m, listener_id)
                if r is not None:
                    out.append(r)
            if not out:
                return self._send(202, None, extra)
            return self._send(200, out, extra)

        result = self._one(msg, listener_id)
        if result is None:
            return self._send(202, None, extra)   # notification
        return self._send(200, result, extra)

    def _agent_chat(self, listener_id):
        """Simulator endpoint: Nova selects and runs tools from the MCP registry."""
        if not self.server.agent_runner:
            return self._send(503, {"error": "Nova agent is not configured"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > 16_384:
            return self._send(413, {"error": "request is too large"})
        try:
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            return self._send(400, {"error": "invalid JSON"})
        question = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            return self._send(400, {
                "error": "text must be a non-empty string of at most 1000 characters"
            })
        try:
            result = self.server.agent_runner(question.strip(), listener_id)
        except Exception as e:                           # noqa: BLE001
            from ..language.agent import AgentUnavailable
            if isinstance(e, AgentUnavailable):
                LOG.warning("Nova agent unavailable: %s", e)
                return self._send(503, {"error": "Nova agent unavailable"})
            LOG.exception("Nova agent request failed")
            return self._send(500, {"error": "Nova agent request failed"})
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


class McpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, tool_runner, resolve_listener, allowed_origins,
                 agent_runner=None):
        ThreadingHTTPServer.__init__(self, addr, Handler)
        self.agent_runner = agent_runner
        self.sessions = Sessions()
        self.dispatcher = Dispatcher(tool_runner, self.sessions)
        self.resolve_listener = resolve_listener
        self.allowed_origins = set(allowed_origins)


def serve(host, port, tool_runner, resolve_listener, allowed_origins, agent_runner=None):
    srv = McpServer((host, port), tool_runner, resolve_listener, allowed_origins,
                    agent_runner)
    LOG.info("MCP endpoint on http://%s:%d/mcp (spec %s)", host, port, PROTOCOL_VERSION)
    return srv
