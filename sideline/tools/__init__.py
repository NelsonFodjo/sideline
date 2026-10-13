"""Tool implementations.

Every tool is a function with the same signature:

    run(ctx, args, listener_id) -> (spoken_text, structured, ui_payload)

`spoken_text` is what Alexa+ will read (it may rephrase). `structured`
is machine-readable detail, which is where a judge or a developer can
see exactly what the server knew. `ui_payload` is the MCP Apps card for
screened devices, or None.

Rule applied throughout: nothing essential may live only in the UI
payload. A listener on a voice-only Echo must get the whole answer in
`spoken_text`. See docs/ACCESSIBILITY.md - this is an accessibility
product and a screen-only fact is a bug, not a feature.
"""

import datetime

from .. import clock
# The tool modules import the helpers below, so they are imported last (see the end of this file).

# What listeners call teams, when it is not the feed's name. Short on purpose: a nickname that
# is not here still finds its team by spelling and sound.
NICKNAMES = {"spurs": "tottenham", "gunners": "arsenal", "man u": "manchester united",
             "man utd": "manchester united", "man city": "manchester city", "city": "manchester city",
             "copenhagen": "kobenhavn", "fck": "kobenhavn", "gers": "rangers", "the hoops": "celtic"}


def _words(text):
    """Lowercase, accent-free word tokens: "Sønderjyske" is "sonderjyske", as it is said."""
    from .. import resolve
    return resolve.words(text)


def _is_team(fx_side, name):
    """Does this side of a fixture mean the team the listener named?

    Whole-name containment first ("Arsenal" is in "Arsenal W", which is why more than
    one hit is asked about, not guessed), then a close spelling or sound, so a name that
    came through a little off ("Asenal") still finds the team.
    """
    from .. import resolve
    want, side = _words(NICKNAMES.get(" ".join(_words(name)), name)), _words(fx_side)
    if not want or not side:
        return False
    if " ".join(want) in " ".join(side):
        return True
    return resolve.similarity(want, side) >= 0.82


def day_fixtures(ctx, offset, tz=None):
    """The fixtures on the listener's own day (today 0, tomorrow 1, yesterday -1).

    The feed lists a UTC day, and the listener's day is not: at +4 a 01:00 kick-off belongs to
    the previous UTC date. So the UTC dates the local day touches are read (each kept for minutes,
    so this costs the hourly limit little) and only matches inside the local day are kept. With
    no zone known the UTC day is used, as before.
    """
    if tz is None:
        return ctx.provider.fixtures_on(offset)
    now = clock.now()
    local = (now + datetime.timedelta(minutes=int(tz))).date() + datetime.timedelta(days=offset)
    start = datetime.datetime(local.year, local.month, local.day, tzinfo=clock.UTC) - datetime.timedelta(minutes=int(tz))
    end = start + datetime.timedelta(days=1)
    out, seen = [], set()
    for utc_day in sorted({start.date(), (end - datetime.timedelta(seconds=1)).date()}):
        for fx in ctx.provider.fixtures_on((utc_day - now.date()).days):
            ko = clock.kickoff(fx)
            if fx.get("fixture_id") in seen or (ko is not None and not start <= ko < end):
                continue
            seen.add(fx.get("fixture_id"))
            out.append(fx)
    return out


def find_matches(ctx, team, opponent=None, offsets=(0, 1, -1), tz=None):
    """Fixtures for `team` (against `opponent`, if named): today first, then tomorrow, then yesterday.

    Stops at the first day with any. Whatever the feed cannot see (a free plan sees only
    yesterday to tomorrow) is simply not found, and said so by the caller.
    """
    for offset in offsets:
        hits = []
        for fx in day_fixtures(ctx, offset, tz):
            home, away = fx.get("home"), fx.get("away")
            if _is_team(home, team) and (not opponent or _is_team(away, opponent)):
                hits.append(fx)
            elif _is_team(away, team) and (not opponent or _is_team(home, opponent)):
                hits.append(fx)
        if hits:
            # "Arsenal" means Arsenal, not Arsenal W or Arsenal U19, when the first is on:
            # a name that is exactly a side beats one that merely contains it.
            exact = [f for f in hits
                     if _words(team) in (_words(f.get("home")), _words(f.get("away")))
                     and (not opponent or _words(opponent) in (_words(f.get("home")), _words(f.get("away"))))]
            return exact or hits
    return []


def suggestions(ctx, team, limit=3, tz=None):
    """Today's fixtures whose teams sound like what was heard ("asana" for Arsenal), best first.

    A voice recogniser turns a team into another word. A listener who cannot see a screen
    has no way to spot that, so the answer to an unknown name is an offer, not a refusal.
    """
    from .. import resolve
    want = _words(team)
    if not want:
        return []
    scored = []
    for fx in day_fixtures(ctx, 0, tz):
        best = max(resolve.similarity(want, _words(fx.get(side))) for side in ("home", "away"))
        if best >= 0.6:
            scored.append((best, fx))
    scored.sort(key=lambda p: -p[0])
    return [fx for _, fx in scored[:limit]]


