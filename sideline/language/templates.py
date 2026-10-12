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
"""


def _upper_first(s):
    """Capitalise the first letter only.

    str.capitalize() lowercases everything after it, which turns
    "set up by Odegaard" into "set up by odegaard". Player names are the
    one thing in this product that must never be mangled.
    """
    return (s[:1].upper() + s[1:]) if s else s


def ordinal_minute(minute, stoppage=0):
    """Minutes said the way people say them.

    Returns (phrase, needs_preposition). "on 34" works; "on just before
    half time" does not, so the caller has to know which it got.
    """
    if stoppage:
        if minute == 45:
            return "just before half time", False
        if minute == 90:
            return "deep into stoppage time", False
        return "%d plus %d" % (minute, stoppage), True
    return "%d" % minute, True


def when(minute, stoppage=0):
    phrase, prep = ordinal_minute(minute, stoppage)
    return ("on " + phrase) if prep else phrase


def say_score(fixture):
    h, a = fixture["score"]["home"], fixture["score"]["away"]
    home, away = fixture["home"], fixture["away"]
    if h == a:
        if h == 0:
            return "%s and %s, still goalless" % (home, away)
        return "%s %d, %s %d" % (home, h, away, a)
    lead = (home, h, away, a) if h > a else (away, a, home, h)
    return "%s %d, %s %d" % lead


def say_match_state(fixture):
    score = say_score(fixture)
    status = fixture.get("status")
    minute = fixture.get("minute") or 0
    if status in ("finished", "FT"):
        return "Full time. %s." % score
    if status in ("HT",):
        return "Half time. %s." % score
    if minute <= 0:
        return "%s against %s, not started yet." % (fixture["home"], fixture["away"])
    return "%s, %d minutes in." % (score, minute)


def say_event(e, brief=False):
    kind = e["kind"]
    w = when(e["minute"], e.get("stoppage", 0))
    if kind == "goal":
        bits = ["%s scored %s" % (e.get("player") or "Someone", w)]
        if e.get("detail"):
            # Only lowercase the first letter. Lowercasing the whole
            # string turns "Left foot, past Raya" into "past raya".
            d = e["detail"]
            bits.append(d[:1].lower() + d[1:])
        if e.get("assist") and not brief:
            bits.append("set up by %s" % e["assist"])
        return ", ".join(bits)
    if kind == "card":
        colour = e.get("colour", "yellow")
        verb = "was sent off" if colour == "red" else "was booked"
        out = "%s %s %s" % (e.get("player") or "A player", verb, w)
        if e.get("reason") and not brief:
            out += " for %s" % e["reason"]
        return out
    if kind == "substitution":
        return "%s came on for %s %s" % (
            e.get("player") or "a substitute", e.get("player_off") or "someone", w)
    if kind == "var":
        return "VAR %s: %s" % (w, e.get("decision") or "checked")
    return "something happened %s" % w


def say_catchup(events, fixture, from_minute, to_minute):
    """Template catch-up. The Bedrock version reads better; this is correct.

    Ordering is deliberate and is the thing a naive implementation gets
    wrong: goals first regardless of when they happened, because that is
    what the listener actually wants to know. Chronological order buries
    the goal behind a substitution.
    """
    if not events:
        return "Nothing since you last asked. %s." % say_score(fixture)

    goals = [e for e in events if e["kind"] == "goal"]
    rest = [e for e in events if e["kind"] != "goal"]

    parts = []
    if goals:
        parts.append(_upper_first(". ".join(say_event(g) for g in goals)))
    if rest:
        said = [say_event(r) for r in rest[:3]]
        if len(said) == 1:
            joined = said[0]
        else:
            joined = "%s and %s" % (", ".join(said[:-1]), said[-1])
        parts.append(_upper_first(joined))
    parts.append("It's %s." % say_score(fixture))
    return " ".join(p if p.endswith(".") else p + "." for p in parts)


def say_lineups(lineups, team=None):
    out = []
    for side, data in lineups.items():
        if team and team.lower() not in side.lower():
            continue
        xi = data.get("xi") or []
        line = "%s in a %s." % (side, data.get("formation") or "standard shape")
        if xi:
            # Keeper first, then the rest. A listener building a mental
            # picture needs the shape, not an alphabetical list.
            line += " %s in goal. Then %s." % (xi[0], ", ".join(xi[1:]))
        out.append(line)
    return " ".join(out) or "No line-up published yet."


def say_officials(o):
    bits = []
    if o.get("referee"):
        bits.append("%s is refereeing." % o["referee"])
    y, r = o.get("yellows_shown"), o.get("reds_shown")
    if y is not None:
        card_line = "%d yellow%s" % (y, "" if y == 1 else "s")
        if r:
            card_line += " and %d red" % r
        bits.append("%s so far." % card_line)
    if o.get("assistants"):
        bits.append("Assistants: %s." % ", ".join(o["assistants"]))
    return " ".join(bits) or "No official details published."


def say_milestones(key_events, all_events, fixture, minutes_away):
    """Template milestones, for an absence too long to read back in full.

    Forty minutes of match narrated by ear is unusable. The friend on the
    sofa does not do it either - they say what changed the game and let
    you ask for the rest.
    """
    if not key_events:
        return ("Nothing major in the last %d minutes. %s."
                % (minutes_away, say_score(fixture)))

    said = [say_event(e, brief=True) for e in key_events[:3]]
    if len(said) == 1:
        joined = said[0]
    else:
        joined = "%s and %s" % (", ".join(said[:-1]), said[-1])

    rest = len(all_events) - len(key_events)
    out = "In the %d minutes you were away: %s. It's %s." % (
        minutes_away, _upper_first(joined), say_score(fixture))
    if rest > 0:
        out += " Want the rest?"
    return out
