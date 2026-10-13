"""The numbers for a match: possession, shots, corners, fouls and cards."""

from ..mcp.errors import ToolError
from . import feed, resolve_fixture

_LABELS = (("possession", "Possession", " percent"), ("shots", "Shots", ""), ("shots_on_target", "On target", ""),
           ("corners", "Corners", ""), ("fouls", "Fouls", ""), ("yellow_cards", "Yellow cards", ""),
           ("red_cards", "Red cards", ""))


def _line(label, unit, home, away, a, b):
    if a is None and b is None:
        return None
    return "%s: %s %s%s, %s %s%s" % (label, home, a if a is not None else "none", unit if a is not None else "",
                                      away, b if b is not None else "none", unit if b is not None else "")


def run(ctx, args, listener_id):
    fx = resolve_fixture(ctx, args, listener_id, prefers="played")
    stats = feed(ctx, "match_stats", fx["fixture_id"])
    if not stats:
        raise ToolError("There are no statistics for this match yet.",
                        {"reason": "no_match", "fixture_id": fx["fixture_id"]})
    home, away = fx["home"], fx["away"]
    a, b = stats.get(home) or {}, stats.get(away) or {}
    parts = [_line(label, unit, home, away, a.get(key), b.get(key)) for key, label, unit in _LABELS]
    parts = [p for p in parts if p]
    if not parts:
        raise ToolError("There are no statistics for this match yet.",
                        {"reason": "no_match", "fixture_id": fx["fixture_id"]})
    return ". ".join(parts) + ".", {"home": home, "away": away, "stats": stats, "generated_by": "template"}, None
