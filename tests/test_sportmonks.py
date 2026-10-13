"""The Sportmonks provider, against canned responses in the shape its documentation describes.

No token, no network: urllib is patched. These are NOT recordings of the live service: the data
is invented and the shapes follow Sportmonks' v3 documentation, so they pin our reading of it.
Whether the live service agrees is `make verify-data` with a real token (docs/DATA_PROVIDERS.md
says what has been run). Pinned here: the vendor's states become our short codes, a missed
penalty is not a goal, a second yellow is a red, the token goes in a header and never a URL,
and a refused request is an error with the vendor's own words, never "no such match".
"""

import io
import json
import urllib.error
import urllib.request

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

from sideline import providers
from sideline.providers import sportmonks
from sideline.providers.base import ProviderUnavailable
from sideline.providers.sportmonks import SportmonksProvider

CALLS = []
ROUTES = {}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None, context=None):
    CALLS.append((req.full_url, req.headers.get("Authorization")))
    for needle, body in ROUTES.items():
        if needle in req.full_url:
            if isinstance(body, urllib.error.HTTPError):
                raise body
            return Resp(json.dumps(body).encode())
    return Resp(json.dumps({"data": []}).encode())


def http_error(code, body):
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(json.dumps(body).encode()))


def side(pid, name, location):
    return {"id": pid, "name": name, "meta": {"location": location}}


def detail(state="INPLAY_2ND_HALF", **extra):
    doc = {"id": 501, "starting_at": "2026-10-13 19:00:00", "starting_at_timestamp": 1791918000,
           "state": {"developer_name": state},
           "participants": [side(1, "Invented Rovers", "home"), side(2, "Made-up United", "away")],
           "scores": [{"description": "CURRENT", "score": {"goals": 2, "participant": "home"}},
                      {"description": "CURRENT", "score": {"goals": 1, "participant": "away"}},
                      {"description": "1ST_HALF", "score": {"goals": 9, "participant": "home"}}],
           "periods": [{"minutes": 45, "ticking": False}, {"minutes": 67, "ticking": True}],
           "venue": {"name": "Invented Park", "city_name": "Inventville"},
           "league": {"id": 8, "name": "Invented Premiership", "country": {"name": "Inventland"}},
           "events": [], "lineups": [], "formations": [], "referees": []}
    doc.update(extra)
    return {"data": doc}


def ev(type_name, minute, player, other=None, pid=1, extra=0, addition=None, type_id=None):
    return {"type": {"developer_name": type_name} if type_name else None, "type_id": type_id,
            "minute": minute, "extra_minute": extra, "player_name": player,
            "related_player_name": other, "participant_id": pid, "addition": addition}


