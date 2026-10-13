#!/usr/bin/env python3
"""When are the next matches in the leagues this token covers? For planning a demo.

    python3 scripts/next_matches.py          # the next 10 days
    python3 scripts/next_matches.py 21       # the next 21 days

The free plan covers only a few leagues, so a match to follow has to be in one of them. This asks the
feed for each day (one call a day, well inside the hourly limit) and lists kick-offs in your own time zone.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env, environment wins)
from sideline import providers  # noqa: E402
from sideline.config import CONFIG  # noqa: E402
from sideline.providers import ProviderUnavailable  # noqa: E402


def main():
    if not CONFIG.sportmonks_token:
        print(" FAIL  no token: set SPORTMONKS_TOKEN (see .env.example)")
        return 1
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
    provider = providers.build(CONFIG.sportmonks_token)
    try:
        leagues = provider.competitions()
    except ProviderUnavailable as e:
        print(" FAIL  the feed refused the token: %s" % e)
        return 1
    print("covered: %s\n" % ", ".join("%s (%s)" % (c["name"], c["country"]) for c in leagues))
    found = 0
    for offset in range(0, days + 1):
        try:
            fixtures = provider.fixtures_on(offset)
        except ProviderUnavailable as e:
            print(" stopped at day +%d: %s" % (offset, e))
            break
        for fx in sorted(fixtures, key=lambda f: f.get("kickoff") or ""):
            ko = datetime.datetime.fromisoformat(fx["kickoff"]).astimezone()
            print("  %s  %-34s %-10s %s" % (ko.strftime("%a %d %b %H:%M"), "%s v %s" % (fx["home"], fx["away"]),
                                          fx.get("status") or "", fx.get("competition") or ""))
            found += 1
    print("\n%d matches in the next %d days (times in this machine's zone)" % (found, days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
