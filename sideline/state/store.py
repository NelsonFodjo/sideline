"""Listener state and the match event log.

This module is the product. Everything else is plumbing.

Two things live here that Alexa+ structurally cannot hold:

  1. `last_told_at` - when we last told THIS listener anything about THIS
     match. It is what makes "what did I miss" answerable without the
     listener having to say how long they were away. Alexa+ has no
     equivalent and no way to acquire one: it sees only the current turn.

  2. The event log - every goal, card, substitution and VAR decision,
     captured by the poller as it happens, whether or not anyone was in
     the room. A model cannot hold this because the match is happening
     now.

Design decisions worth knowing before you change anything:

  * Events are append-only and immutable once written, except for the
    `superseded_by` field (used when VAR overturns a goal - see
    `supersede`). A listener who asks about a disallowed goal should
    hear that it was disallowed, not have the event vanish.
  * `told_event_ids` is tracked separately from `last_told_at`. The
    timestamp answers "what window", the id set answers "did we already
    mention this specific thing". Both are needed: a listener can ask
    about one event explicitly and then later ask what they missed, and
    we should not repeat it.
"""

import threading
import time
import uuid

from .. import clock


def event_key(event):
    """What makes two events the same one: the minute and the stoppage minute, what kind, who, and the one detail that
    tells apart two of a kind in a minute (a penalty's outcome, a card's colour, who came off, which free throw).
    Without these, a second goal in stoppage time, a booking then a red, or free throw 2 of 2 were dropped as repeats."""
    kind = event.get("kind")
    detail = event.get("outcome") or event.get("colour") or event.get("player_off") or (
        event.get("detail") if kind == "basket" else None)
    return (event.get("minute"), event.get("stoppage") or 0, kind, event.get("player"), detail)


# Fields a later read may fill in for an event already logged (the assist added a minute after the goal).
_FILLED_LATER = ("assist", "reason", "keeper", "conceded_by")


def backdate(event, live_minute, now=None):
    """Estimate when an event we have only just fetched really happened, for the spoiler guard.

    `at` is when we first saw it. For an event the poller catches as it happens that is accurate to a poll. For one
    read late (a match followed at 60', a restart) every old event would look brand new and be held back for the
    whole delay. A minute m event, read when the match is at minute M, happened at the latest M-m-1 whole minutes
    ago, so `happened_by` records that: never earlier than the truth, so it can only hide too long, not spoil.
    `at` itself is left alone: delay calibration (sync.py) reads it as "when we first logged this".
    """
    now = time.time() if now is None else now
    behind = (live_minute or 0) - event["minute"] - 1
    if behind > 0:
        event["happened_by"] = min(event["at"], now - behind * 60)
    return event


def released_at(event):
    """The moment the feed's version of this event is taken to have happened (see backdate)."""
    return event.get("happened_by") or event["at"]


def new_id(prefix):
    return "%s-%s" % (prefix, uuid.uuid4().hex[:8])


class Event(dict):
    """One thing that happened in a match.

    A dict subclass so it serialises straight to JSON with no encoder.
    """

    @staticmethod
    def make(fixture_id, minute, kind, **fields):
        e = Event({
            "id": new_id("e"),
            "fixture_id": fixture_id,
            "minute": minute,
            "kind": kind,                 # per sport, e.g. goal | card | substitution | var | period
            "at": time.time(),
            "superseded_by": None,
        })
        e.update(fields)
        return e


class Listener(dict):
    @staticmethod
    def make(listener_id):
        return Listener({
            "listener_id": listener_id,
            "following": None,            # fixture id
            "supports": None,             # team name, used for tone only
            "last_told_at": None,         # match minute, not wall clock
            "told_event_ids": [],
            "language": "en",
            # Seconds the listener's picture runs behind the live feed.
            # None until armed: follow_match sets a conservative prior
            # from the device locale so we never spoil by default, and
            # the first audio anchor replaces it with a measurement.
            # See sideline/sync.py.
            "broadcast_offset": None,
            "offset_source": None,
            "offset_calibrated": False,
            "locale": None,
        })


