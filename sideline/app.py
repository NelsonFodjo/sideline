"""Wiring. The only place that knows which provider and store are in use."""

import logging

from . import auth, language, secretsmanager
from .config import CONFIG
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
    """Who is asking.

    With SIDELINE_AUTH=required the server verifies the bearer token and
    uses its `sub` claim (see sideline/auth.py) and never calls this.
    This function is the SIDELINE_AUTH=off path: a header, then a single
    shared id, so the simulator and `curl` work without an identity
    provider. Unsafe for more than one real listener, because the id is
    the ONLY thing keying listener state.
    """
    return headers.get("X-Sideline-Listener") or "local-listener"


def build():
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s  %(message)s")

    replay = dict(path=CONFIG.replay_path, speed=CONFIG.replay_speed,
                  start_minute=CONFIG.replay_start)
    if CONFIG.provider == "replay":
        provider = build_provider("replay", **replay)
    else:
        # The environment variable wins; Secrets Manager is the fallback.
        key = CONFIG.football_key or secretsmanager.football_key(
            CONFIG.football_secret, CONFIG.region)
        if CONFIG.provider == "apifootball" and not key:
            # A live provider with no key would answer every question with
            # "unavailable". Better to say so loudly and serve the real
            # recorded match, so the server is still demonstrably working.
            logging.getLogger("sideline").warning(
                "SIDELINE_PROVIDER=apifootball but no key (SIDELINE_FOOTBALL_KEY "
                "or SIDELINE_FOOTBALL_SECRET): falling back to the recorded match")
            provider = build_provider("replay", **replay)
        else:
            provider = build_provider(CONFIG.provider, api_key=key)

    store = build_store(CONFIG.state, table_name=CONFIG.table, region=CONFIG.region)
    ctx = Context(provider, store, language)

    def run_tool(name, args, listener_id):
        return REGISTRY[name](ctx, args, listener_id)

    srv = mcp_server.serve(CONFIG.host, CONFIG.port, run_tool,
                           resolve_listener, CONFIG.allowed_origins,
                           authenticator=auth.build(CONFIG))
    poller = Poller(ctx, CONFIG.poll_seconds)
    return ctx, srv, poller


def main():
    ctx, srv, poller = build()
    poller.start()
    log = logging.getLogger("sideline")
    from .voice import capabilities
    caps = capabilities()
    log.info("provider=%s state=%s bedrock=%s",
             ctx.provider.name, type(ctx.store).__name__.replace("Store", "").lower(),
             "on" if language.bedrock.available() else "off")
    log.info("voice: in=%s out=%s%s",
             caps["stt"] or "browser", caps["tts"] or "browser",
             (" (%s, %s)" % (caps["voice"], caps["engine"])) if caps["tts"] else "")
    log.info("try:  curl -s localhost:%d/health", CONFIG.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("stopping")
    finally:
        poller.stop()
        srv.server_close()
