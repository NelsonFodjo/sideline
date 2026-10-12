"""Wiring. The only place that knows which provider and store are in use."""

import logging

from . import language
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

    In production this is the account-linked subject claim from the
    OAuth token Alexa+ presents. Account linking is documented in
    docs/ALEXA_SETUP.md.

    Locally we fall back to a header, then to a single shared id, so the
    simulator and `curl` work without an identity provider. The id is
    the ONLY thing keying listener state, so getting it wrong means one
    listener hears another's catch-up - which is why it lives in one
    function rather than being inlined anywhere.
    """
    # -------------------------------------------------------------
    # auth = headers.get("Authorization", "")
    # if auth.startswith("Bearer "):
    #     claims = verify_jwt(auth[7:])        # see docs/ALEXA_SETUP.md
    #     return claims["sub"]
    # -------------------------------------------------------------
    return headers.get("X-Sideline-Listener") or "local-listener"


def build():
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s %(name)s  %(message)s")

    if CONFIG.provider == "replay":
        provider = build_provider("replay", path=CONFIG.replay_path,
                                  speed=CONFIG.replay_speed,
                                  start_minute=CONFIG.replay_start)
    else:
        provider = build_provider(CONFIG.provider, api_key=CONFIG.football_key)

    store = build_store(CONFIG.state, table_name=CONFIG.table, region=CONFIG.region)
    ctx = Context(provider, store, language)

    def run_tool(name, args, listener_id):
        return REGISTRY[name](ctx, args, listener_id)

    srv = mcp_server.serve(CONFIG.host, CONFIG.port, run_tool,
                           resolve_listener, CONFIG.allowed_origins)
    poller = Poller(ctx, CONFIG.poll_seconds)
    return ctx, srv, poller


def main():
    ctx, srv, poller = build()
    poller.start()
    log = logging.getLogger("sideline")
    from .voice import capabilities
    caps = capabilities()
    log.info("provider=%s state=%s bedrock=%s",
             CONFIG.provider, CONFIG.state, "on" if CONFIG.bedrock else "off")
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
