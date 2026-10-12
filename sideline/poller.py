"""The background poller.

This is the half of the system that runs when nobody is talking to
Alexa, and it is what makes "what did I miss" possible at all. A product
that only fetches data when asked cannot tell you about a goal you were
not in the room for - by the time you ask, you have to know to ask.

In production this is EventBridge Scheduler invoking a Lambda every 15
seconds. Locally it is a thread. Same code either way: poll_once() is
the whole unit of work and has no idea which is calling it.

Two things it gets right that a naive loop would not:

  1. It polls an OVERLAPPING window (since_minute minus a margin) and
     relies on the store's dedupe, rather than trying to track exactly
     where it got to. Feeds revise events - a goal gets an assist added
     a minute later, a card changes from yellow to red. Re-reading is
     cheap and correct; bookkeeping is neither.

  2. It only polls fixtures somebody is actually following. Polling
     every live match in the world would be a nice way to exhaust a
     request budget in an afternoon.
"""

import logging
import threading
import time

LOG = logging.getLogger("sideline.poller")

OVERLAP_MINUTES = 3


def poll_once(ctx):
    """One cycle. Safe to call from a Lambda handler."""
    try:
        fixtures = ctx.store.all_followed_fixtures()
    except AttributeError:
        fixtures = []
    found = 0
    for fid in fixtures:
        try:
            fx = ctx.provider.fixture(fid)
            if not fx:
                continue
            ctx.store.save_fixture({"fixture_id": fid, **fx})
            known = ctx.store.events(fid)
            high = max([e["minute"] for e in known], default=0)
            since = max(0, high - OVERLAP_MINUTES)
            for e in ctx.provider.events(fid, since_minute=since):
                before = len(ctx.store.events(fid))
                ctx.store.append_event(e)
                if len(ctx.store.events(fid)) > before:
                    found += 1
                    LOG.info("logged %s on %s' in fixture %s",
                             e["kind"], e["minute"], fid)
                    _handle_var(ctx, fid, e)
        except Exception as e:                                  # noqa: BLE001
            # A provider wobble must not kill the poller. The listener
            # would rather have a gap in the log than a dead server.
            LOG.warning("poll failed for fixture %s: %s", fid, e)
    return found


def _handle_var(ctx, fid, event):
    """Mark a goal superseded when VAR overturns it.

    We do not delete the goal. A listener who heard the crowd go up
    needs to be told it was chalked off, and a deleted row cannot tell
    them anything.
    """
    if event.get("kind") != "var":
        return
    decision = (event.get("decision") or "").lower()
    if "disallow" not in decision and "cancel" not in decision:
        return
    for e in reversed(ctx.store.events(fid)):
        if e["kind"] == "goal" and abs(e["minute"] - event["minute"]) <= 3:
            if hasattr(ctx.store, "supersede"):
                ctx.store.supersede(fid, e["id"], event["id"])
                LOG.info("goal on %s' superseded by VAR", e["minute"])
            break


class Poller(threading.Thread):
    daemon = True

    def __init__(self, ctx, interval):
        threading.Thread.__init__(self, name="sideline-poller")
        self.ctx = ctx
        self.interval = interval
        self._stop = threading.Event()

    def run(self):
        LOG.info("poller started, every %ds", self.interval)
        while not self._stop.is_set():
            poll_once(self.ctx)
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
