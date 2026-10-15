"""The background poller.

This is the half of the system that runs when nobody is talking to
Alexa, and it is what makes "what did I miss" possible at all. A product
that only fetches data when asked cannot tell you about a goal you were
not in the room for - by the time you ask, you have to know to ask.

It runs as a thread inside the server. poll_once() is the whole unit of
work and has no idea which is calling it.

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

from . import clock
from .state.store import backdate, event_key
from .status import OVER

LOG = logging.getLogger("sideline.poller")

OVERLAP_MINUTES = 3

# The fast interval (SIDELINE_POLL_SECONDS) is for a match in play. A match that has not started
# cannot change, so it is looked at only now and then, and kept to the fast rate from shortly
# before the kick-off. A match that is over is read once (below).
MISSES_BEFORE_BACKING_OFF = 3         # an id the feed does not know costs a call each cycle: after this many in a row, look less often
BACKOFF_SECONDS = 300
WAITING_SECONDS = 300
LEAD_SECONDS = 600

# A match that is over cannot change, so once it has been read in that state the poller leaves it
# alone: every poll is a call against the feed's hourly limit.


def poll_once(ctx, only=None):
    """One cycle: read every followed match once and log what is new. `only` reads just that match (a listener who has
    just followed one needs its events, not a sweep of every match anyone follows)."""
    try:
        fixtures = [only] if only is not None else ctx.store.all_followed_fixtures()
    except Exception as e:                                      # noqa: BLE001 - a store hiccup (throttle, expired credential) skips a cycle
        LOG.warning("could not list the followed matches this cycle: %s", e)
        fixtures = []
    found = 0
    done = ctx.__dict__.setdefault("finished_fixtures", set())
    due = ctx.__dict__.setdefault("next_read", {})
    for fid in fixtures:
        if fid in done or time.time() < due.get(fid, 0):
            continue
        try:
            fx = ctx.provider.fixture(fid)
            misses = ctx.__dict__.setdefault("missing_fixtures", {})
            if not fx:
                misses[fid] = misses.get(fid, 0) + 1
                if misses[fid] >= MISSES_BEFORE_BACKING_OFF:
                    due[fid] = time.time() + BACKOFF_SECONDS      # not "never": a blip must not lose a live match for good
                    misses[fid] = 0
                    LOG.warning("fixture %s was not found %d times in a row; trying again in %ds",
                                fid, MISSES_BEFORE_BACKING_OFF, BACKOFF_SECONDS)
                continue
            misses.pop(fid, None)                                  # found: the count is of misses in a row
            ctx.store.save_fixture({"fixture_id": fid, **fx})
            known = ctx.store.events(fid)
            high = max([e["minute"] for e in known], default=0)
            since = max(0, high - OVERLAP_MINUTES)
            batch = [backdate(e, fx.get("minute")) for e in ctx.provider.events(fid, since_minute=since)]
            seen = {event_key(e) for e in known}
            fresh = []
            for e in batch:
                if event_key(e) not in seen:
                    seen.add(event_key(e))
                    fresh.append(e)
            ctx.store.append_events(batch)           # all of them, so a detail the feed filled in later is merged
            for e in fresh:
                found += 1
                LOG.info("logged %s on %s' in fixture %s", e["kind"], e["minute"], fid)
                _handle_var(ctx, fid, e)
            if fx.get("status") in OVER:
                done.add(fid)
            elif fx.get("status") == "NS":
                ko = clock.until_kickoff(fx)
                if ko is None or ko.total_seconds() > LEAD_SECONDS:
                    due[fid] = time.time() + WAITING_SECONDS
            else:
                due.pop(fid, None)
        except Exception as e:                                  # noqa: BLE001
            # A provider wobble must not kill the poller. The listener
            # would rather have a gap in the log than a dead server.
            LOG.warning("poll failed for fixture %s: %s", fid, e)
    return found


def _handle_var(ctx, fid, event):
    """Mark a score superseded when a review (VAR, a replay) overturns it.

    We do not delete the score. A listener who heard the crowd go up
    needs to be told it was chalked off, and a deleted row cannot tell
    them anything. Which events review which is the sport's call:
    see SportProfile.overturned.
    """
    from . import sports
    sp = sports.for_fixture(ctx.store.fixture(fid))
    target = sp.overturned(event, ctx.store.events(fid))
    if target and hasattr(ctx.store, "supersede"):
        ctx.store.supersede(fid, target["id"], event["id"])
        LOG.info("%s on %s' superseded by %s", target["kind"], target["minute"],
                 event["kind"])


class Poller(threading.Thread):
    daemon = True

    def __init__(self, ctx, interval):
        threading.Thread.__init__(self, name="sideline-poller")
        self.ctx = ctx
        self.interval = interval
        self._halt = threading.Event()

    def run(self):
        LOG.info("poller started, every %ds", self.interval)
        while not self._halt.is_set():
            try:
                poll_once(self.ctx)
            except Exception:                                      # noqa: BLE001 - nothing may end the thread: a gap beats a dead server
                LOG.exception("poll cycle failed; carrying on")
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()
