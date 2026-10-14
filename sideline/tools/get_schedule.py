"""When a team plays next, or how its last matches finished.

A team question, not a match question: the team is found by name and its matches are read as far ahead and back as
the feed allows (about six weeks ahead and three months back on the free plan), whatever is being followed. Said with the
time in the listener's own clock, so a listener is never told a team "doesn't play" when the truth is that it plays
next Saturday. A feed that cannot look further falls back to yesterday, today and tomorrow, and says so.
"""

from .. import clock
from ..mcp.errors import ToolError
from . import _is_team, feed, find_matches, no_team, not_found, possessive

NEXT, LAST = 3, 5


def _score(f):
    return "%s %s, %s %s" % (f["home"], f["score"]["home"], f["away"], f["score"]["away"])


def _outcome(f, team_id, team_name=None):
    """W, D or L for the team, or None when the side cannot be told."""
    mine, theirs = (f["score"]["home"], f["score"]["away"]) if (team_id and f.get("home_id") == team_id) or (team_name and _is_team(f.get("home"), team_name)) \
        else (f["score"]["away"], f["score"]["home"])
    return "W" if mine > theirs else "L" if mine < theirs else "D"


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    opponent = (args.get("opponent") or "").strip() or None
    which = args.get("which") or "next"
    tz = clock.zone_from(ctx.store.listener(listener_id))
    phrase = clock.zone_phrase(tz)
    shown_name = team.capitalize() if team.islower() else team

    if "team_matches" not in getattr(ctx.provider, "capabilities", ()):
        return _near(ctx, team, opponent, tz, phrase, shown_name)

    try:
        data = feed(ctx, "team_matches", team)
    except ToolError as e:
        if (e.detail or {}).get("reason") != "not_supported":
            raise
        return _near(ctx, team, opponent, tz, phrase, shown_name)            # a feed that cannot look further
    if not data:
        raise no_team(ctx, team)
    name = data["team"]

    if which == "last":
        done = [f for f in data["recent"] if not opponent or _is_team(f["home"], opponent) or _is_team(f["away"], opponent)]
        if not done:
            raise ToolError("I can't see any recent results for %s%s." % (name, " against %s" % opponent if opponent else ""),
                            {"reason": "no_match", "team": name})
        items = ["%s, %s" % (_score(f), clock.say_day(clock.kickoff(f), tz_minutes=tz)) for f in done[:LAST]]
        form = "".join(_outcome(f, data.get("team_id"), data.get("team")) for f in done[:LAST])
        spoken = "%s last %s: %s." % (possessive(name), "result" if len(items) == 1 else "%d results" % len(items), ". ".join(items))
        return spoken, {"team": name, "which": "last", "form": form, "matches": [
            {"home": f["home"], "away": f["away"], "score": f["score"], "kickoff": f.get("kickoff")}
            for f in done[:LAST]], "generated_by": "template"}, None

    ahead = [f for f in data["upcoming"] if not opponent or _is_team(f["home"], opponent) or _is_team(f["away"], opponent)]
    if not ahead:
        raise ToolError("I can't see %s%s coming up in the next six weeks." % (
            name, " against %s" % opponent if opponent else ""), {"reason": "no_match", "team": name})
    items = [clock.say_fixture(f, tz, with_zone=False) for f in ahead[:NEXT]]
    spoken = "%s next%s: %s." % (name, ", in %s" % phrase if phrase else "", ". ".join(items))
    return spoken, {"team": name, "which": "next", "matches": [
        {"home": f["home"], "away": f["away"], "kickoff": f.get("kickoff"), "status": f.get("status")}
        for f in ahead[:NEXT]], "generated_by": "template"}, None


def _near(ctx, team, opponent, tz, phrase, shown_name):
    """The fallback for a feed that cannot look further: yesterday, today and tomorrow."""
    found = []
    for offset in (-1, 0, 1):
        found.extend(find_matches(ctx, team, opponent, offsets=(offset,), tz=tz))
    if not found:
        raise not_found(ctx, team, opponent, tz)
    found.sort(key=lambda f: f.get("kickoff") or "")
    items = [clock.say_fixture(f, tz, with_zone=False) for f in found[:4]]
    spoken = "%s%s: %s." % (shown_name, ", in %s" % phrase if phrase else "", ". ".join(items))
    return spoken, {"team": team, "matches": [{"home": f["home"], "away": f["away"], "kickoff": f.get("kickoff"),
                                               "status": f.get("status")} for f in found[:4]],
                    "generated_by": "template"}, None
