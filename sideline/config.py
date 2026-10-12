"""Configuration. Environment variables first.

Configuration comes from environment variables, which take priority over
everything. An optional .env file in the repo root fills in whatever you
have not exported (sideline/envfile.py); it is git-ignored. See
docs/ENVIRONMENT.md for every variable, and `make env` to see which are
set (it never prints a value).

Integrations default to "auto": present credentials switch them on
(sideline/autodetect.py), an explicit value always wins.

Defaults are chosen so that `python -m sideline` with no environment at
all starts a working server against a recorded match. A judge should be
able to clone this and hear a real answer in under a minute, with no
AWS account and no API key. Anything that would break that is opt-in.
"""

import os

from . import autodetect

# Paths in this file resolve against the repository, not against whatever
# directory you happen to be standing in. Without this, `python3 run.py`
# from anywhere but the repo root fails to find the replay data - which
# is a confusing error for something that has nothing to do with the
# user's mistake.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _path(value):
    return value if os.path.isabs(value) else os.path.join(_ROOT, value)


def _bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


class Config:
    host = os.environ.get("SIDELINE_HOST", "127.0.0.1")
    port = int(os.environ.get("SIDELINE_PORT", "8765"))

    # auto (default) | replay | apifootball. Auto = live when a key is present.
    provider = autodetect.provider_kind(os.environ)
    replay_path = _path(os.environ.get("SIDELINE_REPLAY",
                                       "data/replay/spurs-arsenal-2016.json"))
    replay_speed = float(os.environ.get("SIDELINE_REPLAY_SPEED", "1.0"))
    replay_start = int(os.environ.get("SIDELINE_REPLAY_START", "0"))
    football_key = os.environ.get("SIDELINE_FOOTBALL_KEY", "")
    # Secrets Manager name or ARN; read at startup if no key is set above.
    football_secret = os.environ.get("SIDELINE_FOOTBALL_SECRET", "")

    # auto (default) | memory | dynamo. See autodetect.py; table: docs/AWS_SETUP.md
    state = autodetect.state_kind(os.environ)
    table = os.environ.get("SIDELINE_TABLE", "sideline")
    region = os.environ.get("AWS_REGION", "us-east-1")

    bedrock = autodetect.bedrock_enabled(os.environ)

    poll_seconds = int(os.environ.get("SIDELINE_POLL_SECONDS", "15"))

    # Origin allow-list. Alexa+ sends no Origin header, so this only
    # affects browsers - which is the point: it closes the DNS-rebinding
    # hole the MCP spec warns about for locally bound servers.
    allowed_origins = [o.strip() for o in os.environ.get(
        "SIDELINE_ALLOWED_ORIGINS", "localhost,127.0.0.1").split(",") if o.strip()]

    # off (default) | required. See sideline/auth.py and docs/ALEXA_SETUP.md.
    auth = os.environ.get("SIDELINE_AUTH", "off").strip().lower()
    auth_issuer = os.environ.get("SIDELINE_AUTH_ISSUER", "")
    # Optional: enforce this `aud`. Alexa's docs do not say tokens carry one.
    auth_audience = os.environ.get("SIDELINE_AUTH_AUDIENCE", "")
    auth_scopes = os.environ.get("SIDELINE_AUTH_SCOPES", "")
    auth_jwks_url = os.environ.get("SIDELINE_AUTH_JWKS_URL", "")
    auth_hs256_secret = os.environ.get("SIDELINE_AUTH_HS256_SECRET", "")
    # Canonical HTTPS URL of this server's MCP endpoint, exactly as in the
    # Alexa+ add-on manifest. Published as `resource` in the RFC 9728 metadata.
    public_url = os.environ.get("SIDELINE_PUBLIC_URL", "")

    log_level = os.environ.get("SIDELINE_LOG", "INFO")


CONFIG = Config()
