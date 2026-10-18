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
import time

from .. import clock, names, resolve
from ..state.store import backdate
from ..status import FINISHED, has_started, is_live
# The tool modules import the helpers below, so they are imported last (see the end of this file).

# What listeners call teams, when it is not the feed's name. Short on purpose: a nickname that
# is not here still finds its team by spelling and sound.
NICKNAMES = {"spurs": "tottenham", "gunners": "arsenal", "man u": "manchester united",
             "man utd": "manchester united", "man city": "manchester city", "city": "manchester city",
             "copenhagen": "kobenhavn", "fck": "kobenhavn", "gers": "rangers", "the hoops": "celtic",
             "psg": "paris saint germain", "paris sg": "paris saint germain"}


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
    if names.whole_words(want, side):                  # whole words: "Villa" is not Villarreal, "Arsenal" is "Arsenal W"
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
    utc_days = sorted({start.date(), (end - datetime.timedelta(seconds=1)).date()})
    if len(utc_days) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            fetched_lists = list(pool.map(lambda d: ctx.provider.fixtures_on((d - now.date()).days), utc_days))
        for fl in fetched_lists:
            for fx in fl:
                ko = clock.kickoff(fx)
                if fx.get("fixture_id") in seen or (ko is not None and not start <= ko < end):
                    continue
                seen.add(fx.get("fixture_id"))
                out.append(fx)
    else:
        for fx in ctx.provider.fixtures_on((utc_days[0] - now.date()).days):
            ko = clock.kickoff(fx)
            if fx.get("fixture_id") in seen or (ko is not None and not start <= ko < end):
                continue
            seen.add(fx.get("fixture_id"))
            out.append(fx)
    return out


def matches_from_schedule(ctx, team, opponent=None, offsets=(0, 1, -1), tz=None):
    """The same answer as find_matches (today first, then tomorrow, then yesterday), from the team's own schedule: a
    few requests instead of a scoreboard per sport per day. None means the feed cannot say (it has no schedules, or
    does not know the team) and the caller should scan; an empty list means the team has nothing within those days."""
    try:
        data = ctx.provider.team_matches(team)
    except NotImplementedError:
        return None
    if not data:
        return None
    pool = data["recent"] + data["upcoming"]
    if opponent:
        pool = [fx for fx in pool if _is_team(fx.get("home"), opponent) or _is_team(fx.get("away"), opponent)]
    shift = datetime.timedelta(minutes=int(tz or 0))
    today = (clock.now() + shift).date()
    by_day = {}
    for fx in pool:
        ko = clock.kickoff(fx)
        if ko is not None:
            by_day.setdefault(((ko + shift).date() - today).days, []).append(fx)
    live = [fx for fx in pool if is_live(fx)]
    for off in offsets:
        hits = list(by_day.get(off, []))
        if off == 0:                                   # a match that began last night and is still going is today's
            hits += [fx for fx in live if fx not in hits]
        if hits:
            return hits
    return []


def find_matches(ctx, team, opponent=None, offsets=(0, 1, -1), tz=None):
    """Fixtures for `team` (against `opponent`, if named): today first, then tomorrow, then yesterday.

    Stops at the first day with any. Whatever the feed cannot see (a free plan sees only
    yesterday to tomorrow) is simply not found, and said so by the caller.
    """
    if len(offsets) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(offsets)) as pool:
            all_day_fixtures = list(pool.map(lambda off: (off, day_fixtures(ctx, off, tz)), offsets))
    else:
        all_day_fixtures = [(offsets[0], day_fixtures(ctx, offsets[0], tz))] if offsets else []

    for offset, fixtures in all_day_fixtures:
        hits = []
        for fx in fixtures:
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
        names = ", or ".join(clock.say_fixture(m, tz) if m.get("away") else m.get("home") for m in close)
        return ToolError("I couldn't find %s. Did you mean %s?" % (team, names),
                         {"reason": "ambiguous", "candidates": close})
    what = "%s against %s" % (team, opponent) if team and opponent else ("a match for %s" % team if team else "that match")
    return ToolError("I can't find %s yesterday, today or tomorrow." % what,
                     {"reason": "no_match", "team": team, "opponent": opponent})


