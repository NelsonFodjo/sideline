"""The league table, or where one team sits in it."""

from .. import resolve
from ..mcp.errors import ToolError
from . import competition_for, feed, ordinal

TOP = 5


def _row_is(row, team):
    want, have = resolve.words(team), resolve.words(row.get("team"))
    return " ".join(want) in " ".join(have) or resolve.similarity(want, have) >= 0.82


def _league_of(ctx, team):
    """The competition whose table has `team` in it, found from the team's own matches (a team needs no match
    followed to be asked about). Each competition it plays in is tried in turn; a cup has no table and is skipped."""
    try:
        found = ctx.provider.team_matches(team)
    except NotImplementedError:
        return None, None
    names = []
    for fx in ((found or {}).get("recent") or []) + ((found or {}).get("upcoming") or []):
        if fx.get("competition") and fx["competition"] not in names:
            names.append(fx["competition"])
    for name in names[:3]:
        table = ctx.provider.standings(name)
        if table and any(_row_is(r, team) for r in table):
            return name, table
    return None, None


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    table = None
    try:
        competition = competition_for(ctx, args, listener_id)
    except ToolError:
        if not team:
            raise
        competition, table = _league_of(ctx, team)
        if not competition:
            raise
    if table is None:
        table = feed(ctx, "standings", competition)
    if not table:
        raise ToolError("I can't see a table for %s." % competition,
                        {"reason": "no_match", "competition": competition})
    table = sorted(table, key=lambda r: r.get("position") or 999)
    if team:
        mine = next((r for r in table if _row_is(r, team)), None)
        if mine:
            games = " from %s games" % mine["played"] if mine.get("played") else ""
            spoken = "In the %s, %s are %s with %s %s%s." % (
                competition, mine["team"], ordinal(mine["position"]), mine.get("points"),
                "point" if mine.get("points") == 1 else "points", games)
            if mine["position"] > 1:
                lead = table[0]
                spoken += " %s lead with %s." % (lead["team"], lead.get("points"))
            return spoken, {"competition": competition, "team": mine, "generated_by": "template"}, None
        raise ToolError("I can't see %s in the %s table." % (team, competition),
                        {"reason": "no_match", "team": team, "competition": competition})
    top = table[:TOP]
    spoken = "The %s table: %s." % (competition, ". ".join(
        "%s, %s, %s %s" % (ordinal(r["position"]).capitalize(), r["team"], r.get("points"),
                           "point" if r.get("points") == 1 else "points") for r in top))
    return spoken, {"competition": competition, "table": top, "total": len(table),
                    "generated_by": "template"}, None
