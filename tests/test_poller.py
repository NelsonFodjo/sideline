"""The poller spends the feed's hourly limit, so it must not spend it on a match that is over."""

from conftest import make_ctx

from sideline.poller import poll_once


def main():
    ctx = make_ctx(start_minute=40)
    reads = []
    real = ctx.provider.fixture
    ctx.provider.fixture = lambda fid: reads.append(fid) or real(fid)
    ctx.store.listener("u").update(following=1208341)

    poll_once(ctx)
    poll_once(ctx)
    assert reads == [1208341, 1208341], "a match in play is read every cycle"
    print("ok  a match in play is polled every cycle")

    del reads[:]
    ctx.provider.jump_to(95)                          # full time
    poll_once(ctx)
    assert reads == [1208341], "the final whistle is read once"
    full = len(ctx.store.events(1208341))
    for _ in range(3):
        poll_once(ctx)
    assert reads == [1208341], "and then the match is left alone: %s" % reads
    assert len(ctx.store.events(1208341)) == full and full > 0
    print("ok  a finished match is read once, with its events, and then no longer polled")

    # A match that has not started is looked at now and then, not every cycle.
    import time
    from sideline import clock, poller
    ctx = make_ctx(start_minute=0)
    ctx.store.listener("u").update(following=1208341)
    reads = []
    ko = (clock.now() + __import__("datetime").timedelta(hours=3)).isoformat()
    ctx.provider.fixture = lambda fid: reads.append(fid) or {"fixture_id": fid, "home": "A", "away": "B", "minute": 0,
                                                              "status": "NS", "score": {"home": 0, "away": 0}, "kickoff": ko}
    ctx.provider.events = lambda fid, since_minute=0: []
    poll_once(ctx)
    poll_once(ctx)
    assert reads == [1208341], "not started, hours away: read once, then left for a few minutes"
    ctx.next_read[1208341] = time.time() - 1
    poll_once(ctx)
    assert len(reads) == 2, "and read again when it is due"
    soon = (clock.now() + __import__("datetime").timedelta(minutes=5)).isoformat()
    ko = soon
    ctx.next_read[1208341] = time.time() - 1
    poll_once(ctx)
    poll_once(ctx)
    assert len(reads) == 4, "within ten minutes of kick-off it is read every cycle"
    print("ok  a match not yet started is checked every few minutes, and every cycle from shortly before kick-off")

    print("\npoller: all good")


if __name__ == "__main__":
    main()
