"""Test doubles. Nothing here ships with the product.

`ReplayProvider` stands in for the live football feed so the suite runs offline
and deterministically: it plays a small JSON fixture back on a clock the test
controls (`jump_to`). The fixtures in tests/fixtures/ are INVENTED (made-up
teams, players and events), clearly labelled as such, and exist only to be
stable and small. The product itself has no recorded data and no demo mode: it
reads the live feed (sideline/providers/sportmonks.py).
"""

import json
import time

from sideline import sports
from sideline.providers.base import Provider
from sideline.state.store import Event


class ReplayProvider(Provider):
    """One or more invented test fixtures, played back on one shared clock.

    `path` may be a single file or a list: a listener can then follow a
    football match and a basketball game from the same server, which is
    how the sport seam is exercised end to end. Each file's `fixture`
    carries a `sport` key (absent means football).
    """
    name = "replay"

    def __init__(self, path, speed=1.0, start_minute=0):
        paths = [path] if isinstance(path, str) else list(path)
        self._docs = {}
        for p in paths:
            with open(p, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            self._docs[int(doc["fixture"]["fixture_id"])] = doc
        self.speed = speed
        self._t0 = time.time()
        self._start_minute = start_minute

    def _doc(self, fixture_id):
        return self._docs.get(int(fixture_id))

    @staticmethod
    def _sport(doc):
        return sports.for_fixture(doc["fixture"])

    # ------------------------------------------------------- the clock
    def now_minute(self):
        elapsed = (time.time() - self._t0) * self.speed / 60.0 if self.speed else 0.0
        return int(self._start_minute + elapsed)

    def jump_to(self, minute):
        """Position the clock at `minute` (the tests never wait in real time)."""
        if not self.speed:
            self._start_minute = minute
            self._t0 = time.time()
        else:
            self._t0 = time.time() - (minute - self._start_minute) * 60.0 / self.speed

    # ---------------------------------------------------------- reads
    def fixtures_today(self):
        # Must return the SAME enriched shape as fixture(), or callers
        # that pick a match from this list get one with no minute and no
        # score - which is how follow_match ended up announcing a match
        # at minute 70 as "not kicked off yet".
        return [self.fixture(fid) for fid in self._docs]

    def fixture(self, fixture_id):
        doc = self._doc(fixture_id)
        if not doc:
            return None
        sp = self._sport(doc)
        fx = dict(doc["fixture"])
        fx.setdefault("sport", sp.key)
        fx["minute"] = min(self.now_minute(), sp.regulation_minutes)
        # Before kick-off the feed says "NS" (not started), as ESPN does; "live" at minute 0 is not a thing it says.
        fx["status"] = ("finished" if self.now_minute() >= sp.regulation_minutes
                        else "NS" if self.now_minute() <= 0 else "live")
        fx["score"] = self._score_at(doc, fx["minute"])
        return fx

    def events(self, fixture_id, since_minute=0):
        doc = self._doc(fixture_id)
        if not doc:
            return []
        now = self.now_minute()
        out = []
        for raw in doc["events"]:
            if raw["minute"] > now or raw["minute"] <= since_minute:
                continue
            out.append(self._to_event(doc, raw))
        return out

    def lineups(self, fixture_id):
        return self._doc(fixture_id)["lineups"]

    def officials(self, fixture_id):
        doc = self._doc(fixture_id)
        o = dict(doc["officials"])
        now = self.now_minute()
        o.update(self._sport(doc).official_counts(
            [e for e in doc["events"] if e["minute"] <= now]))
        return o

    capabilities = frozenset(__import__("sideline.providers.base", fromlist=["CAPABILITIES"]).CAPABILITIES)

    def search(self, query, kind="team"):
        pool = self._first_doc().get("search", {}).get(kind, [])
        want = query.lower()
        return [h for h in pool if want[:3] in h["name"].lower()]

    def competitions(self, country=None):
        return [c for c in self._first_doc().get("competitions", [])
                if not country or country.lower() in c["country"].lower()]

    def standings(self, competition):
        return self._first_doc().get("standings", {}).get(competition)

    def top_scorers(self, competition):
        return self._first_doc().get("top_scorers", {}).get(competition)

    def match_stats(self, fixture_id):
        return self._doc(fixture_id).get("stats")

    def player_stats(self, player, team=None):
        return self._first_doc().get("player_stats", {}).get(player.lower().split()[-1])

    def injuries(self, fixture_id):
        return list(self._doc(fixture_id).get("injuries", []))

    def form(self, fixture_id):
        return self._doc(fixture_id).get("form")

    def _first_doc(self):
        return next(iter(self._docs.values()))

    def head_to_head(self, fixture_id, limit=5):
        return self._doc(fixture_id).get("head_to_head", [])[:limit]

    # --------------------------------------------------------- private
    def _score_at(self, doc, minute):
        """The score at `minute`, with reviews applied as the poller would.

        A recording lists the original score and the review that chalks it
        off as two events; counting only the first would put the provider
        out of step with the store, which marks the original superseded.
        """
        sp = self._sport(doc)
        seen = [e for e in doc["events"] if e["minute"] <= minute]
        flagged = []
        for e in seen:
            target = sp.overturned(e, seen)
            if target is not None:
                flagged.append(id(target))
        live = [e for e in seen if id(e) not in flagged]
        return sp.score_from(live, doc["fixture"]["home"])

    def _to_event(self, doc, raw):
        fid = doc["fixture"]["fixture_id"]
        e = Event.make(fid, raw["minute"], raw["kind"])
        for k, v in raw.items():
            if k not in ("minute", "kind"):
                e[k] = v
        # Deterministic id so a replayed event keeps the same id across
        # restarts; otherwise dedupe in the store cannot work and the
        # tests become flaky. Two events of one kind in one minute (two
        # baskets) need a sequence number to stay distinct.
        same = [r for r in doc["events"]
                if r["minute"] == raw["minute"] and r["kind"] == raw["kind"]]
        seq = same.index(raw)
        e["id"] = "e-%s-%03d-%s%s" % (fid, raw["minute"], raw["kind"][:3],
                                      "" if seq == 0 else "-%d" % seq)
        return e
