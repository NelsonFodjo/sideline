"""What happened in a match: goals, cards, substitutions, VAR. Any match that has been played, or is in play.

No follow is needed and nothing is read from the log of what this listener has been told: the events come from the
feed (kept once read), so a match played last month can be asked about as easily as one in play. It is read out in
parts that are comfortable to hear: the result and the goals first, then the rest by name, because a list of fifteen
substitutions read in one breath is not something a listener can use.
"""

import re

from .. import clock, sports
from ..mcp.errors import ToolError
from ..status import FINISHED, has_started
from . import events_for, feed, resolve_fixture

LISTED = 6
LISTED_GOALS = 12          # a football match is told to its last goal: the winner must never be "and 1 more"
_KINDS = {"goals": "goal", "cards": "card", "substitutions": "substitution", "var": "var", "penalties": "penalty"}
_WORD = {"goal": ("goal", "goals"), "card": ("card", "cards"), "substitution": ("substitution", "substitutions"),
         "var": ("VAR decision", "VAR decisions"), "penalty": ("penalty", "penalties")}


def _count(n, kind):
    one, many = _WORD[kind]
    return "%d %s" % (n, one if n == 1 else many)


def _said(sp, e):
    out = sp.say_event(e)
    return out[:1].upper() + out[1:]


LATEST_COMMENTARY = 5


MOST_NEW_LINES = 3

# What a listener wants read out in the middle of a match. Routine lines (throw-ins, goal kicks, a pass that went astray)
# are the bulk of a feed's running commentary and make a voice sound like a ticker; a client can ask for these only.
_KEY_LINE = re.compile(r"\b(goal(?![\s-]*kick)|scores?|penalty|penalt|yellow card|red card|booked|sent off|dismissed|substitution|replaces|"
                       r"var\b|disallowed|offside goal|hits the (?:post|bar|woodwork|crossbar)|saved|saves|"
                       r"kick.?off|half.?time|full.?time|second half|first half|extra time|shoot.?out|injur)", re.I)


def is_key_line(line):
    return bool(_KEY_LINE.search(line.get("text") or ""))


def _commentary(ctx, fx, sp, since=None, key_only=False):
    """The latest lines of the match's running commentary, up to where the listener's screen has reached.

    With `since` (the `cursor` an earlier call returned) only the lines after it come back, so a client that polls
    can read the match out as it goes without repeating itself; -1 means "from now": nothing, only the cursor. The
    cursor counts lines the listener's picture has reached, so a delayed listener's cursor never runs ahead of it.
    If more than MOST_NEW_LINES arrived, only the newest are given and `skipped` says how many were left out."""
    try:
        lines = ctx.provider.commentary(fx["fixture_id"])
    except (NotImplementedError, AttributeError):
        lines = None
    if not lines:
        raise ToolError("I don't have the commentary for %s against %s." % (fx["home"], fx["away"]),
                        {"reason": "no_commentary", "fixture_id": fx["fixture_id"]})
    reached = fx.get("minute")
    if reached is not None and fx.get("broadcast_offset"):          # a delayed listener: nothing their picture has not shown
        lines = [l for l in lines if l["minute"] <= reached]
    cursor = len(lines)
    if since is not None:
        new = [] if since < 0 else lines[since:]
        if key_only:
            new = [l for l in new if is_key_line(l)]
        skipped = max(0, len(new) - MOST_NEW_LINES)
        new = new[-MOST_NEW_LINES:]
        said = " ".join("On %s, %s" % (("%d plus %d" % (l["minute"], l["stoppage"])) if l["stoppage"] else l["minute"],
                                    l["text"] if l["text"].endswith((".", "!", "?")) else l["text"] + ".") for l in new)
        return (said or "Nothing new in the commentary."), {
            "fixture_id": fx["fixture_id"], "commentary": new, "cursor": cursor, "skipped": skipped,
            "generated_by": "template", "verbatim": True}, None
    latest = lines[-LATEST_COMMENTARY:]
    if not latest:
        raise ToolError("Nothing has been said in the commentary yet.", {"reason": "no_commentary", "fixture_id": fx["fixture_id"]})
    said = " ".join("On %s, %s" % (("%d plus %d" % (l["minute"], l["stoppage"])) if l["stoppage"] else l["minute"],
                                   l["text"] if l["text"].endswith((".", "!", "?")) else l["text"] + ".") for l in latest)
    spoken = "The latest from the commentary in %s against %s. %s" % (fx["home"], fx["away"], said)
    return spoken, {"fixture_id": fx["fixture_id"], "commentary": latest, "cursor": cursor, "generated_by": "template", "verbatim": True}, None


