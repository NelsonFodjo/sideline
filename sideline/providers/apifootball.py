"""The live football feed: API-Football (api-sports.io).

The only provider the product ships. It turns the vendor's JSON into our
internal Event shape (see base.py for the rules every provider must follow).

The key is read from SIDELINE_FOOTBALL_KEY and is never written to a file. A
free plan allows 100 requests a day, so the poller defaults to a 60 s interval
(SIDELINE_POLL_SECONDS); one followed match then costs about 100 requests over
its length. Observed on a free plan: refresh and quota behaviour are in
docs/DATA_PROVIDERS.md.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from .. import tls
from .base import Provider, ProviderUnavailable  # noqa: F401 (re-exported)

LOG = logging.getLogger("sideline.provider")

BASE = "https://v3.football.api-sports.io"
TIMEOUT = 6


class ApiFootballProvider(Provider):
    name = "apifootball"

    def __init__(self, api_key=None, cache_seconds=12):
        self.api_key = api_key or ""
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
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=tls.context()) as r:
                doc = json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            # Never let a provider outage become a protocol error. The
            # tool layer turns this into something the listener can hear.
            LOG.warning("provider %s failed: %s", path, e)
            raise ProviderUnavailable(str(e))
        problem = self._problem(doc)
        if problem:
            # API-Football reports a bad key or an exhausted quota as
            # HTTP 200 with an `errors` field and an empty `response`.
            # Left alone that reads as "no such match", which is a lie
            # the listener would act on.
            LOG.warning("provider %s refused: %s", path, problem)
            raise ProviderUnavailable(problem)
        self._cache[key] = (time.time(), doc)
        return doc

    @staticmethod
    def _problem(doc):
        errors = doc.get("errors")
        if not errors:
            return ""
        if isinstance(errors, dict):
            return "; ".join("%s: %s" % kv for kv in errors.items())
        return "; ".join(str(e) for e in errors)

    # ----------------------------------------------------------- reads
    def fixture(self, fixture_id):
        doc = self._get("fixtures", id=fixture_id)
        items = doc.get("response") or []
        if not items:
            return None
        return self._norm_fixture(items[0])

    def fixtures_today(self):
        """Today's fixtures, not just the ones live this second.

        "Follow the Arsenal game" is usually said before kick-off, when
        `live=all` is empty. Two calls, both cached; the date call is
        the one that matters, live is added so a match that kicked off
        before midnight UTC is still found.
        """
        import datetime
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        seen, out = set(), []
        for doc in (self._get("fixtures", date=today),
                    self._get("fixtures", live="all")):
            for i in doc.get("response", []):
                fx = self._norm_fixture(i)
                if fx["fixture_id"] not in seen:
                    seen.add(fx["fixture_id"])
                    out.append(fx)
        return out

    def _embedded(self, fixture_id, key):
        """`fixtures?id=` carries events and lineups inside it.

        One call per poll instead of three, which is the difference
        between fitting a free plan's daily quota and not. Returns None
        when the response does not include the key, and the caller falls
        back to the dedicated endpoint.
        """
        items = self._get("fixtures", id=fixture_id).get("response") or []
        if items and isinstance(items[0].get(key), list):
            return items[0][key]
        return None

    def events(self, fixture_id, since_minute=0):
        raws = self._embedded(fixture_id, "events")
        if raws is None:
            raws = self._get("fixtures/events", fixture=fixture_id).get("response", [])
        out = []
        for raw in raws:
            e = self._norm_event(fixture_id, raw)
            if e and e["minute"] > since_minute:
                out.append(e)
        return out

    def lineups(self, fixture_id):
        sides = self._embedded(fixture_id, "lineups")
        if sides is None:
            sides = self._get("fixtures/lineups", fixture=fixture_id).get("response", [])
        out = {}
        for side in sides:
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
        # No `last=`: free plans refuse that parameter, so take the most
        # recent meetings ourselves.
        doc = self._get("fixtures/headtohead",
                        h2h="%s-%s" % (fx["home_id"], fx["away_id"]))
        past = [self._norm_fixture(i) for i in doc.get("response", [])]
        # The feed lists this fixture among the meetings; it is not "before".
        past = [f for f in past if f["fixture_id"] != fx["fixture_id"]]
        past.sort(key=lambda f: f.get("kickoff") or "", reverse=True)
        return past[:limit]

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
            # "Missed Penalty" arrives as type Goal. It is not a goal.
            if "missed" in detail.lower():
                return None
            # "Normal Goal" is the vendor's filler, not something to read out.
            detail = {"normal goal": "", "own goal": "own goal",
                      "penalty": "penalty"}.get(detail.lower(), detail)
            return self.mk_goal(fixture_id, minute, player, team, assist=assist,
                                detail=detail, stoppage=stoppage)
        if kind == "card":
            # "Yellow Card", "Red Card", "Second Yellow card". A second
            # yellow is a sending-off, so it is a red to the listener.
            low = detail.lower()
            colour = "red" if ("red" in low or "second yellow" in low) else "yellow"
            reason = (raw.get("comments") or "").strip()
            return self.mk_card(fixture_id, minute, player, team, colour,
                                reason=reason[:1].lower() + reason[1:],
                                stoppage=stoppage)
        if kind == "subst":
            return self.mk_sub(fixture_id, minute, on=assist, off=player,
                               team=team, stoppage=stoppage)
        if kind == "var":
            return self.mk_var(fixture_id, minute, decision=detail,
                               player=player, team=team, stoppage=stoppage)
        return None

