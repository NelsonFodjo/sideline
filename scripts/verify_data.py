#!/usr/bin/env python3
"""Check the live football feed, and show what a listener would hear from it.

    python3 scripts/verify_data.py                 # key accepted, quota, today's fixtures
    python3 scripts/verify_data.py --tools         # also run the core tools on a real match
    python3 scripts/verify_data.py --tools 1641084 # ...on a specific fixture id

Reads SPORTMONKS_TOKEN. The first form costs two or three requests; --tools
costs roughly ten more (the provider caches for 12 s). It prefers a match that
is live now, then one that has finished. Exits 1 if the key does not work.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env, environment wins)
from sideline import language  # noqa: E402
from sideline.app import Context  # noqa: E402
from sideline.config import CONFIG  # noqa: E402
from sideline.mcp.errors import ToolError  # noqa: E402
from sideline import providers  # noqa: E402
from sideline.providers import ProviderUnavailable  # noqa: E402
from sideline.state import MemoryStore  # noqa: E402
from sideline.tools import REGISTRY  # noqa: E402

LIVE = ("1H", "2H", "HT", "ET", "P", "LIVE", "BT")


def check_key():
    """The token, the leagues the plan covers, and how many calls are left this hour."""
    provider = providers.build(CONFIG.sportmonks_token)
    try:
        doc = provider._get("leagues", include="country")
    except ProviderUnavailable as e:
        print(" FAIL  the feed refused the token: %s" % e)
        return None
    leagues = ["%s (%s)" % (i.get("name"), (i.get("country") or {}).get("name", "?"))
               for i in doc.get("data") or []]
    limit = doc.get("rate_limit") or {}
    print("  ok   token accepted  calls left this hour: %s  leagues: %s" % (
        limit.get("remaining", "?"), ", ".join(leagues) or "none"))
    return provider


def pick(fixtures, wanted):
    if wanted:
        return next((f for f in fixtures if f["fixture_id"] == wanted), {"fixture_id": wanted})
    for group in ([f for f in fixtures if f.get("status") in LIVE],
                  [f for f in fixtures if f.get("status") in ("FT", "finished")]):
        if group:
            return group[0]
    return None


def run_tools(provider, fixture_id):
    ctx = Context(provider, MemoryStore(), language)
    who = "verify-data"
    steps = [("follow_match", {"fixture_id": fixture_id}),
             ("get_match_state", {}), ("get_fixtures", {}), ("get_match_preview", {}), ("get_lineups", {}), ("what_did_i_miss", {}),
             ("get_event_detail", {"kind": "score"}), ("get_officials", {}),
             ("get_player_context", {"player": "he"}), ("get_head_to_head", {}),
             ("sync_broadcast_delay", {"check": True})]
    print("\nwhat a listener hears (fixture %s):\n" % fixture_id)
    for name, args in steps:
        try:
            spoken, _, _ = REGISTRY[name](ctx, args, who)
            print("  %-22s %s" % (name, spoken))
        except ToolError as e:
            why = (e.detail or {}).get("problem")
            print("  %-22s (declined) %s%s" % (name, e.spoken, "  [%s]" % why if why else ""))
        except ProviderUnavailable as e:
            print("  %-22s (feed refused) %s" % (name, e))


def main():
    if not CONFIG.sportmonks_token:
        print(" FAIL  no token: set SPORTMONKS_TOKEN (see .env.example)")
        return 1
    provider = check_key()
    if provider is None:
        return 1
    try:
        fixtures = provider.fixtures_today()
    except ProviderUnavailable as e:
        print(" FAIL  fixtures: %s" % e)
        return 1
    live = [f for f in fixtures if f.get("status") in LIVE]
    print("  ok   %d fixtures today, %d live now" % (len(fixtures), len(live)))
    for f in (live or fixtures)[:8]:
        print("       %-34s %-4s %s" % ("%s v %s" % (f["home"], f["away"]), f["status"],
                                        f["fixture_id"]))
    if "--tools" in sys.argv:
        args = [a for a in sys.argv[1:] if a != "--tools"]
        chosen = pick(fixtures, int(args[0]) if args and args[0].isdigit() else None)
        if not chosen:
            print("\nnothing live or finished to run the tools on; pass a fixture id")
            return 0
        run_tools(provider, chosen["fixture_id"])
    else:
        print("\nnext: python3 scripts/verify_data.py --tools   |   make run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
