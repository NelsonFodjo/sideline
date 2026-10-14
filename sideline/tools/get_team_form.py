"""How each side has been doing: their last results, as words.

With a team named, it is about that team alone and needs no match (its last results from the feed). Without one, it is
the two sides in the match being discussed.
"""

from ..mcp.errors import ToolError
from . import feed, resolve_fixture

_WORDS = {"W": "won", "D": "drew", "L": "lost"}


def _say(form):
    return ", ".join(_WORDS[c] for c in (form or "").upper() if c in _WORDS)


def _letters(f, team_id, team_name=None):
    from . import _is_team
    mine, theirs = (f["score"]["home"], f["score"]["away"]) if (team_id and f.get("home_id") == team_id) or (team_name and _is_team(f.get("home"), team_name)) \
        else (f["score"]["away"], f["score"]["home"])
    return "W" if mine > theirs else "L" if mine < theirs else "D"


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    if team and "team_matches" in getattr(ctx.provider, "capabilities", ()):
        try:
            data = feed(ctx, "team_matches", team)
        except ToolError as e:
            if (e.detail or {}).get("reason") != "not_supported":
                raise
            data = False                                         # a feed that cannot: use the match's own form below
        if data is not False:
            recent = (data or {}).get("recent") or []
            if not recent:
                raise ToolError("I don't have recent results for %s." % team, {"reason": "no_match", "team": team})
            last = recent[:5][::-1]                              # oldest first, as the form is read
            form = "".join(_letters(f, data.get("team_id"), data.get("team")) for f in last)
            return ("%s recently: %s." % (data["team"], _say(form)),
                    {"team": data["team"], "form": form, "generated_by": "template"}, None)
    fx = resolve_fixture(ctx, args, listener_id, prefers="coming")
    form = feed(ctx, "form", fx["fixture_id"]) or {}
    home, away = _say(form.get("home")), _say(form.get("away"))
    if not home and not away:
        raise ToolError("I don't have recent form for this match.", {"reason": "no_match"})
    parts = []
    if home:
        parts.append("%s recently: %s." % (fx["home"], home))
    if away:
        parts.append("%s recently: %s." % (fx["away"], away))
    return " ".join(parts), {"form": form, "generated_by": "template"}, None
