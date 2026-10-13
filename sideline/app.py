"""Wiring. The only place that knows which provider and store are in use."""

import logging
import sys
import threading

from . import audit, language
from .config import CONFIG
from .mcp import registry
from .mcp import server as mcp_server
from .mcp.client import McpClient
from .poller import Poller
from .providers import build as build_provider
from .providers.sportmonks import HOURLY_CALLS
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

    folder = audit.setup(CONFIG.log_dir, CONFIG.log_keep_days)
    if folder:
        logging.getLogger("sideline").info("logs: %s (a new file each day, kept %d days)", folder, CONFIG.log_keep_days)

    test_provider = provider is not None
    if provider is None:
        if not CONFIG.sportmonks_token:
            raise ConfigError(
                "SPORTMONKS_TOKEN is not set.\n"
                "  Sideline reads a live football feed (Sportmonks) and has no recorded\n"
                "  or demo data. Get a free token at https://www.sportmonks.com, then:\n"
                "      cp .env.example .env     # and put the token in SPORTMONKS_TOKEN\n"
                "  See the README, 'Run it'.")
        provider = build_provider(CONFIG.sportmonks_token)

    # Offer only the tools this feed can answer: a model is never shown a tool that would fail.
    registry.limit_to(getattr(provider, "capabilities", None))
    # A server built with a test provider (invented data) must never write to a real table: that is how a followed
    # match the feed has never heard of once ended up in someone's DynamoDB. Memory only, whatever SIDELINE_STATE says.
    store = build_store("memory" if test_provider else CONFIG.state, table_name=CONFIG.table, region=CONFIG.region)
    ctx = Context(provider, store, language)

    run_tool = tool_runner(ctx)

    def run_agent(question, listener_id, tz_offset_minutes=None, interrupted=None, tz_name=None):
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
        if tz_offset_minutes is not None:
            # Times are said in the listener's own clock, as the page reports it.
            rec = ctx.store.listener(listener_id)
            if rec.get("tz_offset_minutes") != tz_offset_minutes or rec.get("tz_name") != tz_name:
                rec["tz_offset_minutes"] = tz_offset_minutes
                rec["tz_name"] = tz_name
                ctx.store.save_listener(rec)
        result = run_agent_turn(ctx, understood["agent_text"], listener_id, run_agent_tool,
                                interrupted=interrupted)
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
    per_hour = 3600 // max(1, CONFIG.poll_seconds)
    log.info("poll: every %ds while a match is in play, so one uses %d of the plan's %d calls an hour "
             "(a match not yet started is checked every 5 minutes, a finished one once)",
             CONFIG.poll_seconds, per_hour, HOURLY_CALLS)
    if per_hour * 2 > HOURLY_CALLS:
        log.warning("poll: over half the hourly limit goes on one match; the rest is for questions "
                    "(searches, previews, standings). Raise SIDELINE_POLL_SECONDS if the feed starts refusing.")
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