class Store:
    """Interface. See MemoryStore below and DynamoStore in dynamo.py."""

    def listener(self, listener_id): raise NotImplementedError
    def save_listener(self, rec): raise NotImplementedError
    def forget_listener(self, listener_id):
        """Erase everything kept about a listener: the match followed, teams, settings, what they have heard."""
        raise NotImplementedError

    def followers(self, fixture_id):
        """Listener ids following a fixture. A backend that cannot answer
        returns [] and the product still works."""
        return []
    def append_event(self, event): raise NotImplementedError
    def append_events(self, events):
        """Log several events. The same as appending each, and a backend may do them at once."""
        for e in events:
            self.append_event(e)
    def events(self, fixture_id): raise NotImplementedError
    def fixture(self, fixture_id): raise NotImplementedError
    def save_fixture(self, rec): raise NotImplementedError

    # ---------------------------------------------------------- shared
    # These are deliberately on the base class: the gap calculation is
    # the heart of the product and must not drift between backends.

    def gap_for(self, listener_id, fixture_id, since_minute=None):
        """Events this listener has not been told about.

        Returns (events, from_minute, to_minute).

        `since_minute` overrides the stored marker, for when the listener
        says something explicit like "since half time". Otherwise we use
        last_told_at, and if that is None - they have never asked
        anything - we return the whole match so far, which is the right
        answer for someone who just walked in.
        """
        rec = self.listener(listener_id)
        start = since_minute if since_minute is not None else rec.get("last_told_at")
        if start is None:
            start = -1                      # include minute 0
        told = set(rec.get("told_event_ids") or [])

        # Never hand back an event the listener's picture has not reached.
        # Without this the catch-up itself becomes the spoiler.
        events, floor = self.on_screen(fixture_id, rec.get("broadcast_offset"))

        out = []
        high = start
        for e in events:
            if e["minute"] <= start:
                continue
            if e["id"] in told:
                continue
            if e.get("kind") == "period":
                continue                    # half-time markers are not news
            out.append(e)
            high = max(high, e["minute"])
        if floor is not None:
            # An event still to reach their screen shares this minute or an earlier one: do not mark it as told.
            high = min(high, max(start, floor - 1))
        return out, max(start, 0), high

    def on_screen(self, fixture_id, offset, now=None):
        """The events a listener `offset` seconds behind the feed has seen, and the minute of the earliest one still
        to come (None when nothing is held back). An event is on their screen once `at + offset` has passed."""
        events = self.events(fixture_id)
        if not offset:
            return events, None
        now = time.time() if now is None else now
        shown = [e for e in events if released_at(e) + offset <= now]
        held = [e["minute"] for e in events if released_at(e) + offset > now]
        return shown, (min(held) if held else None)

    def score_at(self, fixture_id, minute):
        """The score as it stood at a given minute.

        Needed because a calibrated listener is watching the past: if
        their picture is 40 seconds behind and a goal has just gone in,
        the honest answer to "what's the score" is the score before it.
        Returns None when we have no events to compute from.
        """
        evs = self.events(fixture_id)
        if not evs:
            return None
        fx = self.fixture(fixture_id) or {}
        from .. import sports
        return sports.for_fixture(fx).score_from(evs, fx.get("home"), minute)

    def mark_told(self, listener_id, minute, event_ids=()):
        """Move the marker forward. Never backwards.

        Called after any tool that actually told the listener something.
        Moving it backwards would make a listener hear the same goal
        twice, which is worse than silence.
        """
        rec = self.listener(listener_id)
        prev = rec.get("last_told_at")
        if prev is None or minute > prev:
            rec["last_told_at"] = minute
        ids = list(rec.get("told_event_ids") or [])
        for eid in event_ids:
            if eid not in ids:
                ids.append(eid)
        rec["told_event_ids"] = ids[-200:]   # bounded; a match has far fewer
        self.save_listener(rec)
        return rec


class MemoryStore(Store):
    """Default backend.

    Used by the test suite and when no DynamoDB table is available.
    Deliberately the default when there are no AWS credentials, so the
    server runs (and the tests pass) without an AWS account - see README, "Run it".
    """

    def __init__(self):
        self._listeners = {}
        self._events = {}
        self._fixtures = {}
        self._lock = threading.RLock()

    def listener(self, listener_id):
        with self._lock:
            if listener_id not in self._listeners:
                self._listeners[listener_id] = Listener.make(listener_id)
            return self._listeners[listener_id]

    def save_listener(self, rec):
        with self._lock:
            self._listeners[rec["listener_id"]] = rec
            return rec

    def forget_listener(self, listener_id):
        with self._lock:
            self._listeners.pop(listener_id, None)

    def append_event(self, event):
        with self._lock:
            bucket = self._events.setdefault(event["fixture_id"], [])
            # Idempotent on (fixture, minute, kind, player): the poller
            # re-reads an overlapping window every cycle and must not
            # create duplicates. Without this the listener is told about
            # the same goal four times.
            key = event_key(event)
            for e in bucket:
                if event_key(e) == key:
                    for field in _FILLED_LATER:           # the feed fills details in after the event: keep them
                        if event.get(field) and not e.get(field):
                            e[field] = event[field]
                    return e
            bucket.append(event)
            bucket.sort(key=lambda e: (e["minute"], e["at"]))
            return event

    def events(self, fixture_id):
        with self._lock:
            return list(self._events.get(fixture_id, []))

    def supersede(self, fixture_id, event_id, by_event_id):
        with self._lock:
            for e in self._events.get(fixture_id, []):
                if e["id"] == event_id:
                    e["superseded_by"] = by_event_id
                    return e
        return None

    def fixture(self, fixture_id):
        with self._lock:
            return self._fixtures.get(fixture_id)

    def save_fixture(self, rec):
        with self._lock:
            self._fixtures[rec["fixture_id"]] = rec
            return rec

    def followers(self, fixture_id):
        """Listener ids currently following this fixture."""
        with self._lock:
            return sorted(r["listener_id"] for r in self._listeners.values()
                          if r.get("following") == fixture_id)

    def all_followed_fixtures(self):
        """Fixtures at least one listener is following - what the poller polls."""
        with self._lock:
            return sorted({r["following"] for r in self._listeners.values()
                           if r.get("following")})
