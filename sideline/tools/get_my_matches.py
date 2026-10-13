"""Which of the listener's teams are playing, with times in their own clock."""

from .. import clock
from ..mcp.errors import ToolError
from . import _is_team, day_fixtures

OFFSETS = {"yesterday": -1, "today": 0, "tomorrow": 1}


def run(ctx, args, listener_id):
    rec = ctx.store.listener(listener_id)
    mine = list(rec.get("favourites") or [])
    if not mine:
        raise ToolError("You haven't told me your teams yet. Tell me which teams you support.",
                        {"reason": "no_favourites"})
    when = args.get("when") if args.get("when") in OFFSETS else "today"
    tz = clock.zone_from(rec)
    found, seen = [], set()
    for fx in day_fixtures(ctx, OFFSETS[when], tz):
        if any(_is_team(fx.get("home"), t) or _is_team(fx.get("away"), t) for t in mine) \
                and fx["fixture_id"] not in seen:
            seen.add(fx["fixture_id"])
            found.append(fx)
    if not found:
        raise ToolError("None of your teams are playing %s." % when,
                        {"reason": "no_match", "when": when, "favourites": mine})
    found.sort(key=lambda f: f.get("kickoff") or "")
    phrase = clock.zone_phrase(tz)
    items = [clock.say_fixture(f, tz, with_day=False, with_zone=False) for f in found[:5]]
    spoken = "%s%s: %s." % (when.capitalize(), ", in %s" % phrase if phrase else "", ". ".join(items))
    return spoken, {"when": when, "favourites": mine,
                    "matches": [{"home": f["home"], "away": f["away"], "kickoff": f.get("kickoff")}
                                for f in found[:5]], "generated_by": "template"}, None