def run(ctx, args, listener_id):
    fx = resolve_fixture(ctx, args, listener_id, prefers="played")
    tz = fx.get("tz_offset_minutes")
    sp = sports.for_fixture(fx)
    started = has_started(fx)
    if not started:
        ko = clock.kickoff(fx)
        raise ToolError("%s against %s has not started yet. %s" % (
            fx["home"], fx["away"], clock.say_kickoff(fx, sp.start_word, tz_minutes=tz)),
            {"reason": "not_started", "fixture_id": fx["fixture_id"], "kickoff": ko.isoformat() if ko else None})
    part = args.get("part") or "all"
    if part == "pitching":
        pitched = feed(ctx, "pitchers", fx["fixture_id"]) if sp.key == "baseball" else {}
        if not pitched:
            raise ToolError("I don't have the pitchers for %s against %s." % (fx["home"], fx["away"]),
                            {"reason": "no_pitching", "fixture_id": fx["fixture_id"]})
        spoken = " ".join("%s used %s." % (team, ", ".join("%s%s" % (n, " for %s innings" % ip if ip else "") for n, ip in rows))
                          for team, rows in pitched.items() if rows)
        return spoken, {"fixture_id": fx["fixture_id"], "pitchers": pitched, "generated_by": "template"}, None
    if part == "commentary":
        since = args.get("since_line")
        return _commentary(ctx, fx, sp, since if isinstance(since, int) and not isinstance(since, bool) else None,
                           key_only=args.get("key_only") is True)
    events = [e for e in events_for(ctx, fx) if e.get("kind") != "period"]

    when = clock.kickoff(fx)
    day = clock.say_day(when, tz_minutes=tz) if when and fx.get("status") in FINISHED else ""
    head = "%s against %s%s: %s" % (fx["home"], fx["away"], (", " + day) if day else "", sp.say_match_state(fx))
    groups = {"goal": [e for e in events if sp.is_score(e)]}
    for kind in ("card", "substitution", "var", "penalty"):
        groups[kind] = [e for e in events if e.get("kind") == kind]
    structured = {"fixture_id": fx["fixture_id"], "home": fx["home"], "away": fx["away"], "score": fx["score"],
                  "status": fx.get("status"), "events": [dict(e) for e in events], "generated_by": "template",
                  "verbatim": True}

    if sp.key == "basketball" and part in ("all", "goals"):
        scorers = {}
        for e in groups["goal"]:
            if e.get("player"):
                scorers[e["player"]] = scorers.get(e["player"], 0) + int(e.get("points") or 1)
        best = sorted(scorers.items(), key=lambda kv: -kv[1])[:3]
        spoken = head + ("." if not head.endswith(".") else "")
        if best:
            spoken += " Leading scorers: %s." % ", ".join("%s with %d" % kv for kv in best)
        return spoken, structured, None

    if part in _KINDS:
        kind = _KINDS[part]
        mine = groups[kind]
        if not mine:
            if not events and sp.key != "football":
                raise ToolError("The feed has no play-by-play for %s against %s, so I can't say who scored. The final is %s %s, %s %s." % (
                    fx["home"], fx["away"], fx["home"], fx["score"]["home"], fx["away"], fx["score"]["away"]),
                    {"reason": "no_plays", "fixture_id": fx["fixture_id"]})
            return "There were no %s in %s against %s." % (_WORD[kind][1], fx["home"], fx["away"]), structured, None
        cap = LISTED_GOALS if (kind == "goal" and sp.key == "football") else LISTED
        shown = mine[:cap]
        spoken = "%s in %s against %s: %s." % (_WORD[kind][1].capitalize(), fx["home"], fx["away"],
                                               ". ".join(_said(sp, e) for e in shown))
        if len(mine) > len(shown):
            spoken += " And %d more." % (len(mine) - len(shown))
        return spoken, structured, None

    # The whole story, kept short: the result, every goal, and what else there is to ask for.
    spoken = head
    goals = groups["goal"]
    # Goals and penalties as one story, in the order they happened (a penalty given, then saved, then the next goal).
    story = sorted(goals + groups["penalty"], key=lambda e: (e["minute"], e.get("stoppage") or 0))
    cap = LISTED_GOALS if sp.key == "football" else LISTED
    if goals:
        spoken += " " + ". ".join(_said(sp, e) for e in story[:cap]) + "."
        if len(story) > cap:
            spoken += " And %d more." % (len(story) - cap)
    else:
        spoken += " There were no goals." if fx["score"]["home"] == fx["score"]["away"] == 0 else ""
        if groups["penalty"]:
            spoken += " " + ". ".join(_said(sp, e) for e in groups["penalty"][:LISTED]) + "."
    more = [_count(len(groups[k]), k) for k in ("card", "substitution", "var") if groups[k]]
    if more:
        spoken += " There were also %s. Ask for any of them." % (", ".join(more[:-1]) + " and " + more[-1]
                                                                 if len(more) > 1 else more[0])
    return spoken, structured, None
