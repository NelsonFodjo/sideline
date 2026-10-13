"""What Sideline can do with the feed it is connected to, in words.

The list is not written down here: it is read from the tools that are actually offered, so
it is true for this feed and changes with it.
"""

from ..mcp import registry
from .. import sports

_SAY = {
    "fixtures": "what's on and when teams play", "events": "what happened in a match and what you missed",
    "lineups": "line-ups and who is playing", "officials": "the referee", "h2h": "head to head",
    "stats": "match statistics", "injuries": "injuries and suspensions", "form": "recent form",
    "standings": "league tables", "top_scorers": "top scorers", "player_stats": "a player's season",
    "search": "looking up a team or player", "competitions": "which competitions I cover",
    "squad": "a team's squad, manager and captain", "team_stats": "a team's season",
}


def run(ctx, args, listener_id):
    names = [t["name"] for t in registry.public_tools()]
    caps = []
    for tool in names:
        need = registry.TOOL_REQUIRES.get(tool)
        if need and need in _SAY and _SAY[need] not in caps:
            caps.append(_SAY[need])
    caps += ["remembering your teams", "how you like answers"]
    sport_names = sorted(sports.known())
    spoken = "I'm reading %s. I can tell you %s." % (
        ctx.provider.name if ctx.provider.name != "base" else "the live feed",
        ", ".join(caps[:-1]) + ", and " + caps[-1] if len(caps) > 1 else caps[0])
    return spoken, {"provider": ctx.provider.name, "tools": names, "capabilities": sorted(ctx.provider.capabilities),
                    "sports": sport_names, "generated_by": "template", "verbatim": True}, None
