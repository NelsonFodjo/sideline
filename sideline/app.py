"""Wiring. The only place that knows which provider and store are in use."""

import logging
import sys
import threading

from . import language
from .config import CONFIG
from .mcp import server as mcp_server
from .mcp.client import McpClient
from .poller import Poller
from .providers import build as build_provider
from .state import build as build_store
from .tools import REGISTRY


class ConfigError(RuntimeError):
    """The server cannot start with what it has been given. The message says what to do."""


class Context:
    """Everything a tool needs. Passed to every tool call."""

    def __init__(self, provider, store, lang):
        self.provider = provider
        self.store = store
        self.lang = lang


def resolve_listener(headers):
    """Who is asking: a header, else one shared id.

    There is no account linking, so identity is only a convenience key for
    listener state. Safe for one real listener; do not expose to several.
    """
    return headers.get("X-Sideline-Listener") or "local-listener"


def tool_runner(ctx):
    """The function the MCP server calls for every tools/call."""
    def run_tool(name, args, listener_id, agent=False):
        if agent and name == "what_did_i_miss":
            # The agent wants the event facts, not a second model-written paragraph.
            return REGISTRY[name](ctx, args, listener_id, agent_mode=True)
        return REGISTRY[name](ctx, args, listener_id)
    return run_tool


def build(provider=None):
    """The context, server and poller. `provider` is for tests; the product
    always reads the live football feed."""
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s  %(message)s")

    if provider is None:
        if not CONFIG.football_key:
            raise ConfigError(
                "SIDELINE_FOOTBALL_KEY is not set.\n"
                "  Sideline reads a live football feed (API-Football) and has no recorded\n"
                "  or demo data. Get a free key at https://dashboard.api-football.com, then:\n"
                "      cp .env.example .env     # and put the key in SIDELINE_FOOTBALL_KEY\n"
                "  See the README, 'Run it'.")
        provider = build_provider(CONFIG.football_key)

    store = build_store(CONFIG.state, table_name=CONFIG.table, region=CONFIG.region)
    ctx = Context(provider, store, language)

    run_tool = tool_runner(ctx)

    def run_agent(question, listener_id):
        from . import resolve
        from .language.agent import run as run_agent_turn

        def run_agent_tool(name, args, tool_listener_id):
            # Nova's tool calls go through our own /mcp endpoint, as an external
            # client's would: the simulator really is an MCP client.
            return bridge.call(name, args, tool_listener_id, agent=True)

        # What did they mean? A short answer to a choice we just offered is
        # snapped to the closest option, and a misheard name from this match is
        # repaired, before the model ever sees it.
        understood = resolve.understand(ctx, listener_id, question)
        result = run_agent_turn(ctx, understood["agent_text"], listener_id, run_agent_tool)
        resolve.learn(ctx, listener_id, result)
        if understood["changed"]:
            result["understood"] = understood["text"]
            result["heard"] = understood["heard"]
            result["understood_why"] = understood["why"]
        return result

    srv = mcp_server.serve(CONFIG.host, CONFIG.port, run_tool, resolve_listener,
                           CONFIG.allowed_origins, agent_runner=run_agent)
    bridge = McpClient("http://127.0.0.1:%d/mcp" % srv.server_address[1])
    from . import voice
    srv.voice_hint = lambda listener_id: voice.vocabulary_hint(ctx, listener_id)
    poller = Poller(ctx, CONFIG.poll_seconds)
    return ctx, srv, poller


def main():
    try:
        ctx, srv, poller = build()
    except ConfigError as e:
        sys.exit("\n" + str(e) + "\n")
    poller.start()
    log = logging.getLogger("sideline")
    from .voice import capabilities
    caps = capabilities()
    log.info("provider=%s state=%s bedrock=%s",
             ctx.provider.name,
             type(ctx.store).__name__.replace("Store", "").lower(),
             "on" if language.bedrock.available() else "off")
    log.info("voice: in=%s out=%s%s",
             caps["stt"] or "browser", caps["tts"] or "browser",
             (" (%s)" % caps["voice"]) if caps["tts"] else "")
    threading.Thread(target=_warm, daemon=True, name="sideline-warm").start()
    log.info("try:  open http://%s:%d/   (health: /health)", CONFIG.host, CONFIG.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("stopping")
    finally:
        poller.stop()
        srv.server_close()


def _warm():
    from . import voice
    voice.warm()
