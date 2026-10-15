"""Anything that changes while a match is on is read live; nothing is served from an old copy.

Offline: the provider's network call is replaced, so the test counts calls and times nothing.
"""

import datetime
import time

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

from sideline.providers.espn import EspnProvider
from sideline.state.store import MemoryStore, Event, event_key


def main():
    p = EspnProvider()
    # what changes during a match is kept for seconds, what cannot change for hours
    assert p._ttl_for("https://x/scoreboard?dates=1") <= 5 and p.LIVE_SUMMARY_TTL <= 5 and p._ttl_for("https://x/schedule") <= 30
    assert p._ttl_for("https://x/standings") <= 60 and p.FIXTURES_SECONDS <= 10
    assert p._ttl_for("https://x/leagues/dropdown?sport=soccer") >= 3600 and p.FINISHED_SUMMARY_TTL >= 3600
    print("ok  live pages are kept for seconds; only league names and finished matches are kept for hours")

    day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    p._fixtures_cache = {(0, None, day): (time.time() - 30, ["a list 30 seconds old"])}
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("fetched")
    p._all_soccer = boom
    p.basketball_leagues = p.football_leagues = p.baseball_leagues = p.hockey_leagues = []
    try:
        out = p.fixtures_on(0)
        assert out != ["a list 30 seconds old"], "an old list is never served"
    except Exception:
        pass
    assert calls, "a list older than ten seconds is read again, first"
    print("ok  a day's list older than ten seconds is fetched again before answering")

    # when the feed is down, an old copy of a LIVE page is never served; one that cannot have changed still is
    live = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates=20261015&limit=500"
    finished = "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/summary?event=1"
    p.cache.set(live, {"events": ["old score"]}, 300)
    p.cache.set(finished, {"header": {"competitions": [{"status": {"type": {"completed": True, "state": "post"}}}]}}, 300)
    p.cache._clock = lambda: time.monotonic() + 1000                     # both copies are long past their expiry
    p._http_get = lambda url: (_ for _ in ()).throw(RuntimeError("down"))
    assert p._fetch_json(live) == {}, "a live scoreboard is not answered from an old copy"
    print("ok  with the feed down a live scoreboard is not answered from an old copy")

    # warm() asks for the league names and today's matches together and never raises
    seen = []
    p2 = EspnProvider()
    p2._league_index = lambda: seen.append("index")
    p2.fixtures_on = lambda offset=0, sport=None: seen.append("today")
    p2.warm()
    assert sorted(seen) == ["index", "today"]
    p2._league_index = lambda: (_ for _ in ()).throw(RuntimeError("down"))
    p2.warm()
    print("ok  warm() opens the connections, and a failure costs nothing")

    # events are written as a batch and read back once
    s = MemoryStore()
    evs = [Event.make(7, m, "goal", player="P%d" % m) for m in (5, 6, 7)]
    s.append_events(evs + evs)
    assert len(s.events(7)) == 3
    print("ok  append_events logs a batch and ignores a repeat")
    print("\nfast and live: all good")


if __name__ == "__main__":
    main()