def main():
    urllib.request.urlopen = fake_urlopen
    sportmonks.urllib.request.urlopen = fake_urlopen
    p = SportmonksProvider("secret-token", cache_seconds=0)

    # --- a fixture, in our shape
    ROUTES["fixtures/501"] = detail()
    fx = p.fixture(501)
    assert (fx["home"], fx["away"], fx["fixture_id"]) == ("Invented Rovers", "Made-up United", 501)
    assert fx["score"] == {"home": 2, "away": 1}, "only the CURRENT score, not the first half's"
    assert fx["minute"] == 67 and fx["status"] == "2H", fx
    assert (fx["venue"], fx["city"], fx["competition"], fx["country"]) == (
        "Invented Park", "Inventville", "Invented Premiership", "Inventland")
    assert fx["kickoff"] == "2026-10-13T19:00:00+00:00", fx["kickoff"]
    url, auth = CALLS[-1]
    assert auth == "secret-token" and "secret-token" not in url, "the token is a header, never in a URL"
    assert "include=participants;league.country;venue;state;scores;periods;events.type" in url, url
    print("ok  a fixture: names, the current score, the ticking minute, the ground, kick-off in ISO, token in a header")

    # --- states become the short codes the rest of Sideline speaks
    for state, code in (("NOT_STARTED", "NS"), ("INPLAY_1ST_HALF", "1H"), ("HT", "HT"), ("HALF_TIME", "HT"),
                        ("INPLAY_2ND_HALF", "2H"), ("FT", "FT"), ("FINISHED", "FT"), ("AET", "AET"),
                        ("POSTPONED", "PST"), ("CANCELLED", "CANC")):
        assert sportmonks._status({"developer_name": state}) == code, (state, sportmonks._status({"developer_name": state}))
    ROUTES["fixtures/501"] = detail("HT", periods=[{"minutes": 45, "ticking": False}])
    assert p.fixture(501)["minute"] == 45, "half time is minute 45"
    ROUTES["fixtures/501"] = detail("NOT_STARTED", periods=[], scores=[])
    assert (p.fixture(501)["minute"], p.fixture(501)["status"]) == (0, "NS")
    print("ok  states become NS, 1H, HT, 2H, FT, AET, PST, CANC; half time is 45 and not started is 0")

    # --- events: the traps, plus the ordinary ones
    ROUTES["fixtures/501"] = detail(events=[
        ev("GOAL", 10, "Saka", "Odegaard"),
        ev("MISSED_PENALTY", 20, "Kane", pid=2),
        ev("YELLOWCARD", 30, "Rice", addition="Foul"),
        ev("YELLOWREDCARD", 55, "Rice"),
        ev("SUBSTITUTION", 60, "Trossard", "Saka"),
        ev("VAR", 66, "Kane", pid=2, addition="Goal cancelled"),
        ev(None, 75, "Id Only", type_id=19),
        ev("CORNER", 80, "Nobody"),
        ev("OWNGOAL", 90, "Romero", pid=2, extra=2),
    ])
    es = p.events(501)
    kinds = [(e["minute"], e["kind"], e.get("colour") or "") for e in es]
    assert kinds == [(10, "goal", ""), (30, "card", "yellow"), (55, "card", "red"), (60, "substitution", ""),
                     (66, "var", ""), (75, "card", "yellow"), (90, "goal", "")], kinds
    assert es[0]["player"] == "Saka" and es[0]["assist"] == "Odegaard" and es[0]["team"] == "Invented Rovers"
    sub_ev = [e for e in es if e["kind"] == "substitution"][0]
    assert sub_ev["player"] == "Trossard" and sub_ev["player_off"] == "Saka", "on, off"
    assert es[-1]["stoppage"] == 2 and es[-1]["detail"] == "own goal"
    assert p.events(501, since_minute=60)[0]["minute"] == 66
    print("ok  events: a missed penalty is not a goal, a second yellow is a red, subs and VAR, a type id when there is no name")

    # --- line-ups and officials
    ROUTES["fixtures/501"] = detail(
        formations=[{"participant_id": 1, "formation": "4-3-3"}, {"participant_id": 2, "formation": "4-4-2"}],
        lineups=[{"team_id": 1, "type_id": 11, "player_name": "Keeper One", "jersey_number": 1},
                 {"team_id": 1, "type_id": 12, "player_name": "Bench One", "jersey_number": 12},
                 {"team_id": 2, "type_id": 11, "player_name": "Keeper Two", "jersey_number": 13}],
        referees=[{"referee": {"display_name": "Ref Invented"}}])
    lu = p.lineups(501)
    assert lu["Invented Rovers"] == {"formation": "4-3-3", "xi": ["Keeper One"], "numbers": {"Keeper One": 1},
                                      "bench": ["Bench One"], "coach": None}, lu
    assert lu["Made-up United"]["formation"] == "4-4-2"
    assert p.officials(501) == {"referee": "Ref Invented", "venue": "Invented Park"}
    ROUTES["fixtures/501"] = detail()
    assert p.lineups(501) == {}, "no line-ups yet: nothing, not empty teams"
    print("ok  line-ups carry formation, eleven, numbers and bench; officials give the referee; none yet is empty")

    # --- a day's list, cached for the plan's sake
    ROUTES.clear()
    ROUTES["fixtures/date/"] = {"data": [detail("NOT_STARTED", periods=[], scores=[])["data"]]}
    day = p.fixtures_on(0)
    assert [f["home"] for f in day] == ["Invented Rovers"] and p.fixtures_today()[0]["fixture_id"] == 501
    print("ok  a day's list is one request")

    # --- the optional reads (invented data, the documented shape)
    ROUTES.clear()
    ROUTES["leagues"] = {"data": [{"id": 501, "name": "Invented Premiership", "country": {"name": "Inventland"},
                                   "currentseason": {"id": 9001}}]}
    ROUTES["standings/seasons/9001"] = {"data": [{"position": 1, "points": 20, "participant": {"name": "Invented Rovers"}},
                                                  {"position": 2, "points": 18, "participant": {"name": "Made-up United"}}]}
    ROUTES["topscorers/seasons/9001"] = {"data": [{"total": 7, "player": {"display_name": "A. Scorer"},
                                                    "participant": {"name": "Invented Rovers"}}]}
    ROUTES["teams/search/"] = {"data": [{"id": 1, "name": "Invented Rovers"}]}
    sm = SportmonksProvider("t", cache_seconds=0)
    assert [c["name"] for c in sm.competitions("Inventland")] == ["Invented Premiership"] and sm.competitions("Nowhere") == []
    assert sm.standings("invented premiership") == [
        {"position": 1, "team": "Invented Rovers", "played": None, "points": 20},
        {"position": 2, "team": "Made-up United", "played": None, "points": 18}]
    assert sm.top_scorers("Invented Premiership") == [{"player": "A. Scorer", "team": "Invented Rovers", "goals": 7}]
    assert sm.standings("No Such League") is None
    assert sm.search("Rovers")[0]["name"] == "Invented Rovers"
    ROUTES.clear()
    ROUTES["fixtures/501"] = detail(statistics=[
        {"participant_id": 1, "type": {"developer_name": "BALL_POSSESSION"}, "data": {"value": 62}},
        {"participant_id": 2, "type": {"developer_name": "BALL_POSSESSION"}, "data": {"value": 38}},
        {"participant_id": 1, "type": {"developer_name": "SHOTS_ON_TARGET"}, "data": {"value": 6}},
        {"participant_id": 1, "type": {"developer_name": "SOMETHING_ELSE"}, "data": {"value": 1}}])
    assert sm.match_stats(501) == {"Invented Rovers": {"possession": 62, "shots_on_target": 6},
                                   "Made-up United": {"possession": 38}}
    assert {"standings", "injuries", "form", "player_stats"} <= sm.capabilities
    from sideline.mcp import registry
    try:
        registry.limit_to(SportmonksProvider.capabilities)
        assert len(registry.public_tools()) == 24, "this feed supplies what every tool needs"
    finally:
        registry.limit_to(None)
    print("ok  competitions, tables, scorers, search and stats read in the documented shape (24 tools listed)")

    # --- injuries, form and a player's season (the shapes seen on a real match; the values invented)
    ROUTES.clear()
    ROUTES["fixtures/501"] = detail(sidelined=[
        {"participant_id": 1, "sideline": {"completed": False, "end_date": None,
                                           "player": {"display_name": "Long Term"}, "type": {"name": "Knee Surgery"}}},
        {"participant_id": 2, "sideline": {"completed": False, "end_date": "2099-12-31",
                                           "player": {"display_name": "Back Soon"}, "type": {"name": "Ankle Surgery"}}},
        {"participant_id": 1, "sideline": {"completed": True, "end_date": None,
                                           "player": {"display_name": "Recovered"}, "type": {"name": "Knock"}}},
        {"participant_id": 1, "sideline": {"completed": False, "end_date": "2000-01-01",
                                           "player": {"display_name": "Long Gone"}, "type": {"name": "Knock"}}}])
    assert sm.injuries(501) == [{"player": "Long Term", "team": "Invented Rovers", "reason": "Knee Surgery"},
                                {"player": "Back Soon", "team": "Made-up United", "reason": "Ankle Surgery"}], \
        "ended and completed absences are dropped"

    def played(i, start, home, away, home_id=1, away_id=2, state="FT"):
        d = detail(state)["data"]
        d.update(id=i, starting_at=start, starting_at_timestamp=None,
                 participants=[side(home_id, "Invented Rovers" if home_id == 1 else "Made-up United", "home"),
                               side(away_id, "Made-up United" if away_id == 2 else "Invented Rovers", "away")],
                 scores=[{"description": "CURRENT", "score": {"goals": home, "participant": "home"}},
                         {"description": "CURRENT", "score": {"goals": away, "participant": "away"}}])
        return d
    ROUTES.clear()
    ROUTES["fixtures/501"] = detail()
    ROUTES["fixtures/between/2026-07-15/2026-10-13/1"] = {"data": [
        played(11, "2026-09-01 15:00:00", 2, 0), played(12, "2026-09-08 15:00:00", 1, 1),
        played(13, "2026-09-15 15:00:00", 0, 3, home_id=2, away_id=1),     # Rovers away, won
        played(14, "2026-09-22 15:00:00", 0, 1), played(15, "2026-09-29 15:00:00", 1, 0, state="NOT_STARTED"),
        played(16, "2026-10-05 15:00:00", 3, 0), played(17, "2026-10-13 21:00:00", 5, 0),     # after kick-off
        played(501, "2026-10-13 19:00:00", 2, 1)]}
    ROUTES["fixtures/between/2026-07-15/2026-10-13/2"] = {"data": []}
    form = sm.form(501)
    assert form == {"home": "WDWLW", "away": ""}, form
    ROUTES["fixtures/501"] = detail(participants=[side(1, "Invented Rovers", "home"), side(2, "Made-up United", "away")])
    ROUTES.pop("fixtures/between/2026-07-15/2026-10-13/1")
    ROUTES["fixtures/between/"] = {"data": []}
    assert SportmonksProvider("t", cache_seconds=0).form(501) is None, "no past results at all: none, not empty strings"
    ROUTES.clear()
    ROUTES["players/search/"] = {"data": [{"id": 7, "display_name": "Julien Serrano"}, {"id": 8, "display_name": "Janni Serra"}]}
    ROUTES["players/8"] = {"data": {"statistics": [
        {"season_id": 100, "details": [{"type": {"developer_name": "GOALS"}, "value": {"total": 9}}]},
        {"season_id": 300, "details": [{"type": {"developer_name": "GOALS"}, "value": {"total": 4}},
                                       {"type": {"developer_name": "APPEARANCES"}, "value": {"total": 8}}]},
        {"season_id": 200, "details": []}]}}
    ps = sm.player_stats("Janni Serra")
    assert ps == {"name": "Janni Serra", "team": None, "goals": 4, "assists": None, "appearances": 8}, ps
    assert sm.player_stats("Serra")["name"] == "Janni Serra", "the closer name, of two matches"
    ROUTES["players/search/"] = {"data": [{"id": 9, "display_name": "Totally Different"}]}
    assert SportmonksProvider("t", cache_seconds=0).player_stats("Janni Serra") is None, "a poor match is not a guess"
    print("ok  injuries (ended ones dropped), form (last five finished before kick-off, oldest first) and a player's latest season")

    # --- refusals are errors with the vendor's own words
    for code, body, needle in ((429, {"message": "Rate limit of 180 requests per hour exceeded.", "retry_after": 1800}, "rateLimit"),
                               (401, {"message": "Invalid token"}, "token"),
                               (403, {"message": "No access"}, "token")):
        ROUTES.clear()
        ROUTES["fixtures/"] = http_error(code, body)
        try:
            SportmonksProvider("t", cache_seconds=0).fixture(501)
        except ProviderUnavailable as e:
            assert needle in str(e) and body["message"] in str(e), str(e)
            if code == 429:
                assert "30 minutes" in str(e), "when it resets, in words"
        else:
            raise AssertionError("a refused request looked like an empty result")
    print("ok  429, 401 and 403 raise ProviderUnavailable carrying Sportmonks' own message and the wait")

    assert isinstance(providers.build("t"), SportmonksProvider)
    print("\nsportmonks: all good")


if __name__ == "__main__":
    main()
