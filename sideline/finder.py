"""Working out which match a listener means.

A listener does not say a fixture id. They say "the Celtic game", "the Rangers one", "their last match", "what happened on
the 11th", or nothing at all ("who scored?") and expect Sideline to know. This module is that judgement, in four steps:

  1. REFERENCE. What was actually given: a fixture id, a team, an opponent, a time (last, next, yesterday, today,
     tomorrow, or a date), and what the question is about (a match that was played, or one still to come).
  2. CANDIDATES. Every match that could be meant, from the cheapest source that can answer: the team's matches over the
     last three months and next six weeks (one cached request), else yesterday, today and tomorrow, else what is on today.
  3. SCORE. Each candidate gets a number between 0 and 1 from what was said: the other side must fit the opponent named
     (an almost-match counts by spelling and sound, a clear miss rules the match out); the time asked for ("last" ranks
     the played matches latest first and a second-latest is worth half; a day or a date is a hit or a miss); with no time
     said, a match in play is worth most and the rest fade with distance from now; a match that suits the question (a
     played match for "who scored", an upcoming one for "who's playing") is worth twice one that does not; the match being
     followed gets a lift.
  4. DECIDE. A clear winner is used. Two or more plausible matches are not guessed between: they become a FORK, a numbered
     list with the scores and dates that the listener picks from ("the second one", "the Rangers game"), remembered so
     that the pick answers the question that was asked. Nothing plausible is an honest "I can't find it", with what the
     feed does have for that team.

It reads the feed through the provider's own methods, so it works on any feed that can list a team's matches and degrades to
the days around today on one that cannot.
"""

import datetime
import math

from . import clock, resolve
from .mcp.errors import ToolError
from .status import CALLED_OFF, FINISHED

WHENS = ("last", "next", "yesterday", "today", "tomorrow")
FORK_MAX = 4                  # options read out; more than this is too many to hold in the head by ear
PLAUSIBLE = 0.5               # a runner-up this close to the best is a real alternative
CLEAR_WIN = 0.6               # ...and the best wins outright when the runner-up is below this share of it
FOLLOWED_LIFT = 1.25
DECAY_DAYS = 7.0              # with no time said, a match fades with its distance from now...
FLOOR = 0.1                   # ...but never to nothing: a match weeks ago is still the answer when it is the one that fits
MISMATCH = 0.35               # a match of the wrong kind for the question (played versus upcoming)


class Reference(object):
    """What the listener gave, as the tool received it."""

    def __init__(self, args, prefers=None):
        a = args or {}
        self.fixture_id = a.get("fixture_id")
        self.team = (a.get("team") or "").strip()
        self.opponent = (a.get("opponent") or "").strip()
        self.when = a.get("when") if a.get("when") in WHENS else None
        self.date = _near_year(_date(a.get("date")))
        self.prefers = prefers                    # "played", "coming" or None

    @property
    def open_ended(self):
        """Nothing here names a match: the listener expects Sideline to know."""
        return not (self.fixture_id or self.team or self.opponent or self.when or self.date)

    def about(self):
        bits = [b for b in (self.team, "against " + self.opponent if self.opponent else "") if b]
        return " ".join(bits) or "that match"


def _near_year(day):
    """A model that does not know the year writes last year's. A day more than half a year from today is moved to the
    same day in the year that puts it nearest to now: the listener said "the 20th of September", not a year."""
    if not day:
        return day
    today = clock.now().date()
    best = day
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidate = day.replace(year=year)
        except ValueError:                                         # 29 February
            continue
        if abs((candidate - today).days) < abs((best - today).days):
            best = candidate
    return best if abs((day - today).days) > 180 else day


def _date(raw):
    try:
        return datetime.date.fromisoformat(str(raw)[:10]) if raw else None
    except ValueError:
        return None


def kind(fx):
    """played, live, coming or off."""
    status = fx.get("status")
    if status in FINISHED:
        return "played"
    if status in CALLED_OFF:
        return "off"
    if (fx.get("minute") or 0) > 0:
        return "live"
    return "coming"


