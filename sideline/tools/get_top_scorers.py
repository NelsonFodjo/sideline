"""The leading scorers in a competition."""

from ..mcp.errors import ToolError
from . import competition_for, feed, possessive

TOP = 5


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    try:
        competition = competition_for(ctx, args, listener_id)
    except ToolError:
        if not team:
            raise
        from .get_standings import _league_of           # a team's own league, found from its matches
        competition, _ = _league_of(ctx, team)
        if not competition:
            raise
    rows = feed(ctx, "top_scorers", competition)
    if team and rows:
        from .get_standings import _row_is
        mine = [r for r in rows if r.get("team") and _row_is(r, team)]
        if not mine:
            raise ToolError("No %s player is among the top scorers in the %s." % (team, competition),
                            {"reason": "no_match", "team": team, "competition": competition})
        rows = mine
    if not rows:
        raise ToolError("I can't see the top scorers for %s." % competition,
                        {"reason": "no_match", "competition": competition})
    rows = sorted(rows, key=lambda r: -(r.get("goals") or 0))[:TOP]
    lead = "%s top scorers in the %s" % (possessive(team), competition) if team else "Top scorers in the %s" % competition
    spoken = "%s: %s." % (lead, ". ".join(
        "%s, %s, %s %s" % (r["player"], r["team"], r["goals"], "goal" if r["goals"] == 1 else "goals")
        if r.get("team") else "%s, %s %s" % (r["player"], r["goals"], "goal" if r["goals"] == 1 else "goals")
        for r in rows))
    return spoken, {"competition": competition, "scorers": rows, "generated_by": "template"}, None
