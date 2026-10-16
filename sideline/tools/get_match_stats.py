"""The numbers for a match: possession, shots, corners, fouls and cards."""

from ..mcp.errors import ToolError
from . import feed, resolve_fixture

_LABELS = (("possession", "Possession", " percent"), ("shots", "Shots", ""), ("shots_on_target", "On target", ""),
           ("corners", "Corners", ""), ("fouls", "Fouls", ""), ("yellow_cards", "Yellow cards", ""),
           ("red_cards", "Red cards", ""))

_BB_LABELS = (("field_goals", "Field goals", ""), ("field_goal_pct", "Field goal pct", " percent"),
              ("three_pointers", "Three pointers", ""), ("free_throws", "Free throws", ""),
              ("rebounds", "Rebounds", ""), ("assists", "Assists", ""), ("steals", "Steals", ""),
              ("blocks", "Blocks", ""), ("turnovers", "Turnovers", ""), ("fouls", "Fouls", ""))


def _line(label, unit, home, away, a, b):
    if a is None and b is None:
        return None
    return "%s: %s %s%s, %s %s%s" % (label, home, a if a is not None else "none", unit if a is not None else "",
                                      away, b if b is not None else "none", unit if b is not None else "")


NOT_PROVIDED = "not provided"


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _pct(v):
    return "%d%%" % round(v) if _num(v) is not None else NOT_PROVIDED


def _pass_accuracy(t):
    done, total = _num(t.get("passes_accurate")), _num(t.get("passes_total"))
    if not total or done is None:
        return NOT_PROVIDED
    return "%d%% (%d/%d)" % (round(100.0 * done / total), done, total)


def _shots(t):
    shots, on = _num(t.get("shots")), _num(t.get("shots_on_target"))
    if shots is None:
        return NOT_PROVIDED
    return "%d (%d)" % (shots, on) if on is not None else "%d" % shots


def _slash(t, keys):
    vals = [_num(t.get(k)) for k in keys]
    return NOT_PROVIDED if all(v is None for v in vals) else " / ".join("%d" % v if v is not None else "-" for v in vals)


def _plain(key):
    return lambda t: "%d" % t[key] if _num(t.get(key)) is not None else NOT_PROVIDED


# metric, how each side's cell is made. Expected goals is shown only when the feed gives it: never worked out.
FOOTBALL_TABLE = (
    ("Possession (%)", lambda t: _pct(t.get("possession"))),
    ("Total shots (on target)", _shots),
    ("Expected goals (xG)", lambda t: "%.2f" % t["xg"] if _num(t.get("xg")) is not None else NOT_PROVIDED),
    ("Pass accuracy (%)", _pass_accuracy),
    ("Fouls / yellow cards / red cards", lambda t: _slash(t, ("fouls", "yellow_cards", "red_cards"))),
    ("Corners", _plain("corners")),
    ("Offsides", _plain("offsides")),
    ("Goalkeeper saves", _plain("saves")),
)


def table_rows(home_stats, away_stats):
    """[{"metric", "home", "away"}] for a football match, in a fixed order."""
    return [{"metric": name, "home": cell(home_stats), "away": cell(away_stats)} for name, cell in FOOTBALL_TABLE]


def _said(label, home, away, h, a):
    if h == NOT_PROVIDED and a == NOT_PROVIDED:
        return None
    return "%s: %s %s, %s %s" % (label, home, h, away, a)


def _cards(t):
    y, r = _num(t.get("yellow_cards")), _num(t.get("red_cards"))
    if y is None and r is None:
        return None
    bits = []
    if y:
        bits.append("%d yellow%s" % (y, "" if y == 1 else "s"))
    if r:
        bits.append("%d red%s" % (r, "" if r == 1 else "s"))
    return " and ".join(bits) or "no cards"


_ONLY = {"possession": ("Possession",), "shots": ("Shots",), "passes": ("Pass accuracy",), "corners": ("Corners",),
         "offsides": ("Offsides",), "saves": ("Saves",), "fouls": ("Fouls",), "cards": ("Cards",)}


def _football_spoken(home, away, rows, a, b, only=None):
    """The table as a person would say it: a number per side, what the feed lacks left out or admitted."""
    by = {r["metric"]: r for r in rows}
    parts = []

    def add(metric, label, fmt=lambda v: v):
        r = by[metric]
        parts.append(_said(label, home, away, fmt(r["home"]), fmt(r["away"])))
    add("Possession (%)", "Possession", lambda v: v.replace("%", " percent"))
    add("Total shots (on target)", "Shots, with those on target in brackets")
    add("Pass accuracy (%)", "Pass accuracy", lambda v: v.split(" (")[0].replace("%", " percent"))
    add("Corners", "Corners")
    add("Offsides", "Offsides")
    add("Goalkeeper saves", "Saves")
    if _num(a.get("fouls")) is not None and _num(b.get("fouls")) is not None:
        parts.append("Fouls: %s %d, %s %d" % (home, a["fouls"], away, b["fouls"]))
    ca, cb = _cards(a), _cards(b)
    if ca and cb:
        parts.append("Cards: %s %s, %s %s" % (home, ca, away, cb))
    parts = [p for p in parts if p]
    if only:                                    # one number asked for: say that one, not the whole table
        start = _ONLY.get(only, ())
        parts = [p for p in parts if p.startswith(start)]
        if not parts:
            return "The feed has no %s for this match." % only.replace("_", " ")
        return ". ".join(parts) + "."
    if by["Expected goals (xG)"]["home"] == NOT_PROVIDED:
        parts.append("The feed gives no expected goals for this match")
    return ". ".join(parts) + "."


def run(ctx, args, listener_id):
    fx = resolve_fixture(ctx, args, listener_id, prefers="played")
    stats = feed(ctx, "match_stats", fx["fixture_id"])
    if not stats:
        raise ToolError("There are no statistics for this match yet.",
                        {"reason": "no_match", "fixture_id": fx["fixture_id"]})
    home, away = fx["home"], fx["away"]
    a, b = stats.get(home) or {}, stats.get(away) or {}
    if fx.get("sport") in (None, "football") and (a or b):
        rows = table_rows(a, b)
        warn = "These are live numbers, a moment ahead of your picture. " if fx.get("broadcast_offset") else ""
        return (warn + _football_spoken(home, away, rows, a, b, args.get("stat")),
                {"home": home, "away": away, "stats": stats, "table": rows, "generated_by": "template"},
                {"table": rows, "home": home, "away": away})
    labels = _BB_LABELS if fx.get("sport") == "basketball" else _LABELS
    parts = [_line(label, unit, home, away, a.get(key), b.get(key)) for key, label, unit in labels]
    parts = [p for p in parts if p]
    if not parts:
        raise ToolError("There are no statistics for this match yet.",
                        {"reason": "no_match", "fixture_id": fx["fixture_id"]})
    return ". ".join(parts) + ".", {"home": home, "away": away, "stats": stats, "generated_by": "template"}, None