def _local_day(fx, tz):
    ko = clock.kickoff(fx)
    return (ko + datetime.timedelta(minutes=int(tz or 0))).date() if ko else None


# ------------------------------------------------------------------ candidates
def candidates(ctx, ref, rec, tz):
    """Every match that could be meant."""
    from .tools import day_fixtures, find_matches
    found = {}

    def add(fx):
        if fx and fx.get("fixture_id") is not None and fx.get("home") and fx.get("away"):
            found.setdefault(fx["fixture_id"], fx)

    if ref.team:
        data = None
        try:
            data = ctx.provider.team_matches(ref.team)
        except NotImplementedError:
            pass
        if data:
            for fx in data["recent"] + data["upcoming"]:
                add(fx)
        else:                                                     # a feed that cannot look further
            for offset in (-1, 0, 1):
                for fx in find_matches(ctx, ref.team, None, offsets=(offset,), tz=tz):
                    add(fx)
    else:
        following = rec.get("following")
        if following:
            add(ctx.provider.fixture(following))
        for offset in (0, -1) if ref.when in ("last", "yesterday") else (0,):
            for fx in day_fixtures(ctx, offset, tz):
                add(fx)
    return list(found.values())


# ----------------------------------------------------------------------- score
def _other_side_fit(fx, name):
    """How well a named side fits either team of the fixture, 0 to 1."""
    from .tools import NICKNAMES, _words
    want = _words(NICKNAMES.get(" ".join(_words(name)), name))
    best = 0.0
    for side in (fx.get("home"), fx.get("away")):
        have = _words(side)
        if want and have:
            best = max(best, 1.0 if " ".join(want) in " ".join(have) else resolve.similarity(want, have))
    return best


def score_all(cands, ref, followed, tz, now=None):
    """[(score, fixture)], best first. Scores are between 0 and 1.25 and mean 'how likely this is the one'."""
    now = now or clock.now()
    today = (now + datetime.timedelta(minutes=int(tz or 0))).date()

    # First, what cannot be meant: a match called off, the wrong opponent, the wrong day. Ranking ("last" means the
    # latest of the matches that fit) is done only among what is left, or a match against another side would crowd it.
    pool = []
    for fx in cands:
        k = kind(fx)
        if k == "off":
            continue
        fit = 1.0
        if ref.opponent:
            fit = _other_side_fit(fx, ref.opponent)
            if fit < 0.6:
                continue
        if ref.date or ref.when in ("yesterday", "today", "tomorrow"):
            want = ref.date or today + datetime.timedelta(days={"yesterday": -1, "today": 0, "tomorrow": 1}[ref.when])
            if _local_day(fx, tz) != want:
                continue
        elif ref.when == "last" and k == "coming":
            continue
        elif ref.when == "next" and k != "coming":
            continue
        pool.append((fx, k, fit))

    played = sorted((f for f, k, _ in pool if k == "played"), key=lambda f: f.get("kickoff") or "", reverse=True)
    coming = sorted((f for f, k, _ in pool if k == "coming"), key=lambda f: f.get("kickoff") or "")
    recency = {f["fixture_id"]: i for i, f in enumerate(played)}
    ahead = {f["fixture_id"]: i for i, f in enumerate(coming)}
    any_live = any(k == "live" for _, k, _ in pool)

    scored = []
    for fx, k, fit in pool:
        s = 0.5 + 0.5 * fit if ref.opponent else 1.0
        if ref.date or ref.when in ("yesterday", "today", "tomorrow"):
            pass                                                   # a hit is a hit
        elif ref.when == "last":
            s *= 1.0 if k == "live" else 1.0 / (1.0 + recency[fx["fixture_id"]] * (1.2 if any_live else 1.0))
        elif ref.when == "next":
            s *= 1.0 / (1.0 + ahead[fx["fixture_id"]])
        else:                                                      # no time said: in play first, then nearest to now
            ko = clock.kickoff(fx)
            days = abs((ko - now).total_seconds()) / 86400.0 if ko else 0.0
            s *= 1.0 if k == "live" else max(FLOOR, math.exp(-days / DECAY_DAYS))
        if ref.prefers and k != "live" and k != ref.prefers:
            s *= MISMATCH
        if followed is not None and fx["fixture_id"] == followed:
            s *= FOLLOWED_LIFT
        scored.append((s, fx))
    scored.sort(key=lambda p: -p[0])
    return scored


