#!/usr/bin/env python3
"""Check the live football feed before you rely on it.

    python3 scripts/verify_provider.py

Reads SIDELINE_FOOTBALL_KEY (or SIDELINE_FOOTBALL_SECRET) from the
environment, calls API-Football's /status (account and daily
quota) and lists today's fixtures. Costs two or three requests.
Exits 1 if the key does not work.
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env, environment wins)
from sideline import secretsmanager  # noqa: E402
from sideline.config import CONFIG  # noqa: E402
from sideline.providers.apifootball import (BASE, ApiFootballProvider,  # noqa: E402
                                            ProviderUnavailable)


def main():
    key = CONFIG.football_key or secretsmanager.football_key(
        CONFIG.football_secret, CONFIG.region)
    if not key:
        print(" FAIL  no key: set SIDELINE_FOOTBALL_KEY (docs/ENVIRONMENT.md).")
        return 1
    req = urllib.request.Request(BASE + "/status", headers={"x-apisports-key": key})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            doc = json.loads(r.read().decode("utf-8"))
    except Exception as e:                                     # noqa: BLE001
        print(" FAIL  could not reach %s: %s" % (BASE, e))
        return 1
    problem = ApiFootballProvider._problem(doc)
    if problem:
        print(" FAIL  the feed refused the key: %s" % problem)
        return 1
    r = doc.get("response") or {}
    reqs = r.get("requests") or {}
    print("  ok   key accepted  plan=%s  requests today %s of %s" % (
        (r.get("subscription") or {}).get("plan", "?"),
        reqs.get("current", "?"), reqs.get("limit_day", "?")))
    try:
        fx = ApiFootballProvider(key).fixtures_today()
    except ProviderUnavailable as e:
        print(" FAIL  fixtures: %s" % e)
        return 1
    print("  ok   %d fixtures today (live or scheduled)" % len(fx))
    for f in fx[:8]:
        print("       %-28s %s  %s" % ("%s v %s" % (f["home"], f["away"]),
                                      f["status"], f["fixture_id"]))
    print("\nnow:  SIDELINE_PROVIDER=apifootball python3 -m sideline")
    print("note: a 100-calls/day free plan will not last a match at a 15 s poll;")
    print("      set SIDELINE_POLL_SECONDS=60 or use a paid plan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
