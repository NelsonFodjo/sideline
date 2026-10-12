"""Replay provider - a recorded real match, played back at real speed.

This is not a mock. It is a real match, captured from a real provider
with scripts/record_match.py, and replayed through the identical code
path the live provider uses. Two reasons it exists, both practical:

  1. You cannot develop a live-football product at 2am on a Tuesday.
     Without this, every change has to wait for a fixture.
  2. The demo video has to be filmable. A live match that turns out to
     be nil-nil with no cards is an unusable three minutes.

Honesty rule: anything demoed from replay is described as "a recorded
real match, replayed", never implied to be live. The data is genuine;
the clock is ours. Say so in the video.

Speed: `speed=1.0` is real time (90 minutes). `speed=90` runs a full
match in a minute, which is what the test suite uses.
"""

import json
import time

from .base import Provider
from ..state.store import Event


class ReplayProvider(Provider):
    name = "replay"

    def __init__(self, path, speed=1.0, start_minute=0):
        with open(path, "r", encoding="utf-8") as fh:
            self._doc = json.load(fh)
        self.speed = speed
        self._t0 = time.time()
        self._start_minute = start_minute
        self._fx = self._doc["fixture"]

    # ------------------------------------------------------- the clock
    def now_minute(self):
        elapsed = (time.time() - self._t0) * self.speed / 60.0
        return int(self._start_minute + elapsed)

    def jump_to(self, minute):
        """Used by tests and by the demo rehearsal script."""
        self._t0 = time.time() - (minute - self._start_minute) * 60.0 / self.speed

    # ---------------------------------------------------------- reads
    def fixtures_today(self):
        # Must return the SAME enriched shape as fixture(), or callers
        # that pick a match from this list get one with no minute and no
        # score - which is how follow_match ended up announcing a match
        # at minute 70 as "not kicked off yet".
        return [self.fixture(self._fx["fixture_id"])]

    def fixture(self, fixture_id):
        if int(fixture_id) != int(self._fx["fixture_id"]):
            return None
        fx = dict(self._fx)
        fx["minute"] = min(self.now_minute(), 90)
        fx["status"] = "finished" if self.now_minute() >= 90 else "live"
        fx["score"] = self._score_at(fx["minute"])
        return fx

    def events(self, fixture_id, since_minute=0):
        if int(fixture_id) != int(self._fx["fixture_id"]):
            return []
        now = self.now_minute()
        out = []
        for raw in self._doc["events"]:
            if raw["minute"] > now or raw["minute"] <= since_minute:
                continue
            out.append(self._to_event(raw))
        return out

    def lineups(self, fixture_id):
        return self._doc["lineups"]

    def officials(self, fixture_id):
        o = dict(self._doc["officials"])
        now = self.now_minute()
        o["yellows_shown"] = sum(
            1 for e in self._doc["events"]
            if e["kind"] == "card" and e.get("colour") == "yellow" and e["minute"] <= now)
        o["reds_shown"] = sum(
            1 for e in self._doc["events"]
            if e["kind"] == "card" and e.get("colour") == "red" and e["minute"] <= now)
        return o

    def head_to_head(self, fixture_id, limit=5):
        return self._doc.get("head_to_head", [])[:limit]

    # --------------------------------------------------------- private
    def _score_at(self, minute):
        h = a = 0
        for e in self._doc["events"]:
            if e["minute"] > minute or e["kind"] != "goal":
                continue
            if e.get("superseded"):
                continue
            if e["team"] == self._fx["home"]:
                h += 1
            else:
                a += 1
        return {"home": h, "away": a}

    def _to_event(self, raw):
        e = Event.make(self._fx["fixture_id"], raw["minute"], raw["kind"])
        for k, v in raw.items():
            if k not in ("minute", "kind"):
                e[k] = v
        # Deterministic id so a replayed event keeps the same id across
        # restarts; otherwise dedupe in the store cannot work and the
        # tests become flaky.
        e["id"] = "e-%s-%03d-%s" % (self._fx["fixture_id"], raw["minute"], raw["kind"][:3])
        return e
