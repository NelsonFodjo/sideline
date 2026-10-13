"""The leading scorers in a competition."""

from ..mcp.errors import ToolError
from . import competition_for, feed

TOP = 5


def run(ctx, args, listener_id):
    competition = competition_for(ctx, args, listener_id)
    rows = feed(ctx, "top_scorers", competition)
    if not rows:
        raise ToolError("I can't see the top scorers for %s." % competition,
                        {"reason": "no_match", "competition": competition})
    rows = sorted(rows, key=lambda r: -(r.get("goals") or 0))[:TOP]
    spoken = "Top scorers in the %s: %s." % (competition, ". ".join(
        "%s, %s, %s %s" % (r["player"], r["team"], r["goals"], "goal" if r["goals"] == 1 else "goals")
        if r.get("team") else "%s, %s %s" % (r["player"], r["goals"], "goal" if r["goals"] == 1 else "goals")
        for r in rows))
    return spoken, {"competition": competition, "scorers": rows, "generated_by": "template"}, None
