"""What is on: the matches for a day, each with its time.

"Which teams are playing today?", "what's live?", "any Premier League tonight?".
A listener who knows no team name yet has no way to ask the other tools, so this is how a
match gets found. Every match is read out with its kick-off time in the listener's own clock
(or the minute, if it is under way), because for a list the time is the point.

It reads the day's list the server already keeps (one cached request), so it costs the
free plan nothing extra. It does not follow anything and does not advance last_told_at.
"""

import datetime

from .. import clock
from ..finder import _date
from ..mcp.errors import ToolError
from ..status import FINISHED
from . import day_fixtures

LISTED = 5
LOOK_AHEAD_DAYS = 10     # an empty day looks this far for the next one with matches (cached requests, free plan)
OFFSETS = {"yesterday": -1, "today": 0, "tomorrow": 1}


def _rank(fx):
    live = (fx.get("minute") or 0) > 0 and fx.get("status") not in FINISHED
    return (0 if live else 1, fx.get("kickoff") or "")


def _matches(fx, competition):
    if not competition:
        return True
    want = " ".join(competition.lower().split())
    hay = " ".join(("%s %s" % (fx.get("competition") or "", fx.get("country") or "")).lower().split())
    if want in hay:
        return True
    # "the Scottish Premiership" for a competition the feed calls "Premiership": the whole of the feed's name is in
    # what was said (a play-off is not matched by its parent's name, nor a Premier League by a Premiership)
    name = (fx.get("competition") or "").lower().replace("-", " ").split()
    return bool(name) and set(name) <= set(want.replace("-", " ").split())


def run(ctx, args, listener_id):
    when = (args.get("when") or "today").lower()
    if when not in OFFSETS:
        when = "today"
    day = _date(args.get("date"))
    competition = (args.get("competition") or "").strip()
    live_only = bool(args.get("live_only"))
    tz = clock.zone_from(ctx.store.listener(listener_id))

    def on_day(offset):
        found = [f for f in day_fixtures(ctx, offset, tz)
                 if f.get("home") and f.get("away") and _matches(f, competition)
                 and (not live_only or ((f.get("minute") or 0) > 0 and f.get("status") not in FINISHED))]
        found.sort(key=_rank)
        return found

    offset = OFFSETS[when]
    if day:
        # "on Saturday", "on the 20th": the model works the date out from today's date, which it is told
        now_local = (clock.now() + datetime.timedelta(minutes=int(tz or 0))).date()
        offset = (day - now_local).days
        noon = datetime.datetime(day.year, day.month, day.day, 12, tzinfo=clock.UTC) - datetime.timedelta(minutes=int(tz or 0))
        when = clock.say_day(noon, tz_minutes=tz)
    fixtures = on_day(offset)
    skipped = None
    if not fixtures and not live_only and offset >= 0:
        # "the next matches" on a quiet day: say so, then name the next day that has some
        for ahead in range(offset + 1, offset + 1 + LOOK_AHEAD_DAYS):
            fixtures = on_day(ahead)
            if fixtures:
                skipped, offset = when, ahead
                ko = clock.kickoff(fixtures[0])
                when = clock.say_day(ko, tz_minutes=tz) if ko else "later"
                break

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
        zone = ", in %s" % phrase if phrase else ""
        if skipped:
            intro = "Nothing %s%s. The next matches are %s%s%s:" % (skipped, where, when, where, zone)
        else:
            intro = "%s%s%s:" % (when[:1].upper() + when[1:], where, zone)
    spoken = "%s %s." % (intro, ". ".join(items))
    rest = len(fixtures) - len(shown)
    if rest > 0:
        spoken += " And %d more. Ask for a team or a competition to narrow it down." % rest
    structured = {"when": when, "competition": competition or None, "live_only": live_only,
                  "total": len(fixtures),
                  "skipped": skipped, "matches": [{"home": f["home"], "away": f["away"], "competition": f.get("competition"),
                               "kickoff": f.get("kickoff"), "minute": f.get("minute") or 0,
                               "status": f.get("status")} for f in shown],
                  "generated_by": "template"}
    return spoken, structured, None