# ---------------------------------------------------------------------- decide
def say_option(fx, tz):
    """One option as it is read out in a fork: the score and day for a played match, the time for one still to come."""
    k = kind(fx)
    if k == "played":
        ko = clock.kickoff(fx)
        day = clock.say_day(ko, tz_minutes=tz) if ko else ""
        return "%s %s, %s %s%s" % (fx["home"], fx["score"]["home"], fx["away"], fx["score"]["away"],
                                   ", " + day if day else "")
    return clock.say_fixture(fx, tz)


def decide(scored):
    """('one', fixture) for a clear winner, ('fork', [fixtures]) for several plausible, ('none', None)."""
    if not scored or scored[0][0] <= 0.02:
        return "none", None
    top = scored[0][0]
    plausible = [f for s, f in scored if s >= PLAUSIBLE * top]
    if len(plausible) == 1 or scored[1][0] < CLEAR_WIN * top:
        return "one", scored[0][1]
    return "fork", plausible[:FORK_MAX]


def resolve_match(ctx, ref, rec, tz, question_hint=None):
    """The one fixture the listener means, or a ToolError that forks, or says what was not found."""
    cands = candidates(ctx, ref, rec, tz)
    scored = score_all(cands, ref, rec.get("following"), tz)
    outcome, picked = decide(scored)
    if outcome == "one":
        fx = dict(picked)
        fx["found_by"] = "followed" if fx["fixture_id"] == rec.get("following") else (
            "asked" if (ref.when or ref.date or ref.opponent) else "nearest")
        fx["alternatives"] = len(scored) - 1
        return fx
    if outcome == "fork":
        options = ", or ".join("%d, %s" % (i + 1, say_option(f, tz)) for i, f in enumerate(picked))
        lead = "I can see more than one %s match. Which one: " % ref.team if ref.team else "Which match do you mean: "
        raise ToolError("%s%s?" % (lead, options),
                        {"reason": "ambiguous", "candidates": picked, "fork": True})
    raise _nothing(ctx, ref, cands, tz)


def _nothing(ctx, ref, cands, tz):
    """Nothing fits: say so, and say what the feed does have, so the listener can steer."""
    from .tools import not_found
    if ref.team and not cands and "team_matches" in getattr(ctx.provider, "capabilities", ()):
        try:
            if ctx.provider.team_matches(ref.team) is None:
                return ToolError("I can't find a team called %s. Which team do you mean?" % ref.team,
                                 {"reason": "no_match", "team": ref.team})
        except NotImplementedError:
            pass
    if ref.team and (not cands or not (ref.when or ref.date)):
        return not_found(ctx, ref.team, ref.opponent or None, tz)
    when = {"last": "a played match", "next": "an upcoming match", "yesterday": "a match yesterday",
            "today": "a match today", "tomorrow": "a match tomorrow"}.get(ref.when, "that match")
    if ref.date:
        when = "a match on %d %s" % (ref.date.day, ref.date.strftime("%B"))
    now = clock.now()
    near = sorted((f for f in cands if clock.kickoff(f)), key=lambda f: abs((clock.kickoff(f) - now).total_seconds()))[:3]
    tail = (" I do see: %s." % ", or ".join(say_option(f, tz) for f in near)) if near else ""
    who = ref.team or "that team"
    return ToolError("I can't find %s for %s%s.%s" % (when, who, " against " + ref.opponent if ref.opponent else "", tail),
                     {"reason": "no_match", "team": ref.team, "candidates": near} if near else
                     {"reason": "no_match", "team": ref.team})