def covered_leagues(ctx):
    """The competitions the feed covers, as "Name (Country)", or [] when it cannot say."""
    leagues = []
    try:
        for c in ctx.provider.competitions() or []:
            if c.get("name") and c["name"] not in leagues and "play-off" not in c["name"].lower():
                leagues.append(c["name"] if not c.get("country") else "%s (%s)" % (c["name"], c["country"]))
    except Exception:                                      # noqa: BLE001  a courtesy: the plain question is enough
        return []
    return leagues


def say_list(items):
    """"a", "a and b", "a, b and c"."""
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else (items[0] if items else "")


def _closest_team(ctx, team):
    """The covered team a misheard name sounds most like ("Selltic" -> Celtic), when the sound is close enough; else None."""
    from .. import resolve
    try:
        names = ctx.provider.known_teams()
    except Exception:                                      # noqa: BLE001  a courtesy: the plain answer is enough
        return None
    want = resolve.words(team)
    best = max(((resolve.similarity(want, resolve.words(n)), n) for n in names), default=(0, None))
    return best[1] if best[0] >= 0.7 else None


def no_team(ctx, team):
    """The question to ask when a team is not found, saying what is covered when the feed can say.

    A name the feed does not know is often a real team outside the leagues the plan covers (Arsenal, on a plan of the
    Danish and Scottish leagues), and "I can't find a team called Arsenal" is then misleading: it is not that it does
    not exist, it is that it is not covered.
    """
    from ..mcp.errors import ToolError
    close = _closest_team(ctx, team)
    if close:
        return ToolError("I can't find %s. Did you mean %s?" % (team, close),
                         {"reason": "no_match", "team": team, "did_you_mean": close})
    leagues = covered_leagues(ctx)
    if len(leagues) > 6:                  # twenty league names read aloud help nobody: ask for the full name instead
        return ToolError("I can't find %s. Try the full name, or tell me which league they play in." % team,
                         {"reason": "no_match", "team": team, "covered": leagues})
    if leagues:
        return ToolError("I can't find %s in the leagues I cover: %s. Which team do you mean?" % (team, say_list(leagues)),
                         {"reason": "no_match", "team": team, "covered": leagues})
    return ToolError("I can't find a team called %s. Which team do you mean?" % team, {"reason": "no_match", "team": team})


def feed(ctx, method, *args, **kwargs):
    """Call an optional read on the feed; a feed without it says so, in words."""
    from ..mcp.errors import ToolError
    try:
        return getattr(ctx.provider, method)(*args, **kwargs)
    except NotImplementedError:
        raise ToolError("The feed I'm connected to doesn't provide that.", {"reason": "not_supported"})


_ORDINALS = ("zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
             "ninth", "tenth")


def possessive(name):
    """"Celtic's", but "Rangers'": a name ending in s takes the apostrophe alone."""
    return name + ("'" if name.endswith(("s", "S")) else "'s")


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
    covered = covered_leagues(ctx)
    raise ToolError("Which competition? %s" % ("I cover %s." % say_list(covered) if covered
                                               else "Tell me one, or follow a match first."),
                    {"reason": "no_competition", "covered": covered})


from ..finder import DISCUSSED_SECONDS       # a follow-up that names no match means the one they asked about in the last ten minutes (finder.py)


def events_for(ctx, fx):
    """The match's events in minute order. A match that was not followed has none logged here, so a played or
    running match is read from the feed once and kept: any match that has been played can be asked about, not only
    the one the poller was watching."""
    fid = fx["fixture_id"]
    logged = ctx.store.events(fid)
    if not logged and has_started(fx):
        try:
            ctx.store.append_events([backdate(e, fx.get("real_minute") or fx.get("minute"))
                                     for e in ctx.provider.events(fid, since_minute=0)])
        except NotImplementedError:
            pass
        logged = ctx.store.events(fid)
    if fx.get("broadcast_offset"):
        logged = ctx.store.on_screen(fid, fx["broadcast_offset"])[0]       # what has reached their screen, by the clock
    return logged


