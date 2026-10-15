"""The response cache (design from BetTrack, MIT: see docs/CREDITS.md) and how the ESPN provider uses it."""

import threading
import time

from sideline.cache import ResponseCache
from sideline.providers.base import ProviderUnavailable
from sideline.providers.espn import EspnProvider


class Clock(object):
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def main():
    # expiry, and a stale copy for a feed that is down
    clock = Clock()
    c = ResponseCache(max_entries=3, clock=clock)
    c.set("a", 1, ttl=10)
    assert c.get("a") == (True, 1)
    clock.t += 11
    assert c.get("a") == (False, None), "expired"
    assert c.stale("a", max_age=60) == (True, 1) and c.stale("a", max_age=5) == (False, None)
    c.set("never", 9, ttl=0)
    assert c.get("never") == (False, None), "a zero ttl keeps nothing"
    print("ok  entries expire; an expired one can still be had when the caller accepts its age")

    # bounded, least recently used out first
    c = ResponseCache(max_entries=3, clock=clock)
    for k in "abc":
        c.set(k, k, 100)
    c.get("a")                                   # a is now the most recently used
    c.set("d", "d", 100)
    assert c.get("b") == (False, None) and c.get("a")[0] and c.get("d")[0], "b, the least recently used, went"
    assert c.stats()["entries"] == 3 and c.evictions == 1
    print("ok  the cache stays at its limit and drops the least recently used")

    # coalescing: ten threads ask for one page at once; one request is made
    c = ResponseCache()
    calls = []

    def slow():
        calls.append(1)
        time.sleep(0.3)
        return {"ok": True}
    results = []
    threads = [threading.Thread(target=lambda: results.append(c.get_or_fetch("k", slow, lambda v: 60))) for _ in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(calls) == 1 and len(results) == 10 and all(r == {"ok": True} for r in results), (len(calls), len(results))
    assert c.stats()["coalesced"] == 9, c.stats()
    print("ok  ten askers at once cost one request (%d shared)" % c.stats()["coalesced"])

    # a failure is not kept, and goes to the one who fetched
    c = ResponseCache()

    def boom():
        raise RuntimeError("down")
    try:
        c.get_or_fetch("x", boom, lambda v: 60)
        raise AssertionError("the failure must reach the caller")
    except RuntimeError:
        pass
    assert c.get("x") == (False, None) and c.get_or_fetch("x", lambda: 5, lambda v: 60) == 5
    print("ok  a failed fetch is not cached: the next asker tries again")

    # the provider: one request however many ask, finished matches kept for hours, live ones for seconds
    p = EspnProvider()
    made = []

    def http(url):
        made.append(url)
        time.sleep(0.2)
        return {"events": [1]}
    p._http_get = http
    out = []
    ts = [threading.Thread(target=lambda: out.append(p._fetch_json("https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates=20261015"))) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(made) == 1 and len(out) == 6, made
    finished = {"header": {"competitions": [{"status": {"type": {"completed": True}}}]}}
    live = {"header": {"competitions": [{"status": {"type": {"completed": False}}}]}}
    summary = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event=1"
    assert p._ttl_for(summary, finished) == p.FINISHED_SUMMARY_TTL and p._ttl_for(summary, live) == p.LIVE_SUMMARY_TTL
    assert p._ttl_for("https://x/standings") == 60.0 and p._ttl_for("https://x/scoreboard?dates=1") == 5.0
    print("ok  six parallel callers, one request; a finished match is kept %dh, a live one %ds"
          % (p.FINISHED_SUMMARY_TTL // 3600, p.LIVE_SUMMARY_TTL))

    # the feed goes down: a page that cannot have changed (a table, a profile) is still served; a live one is not
    p2 = EspnProvider()
    table = "https://site.api.espn.com/apis/v2/sports/soccer/eng.1/standings"
    live_board = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
    p2._http_get = lambda u: {"events": ["x"], "children": ["t"]}
    assert p2._fetch_json(table, ttl=0.001)["children"] == ["t"]
    assert p2._fetch_json(live_board, ttl=0.001)["events"] == ["x"]
    time.sleep(0.01)

    def down(u):
        raise OSError("network down")
    p2._http_get = down
    assert p2._fetch_json(table, ttl=0.001)["children"] == ["t"], "the last good table, while the feed is down"
    assert p2._fetch_json(live_board, ttl=0.001) == {}, "a live scoreboard is never answered from an old copy"
    try:
        p2._fetch_json("https://site.api.espn.com/never-seen", strict=True)
        raise AssertionError("nothing to serve and the feed is down: that must be said")
    except ProviderUnavailable:
        pass
    try:
        p2._fetch_json(live_board, ttl=0.001, strict=True)
        raise AssertionError("a live page with the feed down must be said to be down")
    except ProviderUnavailable:
        pass
    assert p2._fetch_json("https://site.api.espn.com/never-seen") == {}
    print("ok  a feed that is down: a table comes from the last good copy, anything live is said to be unavailable")


if __name__ == "__main__":
    main()
    print("\ncache: all good")
