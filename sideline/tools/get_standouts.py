"""Who stood out in a match, by what the feed counts: goals, assists, shots, saves.

There is no player rating in the feed and none is invented: "best player" and "man of the match" are an opinion, so the
answer is the people who did the most that can be counted, and it says what it ranked by. A listener asking "who was
dangerous?" gets names and numbers they can weigh themselves.
"""

from ..mcp.errors import ToolError
from ..status import has_started
from . import resolve_fixture
from .get_player_context import _did

LISTED = 3
KEEPER_MIN_SAVES = 3          # a goalkeeper stands out for a busy night, not for a quiet one


def _weight(m):
    """Goals count most, then assists, then shots that hit the target, then shots: what makes a player dangerous."""
    return (3 * m.get("totalGoals", 0) + 2 * m.get("goalAssists", 0) + 0.5 * m.get("shotsOnTarget", 0)
            + 0.1 * m.get("totalShots", 0))


def run(ctx, args, listener_id):
    fx = resolve_fixture(ctx, args, listener_id, prefers="played")
    if not has_started(fx):
        raise ToolError("%s against %s hasn't started, so nobody has stood out yet." % (fx["home"], fx["away"]),
                        {"reason": "not_started", "fixture_id": fx["fixture_id"]})
    if fx.get("broadcast_offset"):
        # The player numbers are the feed's live totals: a goal not yet on this listener's screen would be in them.
        raise ToolError("Player numbers for a match in play are up to the second, so they could get ahead of your picture. "
                        "Ask me after the final whistle.", {"reason": "spoiler_guard", "fixture_id": fx["fixture_id"]})
    try:
        lineups = ctx.provider.lineups(fx["fixture_id"])
    except NotImplementedError:
        lineups = {}
    players = []
    for team, data in (lineups or {}).items():
        for name, m in (data.get("match_stats") or {}).items():
            if m:
                players.append({"name": name, "team": team, "position": (data.get("positions") or {}).get(name), "match": m})
    if not players:
        raise ToolError("The feed gives no player numbers for this match yet.",
                        {"reason": "no_player_stats", "fixture_id": fx["fixture_id"]})

    outfield = [p for p in players if (p.get("position") or "") != "goalkeeper" and _weight(p["match"]) > 0]
    outfield.sort(key=lambda p: -_weight(p["match"]))
    keepers = [p for p in players if (p.get("position") or "") == "goalkeeper"
               and p["match"].get("saves", 0) >= KEEPER_MIN_SAVES]
    keepers.sort(key=lambda p: -p["match"].get("saves", 0))
    picked = outfield[:LISTED] + keepers[:1]
    if not picked:
        raise ToolError("Nobody has stood out in numbers: no goals, assists or shots on target in the feed.",
                        {"reason": "nothing_stands_out", "fixture_id": fx["fixture_id"]})

    lines = ["%s, %s: %s" % (p["name"], p["team"], _did(p["match"])) for p in picked]
    spoken = ("The standouts in %s against %s, by goals, assists and shots: %s. "
              "The feed gives no player ratings, so that is what they did, not a verdict." % (
                  fx["home"], fx["away"], ". ".join(lines)))
    return spoken, {"fixture_id": fx["fixture_id"], "standouts": picked, "ranked_by": "goals, assists, shots on target, saves",
                    "generated_by": "template"}, None