def resolve_fixture(ctx, args, listener_id, prefers=None, followed_first=False):
    """The match the listener means (see sideline/finder.py for how).

    A fixture id they were given; else the team, opponent, day or date they named, across the matches the feed can
    see (a match already played counts, as does one still to come); else the match they are following. Several
    plausible matches are not guessed between: that is a ToolError listing them, so they can pick. `prefers` says
    what the question is about, "played" (who scored) or "coming" (who is playing), which breaks ties.
    `followed_first`: with nothing named, the match they follow comes before the one they merely asked about - for
    "what did I miss" and the delay, which are about their own game, not a passing question about another.
    """
    from .. import finder
    from ..mcp.errors import ToolError
    rec = ctx.store.listener(listener_id)
    tz = clock.zone_from(rec)
    ref = finder.Reference(args, prefers)
    fid = ref.fixture_id
    explicit = bool(ref.team or ref.opponent or ref.when or ref.date)

    discussed = False
    if fid:
        fx = ctx.provider.fixture(fid)
        if not fx:
            raise ToolError("I can't find that match any more.", {"reason": "fixture_not_found", "fixture_id": fid})
        discussed = True
    elif explicit:
        fx = finder.resolve_match(ctx, ref, rec, tz)
        discussed = True
    else:
        # Nothing named: the match they were just asking about ("who came on?" after "what happened in the Celtic game?")
        # comes first, then the one they are following. A match is never picked that they did not ask about.
        recent = rec.get("discussed") or {}
        fid = recent.get("fixture_id") if time.time() - (recent.get("at") or 0) <= DISCUSSED_SECONDS else None
        if followed_first and rec.get("following"):
            fid = None
        fx = ctx.provider.fixture(fid) if fid else None
        if fx:
            fx = dict(fx, found_by="discussed")
        if not fx:
            fid = rec.get("following")
            fx = ctx.provider.fixture(fid) if fid else None
        if fid and not fx:
            # The match being followed is one the feed does not know (an id from before, or one it has dropped):
            # forget it, so that every match question does not fail for ever, and say what is true.
            rec["following"], rec["last_told_at"], rec["told_event_ids"] = None, None, []
            ctx.store.save_listener(rec)
            raise ToolError("I'm not following a match right now. Tell me which game to follow, or ask me about a team.",
                            {"reason": "no_fixture", "forgot": fid})
        if not fx:
            # Nothing followed and nothing named. A match is never picked for the listener: they were not asked.
            raise ToolError("I'm not following a match yet. Tell me which game to follow, or name a team.",
                            {"reason": "no_fixture"})

    if discussed and (rec.get("discussed") or {}).get("fixture_id") != fx["fixture_id"]:
        rec["discussed"] = {"fixture_id": fx["fixture_id"], "at": time.time()}
        ctx.store.save_listener(rec)
    elif discussed:
        rec["discussed"]["at"] = time.time()

    # Times are said in the listener's own clock.
    if rec.get("tz_offset_minutes") is not None:
        fx = dict(fx, tz_offset_minutes=clock.zone_from(rec))

    # The broadcast delay applies in ONE place: to the match being followed while it is in play. Every tool downstream
    # sees the match as the listener's screen shows it. A match already played, or one they are not watching, has no delay.
    offset = rec.get("broadcast_offset") or 0
    if offset and rec.get("following") == fx["fixture_id"] and is_live(fx):
        fx = dict(fx)
        real = fx.get("minute") or 0
        shown, floor = ctx.store.on_screen(fx["fixture_id"], offset)
        # Their minute is the feed's minus the delay (rounded up: the feed's minute is whole), or the latest event they
        # have seen if that is later; never as far as an event that has not reached them.
        minute = max([real - clock.delay_minutes(offset)] + [e["minute"] for e in shown if e["minute"] <= real])
        if floor is not None:
            minute = min(minute, floor - 1)
        fx["real_minute"] = real
        fx["minute"] = max(0, minute)
        fx["broadcast_offset"] = offset
        if floor is not None or shown:       # events are logged: what their screen has shown, not the feed's latest
            fx["score"], fx["score_unconfirmed"] = _shown_score(ctx, fx, shown)
    return fx


