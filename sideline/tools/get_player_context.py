"""Who a player is, and what they have done in this match.

Sighted viewers get this from the caption that appears under a player's
name. This is that caption, spoken.

Matching is fuzzy on purpose: listeners say surnames, mispronounce
names, and Alexa's transcription is not perfect. An exact-match lookup
would fail constantly on exactly the names that matter.
"""

from ..mcp.errors import ToolError

# A sighted viewer resolves "he" by looking at the screen. We have no
# camera, so we resolve it from recency instead: whoever the match was
# just about. These windows are in match minutes and are deliberately
# short - beyond them, guessing is worse than asking.
RECENCY = [("card", 2), ("goal", 3), ("substitution", 2), ("var", 2)]

PRONOUNS = {"he", "him", "his", "she", "her", "they", "them",
            "that player", "him there", "the player"}


def _norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalpha())


def _resolve_pronoun(ctx, fx):
    """Who 'he' most likely means, from the last few minutes of play.

    Returns (name, why) or (None, None). We would rather return nothing
    and let Alexa+ ask a one-line clarifying question than name the
    wrong player confidently - a blind listener has no way to catch us
    out, which is exactly why we must not guess.
    """
    now = fx.get("minute") or 0
    best = None
    for e in reversed(ctx.store.events(fx["fixture_id"])):
        for kind, window in RECENCY:
            if e["kind"] != kind or now - e["minute"] > window:
                continue
            name = e.get("player")
            if not name:
                continue
            why = {"card": "just booked", "goal": "just scored",
                   "substitution": "just came on", "var": "just checked by VAR"}[kind]
            if best is None or e["minute"] > best[2]:
                best = (name, why, e["minute"])
    if not best:
        return None, None
    return best[0], best[1]


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)

    asked = (args["player"] or "").strip().lower()
    pronoun_used = asked in PRONOUNS
    if pronoun_used:
        name, why = _resolve_pronoun(ctx, fx)
        if not name:
            # Honest refusal beats a confident wrong name.
            raise ToolError(
                "I can't see the screen, so I'm not sure who you mean. "
                "Say the name and I'll tell you about them.",
                {"reason": "pronoun_unresolved", "asked": asked})
        args = dict(args)
        args["player"] = name

    query = _norm(args["player"])
    lineups = ctx.provider.lineups(fx["fixture_id"])

    found = None
    for team, data in lineups.items():
        for name in (data.get("xi") or []) + (data.get("bench") or []):
            n = _norm(name)
            if query == n or query in n or n.endswith(query):
                found = {"name": name, "team": team,
                         "number": (data.get("numbers") or {}).get(name),
                         "starting": name in (data.get("xi") or [])}
                break
        if found:
            break

    if not found:
        raise ToolError(
            "I can't find %s in this match." % args["player"],
            {"reason": "player_not_found", "query": args["player"]})

    involved = [e for e in ctx.store.events(fx["fixture_id"])
                if _norm(e.get("player")) == _norm(found["name"])
                or _norm(e.get("player_off")) == _norm(found["name"])
                or _norm(e.get("assist")) == _norm(found["name"])]

    bits = []
    if pronoun_used:
        # Say who we think they meant, so a wrong guess is correctable.
        bits.append("%s, the one who %s" % (found["name"], why))
    else:
        bits.append("%s, %s" % (found["name"], found["team"]))
    if found.get("number"):
        bits.append("number %s" % found["number"])
    bits.append("started" if found["starting"] else "on the bench")
    spoken = ", ".join(bits) + "."
    if involved:
        spoken += " " + " ".join(
            ctx.lang.templates._upper_first(ctx.lang.templates.say_event(e, brief=True)) + "."
            for e in involved[:3])

    structured = {"fixture_id": fx["fixture_id"], "player": found,
                  "resolved_from_pronoun": pronoun_used,
                  "involvement": [{"minute": e["minute"], "kind": e["kind"]}
                                  for e in involved],
                  "generated_by": "template"}
    return spoken, structured, None
