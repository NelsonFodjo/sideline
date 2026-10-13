"""Deterministic phrasing.

Every tool has a template path that works with no model at all. Three
reasons this exists and is not a fallback afterthought:

  1. LATENCY. Bedrock sits on the critical path to speech. The fast
     tools (get_match_state, get_officials) must answer in well under a
     second, so they never call a model. See docs/BEDROCK.md.
  2. CORRECTNESS. A scoreline is a fact. There is no version of
     "Arsenal one, Spurs nil" that benefits from being generated.
  3. THE REPO RUNS WITHOUT AWS. A judge should be able to clone this,
     run it, and hear real answers with no credentials. If language
     were model-only, the whole thing would be dead on arrival for
     anyone without a Bedrock account.

Bedrock is used where language genuinely has to be *composed* - the
catch-up paragraph - and nowhere else. See bedrock.py.

Style rules for everything in this file, which come from how the
listener is actually using it:

  * Lead with the fact. They are listening with one ear on the TV.
  * Minute first for events: "Saka, on 34" not "on 34, Saka".
  * No preamble. Never "Sure! Here's the line-up for you."
  * Stoppage time said as people say it: "just before half time".

Everything that depends on the sport (how time, scores, events, line-ups
and officials are said) lives in sideline/sports/. The functions here
take an optional `sport` (a profile, a key, or a fixture dict) and
default to football, so older callers behave exactly as before.
"""

from .. import sports


def _upper_first(s):
    """Capitalise the first letter only.

    str.capitalize() lowercases everything after it, which turns
    "set up by Odegaard" into "set up by odegaard". Player names are the
    one thing in this product that must never be mangled.
    """
    return (s[:1].upper() + s[1:]) if s else s


def ordinal_minute(minute, stoppage=0, sport=None):
    """Football minutes said the way people say them.

    Returns (phrase, needs_preposition). Kept for callers that predate
    sport profiles; new code should use `when`.
    """
    if stoppage:
        if minute == 45:
            return "just before half time", False
        if minute == 90:
            return "deep into stoppage time", False
        return "%d plus %d" % (minute, stoppage), True
    return "%d" % minute, True


def when(minute, stoppage=0, sport=None):
    return sports.resolve(sport).when(minute, stoppage)


def say_score(fixture, sport=None):
    return sports.resolve(sport or fixture).say_score(fixture)


def say_match_state(fixture, sport=None):
    return sports.resolve(sport or fixture).say_match_state(fixture)


def say_event(e, brief=False, sport=None):
    return sports.resolve(sport).say_event(e, brief)


def _join(said):
    if len(said) == 1:
        return said[0]
    return "%s and %s" % (", ".join(said[:-1]), said[-1])


def say_catchup(events, fixture, from_minute, to_minute):
    """Template catch-up. The Bedrock version reads better; this is correct.

    Ordering is deliberate and is the thing a naive implementation gets
    wrong: scores first regardless of when they happened, because that is
    what the listener actually wants to know. Chronological order buries
    the goal behind a substitution.
    """
    sp = sports.resolve(fixture)
    if not events:
        return "Nothing since you last asked. %s." % sp.say_score(fixture)

    scores = [e for e in events if sp.is_score(e)]
    rest = [e for e in events if not sp.is_score(e)]

    parts = []
    if scores:
        parts.append(_upper_first(". ".join(sp.say_event(g) for g in scores)))
    if rest:
        parts.append(_upper_first(_join([sp.say_event(r) for r in rest[:3]])))
    parts.append("It's %s." % sp.say_score(fixture))
    return " ".join(p if p.endswith(".") else p + "." for p in parts)


def say_lineups(lineups, team=None, sport=None):
    return sports.resolve(sport).say_lineups(lineups, team)


def say_officials(o, sport=None):
    return sports.resolve(sport).say_officials(o)


def say_milestones(key_events, all_events, fixture, minutes_away):
    """Template milestones, for an absence too long to read back in full.

    Forty minutes of match narrated by ear is unusable. The friend on the
    sofa does not do it either - they say what changed the game and let
    you ask for the rest.
    """
    sp = sports.resolve(fixture)
    if not key_events:
        return ("Nothing major in the last %d minutes. %s."
                % (minutes_away, sp.say_score(fixture)))

    spoken = key_events[:sports.MAX_HEADLINES]
    joined = _join([sp.say_event(e, brief=True) for e in spoken])

    rest = len(all_events) - len(spoken)
    out = "In the %d minutes you were away: %s. It's %s." % (
        minutes_away, _upper_first(joined), sp.say_score(fixture))
    if rest > 0:
        out += " Want the rest?"
    return out
