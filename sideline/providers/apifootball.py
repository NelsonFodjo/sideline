"""Live provider.

Points at a commercial football feed. Kept behind the same Provider
interface as replay so nothing above this file changes when you switch.

WHY THIS IS NOT FREE, and why we checked first:

  * The free tiers we tested are either delayed (no use: the listener
    hears the crowd react before we know anything) or capped at around
    a hundred calls a day (no use: a 90-minute match polled every 15
    seconds is 360 calls).
  * The paid tier we budgeted for refreshes live fixtures and events
    roughly every 15 seconds. That is comfortably inside our latency
    budget, because the listener asks AFTER hearing the crowd, not
    before.

Verifying this was stage one of the build plan, before a line of server
code was written. See docs/DATA_PROVIDERS.md for the capture we took.

The key lives in Secrets Manager, never in this repository. The
.env.example file shows the variable name and nothing else.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from .base import Provider

LOG = logging.getLogger("sideline.provider")

BASE = os.environ.get("SIDELINE_FOOTBALL_BASE", "https://v3.football.api-sports.io")
TIMEOUT = 6


class ApiFootballProvider(Provider):
    name = "apifootball"

    def __init__(self, api_key=None, cache_seconds=12):
        self.api_key = api_key or os.environ.get("SIDELINE_FOOTBALL_KEY", "")
        self.cache_seconds = cache_seconds
        self._cache = {}

    # ------------------------------------------------------------ http
    def _get(self, path, **params):
        """Cached GET.

        The cache is not an optimisation, it is a correctness measure:
        several tools can fire within one turn, and without it we would
        burn the request budget and add latency to the listener's
        answer for data we already have. Nothing in a football match
        changes meaningfully inside 12 seconds.
        """
        import time
        key = (path, tuple(sorted(params.items())))
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self.cache_seconds:
            return hit[1]

        url = "%s/%s?%s" % (BASE, path.lstrip("/"), urllib.parse.urlencode(params))
        req = urllib.request.Request(url, headers={"x-apisports-key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                doc = json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            # Never let a provider outage become a protocol error. The
            # tool layer turns this into something the listener can hear.
            LOG.warning("provider %s failed: %s", path, e)
            raise ProviderUnavailable(str(e))
        self._cache[key] = (time.time(), doc)
        return doc

    # ----------------------------------------------------------- reads
    def fixture(self, fixture_id):
        doc = self._get("fixtures", id=fixture_id)
        items = doc.get("response") or []
        if not items:
            return None
        return self._norm_fixture(items[0])

    def fixtures_today(self):
        doc = self._get("fixtures", live="all")
        return [self._norm_fixture(i) for i in doc.get("response", [])]

    def events(self, fixture_id, since_minute=0):
        doc = self._get("fixtures/events", fixture=fixture_id)
        out = []
        for raw in doc.get("response", []):
            e = self._norm_event(fixture_id, raw)
            if e and e["minute"] > since_minute:
                out.append(e)
        return out

    def lineups(self, fixture_id):
        doc = self._get("fixtures/lineups", fixture=fixture_id)
        out = {}
        for side in doc.get("response", []):
            team = (side.get("team") or {}).get("name")
            out[team] = {
                "formation": side.get("formation"),
                "xi": [p["player"]["name"] for p in side.get("startXI", [])],
                "numbers": {p["player"]["name"]: p["player"].get("number")
                            for p in side.get("startXI", [])},
                "bench": [p["player"]["name"] for p in side.get("substitutes", [])],
                "coach": (side.get("coach") or {}).get("name"),
            }
        return out

    def officials(self, fixture_id):
        fx = self._get("fixtures", id=fixture_id).get("response", [{}])[0]
        return {"referee": (fx.get("fixture") or {}).get("referee"),
                "venue": ((fx.get("fixture") or {}).get("venue") or {}).get("name")}

    def head_to_head(self, fixture_id, limit=5):
        fx = self.fixture(fixture_id)
        if not fx:
            return []
        doc = self._get("fixtures/headtohead",
                        h2h="%s-%s" % (fx["home_id"], fx["away_id"]), last=limit)
        return [self._norm_fixture(i) for i in doc.get("response", [])]

    # ------------------------------------------------------ normalising
    @staticmethod
    def _minute(raw_minute, extra):
        """'45+2' -> (45, 2). See base.py for why we split these."""
        try:
            m = int(raw_minute or 0)
        except (TypeError, ValueError):
            m = 0
        try:
            s = int(extra or 0)
        except (TypeError, ValueError):
            s = 0
        return m, s

    def _norm_fixture(self, raw):
        f, t, g = raw.get("fixture", {}), raw.get("teams", {}), raw.get("goals", {})
        return {
            "fixture_id": f.get("id"),
            "home": (t.get("home") or {}).get("name"),
            "away": (t.get("away") or {}).get("name"),
            "home_id": (t.get("home") or {}).get("id"),
            "away_id": (t.get("away") or {}).get("id"),
            "minute": ((f.get("status") or {}).get("elapsed")) or 0,
            "status": (f.get("status") or {}).get("short"),
            "score": {"home": g.get("home") or 0, "away": g.get("away") or 0},
            "venue": ((f.get("venue") or {}).get("name")),
            "kickoff": f.get("date"),
        }

    def _norm_event(self, fixture_id, raw):
        minute, stoppage = self._minute((raw.get("time") or {}).get("elapsed"),
                                        (raw.get("time") or {}).get("extra"))
        team = (raw.get("team") or {}).get("name")
        player = (raw.get("player") or {}).get("name")
        assist = (raw.get("assist") or {}).get("name")
        kind = (raw.get("type") or "").lower()
        detail = raw.get("detail") or ""

        if kind == "goal":
            return self.mk_goal(fixture_id, minute, player, team, assist=assist,
                                detail=detail, stoppage=stoppage)
        if kind == "card":
            colour = "red" if "red" in detail.lower() else "yellow"
            return self.mk_card(fixture_id, minute, player, team, colour,
                                reason=raw.get("comments"), stoppage=stoppage)
        if kind == "subst":
            return self.mk_sub(fixture_id, minute, on=assist, off=player,
                               team=team, stoppage=stoppage)
        if kind == "var":
            return self.mk_var(fixture_id, minute, decision=detail,
                               player=player, team=team, stoppage=stoppage)
        return None


class ProviderUnavailable(Exception):
    pass
