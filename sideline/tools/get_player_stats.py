"""How a player is doing this season."""

from ..mcp.errors import ToolError
from . import feed


def run(ctx, args, listener_id):
    player = (args.get("player") or "").strip()
    team = (args.get("team") or "").strip() or None
    s = feed(ctx, "player_stats", player, team)
    if not s:
        raise ToolError("I can't find season figures for %s." % player,
                        {"reason": "no_match", "player": player})
    bits = []
    if s.get("appearances") is not None:
        bits.append("%s %s" % (s["appearances"], "appearance" if s["appearances"] == 1 else "appearances"))
    if s.get("goals") is not None:
        bits.append("%s %s" % (s["goals"], "goal" if s["goals"] == 1 else "goals"))
    if s.get("assists") is not None:
        bits.append("%s %s" % (s["assists"], "assist" if s["assists"] == 1 else "assists"))
    if not bits:
        raise ToolError("I can't find season figures for %s." % player, {"reason": "no_match", "player": player})
    spoken = "%s%s this season: %s." % (s.get("name") or player, " for %s" % s["team"] if s.get("team") else "",
                                       ", ".join(bits))
    return spoken, {"player": s, "generated_by": "template"}, None
