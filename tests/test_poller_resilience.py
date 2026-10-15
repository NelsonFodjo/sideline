"""The poller outlives errors and does not drop a live match; and real events are not mistaken for repeats.

ST-05 one store error killed the thread for good; ST-06 three scattered misses gave a live match up for ever; ST-07 a
second goal in stoppage time, a booking then a red card, or free throw 2 of 2 were dropped as duplicates.
"""

import time

from conftest import make_ctx

from sideline import poller
from sideline.state.dynamo import event_sk
from sideline.state.store import Event, MemoryStore, event_key
from sideline.tools import REGISTRY

L = "u"


def main():
    # a store that throws does not stop a cycle, or the thread
    ctx = make_ctx(start_minute=40)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    good = ctx.store.all_followed_fixtures
    state = {"fail": 3}

    def flaky():
        if state["fail"] > 0:
            state["fail"] -= 1
            raise RuntimeError("ProvisionedThroughputExceededException")
        return good()
    ctx.store.all_followed_fixtures = flaky
    assert poller.poll_once(ctx) == 0, "a store error skips the cycle"
    t = poller.Poller(ctx, interval=0.05)
    t.start()
    time.sleep(0.5)
    assert t.is_alive(), "the thread must outlive its errors"
    t.stop()
    t.join(2)
    assert state["fail"] == 0, "and it kept trying until the store recovered"
    print("ok  a throwing store skips a cycle; the poller thread stays alive")

    # a poll cycle that itself raises (a bug, a provider crash) does not end the thread either
    ctx2 = make_ctx(start_minute=40)
    calls = []
    real = poller.poll_once

    def exploding(c):
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("boom")
        return 0
    poller.poll_once = exploding
    try:
        t2 = poller.Poller(ctx2, interval=0.02)
        t2.start()
        time.sleep(0.4)
        alive = t2.is_alive()
        t2.stop()
        t2.join(2)
    finally:
        poller.poll_once = real
    assert alive and len(calls) >= 3, (alive, calls)
    print("ok  a cycle that raises is logged and the next one runs")

    # scattered misses never add up to giving up; a run of them backs off, never for good
    ctx3 = make_ctx(start_minute=40)
    REGISTRY["follow_match"](ctx3, {"team": "Arsenal"}, L)
    fid = ctx3.store.listener(L)["following"]
    real_fixture = ctx3.provider.fixture
    answers = iter([None, None, "ok", None, None, "ok", None, None, "ok"])

    def sometimes(f):
        a = next(answers)
        return real_fixture(f) if a == "ok" else None
    ctx3.provider.fixture = sometimes
    for _ in range(9):
        ctx3.__dict__.pop("next_read", None)
        poller.poll_once(ctx3)
    assert fid not in ctx3.__dict__.get("finished_fixtures", set()) and not ctx3.__dict__.get("next_read", {}).get(fid), \
        "two misses, then a hit, three times over: still polled every cycle"
    ctx3.provider.fixture = lambda f: None
    ctx3.__dict__.pop("next_read", None)
    for _ in range(poller.MISSES_BEFORE_BACKING_OFF):
        ctx3.__dict__.pop("next_read", None) if False else None
        poller.poll_once(ctx3)
    assert fid not in ctx3.__dict__["finished_fixtures"], "never given up for good"
    assert ctx3.__dict__["next_read"][fid] > time.time(), "a run of misses backs off, and will try again"
    print("ok  scattered misses reset on a hit; a run of them backs off for five minutes, not for ever")

    # the events that used to be dropped
    def ev(minute, kind, player, **kw):
        return Event.make("1", minute, kind, player=player, **kw)
    s = MemoryStore()
    for e in (ev(45, "goal", "Saka", stoppage=0), ev(45, "goal", "Saka", stoppage=3),            # a second goal, in stoppage time
              ev(60, "card", "Rice", colour="yellow"), ev(60, "card", "Rice", colour="red"),   # booked, then sent off
              ev(30, "basket", "Brunson", detail="makes free throw 1 of 2"), ev(30, "basket", "Brunson", detail="makes free throw 2 of 2"),
              ev(88, "penalty", "Torres", outcome="saved")):
        s.append_event(e)
    kinds = [(e["minute"], e["kind"], e.get("stoppage"), e.get("colour") or e.get("outcome")) for e in s.events("1")]
    assert len(s.events("1")) == 7, kinds
    print("ok  a stoppage-time goal, a yellow then a red, free throws 1 and 2 are all kept (%d events)" % len(s.events("1")))

    first = ev(75, "goal", "Martinelli")
    again = ev(75, "goal", "Martinelli", assist="Odegaard")
    s.append_event(first)
    s.append_event(again)
    mine = [e for e in s.events("1") if e["minute"] == 75]
    assert len(mine) == 1 and mine[0]["assist"] == "Odegaard", mine
    print("ok  the same goal read twice is one event, and the assist added later is kept")

    assert event_key(ev(10, "goal", "X")) != event_key(ev(10, "goal", "X", stoppage=2))
    assert event_sk(ev(45, "goal", "Saka")) != event_sk(ev(45, "goal", "Saka", stoppage=3))
    assert event_sk(ev(45, "goal", "Saka")) == event_sk(ev(45, "goal", "Saka")), "the same event keeps the same key"
    print("ok  DynamoDB keys tell them apart too, and the same event always gets the same key")


if __name__ == "__main__":
    main()
    print("\npoller resilience: all good")
