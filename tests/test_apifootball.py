"""The live provider, against canned responses in API-Football's shape.

No key, no network: urllib is patched. These pin the behaviours that
differ from the happy path, because a live match is where they matter:
a missed penalty is not a goal, a second yellow is a sending-off, and a
bad key must not look like "no such match".
"""

import io
import json
import urllib.request

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

from sideline.providers import apifootball
from sideline.providers.apifootball import ApiFootballProvider, ProviderUnavailable

CALLS = []
ROUTES = {}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=None):
    url = req.full_url
    CALLS.append((url, req.headers.get("X-apisports-key")))
    for needle, body in ROUTES.items():
        if needle in url:
            return Resp(json.dumps(body).encode())
    return Resp(json.dumps({"errors": [], "response": []}).encode())


def fixture_item(events=None, lineups=None):
    item = {"fixture": {"id": 77, "referee": "M. Oliver, England", "date": "2026-10-12T15:00:00+00:00",
                        "venue": {"name": "Emirates"}, "status": {"short": "2H", "elapsed": 70}},
            "teams": {"home": {"id": 42, "name": "Arsenal"}, "away": {"id": 47, "name": "Tottenham"}},
            "goals": {"home": 1, "away": 0}}
    if events is not None:
        item["events"] = events
    if lineups is not None:
        item["lineups"] = lineups
    return item


def ev(minute, type_, detail, player="P", team="Arsenal", extra=None, assist=None):
    return {"time": {"elapsed": minute, "extra": extra}, "team": {"name": team},
            "player": {"name": player}, "assist": {"name": assist}, "type": type_, "detail": detail}


def main():
    urllib.request.urlopen = fake_urlopen
    apifootball.urllib.request.urlopen = fake_urlopen

    p = ApiFootballProvider("secret-key", cache_seconds=0)

    # --- events: the three traps, plus the ordinary ones
    ROUTES.clear()
    ROUTES["fixtures?id=77"] = {"errors": [], "response": [fixture_item(events=[
        ev(10, "Goal", "Normal Goal", "Saka", assist="Odegaard"),
        ev(20, "Goal", "Missed Penalty", "Kane", "Tottenham"),
        ev(30, "Card", "Yellow Card", "Rice"),
        ev(55, "Card", "Second Yellow card", "Rice"),
        ev(60, "subst", "Substitution 1", "Saka", assist="Trossard"),
        ev(66, "Var", "Goal cancelled", "Kane", "Tottenham"),
        ev(90, "Goal", "Own Goal", "Romero", "Tottenham", extra=2),
    ], lineups=[])]}
    es = p.events(77)
    kinds = [(e["minute"], e["kind"], e.get("colour") or "") for e in es]
    assert kinds == [(10, "goal", ""), (30, "card", "yellow"), (55, "card", "red"),
                     (60, "substitution", ""), (66, "var", ""), (90, "goal", "")], kinds
    assert es[-1]["stoppage"] == 2
    print("ok  missed penalty is not a goal; second yellow is a red; 90+2 keeps its stoppage")

    # --- one call per poll: events came from the fixture response
    CALLS.clear()
    p.fixture(77)
    p.events(77)
    p.lineups(77)
    assert all("fixtures?id=77" in u for u, _ in CALLS), CALLS
    print("ok  fixture, events and lineups come from one request shape (quota friendly)")

    # --- falls back to the dedicated endpoints when not embedded
    ROUTES.clear()
    ROUTES["fixtures?id=77"] = {"errors": [], "response": [fixture_item()]}
    ROUTES["fixtures/events"] = {"errors": [], "response": [ev(5, "Goal", "Normal Goal", "Saka")]}
    ROUTES["fixtures/lineups"] = {"errors": [], "response": [
        {"team": {"name": "Arsenal"}, "formation": "4-3-3", "coach": {"name": "Arteta"},
         "startXI": [{"player": {"name": "Raya", "number": 22}}], "substitutes": []}]}
    assert [e["kind"] for e in p.events(77)] == ["goal"]
    lu = p.lineups(77)["Arsenal"]
    assert lu["formation"] == "4-3-3" and lu["xi"] == ["Raya"]
    print("ok  falls back to /fixtures/events and /fixtures/lineups")

    # --- key sent, errors surfaced
    assert CALLS[-1][1] == "secret-key"
    ROUTES.clear()
    ROUTES["fixtures"] = {"errors": {"token": "Error/Missing application key"}, "response": []}
    try:
        ApiFootballProvider("bad", cache_seconds=0).fixture(77)
    except ProviderUnavailable as e:
        assert "application key" in str(e)
    else:
        raise AssertionError("a bad key looked like an empty result")
    ROUTES["fixtures"] = {"errors": {"requests": "You have reached the request limit for the day"}, "response": []}
    try:
        ApiFootballProvider("k", cache_seconds=0).fixtures_today()
    except ProviderUnavailable as e:
        assert "request limit" in str(e)
    else:
        raise AssertionError("an exhausted quota looked like an empty result")
    print("ok  bad key and exhausted quota raise ProviderUnavailable, not 'no such match'")

    # --- today's fixtures: pre-kickoff games are found, no duplicates
    ROUTES.clear()
    ROUTES["fixtures?date="] = {"errors": [], "response": [fixture_item()]}
    ROUTES["fixtures?live=all"] = {"errors": [], "response": [fixture_item()]}
    fx = ApiFootballProvider("k", cache_seconds=0).fixtures_today()
    assert len(fx) == 1 and fx[0]["home"] == "Arsenal"
    print("ok  fixtures_today uses the date, merges live, no duplicates")

    print("\napifootball: all good")


if __name__ == "__main__":
    main()