def match_info(fx):
    """What, where and when a match is: the sport, the competition, the ground and its city, and the kick-off (UTC, ISO). For a screen to show."""
    from .. import sports
    return {"sport": sports.for_fixture(fx).key, "competition": fx.get("competition"), "venue": fx.get("venue"),
            "city": fx.get("city"), "kickoff": fx.get("kickoff")}


def _side(team, fx):
    """"home", "away", or None for a team name in an event."""
    if not team:
        return None
    for side in ("home", "away"):
        if team == fx.get(side):
            return side
    want = resolve.words(team)
    for side in ("home", "away"):
        have = resolve.words(fx.get(side))
        if want and have and (names.whole_words(want, have) or names.whole_words(have, want)):
            return side
    return None


def _shown_score(ctx, fx, shown):
    """The score the listener's screen has reached: the feed's own score, less the goals still held back.

    It was once rebuilt by counting goal events, and the event list is the least reliable part of the feed: a lower
    league can list few of its goals, and a team name can fail to match. A goal credited to the wrong side told a listener
    that the team that was behind had scored. The feed's score is the authority; only the few held-back goals are
    taken off it, and if one of those cannot be placed on a side, or the result would be below nothing, the feed's score
    stands and is flagged as unconfirmed rather than guessed.
    """
    from .. import sports
    sport = sports.for_fixture(fx)
    feed = dict(fx.get("score") or {"home": 0, "away": 0})
    shown_ids = {e["id"] for e in shown}
    held = {"home": 0, "away": 0}
    for e in ctx.store.events(fx["fixture_id"]):
        if e["id"] in shown_ids:
            continue
        delta = sport.score_delta(e)
        if not delta:
            continue
        side = _side(e.get("team"), fx)
        if side is None:
            return feed, True
        held[side] += delta
    out = {"home": (feed.get("home") or 0) - held["home"], "away": (feed.get("away") or 0) - held["away"]}
    if out["home"] < 0 or out["away"] < 0:
        return feed, True
    return out, False


from . import (follow_match, get_capabilities, get_competitions, get_event_detail, get_fixtures,
               get_head_to_head, get_injuries, get_lineups, get_match_preview, get_match_report, get_match_stats,
               get_my_matches, get_news, get_standouts, get_player_profile, get_player_stats, get_schedule, get_squad, get_standings, get_team_form, get_team_stats,
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
    "get_player_profile": get_player_profile.run,
    "get_news": get_news.run,
    "get_standouts": get_standouts.run,
    "get_injuries": get_injuries.run,
    "get_team_form": get_team_form.run,
    "get_squad": get_squad.run,
    "get_team_stats": get_team_stats.run,
    "set_favourites": set_favourites.run,
    "get_my_matches": get_my_matches.run,
    "set_preferences": set_preferences.run,
    "get_capabilities": get_capabilities.run,
    "get_match_preview": get_match_preview.run,
    "get_match_report": get_match_report.run,
    "get_lineups": get_lineups.run,
    "what_did_i_miss": what_did_i_miss.run,
    "get_event_detail": get_event_detail.run,
    "get_officials": get_officials.run,
    "get_player_context": get_player_context.run,
    "get_head_to_head": get_head_to_head.run,
    "sync_broadcast_delay": sync_broadcast_delay.run,
}
