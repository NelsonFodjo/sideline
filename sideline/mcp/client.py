"""A minimal MCP client over Streamable HTTP, standard library only.

The voice agent uses it. When Nova chooses a tool, the call is made to this
server's own /mcp endpoint exactly as an external client's would be: a session,
JSON-RPC `tools/call`, schema validation, the same error handling. So the
simulator really is an MCP client of this server, instead of reaching around the
protocol into the tool registry.

It adds one header, `X-Sideline-Agent: 1`, which asks `what_did_i_miss` for its
event facts rather than a model-written paragraph (the agent is a model and would
only paraphrase it; the paragraph costs a second model call).
"""

import json
import threading
import urllib.error
import urllib.request

from .errors import InvalidParams, ToolError

PROTOCOL_VERSION = "2025-11-25"


class McpClient(object):
    def __init__(self, url, timeout=60):
        self.url = url
        self.timeout = timeout
        self._sid = None
        self._id = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------ transport
    def _post(self, body, listener_id, agent=False):
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION,
                   "X-Sideline-Listener": listener_id or ""}
        if agent:
            headers["X-Sideline-Agent"] = "1"
        if self._sid:
            headers["Mcp-Session-Id"] = self._sid
        req = urllib.request.Request(self.url, json.dumps(body).encode("utf-8"), headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            raw = resp.read()
            return sid, (json.loads(raw.decode("utf-8")) if raw else None)

    def _rpc(self, method, params, listener_id, agent=False):
        with self._lock:
            self._id += 1
            return self._post({"jsonrpc": "2.0", "id": self._id, "method": method,
                               "params": params}, listener_id, agent)

    def _initialize(self, listener_id):
        sid, _ = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "sideline-agent", "version": "1"}}, listener_id)
        self._sid = sid
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, listener_id)

    # ----------------------------------------------------------------- tools
    def call(self, name, args, listener_id, agent=False):
        """tools/call. Returns (spoken, structured, ui); raises ToolError when
        the tool declined, InvalidParams when the arguments were refused."""
        if not self._sid:
            self._initialize(listener_id)
        try:
            _, doc = self._rpc("tools/call", {"name": name, "arguments": args},
                               listener_id, agent)
        except urllib.error.HTTPError as e:
            if e.code != 404:                 # 404 = the session is gone: start a new one
                raise
            self._initialize(listener_id)
            _, doc = self._rpc("tools/call", {"name": name, "arguments": args},
                               listener_id, agent)
        if "error" in doc:
            err = doc["error"]
            if err.get("code") == -32602:
                raise InvalidParams(err.get("message", "invalid parameters"))
            raise RuntimeError("MCP error %s: %s" % (err.get("code"), err.get("message")))
        result = doc["result"]
        spoken = (result.get("content") or [{}])[0].get("text", "")
        structured = result.get("structuredContent") or {}
        if result.get("isError"):
            raise ToolError(spoken, structured)
        ui = ((result.get("_meta") or {}).get("ui") or {}).get("data")
        return spoken, structured, ui
