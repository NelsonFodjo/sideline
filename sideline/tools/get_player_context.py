"""Who a player is, and what they have done in this match.

Sighted viewers get this from the caption that appears under a player's
name. This is that caption, spoken.

Matching is fuzzy on purpose: listeners say surnames, mispronounce
names, and Alexa's transcription is not perfect. An exact-match lookup
would fail constantly on exactly the names that matter.
"""

from .. import names, sports
from ..mcp.errors import ToolError
from ..status import FINISHED
from . import events_for

# A sighted viewer resolves "he" by looking at the screen. We have no
# camera, so we resolve it from recency instead: whoever the match was
# just about. These windows are in match minutes and are deliberately
# short - beyond them, guessing is worse than asking.
# Per sport: sideline/sports/ (SportProfile.recency).

PRONOUNS = {"he", "him", "his", "she", "her", "they", "them",
            "that player", "him there", "the player"}


def _same_person(said, name):
    """"Son" is Son Heung-min, not Maddison: whole words of the name, not a fragment of it."""
    return names.whole_words(said, name) or _norm(said) == _norm(name)


def _norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalpha())


def _resolve_pronoun(ctx, fx):
    """Who 'he' most likely means, from the last few minutes of play.

    Returns (name, why) or (None, None). We would rather return nothing
    and let Alexa+ ask a one-line clarifying question than name the
    wrong player confidently - a blind listener has no way to catch us
    out, which is exactly why we must not guess.
    """
    if fx.get("status") in FINISHED:
        return None, None                 # the match is over: "he" has no "just now" to point at
    now = fx.get("minute") or 0
    best = None
    for e in reversed(events_for(ctx, fx)):
        for kind, window, why in sports.for_fixture(fx).recency:
            if e["kind"] != kind or now - e["minute"] > window:
                continue
            name = e.get("player")
            if not name:
                continue
            if best is None or e["minute"] > best[2]:
                best = (name, why, e["minute"])
    if not best:
        return None, None
    return best[0], best[1]


def _did(m):
    """What a player did in the match, as a person would say it: "2 goals, 8 shots, 3 on target and 1 assist"."""
    parts = []
    for key, one, many in (("totalGoals", "goal", "goals"), ("goalAssists", "assist", "assists")):
        if m.get(key):
            parts.append("%d %s" % (m[key], one if m[key] == 1 else many))
    if m.get("totalShots"):
        shots = "%d %s" % (m["totalShots"], "shot" if m["totalShots"] == 1 else "shots")
        parts.append(shots + (" with %d on target" % m["shotsOnTarget"] if m.get("shotsOnTarget") else ""))
    if m.get("saves"):
        parts.append("%d %s" % (m["saves"], "save" if m["saves"] == 1 else "saves"))
        if m.get("goalsConceded"):
            parts.append("%d conceded" % m["goalsConceded"])
    if m.get("ownGoals"):
        parts.append("an own goal")
    return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else (parts[0] if parts else "")


def run(ctx, args, listener_id):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id, prefers="played")

    asked = (args["player"] or "").strip().lower()
    pronoun_used = asked in PRONOUNS
    if pronoun_used:
        name, why = _resolve_pronoun(ctx, fx)
        if not name:
            # Honest refusal beats a confident wrong name.
            over = fx.get("status") in FINISHED
            raise ToolError(
                ("That match is over, so I can't tell who you mean by that. " if over
                 else "I can't see the screen, so I'm not sure who you mean. ")
                + "Say the name and I'll tell you about them.",
                {"reason": "pronoun_unresolved", "asked": asked, "match_over": over})
        args = dict(args)
        args["player"] = name

    lineups = ctx.provider.lineups(fx["fixture_id"])

    found = None
    for team, data in lineups.items():
        for name in (data.get("xi") or []) + (data.get("bench") or []):
            if _same_person(args["player"], name):
                found = {"name": name, "team": team,
                         "number": (data.get("numbers") or {}).get(name),
                         "position": (data.get("positions") or {}).get(name),
                         "match": (data.get("match_stats") or {}).get(name) or {},
                         "starting": name in (data.get("xi") or [])}
                break
        if found:
            break

    if not found:
        # Line-ups are often not published until close to kick-off (and
        # some feeds never have them). The event log still names everyone
        # who has done something, so look there before saying no.
        for e in events_for(ctx, fx):
            for field in ("player", "player_off", "assist"):
                if e.get(field) and _same_person(args["player"], e[field]):
                    found = {"name": e[field], "team": e.get("team"),
                             "number": None, "starting": None}
                    break
            if found:
                break

    if not found:
        raise ToolError(
            "I can't find %s in this match." % args["player"],
            {"reason": "player_not_found", "query": args["player"]})

    involved = [e for e in events_for(ctx, fx)
                if _norm(e.get("player")) == _norm(found["name"])
                or _norm(e.get("player_off")) == _norm(found["name"])
                or _norm(e.get("assist")) == _norm(found["name"])
                or _norm(e.get("keeper")) == _norm(found["name"])]

    bits = []
    if pronoun_used:
        # Say who we think they meant, so a wrong guess is correctable.
        bits.append("%s, the one who %s" % (found["name"], why))
    else:
        bits.append("%s, %s%s" % (found["name"], found["team"], " %s" % found["position"] if found.get("position") else ""))
    if found.get("number"):
        bits.append("number %s" % found["number"])
    if found["starting"] is not None:
        bits.append("started" if found["starting"] else "on the bench")
    spoken = ", ".join(bits) + "."
    did = "" if fx.get("broadcast_offset") else _did(found.get("match") or {})     # live totals could be ahead of their picture
    if did:
        spoken += " In this match: %s." % did
    if involved:
        # Two or more goals by him are one sentence ("Goals on 53 and 75"), not his name over and over.
        mine = [e for e in involved if e.get("kind") == "goal" and _norm(e.get("player")) == _norm(found["name"])]
        rest = [e for e in involved if not (len(mine) > 1 and e in mine)]
        said = []
        if len(mine) > 1:
            said.append("Goals on %s" % " and ".join(str(e["minute"]) for e in mine))
        said += [ctx.lang.templates._upper_first(ctx.lang.templates.say_event(e, brief=True, sport=fx)) for e in rest]
        spoken += " " + " ".join(s + "." for s in said[:3])

    structured = {"fixture_id": fx["fixture_id"], "player": found,
                  "resolved_from_pronoun": pronoun_used,
                  "involvement": [{"minute": e["minute"], "kind": e["kind"]}
                                  for e in involved],
                  "generated_by": "template"}
    return spoken, structured, None
