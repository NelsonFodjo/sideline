"""Switch integrations on when their credentials are present.

The default for each is "auto": if the environment holds what the
integration needs, it is on; if not, it is off and the server still runs.
An explicit value always wins, so `SIDELINE_BEDROCK=off` turns Bedrock off
even with keys exported.

    SIDELINE_BEDROCK   auto | on | off   on when AWS credentials are present
    SIDELINE_PROVIDER  auto | replay | apifootball
                                         apifootball when a football key or
                                         secret is present, else the replay
    SIDELINE_STATE     auto | memory | dynamo
                                         dynamo when AWS credentials (or a
                                         DynamoDB Local endpoint) are present
                                         AND the table answers; otherwise
                                         memory, with a warning

Pure functions of a mapping, so they are tested without touching the real
environment.
"""

_ON = ("1", "true", "yes", "on")
_OFF = ("0", "false", "no", "off")


def aws_credentials(env):
    """Does the environment hold a way to authenticate to AWS?

    Static keys, a named profile, or the web-identity / container variables
    that ECS, EKS and similar set. App Runner and Lambda inject their own;
    set SIDELINE_BEDROCK=on explicitly there (the stack does).
    """
    if env.get("AWS_ACCESS_KEY_ID") and env.get("AWS_SECRET_ACCESS_KEY"):
        return True
    if env.get("AWS_BEARER_TOKEN_BEDROCK"):
        return True
    return any(env.get(k) for k in (
        "AWS_PROFILE", "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI"))


def bedrock_enabled(env):
    v = (env.get("SIDELINE_BEDROCK") or "auto").strip().lower()
    if v in _ON:
        return True
    if v in _OFF:
        return False
    return aws_credentials(env)


def sideline_mode(env):
    """'live' or 'demo'. Defaults to 'demo' unless SIDELINE_MODE=live or a football key is present."""
    v = (env.get("SIDELINE_MODE") or "").strip().lower()
    if v in ("live", "demo"):
        return v
    has_key = env.get("SIDELINE_FOOTBALL_KEY") or env.get("SIDELINE_FOOTBALL_SECRET")
    return "live" if has_key else "demo"


def catchup_mode(env):
    """'live' (call Bedrock on human ask, no prefill) or 'cached' (background precompute)."""
    v = (env.get("SIDELINE_CATCHUP_MODE") or "").strip().lower()
    if v in ("live", "cached"):
        return v
    mode = (env.get("SIDELINE_MODE") or "").strip().lower()
    return "live" if mode == "live" else "cached"


def provider_kind(env):
    v = (env.get("SIDELINE_PROVIDER") or "auto").strip().lower()
    if v != "auto":
        return v
    mode = (env.get("SIDELINE_MODE") or "").strip().lower()
    if mode == "demo":
        return "replay"
    if mode == "live":
        return "apifootball"
    has_key = env.get("SIDELINE_FOOTBALL_KEY") or env.get("SIDELINE_FOOTBALL_SECRET")
    return "apifootball" if has_key else "replay"


def state_kind(env):
    """"memory", "dynamo", or "auto" (try dynamo, fall back to memory)."""
    v = (env.get("SIDELINE_STATE") or "auto").strip().lower()
    if v != "auto":
        return v
    wants = aws_credentials(env) or env.get("SIDELINE_DYNAMO_ENDPOINT")
    return "auto" if wants else "memory"
