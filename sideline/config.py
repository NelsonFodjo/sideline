"""Configuration, from environment variables.

Environment variables win. An optional `.env` file in the repository root fills
in whatever is not exported (sideline/envfile.py); it is git-ignored. Every
variable is documented in docs/ENVIRONMENT.md, and tests/test_environment.py
fails if the code, `.env.example` and that page ever disagree.

There is no demo mode and no recorded data: the server needs a football feed key
(SIDELINE_FOOTBALL_KEY) and says so at startup if it is missing.
"""

import os

# Every environment variable the code reads, and nothing else. This is the one
# source of truth: `make env` prints from it, and tests/test_environment.py fails
# if the code, this list, `.env.example` and docs/ENVIRONMENT.md ever disagree.
# (name, secret?, default, what it does)
VARIABLES = [
    # The live football feed
    ("SIDELINE_FOOTBALL_KEY", True, "", "API-Football key. Required: there is no recorded or demo data"),
    ("SIDELINE_POLL_SECONDS", False, "60", "Seconds between polls of a followed match (free plan: 100 requests a day)"),
    # The server
    ("SIDELINE_HOST", False, "127.0.0.1", "Interface to bind"),
    ("SIDELINE_PORT", False, "8765", "Port"),
    ("SIDELINE_LOG", False, "INFO", "Log level"),
    ("SIDELINE_ALLOWED_ORIGINS", False, "localhost,127.0.0.1", "Browser origins allowed (DNS-rebinding guard)"),
    # AWS: credentials, then what uses them
    ("AWS_REGION", False, "us-east-1", "Region for Bedrock, DynamoDB and Polly"),
    ("AWS_ACCESS_KEY_ID", True, "", "AWS credentials (with the secret below)"),
    ("AWS_SECRET_ACCESS_KEY", True, "", "AWS credentials (with the key id above)"),
    ("AWS_PROFILE", False, "", "A named AWS profile, instead of keys"),
    ("AWS_BEARER_TOKEN_BEDROCK", True, "", "A Bedrock API key (Bedrock only, not Polly or DynamoDB)"),
    ("SIDELINE_BEDROCK", False, "auto", "auto (on when AWS credentials are present), on, or off"),
    ("SIDELINE_BEDROCK_MODEL", False, "amazon.nova-micro-v1:0", "Bedrock model or inference-profile id"),
    ("SIDELINE_STATE", False, "auto", "auto (DynamoDB if it answers, else memory), memory, or dynamo"),
    ("SIDELINE_TABLE", False, "sideline", "DynamoDB table name"),
    # Voice, for the simulator
    ("SIDELINE_POLLY_VOICE", False, "Amy", "Polly voice (speech out)"),
    ("SIDELINE_STT", False, "auto", "Speech in: auto, groq, sonic, or off"),
    ("GROQ_API_KEY", True, "", "Turns on Groq Whisper for speech in. Audio then leaves AWS"),
    ("SIDELINE_LIVE_CAPTION", False, "browser", "browser types interim words while you speak (audio also reaches the browser vendor); off does not"),
]

_ON = ("1", "true", "yes", "on")
_OFF = ("0", "false", "no", "off")


def aws_credentials(env=None):
    """Is there a way to authenticate to AWS in this environment?

    Static keys, a named profile, or a Bedrock API key. Anything else (an
    instance role, say) is not detected here: set SIDELINE_BEDROCK=on and
    SIDELINE_STATE=dynamo explicitly.
    """
    env = os.environ if env is None else env
    if env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY"):
        return True
    return bool(env.get("AWS_PROFILE") or env.get("AWS_BEARER_TOKEN_BEDROCK"))


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

    # The live football feed (API-Football). Required to start the server.
    football_key = os.environ.get("SIDELINE_FOOTBALL_KEY", "")
    # Seconds between polls of each followed match. A free plan allows 100
    # requests a day, which one match at 15 s burns in under half an hour: 60.
    poll_seconds = int(os.environ.get("SIDELINE_POLL_SECONDS", "60"))

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
