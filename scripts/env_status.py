#!/usr/bin/env python3
"""Show which Sideline environment variables are set. Never prints a secret.

    python3 scripts/env_status.py        # or: make env

Secrets show only "set" and a length, so the output is safe to paste into a chat
or a bug report. It reports the environment as the server will see it, including
anything .env supplied (the environment wins), then what each "auto" setting
resolves to. The variable list is sideline/config.py VARIABLES.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env; environment wins)
from sideline import config  # noqa: E402


def main():
    width = max(len(n) for n, *_ in config.VARIABLES)
    for name, secret, default, what in config.VARIABLES:
        v = os.environ.get(name)
        if v:
            shown = "set (%d chars)" % len(v) if secret else "= %s" % v
            mark = "ok"
        else:
            shown = "unset" + ("  -> default %s" % default if default else "")
            mark = "--"
        print("  %s  %-*s  %s" % (mark, width, name, shown))

    print("\nWhat starts, given the above")
    print("  feed      ESPN (multi-sport live feed, zero-auth)")
    print("  bedrock   %s" % ("on" if config.bedrock_enabled() else "off (no AWS credentials, or forced off)"))
    print("  state     %s" % {"auto": "DynamoDB if the table answers, else memory",
                              "dynamo": "DynamoDB (forced)", "memory": "memory"}.get(
                                  config.state_kind(), config.state_kind()))
    print("\nnext: make verify-data (the feed) | make aws-check (the AWS pieces)")
    have_id = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
    have_secret = bool(os.environ.get("AWS_SECRET_ACCESS_KEY"))
    if have_id != have_secret:
        print("\nPROBLEM: only one of AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY is set.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
