"""The league table, or where one team sits in it."""

import re

from .. import names, resolve
from ..mcp.errors import ToolError
from . import competition_for, feed, ordinal

TOP = 5


def _row_is(row, team):
    want, have = resolve.words(team), resolve.words(row.get("team"))
    return names.whole_words(want, have) or resolve.similarity(want, have) >= 0.82


def _standing(r):
    """What a row is ranked on, said: "20 points" for football and hockey, "4-0" for sports kept by their record."""
    if r.get("points") is not None:
        return "%s %s" % (r["points"], "point" if r["points"] == 1 else "points")
    return r.get("record") or "no record"


def _league_of(ctx, team):
    """The competition whose table has `team` in it, found from the team's own matches (a team needs no match
    followed to be asked about). Each competition it plays in is tried in turn; a cup has no table and is skipped."""
    try:
        found = ctx.provider.team_matches(team)
    except NotImplementedError:
        return None, None
    names = []
    for fx in ((found or {}).get("recent") or []) + ((found or {}).get("upcoming") or []):
        c = fx.get("competition") or ""
        if re.fullmatch(r"[a-z0-9]+(\.[a-z0-9]+)+", c):
            continue                            # an unnamed competition (a feed slug such as "eng.w.1"): never read out
        if fx.get("competition") and fx["competition"] not in names:
            names.append(fx["competition"])
    domestic = [n for n in names if not re.search(r"champions|europa|conference league|cup|qualif|nations|friendl|super|playoff", n, re.I)]
    for name in (domestic + [n for n in names if n not in domestic])[:3]:
        table = ctx.provider.standings(name)
        if table and any(_row_is(r, team) for r in table):
            return name, table
    return None, None


_THE = ("league", "cup", "championship", "bundesliga", "eredivisie", "premiership")


def _in(competition):
    """"the Premier League", "the Bundesliga", but "Ligue 1", "La Liga" and "Serie A": people say the article or not."""
    return ("the " if competition.lower().endswith(_THE) else "") + competition


_CONFERENCE = re.compile(r"^(?:the )?(?:eastern|western|atlantic|metropolitan|central|pacific|northeast|southeast|northwest|southwest|"
                         r"afc|nfc|american league|national league|al|nl)(?: conference| division| league)?(?: east| west| north| south| central)?$", re.I)


def run(ctx, args, listener_id):
    team = (args.get("team") or "").strip()
    table = None
    if team and _CONFERENCE.match((args.get("competition") or "").strip()):
        args = dict(args, competition="")             # a conference is part of a league, not a competition: the team's own league has it
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
    table = sorted(table, key=lambda r: (r.get("group") or "", r.get("position") or 999))
    where = _in(competition)
    groups = sorted({r["group"] for r in table if r.get("group")})
    if team:
        mine = next((r for r in table if _row_is(r, team)), None)
        if mine:
            table = [r for r in table if r.get("group") == mine.get("group")]      # their group, not the whole competition
            games = " from %s %s" % (mine["played"], "game" if mine["played"] == 1 else "games") if mine.get("played") else ""
            has_points = mine.get("points") is not None
            spoken = "In %s%s, %s are %s%s %s%s." % (
                where, "" if not mine.get("group") else ", %s" % mine["group"], mine["team"], ordinal(mine["position"]),
                " in the group" if mine.get("group") else "", ("with " if has_points else "at ") + _standing(mine),
                games if has_points else "")
            if mine["position"] > 1:
                lead = table[0]
                spoken += " %s lead%s %s %s." % (lead["team"], " the group" if mine.get("group") else "",
                                                 "with" if has_points else "at", _standing(lead))
            return spoken, {"competition": competition, "team": mine, "generated_by": "template"}, None
        raise ToolError("I can't see %s in %s." % (team, where),
                        {"reason": "no_match", "team": team, "competition": competition})
    if len(groups) > 1:
        # Played in groups: a single "first" would be several different teams. Name each group's leader, and say how to get one.
        leaders = [next(r for r in table if r.get("group") == g) for g in groups]
        spoken = "%s is played in %d groups. The leaders: %s. Ask about a team for its group." % (
            where[:1].upper() + where[1:], len(groups), ". ".join(
                "%s, %s, %s" % (l["group"], l["team"], _standing(l)) for l in leaders[:TOP]))
        return spoken, {"competition": competition, "groups": groups, "leaders": leaders,
                        "generated_by": "template"}, None
    top = table[:TOP]
    spoken = "%s table: %s." % (where[:1].upper() + where[1:], ". ".join(
        "%s, %s, %s" % (ordinal(r["position"]).capitalize(), r["team"], _standing(r)) for r in top))
    return spoken, {"competition": competition, "table": top, "total": len(table),
                    "generated_by": "template"}, None
