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


def run(ctx, args, listener_id):
    player = (args.get("player") or "").strip()
    team = (args.get("team") or "").strip() or None
    s = feed(ctx, "player_stats", player, team)
    if not s:
        raise ToolError("I can't find season figures for %s." % player,
                        {"reason": "no_match", "player": player})
    bits = _bits(s)
    if not bits:
        raise ToolError("I can't find season figures for %s." % player, {"reason": "no_match", "player": player})
    spoken = "%s%s this season: %s." % (s.get("name") or player, " for %s" % s["team"] if s.get("team") else "",
                                       _join(bits))
    country = s.get("international")
    if country and any(country.values()):
        spoken += " For his country: %s." % _join(_bits(country))
    return spoken, {"player": s, "generated_by": "template"}, None
