"""A minimal MCP client over Streamable HTTP, standard library only.

Used by the simulated Alexa+ Nova host to discover the MCP server's tool catalog
and execute any selected `tools/call` through the same protocol an external MCP client uses.

It adds one header, `X-Sideline-Agent: 1`, which asks `what_did_i_miss` for its
event facts rather than a model-written paragraph (the agent is a model and would
only paraphrase it; the paragraph costs a second model call).
"""

import json
import threading
import urllib.error
import urllib.request

from sideline.mcp.errors import InvalidParams, ToolError

PROTOCOL_VERSION = "2025-11-25"


class McpClient(object):
    def __init__(self, url, timeout=60, token=""):
        self.url = url
        self.token = token
        self.timeout = timeout
        self._sid = None                       # None: no session yet; "" a server that issues no session id
        self._id = 0
        self._lock = threading.Lock()          # guards the id counter, the session id and the catalog, nothing else
        self._init_lock = threading.Lock()     # one initialize at a time; never held during a tools/call
        self.instructions = ""
        self._cached_catalog = None

    # ------------------------------------------------------------ transport
    def _post(self, body, listener_id, agent=False, sid=None):
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION,
                   "X-Sideline-Listener": listener_id or ""}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if agent:
            headers["X-Sideline-Agent"] = "1"
        if sid:
            headers["Mcp-Session-Id"] = sid
        req = urllib.request.Request(self.url, json.dumps(body).encode("utf-8"), headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            new_sid = resp.headers.get("Mcp-Session-Id")
            raw = resp.read()
            return new_sid, (json.loads(raw.decode("utf-8")) if raw else None)

    def _rpc(self, method, params, listener_id, agent=False, sid=None):
        # The lock covers the id and the session read only, never the HTTP round trip: one slow tool call must not
        # hold up every other listener's (AG-15).
        with self._lock:
            self._id += 1
            call_id = self._id
            if sid is None:
                sid = self._sid
        return self._post({"jsonrpc": "2.0", "id": call_id, "method": method,
                           "params": params}, listener_id, agent, sid=sid)

    def _initialize(self, listener_id, stale=None):
        """Open a session once. A thread that waited while another opened one uses that one (double-checked)."""
        with self._init_lock:
            with self._lock:
                if self._sid is not None and self._sid != stale:
                    return
            sid, doc = self._rpc("initialize", {
                "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                "clientInfo": {"name": "sideline-nova-mcp-host", "version": "1"}}, listener_id, sid="")
            if not isinstance(doc, dict) or not isinstance(doc.get("result"), dict):
                raise RuntimeError("MCP initialize returned no result")
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, listener_id, sid=sid)
            with self._lock:
                self._sid = sid or ""
                self.instructions = doc["result"].get("instructions") or ""
                self._cached_catalog = None

    def _session(self, listener_id):
        """The current session id, opening one if there is none."""
        with self._lock:
            sid = self._sid
        if sid is None:
            self._initialize(listener_id)
            with self._lock:
                sid = self._sid
        return sid

    # ----------------------------------------------------------------- tools
    def discover(self, listener_id):
        """Fetch the MCP server instructions and current tools/list catalog."""
        with self._lock:
            if self._cached_catalog is not None:
                return self._cached_catalog
        sid = self._session(listener_id)
        try:
            _, doc = self._rpc("tools/list", {}, listener_id, sid=sid)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            self._initialize(listener_id, stale=sid)
            _, doc = self._rpc("tools/list", {}, listener_id)
        if not isinstance(doc, dict):
            raise RuntimeError("MCP tools/list returned an invalid response")
        if "error" in doc:
            err = doc["error"]
            raise RuntimeError("MCP error %s: %s" % (err.get("code"), err.get("message")))
        result = doc.get("result") or {}
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise RuntimeError("MCP tools/list returned no tool catalog")
        catalog = {"instructions": self.instructions, "tools": tools}
        with self._lock:
            self._cached_catalog = catalog
        return catalog

    def call(self, name, args, listener_id, agent=False):
        """tools/call. Returns (spoken, structured, ui); raises ToolError when
        the tool declined, InvalidParams when the arguments were refused,
        RuntimeError when the server gave no usable answer."""
        sid = self._session(listener_id)
        try:
            _, doc = self._rpc("tools/call", {"name": name, "arguments": args},
                               listener_id, agent, sid=sid)
        except urllib.error.HTTPError as e:
            if e.code != 404:                 # 404 = the session is gone: start a new one
                raise
            self._initialize(listener_id, stale=sid)
            _, doc = self._rpc("tools/call", {"name": name, "arguments": args},
                               listener_id, agent)
        if not isinstance(doc, dict):
            # a 202 or an empty body is no answer: a failure the agent reports, not a crash
            raise RuntimeError("MCP tools/call returned no response")
        if "error" in doc:
            err = doc["error"] if isinstance(doc["error"], dict) else {}
            if err.get("code") == -32602:
                raise InvalidParams(err.get("message", "invalid parameters"))
            raise RuntimeError("MCP error %s: %s" % (err.get("code"), err.get("message")))
        result = doc.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("MCP tools/call returned no result")
        spoken = ((result.get("content") or [{}])[0] or {}).get("text", "")
        structured = result.get("structuredContent") or {}
        if result.get("isError"):
            raise ToolError(spoken, structured)
        ui = ((result.get("_meta") or {}).get("ui") or {}).get("data")
        return spoken, structured, ui
