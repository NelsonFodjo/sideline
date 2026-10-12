#!/usr/bin/env python3
"""Show which Sideline environment variables are set. Never prints a value.

    python3 scripts/env_status.py

Secrets show only "set" and a length, so the output is safe to paste into
a chat or a bug report. It reports the environment as the server will see
it, including anything the .env file supplied (environment wins), and then
what each "auto" integration resolves to.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env; environment wins)
from sideline import autodetect  # noqa: E402

# (name, secret?, what it does, default when unset)
GROUPS = [
    ("Runtime mode", [
        ("SIDELINE_MODE", False, "live | demo", "auto: live when football key is set, else demo"),
    ]),
    ("AWS credentials (Bedrock, DynamoDB, Polly, Transcribe)", [
        ("AWS_ACCESS_KEY_ID", True, "access key id", None),
        ("AWS_SECRET_ACCESS_KEY", True, "secret access key", None),
        ("AWS_SESSION_TOKEN", True, "only for temporary credentials", "(none)"),
        ("AWS_REGION", False, "region", "us-east-1"),
    ]),
    ("AWS features", [
        ("SIDELINE_BEDROCK", False, "auto | on | off", "auto: on when AWS keys are present"),
        ("SIDELINE_BEDROCK_MODEL", False, "model or inference-profile id", "anthropic.claude-3-5-haiku-20241022-v1:0"),
        ("SIDELINE_BEDROCK_TIMEOUT", False, "seconds; Alexa+ targets 0.5 round trip", "3.0"),
        ("SIDELINE_CATCHUP_MODE", False, "cached | live", "cached"),
        ("SIDELINE_STATE", False, "auto | memory | dynamo", "auto: DynamoDB if keys + table, else memory"),
        ("SIDELINE_TABLE", False, "DynamoDB table name", "sideline"),
        ("SIDELINE_DYNAMO_ENDPOINT", False, "DynamoDB Local URL", "(real AWS)"),
        ("SIDELINE_EMF", False, "on = CloudWatch metric log lines", "off"),
    ]),
    ("Live football data", [
        ("SIDELINE_PROVIDER", False, "auto | replay | apifootball", "auto: live if a key is set"),
        ("SIDELINE_FOOTBALL_KEY", True, "API-Football key", None),
        ("SIDELINE_FOOTBALL_SECRET", False, "Secrets Manager name/ARN (key var wins)", None),
        ("SIDELINE_POLL_SECONDS", False, "poll interval", "15"),
    ]),
    ("Authentication (SIDELINE_AUTH=required)", [
        ("SIDELINE_AUTH", False, "off | required", "off"),
        ("SIDELINE_AUTH_ISSUER", False, "authorization server issuer URL", None),
        ("SIDELINE_PUBLIC_URL", False, "canonical https URL ending /mcp", None),
        ("SIDELINE_AUTH_JWKS_URL", False, "RS256 signing keys URL", None),
        ("SIDELINE_AUTH_HS256_SECRET", True, "shared secret (tests / simple setups)", None),
        ("SIDELINE_AUTH_SCOPES", False, "scopes_supported", "(none)"),
        ("SIDELINE_AUTH_AUDIENCE", False, "optional aud to enforce", "(not checked)"),
    ]),
    ("Voice for the simulator", [
        ("SIDELINE_POLLY_VOICE", False, "Polly voice", "Amy"),
        ("SIDELINE_STT", False, "auto | transcribe | off", "auto"),
    ]),
]


def main():
    width = max(len(n) for _, g in GROUPS for n, *_ in g)
    for title, rows in GROUPS:
        print("\n" + title)
        for name, secret, what, default in rows:
            v = os.environ.get(name)
            if v:
                shown = "set (%d chars)" % len(v) if secret else "= %s" % v
                mark = "ok"
            else:
                shown = "unset" + ("" if default is None else "  -> default %s" % default)
                mark = "--"
            print("  %s  %-*s  %s" % (mark, width, name, shown))

    env = os.environ
    print("\nWhat starts, given the above")
    print("  bedrock   %s" % ("ON" if autodetect.bedrock_enabled(env) else "off (no AWS keys, or forced off)"))
    prov = autodetect.provider_kind(env)
    print("  data      %s" % ("LIVE API-Football" if prov == "apifootball" else "recorded real match (replay)"))
    st = autodetect.state_kind(env)
    print("  state     %s" % {"auto": "DynamoDB if the table answers, else memory",
                              "dynamo": "DynamoDB (forced)", "memory": "memory"}.get(st, st))
    print("  auth      %s" % env.get("SIDELINE_AUTH", "off"))

    print()
    have_id = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
    have_secret = bool(os.environ.get("AWS_SECRET_ACCESS_KEY"))
    if have_id != have_secret:
        print("PROBLEM: only one of AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY is set.")
        return 1
    if os.environ.get("SIDELINE_BEDROCK", "").lower() == "on" and not have_id:
        print("NOTE: SIDELINE_BEDROCK=on but no AWS keys in the environment; "
              "boto3 will look elsewhere (instance role, a profile) or fall back to templates.")
    if os.environ.get("SIDELINE_PROVIDER") == "apifootball" and not (
            os.environ.get("SIDELINE_FOOTBALL_KEY") or os.environ.get("SIDELINE_FOOTBALL_SECRET")):
        print("PROBLEM: SIDELINE_PROVIDER=apifootball requires SIDELINE_FOOTBALL_KEY in .env.")
    if os.environ.get("SIDELINE_AUTH") == "required":
        for n in ("SIDELINE_AUTH_ISSUER", "SIDELINE_PUBLIC_URL"):
            if not os.environ.get(n):
                print("PROBLEM: SIDELINE_AUTH=required needs %s." % n)
                return 1
    print("next: make aws-check   (checks the AWS pieces)   |   make verify-data   (live feed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
