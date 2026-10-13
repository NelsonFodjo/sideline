"""The match, described: where, when, the weather and the formations.

What a friend would say before the game: the ground and the city, the time in the
listener's own clock, the weather there, and how each side lines up. Every part is a
real fact from the feed or the weather service, and a part that is not available is
left out and listed in `missing`, never filled in.

Does not advance last_told_at: a preview is not news of what happened.
"""

import logging
import re

from .. import clock, sports, weather
from ..providers.base import ProviderUnavailable
from ..status import FINISHED

LOG = logging.getLogger("sideline.preview")


def _title(text):
    return text[:1].upper() + text[1:] if text else text


def _round(text):
    """"Regular Season - 8" is said "round 8"; "Group Stage" is said "group stage"."""
    m = re.match(r"^.*?\s*-\s*(\d+)$", text or "")
    return "round %s" % m.group(1) if m else (text or "").strip().lower()


def _who(fx):
    competition, rnd = fx.get("competition"), _round(fx.get("round"))
    where = ""
    if competition:
        where = " in the %s" % competition
        if rnd and rnd not in competition.lower():
            where += ", %s" % rnd
    return "%s host %s%s." % (fx["home"], fx["away"], where)


def _place(fx):
    venue, city = fx.get("venue"), fx.get("city")
    if venue and city:
        return "It's at %s, in %s." % (venue, city)
    if venue or city:
        return "It's at %s." % (venue or city)
    return ""


def _formations(lineups, fx):
    sides = [(team, (v or {}).get("formation")) for team, v in (lineups or {}).items()]
    sides = [(t, f) for t, f in sides if t and f]
    if not sides:
        return ""
    if len(sides) == 1:
        return "%s line up in a %s." % sides[0]
    return "%s line up in a %s, and %s in a %s." % (sides[0] + sides[1])


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)
    tz = fx.get("tz_offset_minutes")
    sp = sports.for_fixture(fx)
    status = fx.get("status")
    started = (fx.get("minute") or 0) > 0 or status in FINISHED
    missing = []

    parts = [_who(fx), _place(fx)]
    if status in FINISHED:
        parts.append("It has finished. %s." % sp.say_score(fx))
    elif started:
        parts.append(sp.say_match_state(fx))
    else:
        parts.append(clock.say_kickoff(fx, sp.start_word, tz_minutes=tz))

    # The weather, only while it still matters: from a few hours before the start,
    # to the end of the match, and never for a ground we cannot place.
    wx = None
    ko = clock.kickoff(fx)
    if ko and status not in FINISHED:
        ahead = (ko - clock.now()).total_seconds()
        if -3 * 3600 <= ahead <= 7 * 86400:
            wx = weather.at_ground(fx.get("city"), fx.get("country"), ko)
            if wx:
                parts.append("The forecast for %s is %s." % (
                    "the start" if not started else "the match", weather.say(wx)))
            else:
                missing.append("weather")

    lineups = None
    try:
        lineups = ctx.provider.lineups(fx["fixture_id"])
    except ProviderUnavailable as e:
        LOG.warning("preview: lineups unavailable: %s", e)
    forms = _formations(lineups, fx)
    if forms:
        parts.append(forms)
    elif not started:
        parts.append("The line-ups are not out yet.")
        missing.append("formations")

    spoken = " ".join(p.strip() for p in parts if p and p.strip())
    structured = {"home": fx["home"], "away": fx["away"],
                  "venue": fx.get("venue"), "city": fx.get("city"),
                  "competition": fx.get("competition"), "round": fx.get("round"),
                  "clock": clock.snapshot(fx), "weather": wx,
                  "formations": {t: (v or {}).get("formation") for t, v in (lineups or {}).items()},
                  "missing": missing, "generated_by": "template"}
    return spoken, structured, None
