"""A small thread-safe response cache: expiry, a size limit, and one request for many askers.

Design from BetTrack's `mcp/sports_api/cache.py` (MIT, Copyright (c) 2026 Sports Data MCP; see docs/CREDITS.md), rewritten
here for threads instead of asyncio. What it gives the ESPN provider:

* Only successes are stored. A failure kept for a minute would turn a blip into a minute of failure.
* Bounded, least recently used out first, so a long session cannot grow it without limit.
* Coalescing. Several tools ask for the same page at the same moment (a day's scoreboard, a team's schedule); the
  first asker fetches and the rest wait for that answer, so N askers cost one request.
* A copy past its expiry is kept until it is pushed out, so a feed that has just gone down can still be answered from
  the last good page, if the caller says how old a page it will accept (`stale`).
* Counters (hits, misses, coalesced, evictions) so what the cache saves can be measured.
"""

import threading
import time
from collections import OrderedDict

DEFAULT_MAX_ENTRIES = 512
WAIT_FOR_LEADER_SECONDS = 20.0


class ResponseCache(object):
    def __init__(self, max_entries=DEFAULT_MAX_ENTRIES, clock=time.monotonic):
        self.max_entries = max(1, max_entries)
        self._clock = clock
        self._lock = threading.RLock()
        self._entries = OrderedDict()                 # key -> (fetched_at, expires_at, value)
        self._inflight = {}                           # key -> Event, set when the leader is done
        self.hits = self.misses = self.coalesced = self.evictions = self.stale_served = 0

    # ------------------------------------------------------------------ plain reads and writes
    def get(self, key):
        """(True, value) for a fresh entry, else (False, None)."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[1] <= self._clock():
                return False, None
            self._entries.move_to_end(key)            # a key that keeps being asked for survives eviction
            return True, entry[2]

    def stale(self, key, max_age):
        """The last good value for `key` if it is no more than `max_age` seconds old, even past its expiry."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and self._clock() - entry[0] <= max_age:
                self.stale_served += 1
                return True, entry[2]
            return False, None

    def set(self, key, value, ttl):
        """Keep `value` for `ttl` seconds. A ttl of zero or less keeps nothing."""
        if ttl <= 0:
            return
        with self._lock:
            now = self._clock()
            self._entries[key] = (now, now + ttl, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
                self.evictions += 1

    # ------------------------------------------------------------------ one fetch for many askers
    def get_or_fetch(self, key, fetch, ttl_for):
        """The fresh value for `key`, or the result of `fetch()`, kept for `ttl_for(result)` seconds.

        Askers that arrive while a fetch for the same key is under way wait for it and share its result. If it
        fails, the exception goes to the one who fetched; the others then try for themselves.
        """
        found, value = self.get(key)
        if found:
            with self._lock:
                self.hits += 1
            return value
        with self._lock:
            waiting = self._inflight.get(key)
            if waiting is None:
                self._inflight[key] = done = threading.Event()
                self.misses += 1
        if waiting is not None:
            waiting.wait(WAIT_FOR_LEADER_SECONDS)
            found, value = self.get(key)
            if found:
                with self._lock:
                    self.coalesced += 1
                return value
            return self._fetch_and_keep(key, fetch, ttl_for)   # the one who was fetching failed: try on our own
        try:
            return self._fetch_and_keep(key, fetch, ttl_for)
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            done.set()

    def _fetch_and_keep(self, key, fetch, ttl_for):
        value = fetch()
        self.set(key, value, ttl_for(value))
        return value

    def stats(self):
        with self._lock:
            asked = self.hits + self.misses + self.coalesced
            return {"entries": len(self._entries), "hits": self.hits, "misses": self.misses,
                    "coalesced": self.coalesced, "evictions": self.evictions, "stale_served": self.stale_served,
                    "saved": (self.hits + self.coalesced) / float(asked) if asked else 0.0}
