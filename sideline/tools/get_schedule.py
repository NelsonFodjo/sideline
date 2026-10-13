"""When a team plays: its matches from yesterday to tomorrow, each with its time.

All a free feed can see is that window, and the answer says so when it finds nothing, so a
listener is never told a team "doesn't play" when the truth is that Sideline cannot see that far.
"""

from .. import clock
from . import find_matches, not_found


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    opponent = (args.get("opponent") or "").strip() or None
    tz = clock.zone_from(ctx.store.listener(listener_id))
    found = []
    for offset in (-1, 0, 1):
        for fx in find_matches(ctx, team, opponent, offsets=(offset,), tz=tz):
            found.append(fx)
    if not found:
        raise not_found(ctx, team, opponent, tz)
    found.sort(key=lambda f: f.get("kickoff") or "")
    phrase = clock.zone_phrase(tz)
    items = [clock.say_fixture(f, tz, with_zone=False) for f in found[:4]]
    spoken = "%s%s: %s." % (team.capitalize() if team.islower() else team,
                            ", in %s" % phrase if phrase else "", ". ".join(items))
    structured = {"team": team, "matches": [{"home": f["home"], "away": f["away"],
                                             "kickoff": f.get("kickoff"), "status": f.get("status")}
                                            for f in found[:4]], "generated_by": "template"}
    return spoken, structured, None
