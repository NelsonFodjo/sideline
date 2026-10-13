"""What happened in a match: goals, cards, substitutions, VAR. Any match that has been played, or is in play.

No follow is needed and nothing is read from the log of what this listener has been told: the events come from the
feed (kept once read), so a match played last month can be asked about as easily as one in play. It is read out in
parts that are comfortable to hear: the result and the goals first, then the rest by name, because a list of fifteen
substitutions read in one breath is not something a listener can use.
"""

from .. import clock, sports
from ..mcp.errors import ToolError
from ..status import FINISHED
from . import events_for, resolve_fixture

LISTED = 6
_KINDS = {"goals": "goal", "cards": "card", "substitutions": "substitution", "var": "var"}
_WORD = {"goal": ("goal", "goals"), "card": ("card", "cards"), "substitution": ("substitution", "substitutions"),
         "var": ("VAR decision", "VAR decisions")}


def _count(n, kind):
    one, many = _WORD[kind]
    return "%d %s" % (n, one if n == 1 else many)


def _said(sp, e):
    out = sp.say_event(e)
    return out[:1].upper() + out[1:]


def run(ctx, args, listener_id):
    fx = resolve_fixture(ctx, args, listener_id, prefers="played")
    tz = fx.get("tz_offset_minutes")
    sp = sports.for_fixture(fx)
    started = (fx.get("minute") or 0) > 0 or fx.get("status") in FINISHED
    if not started:
        ko = clock.kickoff(fx)
        raise ToolError("%s against %s has not started yet. %s" % (
            fx["home"], fx["away"], clock.say_kickoff(fx, sp.start_word, tz_minutes=tz)),
            {"reason": "not_started", "fixture_id": fx["fixture_id"], "kickoff": ko.isoformat() if ko else None})
    events = [e for e in events_for(ctx, fx) if e.get("kind") != "period"]
    part = args.get("part") or "all"

    when = clock.kickoff(fx)
    day = clock.say_day(when, tz_minutes=tz) if when and fx.get("status") in FINISHED else ""
    head = "%s against %s%s: %s" % (fx["home"], fx["away"], (", " + day) if day else "", sp.say_match_state(fx))
    groups = {"goal": [e for e in events if sp.is_score(e)]}
    for kind in ("card", "substitution", "var"):
        groups[kind] = [e for e in events if e.get("kind") == kind]
    structured = {"fixture_id": fx["fixture_id"], "home": fx["home"], "away": fx["away"], "score": fx["score"],
                  "status": fx.get("status"), "events": [dict(e) for e in events], "generated_by": "template",
                  "verbatim": True}

    if part in _KINDS:
        kind = _KINDS[part]
        mine = groups[kind]
        if not mine:
            return "There were no %s in %s against %s." % (_WORD[kind][1], fx["home"], fx["away"]), structured, None
        shown = mine[:LISTED]
        spoken = "%s in %s against %s: %s." % (_WORD[kind][1].capitalize(), fx["home"], fx["away"],
                                               ". ".join(_said(sp, e) for e in shown))
        if len(mine) > len(shown):
            spoken += " And %d more." % (len(mine) - len(shown))
        return spoken, structured, None

    # The whole story, kept short: the result, every goal, and what else there is to ask for.
    spoken = head
    goals = groups["goal"]
    if goals:
        spoken += " " + ". ".join(_said(sp, e) for e in goals[:LISTED]) + "."
        if len(goals) > LISTED:
            spoken += " And %d more." % (len(goals) - LISTED)
    else:
        spoken += " There were no goals." if fx["score"]["home"] == fx["score"]["away"] == 0 else ""
    more = [_count(len(groups[k]), k) for k in ("card", "substitution", "var") if groups[k]]
    if more:
        spoken += " There were also %s. Ask for any of them." % (", ".join(more[:-1]) + " and " + more[-1]
                                                                 if len(more) > 1 else more[0])
    return spoken, structured, None
