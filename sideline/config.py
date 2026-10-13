"""Configuration, from environment variables.

Environment variables win. An optional `.env` file in the repository root fills
in whatever is not exported (sideline/envfile.py); it is git-ignored. Every
variable is documented in docs/ENVIRONMENT.md, and tests/test_environment.py
fails if the code, `.env.example` and that page ever disagree.

There is no demo mode and no recorded data: the server needs a Sportmonks token
(SPORTMONKS_TOKEN) and says so at startup if it is missing.
"""

import os

# Every environment variable the code reads, and nothing else. This is the one
# source of truth: `make env` prints from it, and tests/test_environment.py fails
# if the code, this list, `.env.example` and docs/ENVIRONMENT.md ever disagree.
# (name, secret?, default, what it does)
VARIABLES = [
    # The live football feed
    ("SPORTMONKS_TOKEN", True, "", "Sportmonks token (free plan: a few leagues, 180 calls an hour). Required: there is no recorded or demo data"),
    ("SIDELINE_POLL_SECONDS", False, "30", "Seconds between polls of a followed match while it is in play (free plan: 180 calls an hour). A match not yet started is checked every 5 minutes, a finished one once"),
    # The server
    ("SIDELINE_HOST", False, "127.0.0.1", "Interface to bind"),
    ("SIDELINE_PORT", False, "8765", "Port"),
    ("SIDELINE_LOG", False, "INFO", "Log level"),
    ("SIDELINE_LOG_DIR", False, "logs", "Folder for daily log files (a text log and a JSON line per call); off disables. Git-ignored"),
    ("SIDELINE_LOG_KEEP_DAYS", False, "14", "Days of log files to keep; older ones are deleted"),
    ("SIDELINE_ALLOWED_ORIGINS", False, "localhost,127.0.0.1", "Browser origins allowed (DNS-rebinding guard)"),
    # AWS: credentials, then what uses them
    ("AWS_REGION", False, "us-east-1", "Region for Bedrock, DynamoDB and Polly"),
    ("AWS_ACCESS_KEY_ID", True, "", "AWS credentials (with the secret below)"),
    ("AWS_SECRET_ACCESS_KEY", True, "", "AWS credentials (with the key id above)"),
    ("SIDELINE_BEDROCK", False, "auto", "auto (on when AWS credentials are present), on, or off"),
    ("SIDELINE_BEDROCK_MODEL", False, "amazon.nova-micro-v1:0", "Bedrock model or inference-profile id"),
    ("SIDELINE_STATE", False, "auto", "auto (DynamoDB if it answers, else memory), memory, or dynamo"),
    ("SIDELINE_TABLE", False, "sideline", "DynamoDB table name"),
    # Voice, for the simulator
    ("SIDELINE_POLLY_VOICE", False, "Amy", "Polly voice (speech out)"),
    ("SIDELINE_POLLY_ENGINE", False, "generative", "Polly engine: generative (most natural, falls back to neural) or neural"),
    ("SIDELINE_STT", False, "auto", "Speech in: auto (Voxtral, then Nova Sonic, on Bedrock), voxtral, sonic, or off"),
    ("SIDELINE_WEATHER", False, "on", "on adds the weather at the ground to a match preview (city and country go to Open-Meteo); off does not"),
    ("SIDELINE_AGENT_TOOLS", False, "all", "Tools offered to the voice agent: all, or core (the core eleven, which route more reliably on a small model)"),
    ("SIDELINE_LIVE_CAPTION", False, "browser", "browser types interim words while you speak (audio also reaches the browser vendor); off does not"),
]

_ON = ("1", "true", "yes", "on")
_OFF = ("0", "false", "no", "off")


def aws_credentials(env=None):
    """Is there a way to authenticate to AWS in this environment?

    The access key pair. Anything else (an instance role, say) is not detected
    here: set SIDELINE_BEDROCK=on and SIDELINE_STATE=dynamo explicitly.
    """
    env = os.environ if env is None else env
    return bool(env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY"))


def bedrock_enabled(env=None):
    """SIDELINE_BEDROCK: auto (on when AWS credentials are present), on, or off."""
    env = os.environ if env is None else env
    v = (env.get("SIDELINE_BEDROCK") or "auto").strip().lower()
    if v in _ON:
        return True
    if v in _OFF:
        return False
    return aws_credentials(env)


def state_kind(env=None):
    """SIDELINE_STATE: memory, dynamo, or auto (try DynamoDB, else memory)."""
    env = os.environ if env is None else env
    v = (env.get("SIDELINE_STATE") or "auto").strip().lower()
    if v != "auto":
        return v
    return "auto" if aws_credentials(env) else "memory"


class Config:
    host = os.environ.get("SIDELINE_HOST", "127.0.0.1")
    port = int(os.environ.get("SIDELINE_PORT", "8765"))
    log_level = os.environ.get("SIDELINE_LOG", "INFO")
    log_dir = os.environ.get("SIDELINE_LOG_DIR", "logs")
    log_keep_days = int(os.environ.get("SIDELINE_LOG_KEEP_DAYS", "14"))

    # The live football feed (Sportmonks). Required to start the server.
    sportmonks_token = os.environ.get("SPORTMONKS_TOKEN", "")
    # Seconds between polls of each followed match. The free plan allows 180 calls an
    # hour per kind of data, so one match in play at 30 s uses two thirds of it.
    poll_seconds = int(os.environ.get("SIDELINE_POLL_SECONDS", "30"))

    # Listener state: DynamoDB, or memory. Table: docs/AWS_SETUP.md.
    state = state_kind()
    table = os.environ.get("SIDELINE_TABLE", "sideline")
    region = os.environ.get("AWS_REGION", "us-east-1")

    # Origin allow-list. Alexa+ sends no Origin header, so this only affects
    # browsers: it closes the DNS-rebinding hole the MCP spec warns about for
    # locally bound servers.
    allowed_origins = [o.strip() for o in os.environ.get(
        "SIDELINE_ALLOWED_ORIGINS", "localhost,127.0.0.1").split(",") if o.strip()]


CONFIG = Config()
