"""A team's season so far: games, results, goals, clean sheets and possession.

A team question, not a match question: found by name, whatever is being followed.
"""

from ..mcp.errors import ToolError
from . import feed, no_team


def _n(v, one, many):
    return "%s %s" % (v, one if v == 1 else many)


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    if not team:
        raise ToolError("Which team?", {"reason": "needs_team"})
    s = feed(ctx, "team_stats", team)
    if not s or s.get("played") is None:
        raise no_team(ctx, team)
    parts = ["%s this season: %s" % (s["team"], _n(s["played"], "game", "games"))]
    if None not in (s.get("won"), s.get("drawn"), s.get("lost")):
        parts[0] += ", won %s, drew %s, lost %s" % (s["won"], s["drawn"], s["lost"])
    elif None not in (s.get("won"), s.get("lost")):
        parts[0] += ", won %s, lost %s" % (s["won"], s["lost"])
    spoken = parts[0] + "."
    if s.get("goals_for") is not None and s.get("goals_against") is not None:
        spoken += " %s scored and %s conceded." % (_n(s["goals_for"], "goal", "goals"), s["goals_against"])
    elif s.get("points_for") is not None and s.get("points_against") is not None:
        spoken += " %s scored and %s conceded." % (_n(s["points_for"], "point", "points"), s["points_against"])
    if s.get("clean_sheets"):
        spoken += " %s." % _n(s["clean_sheets"], "clean sheet", "clean sheets")
    if s.get("possession"):
        spoken += " About %d percent possession a game." % round(s["possession"])
    return spoken, {"stats": s, "generated_by": "template"}, None
