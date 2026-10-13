"""A team's players: how many, who the manager and captain are, and the names by position.

A question about a team ("who's in the Celtic squad", "who's their goalkeeper", "who's the manager") is not a
question about a match, and does not need one: the team is found by name, whatever is being followed.
"""

from ..mcp.errors import ToolError
from . import feed, no_team, possessive

_PLURAL = {"goalkeeper": "goalkeepers", "defender": "defenders", "midfielder": "midfielders", "attacker": "attackers"}
LISTED = 14


def _names(players):
    return ", ".join(p["name"] if not p.get("number") else "%s, number %s" % (p["name"], p["number"]) for p in players)


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    position = (args.get("position") or "").strip().lower()
    if not team:
        fid = ctx.store.listener(listener_id).get("following")
        fx = (ctx.store.fixture(fid) or {}) if fid else {}
        if fx.get("home") and fx.get("away"):
            raise ToolError("Which team: %s or %s?" % (fx["home"], fx["away"]), {"reason": "needs_team"})
        raise ToolError("Which team's squad?", {"reason": "needs_team"})
    s = feed(ctx, "squad", team)
    if not s or not s.get("players"):
        raise no_team(ctx, team)
    players = s["players"]
    if position in _PLURAL:
        mine = [p for p in players if p.get("position") == position]
        if not mine:
            raise ToolError("I don't have any %s listed for %s." % (_PLURAL[position], s["team"]),
                            {"reason": "no_match", "team": s["team"], "position": position})
        shown = mine[:LISTED]
        spoken = "%s %s: %s." % (possessive(s["team"]), _PLURAL[position], _names(shown))
        if len(mine) > len(shown):
            spoken += " And %d more." % (len(mine) - len(shown))
        return spoken, {"team": s["team"], "position": position, "players": shown, "generated_by": "template"}, None
    counts = [(pos, sum(1 for p in players if p.get("position") == pos)) for pos in _PLURAL]
    counts = ["%d %s" % (n, _PLURAL[pos] if n != 1 else pos) for pos, n in counts if n]
    spoken = "%s have %d players: %s." % (s["team"], len(players), ", ".join(counts[:-1]) + " and " + counts[-1]
                                          if len(counts) > 1 else counts[0] if counts else "no positions listed")
    if s.get("coach"):
        spoken += " The manager is %s." % s["coach"]
    if s.get("captain"):
        spoken += " The captain is %s." % s["captain"]
    elif not args.get("position"):
        spoken += " The feed doesn't list a captain."
    spoken += " Ask for a position to hear the names."
    return spoken, {"team": s["team"], "coach": s.get("coach"), "captain": s.get("captain"),
                    "total": len(players), "generated_by": "template"}, None
