"""Wiring. The only place that knows which provider and store are in use."""

import errno
import logging
import sys
import threading
import time

from . import audit, language
from .config import CONFIG, ConfigError  # noqa: F401  (ConfigError is part of this module's surface)
from .mcp import registry, trace
from .mcp import server as mcp_server
from .poller import Poller
from .providers import build as build_provider
from .state import build as build_store
from .tools import REGISTRY


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


_WATCHED = ("following", "last_told_at", "broadcast_offset", "supports", "detail", "language", "sport")


def _listener_view(ctx, listener_id):
    try:
        rec = ctx.store.listener(listener_id)
    except Exception:                                          # noqa: BLE001  logging must never break a call
        return {}
    view = {k: rec.get(k) for k in _WATCHED}
    view["told_events"] = len(rec.get("told_event_ids") or [])
    return view


def _feed_counts(provider):
    cache = getattr(provider, "cache", None)
    s = cache.stats() if cache else {}
    return getattr(provider, "request_count", 0), (s.get("hits", 0) + s.get("coalesced", 0)), s.get("misses", 0)


def tool_runner(ctx):
    """The function the MCP server calls for every tools/call."""
    def run_tool(name, args, listener_id, agent=False):
        before, (req0, hit0, _) = _listener_view(ctx, listener_id), _feed_counts(ctx.provider)
        try:
            if agent and name == "what_did_i_miss":
                # The agent wants the event facts, not a second model-written paragraph.
                return REGISTRY[name](ctx, args, listener_id, agent_mode=True)
            return REGISTRY[name](ctx, args, listener_id)
        finally:
            after = _listener_view(ctx, listener_id)
            req1, hit1, _ = _feed_counts(ctx.provider)
            trace.record(feed_requests=req1 - req0, cache_hits=hit1 - hit0,
                         state_changes={k: [before.get(k), after.get(k)] for k in after if before.get(k) != after.get(k)})
    return run_tool


def build(provider=None):
    """The context, server and poller. `provider` is for tests; the product
    always reads the live football feed."""
    CONFIG.check()
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s  %(message)s")

    folder = audit.setup(CONFIG.log_dir, CONFIG.log_keep_days)
    if folder:
        logging.getLogger("sideline").info("logs: %s (a new file each day, kept %d days)", folder, CONFIG.log_keep_days)

    test_provider = provider is not None
    if provider is None:
        provider = build_provider()

    # Offer only the tools this feed can answer: a model is never shown a tool that would fail.
    registry.limit_to(getattr(provider, "capabilities", None))
    # A server built with a test provider (invented data) must never write to a real table: that is how a followed
    # match the feed has never heard of once ended up in someone's DynamoDB. Memory only, whatever SIDELINE_STATE says.
    store = build_store("memory" if test_provider else CONFIG.state, table_name=CONFIG.table, region=CONFIG.region)
    ctx = Context(provider, store, language)

    run_tool = tool_runner(ctx)

    srv = mcp_server.serve(CONFIG.host, CONFIG.port, run_tool, resolve_listener, CONFIG.allowed_origins)
    srv.auth_token = CONFIG.auth_token
    simulator = _simulator()
    if simulator:
        simulator.attach(srv, ctx, token=CONFIG.auth_token)
    poller = Poller(ctx, CONFIG.poll_seconds)
    return ctx, srv, poller


def _already_running():
    """The message for a port that is taken: say whose it is and how to free it, instead of a traceback."""
    port = CONFIG.port
    url = "http://127.0.0.1:%d" % port
    try:
        import urllib.request
        with urllib.request.urlopen(url + "/health", timeout=2) as r:
            ours = b'"protocol"' in r.read()
    except Exception:                                    # noqa: BLE001
        ours = False
    if ours:
        what = "Sideline is already running on port %d (open %s/ for the simulator)." % (port, url)
    else:
        what = "Port %d is used by another program." % port
    return ("\n%s\nTo stop it and start fresh:  lsof -iTCP:%d -sTCP:LISTEN   then   kill <PID>\n"
            "Or use another port:  SIDELINE_PORT=%d make run\n" % (what, port, port + 1))


def _simulator():
    """The simulated Alexa+ plug-in, if this checkout has it. The MCP server runs without it."""
    try:
        from simulator import host
    except ImportError:
        return None
    return host


def main():
    try:
        ctx, srv, poller = build()
    except ConfigError as e:
        sys.exit("\n" + str(e) + "\n")
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        sys.exit(_already_running())
    poller.start()
    log = logging.getLogger("sideline")
    voice = _voice()
    threading.Thread(target=_warm, args=(ctx,), daemon=True, name="sideline-warm").start()
    log.info("poll: every %ds while a match is in play (a match not yet started is checked every 5 minutes, a finished one once)",
             CONFIG.poll_seconds)
    log.info("provider=%s state=%s bedrock=%s",
             ctx.provider.name,
             type(ctx.store).__name__.replace("Store", "").lower(),
             "on" if language.bedrock.available() else "off")
    if voice:
        caps = voice.capabilities()
        log.info("voice: in=%s out=%s%s",
                 caps["stt"] or "browser", caps["tts"] or "browser",
                 (" (%s)" % caps["voice"]) if caps["tts"] else "")
        threading.Thread(target=voice.warm, daemon=True, name="sideline-warm-voice").start()
    log.info("MCP endpoint: http://%s:%d/mcp   (health: /health)%s", CONFIG.host, CONFIG.port,
             "   simulator: /" if voice else "")
    if CONFIG.host not in ("127.0.0.1", "localhost", "::1") and not CONFIG.auth_token:
        log.warning("listening beyond this machine with no SIDELINE_AUTH_TOKEN: anyone who can reach it can use it")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("stopping")
    finally:
        poller.stop()
        srv.server_close()


def _voice():
    try:
        from simulator import voice
    except ImportError:
        return None
    return voice


def _warm(ctx):
    """Open the connections the first question needs, before anyone asks (the first one is otherwise the slowest):
    the feed's league names and today's matches, the state table, and the model client. Never raises."""
    log = logging.getLogger("sideline")
    started = time.time()
    try:
        warm = getattr(ctx.provider, "warm", None)
        if warm:
            warm()
        ctx.store.listener("warm-up")                # one round trip: connection and credentials, for DynamoDB
        if language.bedrock.available():
            language.bedrock.client()
        log.info("warm: ready in %.1fs", time.time() - started)
    except Exception as exc:                         # noqa: BLE001
        log.debug("warm-up skipped: %s", exc)
