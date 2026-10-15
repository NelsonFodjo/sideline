"""Configuration, from environment variables.

Environment variables win. An optional `.env` file in the repository root fills
in whatever is not exported (sideline/envfile.py); it is git-ignored. Every
variable is documented in docs/ENVIRONMENT.md, and tests/test_environment.py
fails if the code, `.env.example` and that page ever disagree.

There is no demo mode and no recorded data: the server connects to
live multi-sport feeds (ESPN Universal Multi-Sport Provider covering
Soccer, Basketball, American Football, Baseball, and Hockey).
"""

import os

# Every environment variable the code reads, and nothing else. This is the one
# source of truth: `make env` prints from it, and tests/test_environment.py fails
# if the code, this list, `.env.example` and docs/ENVIRONMENT.md ever disagree.
VARIABLES = [
    # Live sports polling
    ("SIDELINE_POLL_SECONDS", False, "30", "Seconds between polls of a followed match while it is in play. A match not yet started is checked every 5 minutes, a finished one once"),
    # The server
    ("SIDELINE_HOST", False, "127.0.0.1", "Interface to bind"),
    ("SIDELINE_PORT", False, "8765", "Port"),
    ("SIDELINE_LOG", False, "INFO", "Log level"),
    ("SIDELINE_LOG_DIR", False, "logs", "Folder for daily log files (a text log and a JSON line per call); off disables. Git-ignored"),
    ("SIDELINE_LOG_KEEP_DAYS", False, "14", "Days of log files to keep; older ones are deleted"),
    ("SIDELINE_ALLOWED_ORIGINS", False, "localhost,127.0.0.1", "Browser origins allowed (DNS-rebinding guard): full origins such as https://host:8443, or bare host names meaning http://<host>:<SIDELINE_PORT>"),
    # AWS: credentials, then what uses them
    ("AWS_REGION", False, "us-east-1", "Region for Bedrock, DynamoDB and Polly"),
    ("AWS_ACCESS_KEY_ID", True, "", "AWS credentials (with the secret below)"),
    ("AWS_SECRET_ACCESS_KEY", True, "", "AWS credentials (with the key id above)"),
    ("SIDELINE_BEDROCK", False, "auto", "auto (on when AWS credentials are present), on, or off"),
    ("SIDELINE_BEDROCK_MODEL", False, "us.anthropic.claude-sonnet-4-5-20250929-v1:0", "Bedrock model or inference-profile id"),
    ("SIDELINE_STATE", False, "auto", "auto (DynamoDB if it answers, else memory), memory, or dynamo"),
    ("SIDELINE_TABLE", False, "sideline", "DynamoDB table name"),
    # Voice, for the simulator
    ("GROQ_API_KEY", True, "", "Groq API key for Whisper Large v3 Turbo (~200ms)"),
    ("SIDELINE_TTS", False, "auto", "Speech out: auto, browser (<15ms), cartesia (~60ms), elevenlabs (~75ms), or polly"),
    ("CARTESIA_API_KEY", True, "", "Cartesia API key for Sonic TTS (~60ms with word timestamps)"),
    ("ELEVENLABS_API_KEY", True, "", "ElevenLabs API key for Flash v2.5 TTS (~75ms with timestamps)"),
    ("ELEVENLABS_VOICE_ID", False, "21m00Tcm4TlvDq8ikWAM", "ElevenLabs voice ID (default: Rachel / conversational)"),
    ("SIDELINE_POLLY_VOICE", False, "Amy", "Polly voice (speech out)"),
    ("SIDELINE_POLLY_ENGINE", False, "generative", "Polly engine: generative (most natural, falls back to neural) or neural"),
    ("SIDELINE_STT", False, "auto", "Speech in: auto (Voxtral, then Nova Sonic, on Bedrock), voxtral, sonic, or off"),
    ("SIDELINE_WEATHER", False, "on", "on adds the weather at the ground to a match preview (city and country go to Open-Meteo); off does not"),
    ("SIDELINE_LIVE_CAPTION", False, "browser", "browser types interim words while you speak (audio also reaches the browser vendor); off does not"),
]

_ON = ("1", "true", "yes", "on")
STATES = ("auto", "memory", "dynamo")


class ConfigError(RuntimeError):
    """The server cannot start with what it has been given. The message says what to do."""
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


def _int(errors, name, raw, low, high):
    """An integer setting, or None (with the problem noted) when it is not one in range."""
    try:
        value = int(str(raw).strip())
    except ValueError:
        errors.append("%s must be a whole number, not %r" % (name, raw))
        return None
    if not low <= value <= high:
        errors.append("%s must be between %d and %d, not %d" % (name, low, high, value))
        return None
    return value


class Config:
    """Read once at import. A bad value never raises here (scripts import this too): it falls back
    to the default and is listed in `errors`; `check()` turns the list into one readable ConfigError."""

    def __init__(self):
        errors = self.errors = []
        self.host = os.environ.get("SIDELINE_HOST", "127.0.0.1")
        self.port = _int(errors, "SIDELINE_PORT", os.environ.get("SIDELINE_PORT", "8765"), 1, 65535) or 8765
        self.log_level = os.environ.get("SIDELINE_LOG", "INFO")
        self.log_dir = os.environ.get("SIDELINE_LOG_DIR", "logs")
        self.log_keep_days = _int(errors, "SIDELINE_LOG_KEEP_DAYS",
                                  os.environ.get("SIDELINE_LOG_KEEP_DAYS", "14"), 1, 3650) or 14

        # Seconds between polls of each followed match.
        self.poll_seconds = _int(errors, "SIDELINE_POLL_SECONDS",
                                 os.environ.get("SIDELINE_POLL_SECONDS", "30"), 5, 3600) or 30

        # Listener state: DynamoDB, or memory. Table: docs/AWS_SETUP.md.
        self.state = state_kind()
        if self.state not in STATES:
            errors.append("SIDELINE_STATE must be one of %s, not %r" % (", ".join(STATES), self.state))
            self.state = "memory"
        self.table = os.environ.get("SIDELINE_TABLE", "sideline")
        self.region = os.environ.get("AWS_REGION", "us-east-1")

        # Origin allow-list. Alexa+ sends no Origin header, so this only affects
        # browsers: it closes the DNS-rebinding hole the MCP spec warns about for
        # locally bound servers. Entries are full origins, or bare host names on this port.
        self.allowed_origins = [o.strip() for o in os.environ.get(
            "SIDELINE_ALLOWED_ORIGINS", "localhost,127.0.0.1").split(",") if o.strip()]

    def check(self):
        """Raise ConfigError naming every bad setting, so the server stops with a sentence, not a traceback."""
        if self.errors:
            raise ConfigError("Sideline cannot start:\n  " + "\n  ".join(self.errors)
                              + "\nFix these in your environment or .env (see docs/ENVIRONMENT.md).")


CONFIG = Config()
