"""Configuration. Environment only, no config files.

Defaults are chosen so that `python -m sideline` with no environment at
all starts a working server against a recorded match. A judge should be
able to clone this and hear a real answer in under a minute, with no
AWS account and no API key. Anything that would break that is opt-in.
"""

import os

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

    # replay (default, no key needed) | apifootball (needs a key)
    provider = os.environ.get("SIDELINE_PROVIDER", "replay")
    replay_path = _path(os.environ.get("SIDELINE_REPLAY",
                                       "data/replay/arsenal-spurs.json"))
    replay_speed = float(os.environ.get("SIDELINE_REPLAY_SPEED", "1.0"))
    replay_start = int(os.environ.get("SIDELINE_REPLAY_START", "0"))
    football_key = os.environ.get("SIDELINE_FOOTBALL_KEY", "")

    # memory (default) | dynamo (reference only in this submission)
    state = os.environ.get("SIDELINE_STATE", "memory")
    table = os.environ.get("SIDELINE_TABLE", "sideline")
    region = os.environ.get("AWS_REGION", "us-east-1")

    bedrock = _bool("SIDELINE_BEDROCK", False)

    poll_seconds = int(os.environ.get("SIDELINE_POLL_SECONDS", "15"))

    # Origin allow-list. Alexa+ sends no Origin header, so this only
    # affects browsers - which is the point: it closes the DNS-rebinding
    # hole the MCP spec warns about for locally bound servers.
    allowed_origins = [o.strip() for o in os.environ.get(
        "SIDELINE_ALLOWED_ORIGINS", "localhost,127.0.0.1").split(",") if o.strip()]

    log_level = os.environ.get("SIDELINE_LOG", "INFO")


CONFIG = Config()