def not_found(ctx, team, opponent=None, tz=None):
    """The honest sentence for a match the feed cannot show, or an offer when it sounds like one."""
    from ..mcp.errors import ToolError
    if opponent:
        mine = find_matches(ctx, team, tz=tz)
        if mine:       # the team is on, but not against that opponent: say what is on
            seen = " or ".join(clock.say_fixture(m, tz) for m in mine[:3])
            return ToolError("I can't find %s against %s, but I can see %s." % (team, opponent, seen),
                             {"reason": "no_match", "team": team, "opponent": opponent})
    close = suggestions(ctx, team, tz=tz)
    if close:
        names = ", or ".join(clock.say_fixture(m, tz) for m in close)
        return ToolError("I couldn't find %s. Did you mean %s?" % (team, names),
                         {"reason": "ambiguous", "candidates": close})
    what = "%s against %s" % (team, opponent) if team and opponent else ("a match for %s" % team if team else "that match")
    return ToolError("I can't find %s yesterday, today or tomorrow." % what,
                     {"reason": "no_match", "team": team, "opponent": opponent})


def feed(ctx, method, *args, **kwargs):
    """Call an optional read on the feed; a feed without it says so, in words."""
    from ..mcp.errors import ToolError
    try:
        return getattr(ctx.provider, method)(*args, **kwargs)
    except NotImplementedError:
        raise ToolError("The feed I'm connected to doesn't provide that.", {"reason": "not_supported"})


_ORDINALS = ("zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
             "ninth", "tenth")


def ordinal(n):
    """1 -> "first", 11 -> "11th": said, not read as a digit."""
    n = int(n)
    if 0 <= n < len(_ORDINALS):
        return _ORDINALS[n]
    return "%d%s" % (n, "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def competition_for(ctx, args, listener_id):
    """The competition the listener means: the one they named, else that of the match they follow."""
    from ..mcp.errors import ToolError
    name = (args.get("competition") or "").strip()
    if name:
        return name
    fid = ctx.store.listener(listener_id).get("following")
    fx = (ctx.store.fixture(fid) or {}) if fid else {}
    if fx.get("competition"):
        return fx["competition"]
    raise ToolError("Which competition? Tell me one, like the Premier League, or follow a match first.",
                    {"reason": "no_competition"})


def resolve_fixture(ctx, args, listener_id):
    """Fixture the listener means.

    Order: explicit argument, then whatever they are following. If
    neither, that is a ToolError with a spoken line Alexa+ can read -
    not an exception. "Which match?" is a reasonable thing to be asked.
    """
    from ..mcp.errors import ToolError
    fid = args.get("fixture_id")
    tz = clock.zone_from(ctx.store.listener(listener_id))
    if not fid and args.get("team"):
        # "When is Arsenal against Lille?" names a match without following it.
        hits = find_matches(ctx, args["team"], args.get("opponent"), tz=tz)
        if not hits:
            raise not_found(ctx, args["team"], args.get("opponent"), tz)
        if len(hits) > 1:
            raise ToolError(
                "I can see more than one %s match. Which one - %s?" % (
                    args["team"], ", or ".join(clock.say_fixture(m, tz) for m in hits[:3])),
                {"reason": "ambiguous", "candidates": hits[:3]})
        fid = hits[0]["fixture_id"]
    if not fid:
        fid = ctx.store.listener(listener_id).get("following")
    if not fid:
        raise ToolError(
            "I'm not following a match yet. Tell me which game to follow.",
            {"reason": "no_fixture"})
    fx = ctx.provider.fixture(fid)
    if not fx:
        raise ToolError("I can't find that match any more.",
                        {"reason": "fixture_not_found", "fixture_id": fid})

    # Apply the broadcast offset HERE, in one place, rather than asking
    # eight tools each to remember to subtract it. Every tool downstream
    # sees the match as the listener's screen is showing it, and none of
    # them needs to know this happened. See sync_broadcast_delay.py.
    rec = ctx.store.listener(listener_id)
    if rec.get("tz_offset_minutes") is not None:
        fx = dict(fx, tz_offset_minutes=clock.zone_from(rec))        # for times said aloud
    offset = rec.get("broadcast_offset") or 0
    if offset:
        fx = dict(fx)
        fx["real_minute"] = fx.get("minute") or 0
        fx["minute"] = max(0, (fx.get("minute") or 0) - offset // 60)
        fx["broadcast_offset"] = offset
        fx["score"] = ctx.store.score_at(fid, fx["minute"]) or fx["score"]
    return fx


from . import (follow_match, get_capabilities, get_competitions, get_event_detail, get_fixtures,
               get_head_to_head, get_injuries, get_lineups, get_match_preview, get_match_stats,
               get_my_matches, get_player_stats, get_schedule, get_standings, get_team_form,
               get_top_scorers, search, set_favourites, set_preferences, get_match_state, get_officials, get_player_context,
               sync_broadcast_delay, what_did_i_miss)

REGISTRY = {
    "follow_match": follow_match.run,
    "get_match_state": get_match_state.run,
    "get_fixtures": get_fixtures.run,
    "search": search.run,
    "get_competitions": get_competitions.run,
    "get_standings": get_standings.run,
    "get_top_scorers": get_top_scorers.run,
    "get_schedule": get_schedule.run,
    "get_match_stats": get_match_stats.run,
    "get_player_stats": get_player_stats.run,
    "get_injuries": get_injuries.run,
    "get_team_form": get_team_form.run,
    "set_favourites": set_favourites.run,
    "get_my_matches": get_my_matches.run,
    "set_preferences": set_preferences.run,
    "get_capabilities": get_capabilities.run,
    "get_match_preview": get_match_preview.run,
    "get_lineups": get_lineups.run,
    "what_did_i_miss": what_did_i_miss.run,
    "get_event_detail": get_event_detail.run,
    "get_officials": get_officials.run,
    "get_player_context": get_player_context.run,
    "get_head_to_head": get_head_to_head.run,
    "sync_broadcast_delay": sync_broadcast_delay.run,
}
