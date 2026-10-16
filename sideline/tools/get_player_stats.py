"""How a player is doing this season."""

from ..mcp.errors import ToolError
from . import feed


def _count(n, one, many):
    return "no %s" % many if n == 0 else "%s %s" % (n, one if n == 1 else many)


def _join(bits):
    return ", ".join(bits[:-1]) + " and " + bits[-1] if len(bits) > 1 else bits[0]


def _bits(s):
    """The figures in `s` that the feed gave, each said as a person would (zero is "no goals", not left out)."""
    bits = []
    for key, one, many in (("starts", "start", "starts"), ("appearances", "appearance", "appearances"),
                           ("goals", "goal", "goals"), ("points", "point", "points"), ("assists", "assist", "assists"),
                           ("rebounds", "rebound", "rebounds"), ("steals", "steal", "steals"),
                           ("blocks", "block", "blocks")):
        if s.get(key) is not None:
            bits.append(_count(s[key], one, many))
    return bits


def _in_game(ctx, args, listener_id, player, team):
    """One game's figures: "how many points did Brunson score last night". The game is the team's last one, or the day or
    opponent named; the box score is the feed's, never worked out."""
    from . import resolve_fixture
    who = feed(ctx, "player_profile", player, team) or {}
    club = team or who.get("team")
    if not club:
        raise ToolError("I can't find %s." % player, {"reason": "no_match", "player": player})
    ask = {"team": club, "when": args.get("when") or "last"}
    if args.get("opponent"):
        ask["opponent"] = args["opponent"]
    fx = resolve_fixture(ctx, ask, listener_id, prefers="played")
    g = feed(ctx, "player_game", fx["fixture_id"], player)
    if not g:
        raise ToolError("%s is not in the box score for %s against %s." % (who.get("name") or player, fx["home"], fx["away"]),
                        {"reason": "no_match", "player": player, "fixture_id": fx["fixture_id"]})
    return ("%s %s against %s." % (g["name"], g["line"] if g["line"].startswith(("pitched", "batted")) else "had " + g["line"],
                                   fx["away"] if (g.get("team") or "") == fx["home"] else fx["home"]),
            {"player": g, "fixture_id": fx["fixture_id"], "generated_by": "template"}, None)


def run(ctx, args, listener_id):
    player = (args.get("player") or "").strip()
    team = (args.get("team") or "").strip() or None
    if args.get("when") or args.get("opponent"):
        return _in_game(ctx, args, listener_id, player, team)
    s = feed(ctx, "player_stats", player, team)
    if not s:
        raise ToolError("I can't find season figures for %s." % player,
                        {"reason": "no_match", "player": player})
    if s.get("line"):                       # another sport's figures, already in its own words
        return ("%s%s, %s." % (s.get("name") or player, " for %s" % s["team"] if s.get("team") else "", s["line"]),
                {"player": s, "generated_by": "template"}, None)
    bits = _bits(s)
    if not bits:
        raise ToolError("I can't find season figures for %s." % player, {"reason": "no_match", "player": player})
    spoken = "%s%s this season: %s." % (s.get("name") or player, " for %s" % s["team"] if s.get("team") else "",
                                       _join(bits))
    country = s.get("international")
    if country and any(country.values()):
        spoken += " For his country: %s." % _join(_bits(country))
    return spoken, {"player": s, "generated_by": "template"}, None
