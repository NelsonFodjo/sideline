"""What is on: the matches for a day, each with its time.

"Which teams are playing today?", "what's live?", "any Premier League tonight?".
A listener who knows no team name yet has no way to ask the other tools, so this is how a
match gets found. Every match is read out with its kick-off time in the listener's own clock
(or the minute, if it is under way), because for a list the time is the point.

It reads the day's list the server already keeps (one cached request), so it costs the
free plan nothing extra. It does not follow anything and does not advance last_told_at.
"""

from .. import clock
from ..mcp.errors import ToolError
from ..status import FINISHED
from . import day_fixtures

LISTED = 5
OFFSETS = {"yesterday": -1, "today": 0, "tomorrow": 1}


def _rank(fx):
    live = (fx.get("minute") or 0) > 0 and fx.get("status") not in FINISHED
    return (0 if live else 1, fx.get("kickoff") or "")


def _matches(fx, competition):
    if not competition:
        return True
    want = " ".join(competition.lower().split())
    hay = " ".join(("%s %s" % (fx.get("competition") or "", fx.get("country") or "")).lower().split())
    return want in hay


def run(ctx, args, listener_id):
    when = (args.get("when") or "today").lower()
    if when not in OFFSETS:
        when = "today"
    competition = (args.get("competition") or "").strip()
    live_only = bool(args.get("live_only"))
    tz = clock.zone_from(ctx.store.listener(listener_id))

    fixtures = [f for f in day_fixtures(ctx, OFFSETS[when], tz)
                if f.get("home") and f.get("away") and _matches(f, competition)
                and (not live_only or ((f.get("minute") or 0) > 0 and f.get("status") not in FINISHED))]
    fixtures.sort(key=_rank)

    # "in the Premier League", "in the Champions League", but "in La Liga" and "in Spain"
    where = (" in %s%s" % ("the " if competition.lower().endswith(("league", "cup", "championship")) else "", competition)
             if competition else "")
    if not fixtures:
        what = "live matches" if live_only else "matches"
        raise ToolError("I can't see any %s%s %s." % (what, where, when),
                        {"reason": "no_match", "when": when, "competition": competition})

    shown = fixtures[:LISTED]
    # the intro names the day, so each match carries only its time
    items = [clock.say_fixture(f, tz, with_day=False, with_zone=False) for f in shown]
    if live_only:
        intro = "Live now%s:" % where
    else:
        phrase = clock.zone_phrase(tz)          # said once here, not after every time
        intro = "%s%s%s:" % (when.capitalize(), where, ", in %s" % phrase if phrase else "")
    spoken = "%s %s." % (intro, ". ".join(items))
    rest = len(fixtures) - len(shown)
    if rest > 0:
        spoken += " And %d more. Ask for a team or a competition to narrow it down." % rest
    structured = {"when": when, "competition": competition or None, "live_only": live_only,
                  "total": len(fixtures),
                  "matches": [{"home": f["home"], "away": f["away"], "competition": f.get("competition"),
                               "kickoff": f.get("kickoff"), "minute": f.get("minute") or 0,
                               "status": f.get("status")} for f in shown],
                  "generated_by": "template"}
    return spoken, structured, None
