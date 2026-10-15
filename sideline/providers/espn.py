"""ESPN multi-sport live feed provider.

Public CDN endpoints, zero authentication, real-time updates across multiple sports
including Football (Soccer), Basketball (NBA), American Football (NFL), Baseball (MLB),
and Hockey (NHL).

Normalises ESPN scoreboards and match summaries into Sideline's unified Fixture,
Event, Lineup, and Stats shapes conforming to Provider (see base.py) and SportProfile (see sports/).
"""

import collections
import datetime
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request

from .. import clock, tls
from ..cache import ResponseCache
from ..state.store import Event
from ..status import FINISHED, IN_PLAY
from .base import Provider, ProviderUnavailable

LOG = logging.getLogger("sideline.provider.espn")
TIMEOUT = 6

try:
    import urllib3
    # The same CA bundle logic as the rest of the product (tls.py): without it a Python with no bundle fails every
    # request here, and each one then pays for a second attempt on the slow path. One retry, not urllib3's default three.
    _ESPN_POOL = urllib3.PoolManager(maxsize=16, num_pools=4, ssl_context=tls.context(), retries=urllib3.Retry(total=1))
except Exception:
    _ESPN_POOL = None

# Sideline says "football" for soccer and "american_football" for the NFL; ESPN's URLs say "soccer" and "football".
_ESPN_SPORT = {"football": "soccer", "soccer": "soccer", "american_football": "football"}


def _espn_sport(sideline_sport):
    return _ESPN_SPORT.get(sideline_sport, sideline_sport)


# Supported sports and default leagues: (key, display_name, country, sport_category)
SOCCER_LEAGUES = [
    ("uefa.champions", "UEFA Champions League", "International"),
    ("eng.1", "English Premier League", "England"),
    ("esp.1", "La Liga", "Spain"),
    ("ita.1", "Serie A", "Italy"),
    ("ger.1", "Bundesliga", "Germany"),
    ("fra.1", "Ligue 1", "France"),
    ("usa.1", "Major League Soccer", "USA"),
    ("afc.champions", "AFC Champions League Elite", "Asia"),
    ("afc.cup", "AFC Champions League Two", "Asia"),
    ("uefa.europa", "UEFA Europa League", "International"),
    ("sco.1", "Scottish Premiership", "Scotland"),
    ("ned.1", "Dutch Eredivisie", "Netherlands"),
    ("por.1", "Portuguese Primeira Liga", "Portugal"),
    ("tur.1", "Turkish Süper Lig", "Turkey"),
    ("eng.2", "English Championship", "England"),
    ("eng.fa", "English FA Cup", "England"),
    ("eng.league_cup", "English Carabao Cup", "England"),
    ("uefa.nations", "UEFA Nations League", "International"),
]

BASKETBALL_LEAGUES = [
    ("nba", "NBA", "USA"),
    ("mens-college-basketball", "NCAA Men's Basketball", "USA"),
    ("wnba", "WNBA", "USA"),
]

FOOTBALL_LEAGUES = [
    ("nfl", "NFL", "USA"),
    ("college-football", "NCAA Football", "USA"),
]

BASEBALL_LEAGUES = [
    ("mlb", "MLB", "USA"),
]

HOCKEY_LEAGUES = [
    ("nhl", "NHL", "USA"),
]

ALL_LEAGUES = (
    [(k, n, c, "soccer", "football") for k, n, c in SOCCER_LEAGUES]
    + [(k, n, c, "basketball", "basketball") for k, n, c in BASKETBALL_LEAGUES]
    + [(k, n, c, "football", "american_football") for k, n, c in FOOTBALL_LEAGUES]
    + [(k, n, c, "baseball", "baseball") for k, n, c in BASEBALL_LEAGUES]
    + [(k, n, c, "hockey", "hockey") for k, n, c in HOCKEY_LEAGUES]
)

STATUS_MAP = {
    "STATUS_SCHEDULED": "NS",
    "STATUS_FIRST_HALF": "1H",
    "STATUS_HALFTIME": "HT",
    "STATUS_SECOND_HALF": "2H",
    "STATUS_IN_PROGRESS": "LIVE",
    "STATUS_END_PERIOD": "LIVE",
    "STATUS_FULL_TIME": "FT",
    "STATUS_FINAL": "FT",
    "STATUS_POSTPONED": "PST",
    "STATUS_CANCELED": "CANC",
    "STATUS_ABANDONED": "ABD",
    "STATUS_OVERTIME": "AET",
    "STATUS_SHOOTOUT": "PEN",
}

def _is_finished_summary(doc):
    """Is this match summary of a game that is over? Then it can be kept for hours."""
    try:
        status = ((doc or {}).get("header") or {}).get("competitions")[0].get("status") or {}
        return bool((status.get("type") or {}).get("completed"))
    except (TypeError, IndexError, AttributeError):
        return False


SOCCER_STAT_MAP = {
    "possessionPct": "possession",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "wonCorners": "corners",
    "foulsCommitted": "fouls",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "offsides": "offsides",
    "saves": "saves",
    "accuratePasses": "passes_accurate",
    "totalPasses": "passes_total",
}

POS_NORMALIZATION = {
    "goalkeeper": "goalkeeper",
    "gk": "goalkeeper",
    "defender": "defender",
    "def": "defender",
    "center-back": "defender",
    "left-back": "defender",
    "right-back": "defender",
    "midfielder": "midfielder",
    "mid": "midfielder",
    "central midfielder": "midfielder",
    "attacking midfielder": "midfielder",
    "defensive midfielder": "midfielder",
    "forward": "attacker",
    "fwd": "attacker",
    "striker": "attacker",
    "attacker": "attacker",
    "winger": "attacker",
    "guard": "guard",
    "point guard": "guard",
    "shooting guard": "guard",
    "center": "center",
}


class EspnProvider(Provider):
    name = "espn"
    capabilities = frozenset({
        "fixtures", "events", "lineups", "officials", "h2h", "stats", "search",
        "competitions", "standings", "top_scorers", "injuries", "form",
        "player_stats", "team_matches", "team_stats", "squad", "player_profile", "news"
    })

    def __init__(self, soccer_leagues=None, basketball_leagues=None, football_leagues=None,
                 baseball_leagues=None, hockey_leagues=None, cache_seconds=10):
        self.soccer_leagues = soccer_leagues or [k for k, _, _ in SOCCER_LEAGUES]
        self.basketball_leagues = basketball_leagues or [k for k, _, _ in BASKETBALL_LEAGUES]
        self.football_leagues = football_leagues or [k for k, _, _ in FOOTBALL_LEAGUES]
        self.baseball_leagues = baseball_leagues or [k for k, _, _ in BASEBALL_LEAGUES]
        self.hockey_leagues = hockey_leagues or [k for k, _, _ in HOCKEY_LEAGUES]
        self.cache_seconds = cache_seconds
        self.cache = ResponseCache(max_entries=1024)      # bounded, one request for many askers (sideline/cache.py)
        self.request_count = 0                           # real network requests made, for measuring
        self._requests = collections.deque(maxlen=2000)  # (number, url) of the latest ones
        self._event_meta = {}  # event_id -> (espn_sport, sideline_sport, league)
        self._team_index = {}  # team_name_lower -> (espn_sport, league, team_id, display_name)
        self._fixture_by_id = {}  # fid -> (timestamp, fixture_dict)

    # ------------------------------------------------------------- http
    # How long a page stays good, by kind. What changes while a match is on (the scoreboard, a match in play, a schedule
    # that shows its clock) is kept for seconds, only so that the several tools one question calls share one read.
    # A page that cannot change again is kept for hours. (The policy is BetTrack's idea; the numbers are ours.) First match wins.
    _TTL_BY_KIND = (("/scoreboard", 5.0), ("/standings", 60.0), ("/news", 120.0), ("/schedule", 30.0),
                    ("/injuries", 300.0), ("/statistics", 900.0), ("/roster", 3600.0), ("/athletes/", 3600.0),
                    ("search/v2", 3600.0), ("leagues/dropdown", 86400.0))
    FINISHED_SUMMARY_TTL = 6 * 3600.0       # a match that is over never changes
    LIVE_SUMMARY_TTL = 5.0                  # a match in play: just long enough for one turn's tools to share one read

    def _ttl_for(self, url, data=None):
        if "/summary" in url:
            return self.FINISHED_SUMMARY_TTL if _is_finished_summary(data) else self.LIVE_SUMMARY_TTL
        for needle, seconds in self._TTL_BY_KIND:
            if needle in url:
                return seconds
        return self.cache_seconds

    def _http_get(self, url):
        """The parsed JSON at `url`, or an exception. One logical request: counted once, whichever path answers."""
        self.request_count += 1
        self._requests.append((self.request_count, url))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sideline/2.0",
            "Accept": "application/json",
        }
        if _ESPN_POOL is not None:
            try:
                resp = _ESPN_POOL.request("GET", url, headers=headers, timeout=TIMEOUT)
                if resp.status >= 400:
                    raise RuntimeError("HTTP %d" % resp.status)
                return json.loads(resp.data.decode("utf-8"))
            except Exception as e:                      # fall through to the standard library, once
                LOG.warning("ESPN pool request failed for %s: %s", url, e)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=tls.context()) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _fetch_json(self, url, ttl=None, strict=False):
        """The JSON at `url`: from the cache, or one request shared by everyone asking for it at once. When it cannot
        be had: a recent copy if there is one; else {} - or, with `strict`, ProviderUnavailable, so the caller can say
        the feed is down rather than that nothing is there. Failures are never cached."""
        try:
            return self.cache.get_or_fetch(url, lambda: self._http_get(url), lambda data: ttl or self._ttl_for(url, data))
        except Exception as e:                          # noqa: BLE001 - any failure to fetch or parse is the same to the caller
            LOG.warning("ESPN request failed for %s: %s", url, e)
            found, old = self.cache.stale(url, max(120.0, 5 * (ttl or self._ttl_for(url))) if "/summary" not in url else 600.0)
            if found and "/scoreboard" not in url and ("/summary" not in url or _is_finished_summary(old)):
                return old                             # never an old score: only what cannot have changed since
            if strict:
                raise ProviderUnavailable("I can't reach the match feed right now.")
            return {}

    # --------------------------------------------------------- fixtures
    def _fetch_scoreboard(self, sport, league, date_str=None, limit=None):
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
        params = [p for p in (f"dates={date_str}" if date_str else "", f"limit={limit}" if limit else "") if p]
        if params:
            url += "?" + "&".join(params)
        return self._fetch_json(url, ttl=30.0, strict=True)

    def _league_index(self):
        """{league id: {"slug", "name"}} for every soccer competition ESPN has (about 220), from one request kept for
        a day. A scoreboard event carries only the league's number; this is how it gets a name and a slug."""
        held = getattr(self, "_league_idx", None)
        if held and time.time() < held[0]:
            return held[1]
        idx, keep = {}, 60.0                                  # a failure is retried in a minute, not a day
        try:
            doc = self._fetch_json("https://site.web.api.espn.com/apis/site/v2/leagues/dropdown?sport=soccer&limit=500",
                                   ttl=86400.0, strict=True)
            idx = {str(l["id"]): {"slug": l.get("slug"), "name": l.get("name")} for l in doc.get("leagues") or [] if l.get("id")}
            keep = 86400.0 if idx else 60.0
        except ProviderUnavailable:
            pass
        self._league_idx = (time.time() + keep, idx)
        return idx

    def _all_soccer(self, date_str):
        """Every soccer match on a day, in every competition ESPN covers, from one request. (The default answer is
        cut at 100 matches; limit=500 is what a busy day needs.)"""
        # The league names come from a separate request that does not depend on the scoreboard: ask for both at once.
        names = threading.Thread(target=self._league_index, daemon=True)
        names.start()
        doc = self._fetch_scoreboard("soccer", "all", date_str, limit=500)
        names.join(20)
        idx = self._league_index()
        out = []
        for ev in doc.get("events") or []:
            m = re.search(r"~l:(\d+)", ev.get("uid") or "")
            info = idx.get(m.group(1)) if m else None
            fx = self._norm_fixture(ev, "football", (info or {}).get("slug") or "all")
            if fx:
                if info and info.get("name"):
                    fx["competition"] = info["name"]
                out.append(fx)
        return out

    def _fetch_summary(self, sport, league, event_id):
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary?event={event_id}"
        return self._fetch_json(url)

    def _resolve_league(self, competition_name):
        """Find (espn_sport, sideline_sport, league_key, league_name) for a competition."""
        if not competition_name:
            return "soccer", "football", "eng.1", "English Premier League"
        q = competition_name.strip().lower()
        # Direct key match
        for k, name, country, espn_sport, sideline_sport in ALL_LEAGUES:
            if k == q:
                return espn_sport, sideline_sport, k, name
        # Substring containment
        for k, name, country, espn_sport, sideline_sport in ALL_LEAGUES:
            if q in name.lower() or name.lower() in q:
                return espn_sport, sideline_sport, k, name
        # Keyword checks
        if any(w in q for w in ("premier", "epl", "england")):
            return "soccer", "football", "eng.1", "English Premier League"
        if any(w in q for w in ("champions", "ucl")):
            return "soccer", "football", "uefa.champions", "UEFA Champions League"
        if any(w in q for w in ("la liga", "laliga", "spain")):
            return "soccer", "football", "esp.1", "La Liga"
        if any(w in q for w in ("serie a", "italy")):
            return "soccer", "football", "ita.1", "Serie A"
        if any(w in q for w in ("bundesliga", "germany")):
            return "soccer", "football", "ger.1", "Bundesliga"
        if any(w in q for w in ("ligue 1", "france")):
            return "soccer", "football", "fra.1", "Ligue 1"
        if any(w in q for w in ("mls", "major league soccer")):
            return "soccer", "football", "usa.1", "Major League Soccer"
        if any(w in q for w in ("nba", "basketball", "wnba")):
            return "basketball", "basketball", "nba", "NBA"
        if any(w in q for w in ("nfl", "american football", "college football", "super bowl")):
            return "football", "american_football", "nfl", "NFL"
        if any(w in q for w in ("mlb", "baseball")):
            return "baseball", "baseball", "mlb", "MLB"
        if any(w in q for w in ("nhl", "hockey")):
            return "hockey", "hockey", "nhl", "NHL"
        return "soccer", "football", "eng.1", "English Premier League"

    FIXTURES_SECONDS = 10.0               # the day's list shows who is live and the minute: kept only briefly

    def fixtures_on(self, offset_days=0, sport=None):
        target_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=offset_days)
        date_str = target_date.strftime("%Y%m%d")
        cache_key = (offset_days, sport, date_str)
        now = time.time()
        hit = getattr(self, "_fixtures_cache", {}).get(cache_key)
        if hit and (now - hit[0]) < self.FIXTURES_SECONDS:
            return hit[1]

        league_tasks = []
        # Soccer fixtures
        if not sport or sport in ("football", "soccer"):
            league_tasks.append(("soccer", "football", "all"))        # every competition, one request

        # Basketball fixtures
        if not sport or sport == "basketball":
            for league in self.basketball_leagues:
                league_tasks.append(("basketball", "basketball", league))

        # American football (NFL) fixtures
        if not sport or sport in ("american_football", "nfl", "football"):
            for league in getattr(self, "football_leagues", ["nfl"]):
                league_tasks.append(("football", "american_football", league))

        # Baseball (MLB) fixtures
        if not sport or sport in ("baseball", "mlb"):
            for league in getattr(self, "baseball_leagues", ["mlb"]):
                league_tasks.append(("baseball", "baseball", league))

        # Hockey (NHL) fixtures
        if not sport or sport in ("hockey", "nhl"):
            for league in getattr(self, "hockey_leagues", ["nhl"]):
                league_tasks.append(("hockey", "hockey", league))

        def _fetch_one_league(item):
            espn_s, sideline_s, lg = item
            try:
                if (espn_s, lg) == ("soccer", "all"):
                    return self._all_soccer(date_str)
                doc = self._fetch_scoreboard(espn_s, lg, date_str)
                items = []
                for ev in doc.get("events") or []:
                    fx = self._norm_fixture(ev, sideline_s, lg)
                    if fx:
                        items.append(fx)
                return items
            except ProviderUnavailable:
                return None                      # this league could not be read: not the same as no matches
            except Exception:
                return []

        out = []
        failed = 0
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(16, len(league_tasks) or 1)) as pool:
            for sub_list in pool.map(_fetch_one_league, league_tasks):
                if sub_list is None:
                    failed += 1
                else:
                    out.extend(sub_list)
        if league_tasks and failed == len(league_tasks):
            raise ProviderUnavailable("I can't reach the match feed right now.")

        if not hasattr(self, "_fixtures_cache"):
            self._fixtures_cache = {}
        self._fixtures_cache[cache_key] = (now, out)
        return out

    def warm(self):
        """What the first question needs, fetched before anyone asks: the league names (which never change) and one read of
        today's matches, which opens the connections. The matches themselves are asked for again, live, by every question.
        Never raises; failing to warm costs only that first question's wait."""
        threads = [threading.Thread(target=fn, daemon=True) for fn in (self._league_index, lambda: self.fixtures_on(0))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)

    def fixtures_today(self):
        return self.fixtures_on(0)

    def fixture(self, fixture_id):
        fid = str(fixture_id)
        # Check in-memory fast fixture cache
        cached_fx = getattr(self, "_fixture_by_id", {}).get(fid)
        if cached_fx:
            ts, fx = cached_fx
            if time.time() - ts < 60.0 or fx.get("status") in ("FT", "AET", "PEN", "PST", "CANC", "ABD"):
                return fx

        # Check cached event meta
        meta = self._event_meta.get(fid)
        if meta:
            espn_sport, sideline_sport, league = meta
            summary = self._fetch_summary(espn_sport, league, fid)
            fx = self._norm_fixture_header(summary, sideline_sport, league, fid)
            if fx:
                if not hasattr(self, "_fixture_by_id"):
                    self._fixture_by_id = {}
                self._fixture_by_id[fid] = (time.time(), fx)
                return fx

        # A soccer match whose league is not known yet: its summary answers through `soccer/all`, one request, where
        # scanning three days of every sport's scoreboard is 24. (Not soccer: the request finds nothing, and the scan below runs.)
        doc = self._fetch_json(f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={fid}")
        league = ((doc.get("header") or {}).get("league") or {}).get("slug") or "all"
        fx = self._norm_fixture_header(doc, "football", league, fid) if doc else None
        if fx:
            self._event_meta[fid] = ("soccer", "football", league)
            self._fixture_by_id[fid] = (time.time(), fx)
            return fx

        # Scan today's fixtures first
        for fx in self.fixtures_on(0):
            if str(fx.get("fixture_id")) == fid:
                if not hasattr(self, "_fixture_by_id"):
                    self._fixture_by_id = {}
                self._fixture_by_id[fid] = (time.time(), fx)
                return fx

        # Scan yesterday and tomorrow only if not found today
        for offset in (-1, 1):
            for fx in self.fixtures_on(offset):
                if str(fx.get("fixture_id")) == fid:
                    if not hasattr(self, "_fixture_by_id"):
                        self._fixture_by_id = {}
                    self._fixture_by_id[fid] = (time.time(), fx)
                    return fx
        return None

    def _norm_fixture(self, raw, sport, league):
        fid = str(raw.get("id"))
        espn_sport = _espn_sport(sport)
        self._event_meta[fid] = (espn_sport, sport, league)

        comps = raw.get("competitions") or []
        if not comps:
            return None
        comp = comps[0]

        competitors = comp.get("competitors") or []
        home_side = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away_side = next((c for c in competitors if c.get("homeAway") == "away"), {})

        home_team = (home_side.get("team") or {}).get("displayName") or (home_side.get("team") or {}).get("name") or "Home"
        away_team = (away_side.get("team") or {}).get("displayName") or (away_side.get("team") or {}).get("name") or "Away"

        # Index teams
        h_id = (home_side.get("team") or {}).get("id")
        a_id = (away_side.get("team") or {}).get("id")
        if home_team and h_id:
            self._team_index[home_team.lower()] = (espn_sport, league, h_id, home_team)
        if away_team and a_id:
            self._team_index[away_team.lower()] = (espn_sport, league, a_id, away_team)

        try:
            home_score = int(home_side.get("score") or 0)
        except (ValueError, TypeError):
            home_score = 0
        try:
            away_score = int(away_side.get("score") or 0)
        except (ValueError, TypeError):
            away_score = 0

        status_obj = raw.get("status") or {}
        type_obj = status_obj.get("type") or {}
        raw_state = type_obj.get("name", "")
        status = STATUS_MAP.get(raw_state, "LIVE" if type_obj.get("state") == "in" else ("FT" if type_obj.get("completed") else "NS"))

        # Minute calculation
        display_clock = status_obj.get("displayClock") or "0'"
        clock_val = status_obj.get("clock") or 0.0
        period = status_obj.get("period") or 0

        if sport == "basketball":
            q = max(0, min(period, 4))
            elapsed = (q - 1) * 12 + max(0, int(12 - (clock_val / 60))) if q > 0 else 0
            minute = elapsed
        else:
            try:
                minute = int(float(str(display_clock).replace("'", "").split("+")[0]))
            except (ValueError, TypeError):
                minute = int(clock_val // 60) if clock_val else (45 if status == "HT" else (90 if status == "FT" else 0))

        venue = (comp.get("venue") or {}).get("fullName")
        city = ((comp.get("venue") or {}).get("address") or {}).get("city")
        kickoff = raw.get("date")

        competition_name = league
        for l_key, l_name, _, _, _ in ALL_LEAGUES:
            if l_key == league:
                competition_name = l_name
                break

        res = {
            "fixture_id": fid,
            "sport": sport,
            "home": home_team,
            "away": away_team,
            "home_id": h_id,
            "away_id": a_id,
            "minute": minute,
            "status": status,
            "score": {"home": home_score, "away": away_score},
            "venue": venue,
            "city": city,
            "competition": competition_name,
            "league_id": league,
            "round": None,
            "country": None,
            "kickoff": kickoff,
        }
        if not hasattr(self, "_fixture_by_id"):
            self._fixture_by_id = {}
        self._fixture_by_id[fid] = (time.time(), res)
        return res

    def _norm_fixture_header(self, summary, sport, league, fid):
        header = summary.get("header") or {}
        comps = header.get("competitions") or []
        if not comps:
            return None
        comp = comps[0]
        competitors = comp.get("competitors") or []
        home_side = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away_side = next((c for c in competitors if c.get("homeAway") == "away"), {})

        home_team = (home_side.get("team") or {}).get("displayName") or "Home"
        away_team = (away_side.get("team") or {}).get("displayName") or "Away"
        try:
            h_score = int(home_side.get("score") or 0)
        except (ValueError, TypeError):
            h_score = 0
        try:
            a_score = int(away_side.get("score") or 0)
        except (ValueError, TypeError):
            a_score = 0

        status_obj = comp.get("status") or {}
        type_obj = status_obj.get("type") or {}
        raw_state = type_obj.get("name", "")
        status = STATUS_MAP.get(raw_state, "LIVE" if type_obj.get("state") == "in" else ("FT" if type_obj.get("completed") else "NS"))

        clock_val = status_obj.get("clock") or 0.0
        period = status_obj.get("period") or 0
        if sport == "basketball":
            q = max(0, min(period, 4))
            minute = (q - 1) * 12 + max(0, int(12 - (clock_val / 60))) if q > 0 else 0
        else:
            display_clock = status_obj.get("displayClock") or "0'"
            try:
                minute = int(float(str(display_clock).replace("'", "").split("+")[0]))
            except (ValueError, TypeError):
                minute = int(clock_val // 60) if clock_val else 0

        competition_name = league
        for l_key, l_name, _, _, _ in ALL_LEAGUES:
            if l_key == league:
                competition_name = l_name
                break

        return {
            "fixture_id": fid,
            "sport": sport,
            "home": home_team,
            "away": away_team,
            "home_id": (home_side.get("team") or {}).get("id"),
            "away_id": (away_side.get("team") or {}).get("id"),
            "minute": minute,
            "status": status,
            "score": {"home": h_score, "away": a_score},
            "venue": (summary.get("gameInfo") or {}).get("venue", {}).get("fullName"),
            "city": (summary.get("gameInfo") or {}).get("venue", {}).get("address", {}).get("city"),
            "competition": competition_name,
            "league_id": league,
            "round": None,
            "country": None,
            "kickoff": comp.get("date"),
        }
        if not hasattr(self, "_fixture_by_id"):
            self._fixture_by_id = {}
        self._fixture_by_id[fid] = (time.time(), res)
        return res

    # ----------------------------------------------------------- events
    def events(self, fixture_id, since_minute=0):
        fid = str(fixture_id)
        meta = self._event_meta.get(fid)
        if meta:
            espn_sport, sideline_sport, league = meta
        else:
            fx = self.fixture(fid)
            if fx:
                sideline_sport = fx.get("sport")
                league = fx.get("league_id")
                espn_sport = _espn_sport(sideline_sport)
            else:
                return []

        summary = self._fetch_summary(espn_sport, league, fid)
        if sideline_sport == "basketball":
            return self._basketball_events(fid, summary, since_minute)
        return self._soccer_events(fid, summary, since_minute)

    @staticmethod
    def _clock_minute(display):
        """(minute, stoppage) from ESPN's clock text: "13'", "90'+4'"."""
        m = re.search(r"(\d+)(?:\+(\d+))?", (display or "").replace("'", ""))
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)

    def _penalty_events(self, fid, summary, since_minute):
        """Penalties awarded, from the commentary: who was fouled, who gave it away, who it was awarded to. The
        taking of it (scored, saved, missed) is a key event and is read in _soccer_events."""
        items = summary.get("commentary") or []
        out = []
        for c in items:
            text = c.get("text") or ""
            given = re.match(r"Penalty conceded by (.+?) \(([^)]+)\)", text)
            if not given:
                continue
            minute, stoppage = self._clock_minute((c.get("time") or {}).get("displayValue"))
            if minute <= since_minute:
                continue
            team = fouled = None
            for other in items:
                if self._clock_minute((other.get("time") or {}).get("displayValue")) != (minute, stoppage):
                    continue
                m = re.match(r"Penalty ([^.]+)\. (.+?) draws a foul", other.get("text") or "")
                if m:
                    team, fouled = m.group(1).strip(), m.group(2).strip()
                    break
            official = {re.sub(r"[^a-z]", "", n.lower()): n for n in (
                (t.get("team") or {}).get("displayName") for t in (summary.get("boxscore") or {}).get("teams") or []) if n}
            team = official.get(re.sub(r"[^a-z]", "", (team or "").lower()), team)       # "Paris Saint Germain" -> its proper name
            out.append(Event.make(fid, minute, "penalty", outcome="awarded", player=fouled, team=team or "",
                                  conceded_by=given.group(1).strip(), stoppage=stoppage))
        return out

    def _soccer_events(self, fid, summary, since_minute):
        out = []
        for ke in summary.get("keyEvents") or []:
            text_type = (ke.get("type") or {}).get("text", "")
            minute, stoppage = self._clock_minute((ke.get("clock") or {}).get("displayValue"))
            if minute <= since_minute:
                continue

            participants = ke.get("participants") or []
            names = [(p.get("athlete") or {}).get("displayName") or p.get("displayName") for p in participants]
            player_name = names[0] if names else None
            # The team is on the event itself; the participants carry only the player.
            team_name = (ke.get("team") or {}).get("displayName") or (
                (participants[0].get("team") or {}).get("displayName") if participants else None)
            text = ke.get("text") or ""

            # Fallback extraction from text if participants missing
            if not player_name:
                m_goal = re.search(r"([A-Z][\w\s\-']+)\s*\(([^)]+)\)\s*(?:right|left|header|penalty)", text, re.I | re.UNICODE)
                if m_goal:
                    player_name = m_goal.group(1).strip()
                    team_name = team_name or m_goal.group(2).strip()

            # Penalties: a scored one is a goal; the rest (saved, missed, off the woodwork) are their own event
            if text_type.startswith("Penalty"):
                outcome = text_type.split("-")[-1].strip().lower() if "-" in text_type else "taken"
                if outcome == "scored":
                    out.append(self.mk_goal(fid, minute, player_name or "Unknown", team_name or "",
                                            detail="penalty", stoppage=stoppage))
                    continue
                if not player_name:
                    m_taker = re.match(r"Penalty \w+\. (.+?) \(([^)]+)\)", text)
                    if m_taker:
                        player_name, team_name = m_taker.group(1).strip(), team_name or m_taker.group(2).strip()
                m_keeper = re.search(r" by (.+?) \(", text)
                out.append(Event.make(fid, minute, "penalty", outcome=outcome, player=player_name or "Unknown",
                                      team=team_name or "", keeper=m_keeper.group(1).strip() if m_keeper else None,
                                      stoppage=stoppage))

            # Goals
            elif "Goal" in text_type:
                assist_name = None
                m_ast = re.search(r"Assisted by (.+?)(?: with | following |\.|$)", text, re.UNICODE)
                if m_ast:
                    assist_name = m_ast.group(1).strip()
                detail = "penalty" if "penalty" in text.lower() else ("own goal" if "own goal" in text.lower() else "")
                out.append(self.mk_goal(fid, minute, player_name or "Unknown", team_name or "",
                                        assist=assist_name, detail=detail, stoppage=stoppage))

            # Cards
            elif "Card" in text_type:
                colour = "red" if "Red" in text_type or "red card" in text.lower() else "yellow"
                reason = ""
                m_rsn = re.search(r"for (?:a )?([^.]+)", text)
                if m_rsn:
                    reason = m_rsn.group(1).strip()
                out.append(self.mk_card(fid, minute, player_name or "Unknown", team_name or "",
                                        colour=colour, reason=reason, stoppage=stoppage))

            # Substitutions: ESPN lists the player on, then the player off
            elif "Substitution" in text_type:
                m_sub = re.match(r"(?:Substitution, [^.]+\. )?(.+?) replaces (.+?)\.?$", text.strip(), re.UNICODE)
                on_p = (names[0] if len(names) > 1 else None) or (m_sub.group(1).strip() if m_sub else player_name or "Unknown")
                off_p = (names[1] if len(names) > 1 else None) or (m_sub.group(2).strip() if m_sub else "Unknown")
                out.append(self.mk_sub(fid, minute, on=on_p, off=off_p, team=team_name or "", stoppage=stoppage))

            # VAR
            elif "VAR" in text_type or "VAR" in text:
                out.append(self.mk_var(fid, minute, decision=text[:80], player=player_name, team=team_name, stoppage=stoppage))

        out.extend(self._penalty_events(fid, summary, since_minute))       # the store orders by minute
        return out

    def _basketball_events(self, fid, summary, since_minute):
        out = []
        plays = summary.get("plays") or []
        for p in plays:
            period = p.get("period", {}).get("number", 1)
            q = max(0, min(period, 4))
            clock_disp = p.get("clock", {}).get("displayValue", "0:00")
            mins, secs = 0, 0
            if ":" in clock_disp:
                parts = clock_disp.split(":")
                mins, secs = int(parts[0]), int(parts[1])
            elapsed = (q - 1) * 12 + max(0, 12 - mins)
            if elapsed <= since_minute:
                continue

            text = p.get("text") or ""
            team = p.get("team", {}).get("displayName") or ""
            pts = int(p.get("scoreValue") or 0)

            if p.get("scoringPlay"):
                m = re.match(r"([A-Z][\w\s\-]+?)\s+makes", text, re.UNICODE)
                player = m.group(1).strip() if m else "Unknown"
                out.append(Event.make(fid, elapsed, "basket", points=pts, player=player, team=team, detail=text))
            elif "foul" in text.lower():
                m = re.match(r"Foul on ([A-Z][\w\s\-]+)", text, re.I | re.UNICODE)
                player = m.group(1).strip() if m else None
                out.append(Event.make(fid, elapsed, "foul", player=player, team=team, detail=text))
            elif "timeout" in text.lower():
                out.append(Event.make(fid, elapsed, "timeout", team=team, detail=text))
            elif "ejection" in text.lower() or "ejected" in text.lower():
                out.append(Event.make(fid, elapsed, "ejection", team=team, detail=text))

        return out

    # ---------------------------------------------------------- lineups
    def lineups(self, fixture_id):
        fid = str(fixture_id)
        meta = self._event_meta.get(fid)
        if meta:
            espn_sport, sideline_sport, league = meta
        else:
            fx = self.fixture(fid)
            if fx:
                sideline_sport = fx.get("sport")
                league = fx.get("league_id")
                espn_sport = _espn_sport(sideline_sport)
            else:
                return {}

        summary = self._fetch_summary(espn_sport, league, fid)
        out = {}

        if sideline_sport == "basketball":
            boxscore = summary.get("boxscore") or {}
            for t_data in boxscore.get("players") or []:
                team_name = (t_data.get("team") or {}).get("displayName") or "Team"
                starters = []
                bench = []
                numbers = {}
                stats_list = t_data.get("statistics") or [{}]
                athletes = stats_list[0].get("athletes") or []
                for a_wrap in athletes:
                    ath = a_wrap.get("athlete") or {}
                    name = ath.get("displayName")
                    if not name:
                        continue
                    num = ath.get("jersey")
                    numbers[name] = num
                    if a_wrap.get("starter"):
                        starters.append(name)
                    else:
                        bench.append(name)
                out[team_name] = {"formation": None, "xi": starters, "bench": bench, "numbers": numbers, "coach": None}
            return out

        # Soccer rosters
        rosters = summary.get("rosters") or []
        for r in rosters:
            team_name = (r.get("team") or {}).get("displayName") or "Team"
            starters = []
            bench = []
            numbers, positions, match_stats = {}, {}, {}
            for ath_wrap in r.get("roster") or []:
                ath = ath_wrap.get("athlete") or {}
                name = ath.get("displayName")
                if not name:
                    continue
                numbers[name] = ath_wrap.get("jersey") or ath.get("jersey")       # the shirt number is on the roster entry
                pos = ath_wrap.get("position") or {}
                positions[name] = (pos.get("displayName") or pos.get("name") or pos.get("abbreviation") or "").lower() or None
                got = {}
                for st in ath_wrap.get("stats") or []:                            # what he did in THIS match
                    try:
                        value = int(float(st.get("displayValue")))
                    except (TypeError, ValueError):
                        continue
                    if value:
                        got[st.get("name")] = value
                match_stats[name] = got
                if ath_wrap.get("starter"):
                    starters.append(name)
                else:
                    bench.append(name)
            formation = r.get("formation")
            out[team_name] = {"formation": formation, "xi": starters, "bench": bench, "numbers": numbers,
                              "positions": positions, "match_stats": match_stats, "coach": None}
        return out

    # ------------------------------------------------------ match_stats
    def match_stats(self, fixture_id):
        fid = str(fixture_id)
        meta = self._event_meta.get(fid)
        if meta:
            espn_sport, sideline_sport, league = meta
        else:
            fx = self.fixture(fid)
            if fx:
                sideline_sport = fx.get("sport")
                league = fx.get("league_id")
                espn_sport = _espn_sport(sideline_sport)
            else:
                return {}

        summary = self._fetch_summary(espn_sport, league, fid)
        boxscore = summary.get("boxscore") or {}
        teams = boxscore.get("teams") or []
        out = {}

        for t in teams:
            team_name = (t.get("team") or {}).get("displayName") or "Team"
            st_dict = {}
            for s in t.get("statistics") or []:
                raw_name = s.get("name")
                val = s.get("displayValue") or s.get("value")
                if sideline_sport == "basketball":
                    if raw_name in ("fieldGoalPct", "freeThrowPct", "threePointFieldGoalPct"):
                        try:
                            st_dict[raw_name] = float(val)
                        except (ValueError, TypeError):
                            st_dict[raw_name] = val
                    elif raw_name == "fieldGoalsMade-fieldGoalsAttempted":
                        st_dict["field_goals"] = val
                    elif raw_name == "threePointFieldGoalsMade-threePointFieldGoalsAttempted":
                        st_dict["three_pointers"] = val
                    elif raw_name == "freeThrowsMade-freeThrowsAttempted":
                        st_dict["free_throws"] = val
                    elif raw_name == "rebounds":
                        try:
                            st_dict["rebounds"] = int(val)
                        except Exception:
                            st_dict["rebounds"] = val
                    elif raw_name == "assists":
                        try:
                            st_dict["assists"] = int(val)
                        except Exception:
                            st_dict["assists"] = val
                    elif raw_name == "steals":
                        try:
                            st_dict["steals"] = int(val)
                        except Exception:
                            st_dict["steals"] = val
                    elif raw_name == "blocks":
                        try:
                            st_dict["blocks"] = int(val)
                        except Exception:
                            st_dict["blocks"] = val
                    elif raw_name == "turnovers":
                        try:
                            st_dict["turnovers"] = int(val)
                        except Exception:
                            st_dict["turnovers"] = val
                    elif raw_name == "fouls":
                        try:
                            st_dict["fouls"] = int(val)
                        except Exception:
                            st_dict["fouls"] = val
                else:
                    if raw_name in SOCCER_STAT_MAP:
                        target = SOCCER_STAT_MAP[raw_name]
                        try:
                            st_dict[target] = float(val) if "." in str(val) else int(val)
                        except (ValueError, TypeError):
                            st_dict[target] = val
            out[team_name] = st_dict

        return out

    # -------------------------------------------------------- standings
    def standings(self, competition):
        espn_sport, sideline_sport, league, _ = self._resolve_league(competition)
        url = f"https://site.api.espn.com/apis/v2/sports/{espn_sport}/{league}/standings"
        doc = self._fetch_json(url, ttl=60)

        entries = []
        children = doc.get("children") or []
        if children:
            for child in children:
                st = child.get("standings") or {}
                # a competition played in groups: a row's position means nothing without its group
                entries.extend(dict(e, _group=child.get("name")) if len(children) > 1 else e
                               for e in st.get("entries") or [])
        else:
            entries = (doc.get("standings") or {}).get("entries") or []

        out = []
        for e in entries:
            tm = e.get("team") or {}
            team_name = tm.get("displayName") or tm.get("name")
            if not team_name:
                continue
            stats_dict = {s.get("name"): s.get("value", s.get("displayValue")) for s in e.get("stats") or []}

            try:
                rank = int(stats_dict.get("rank") or stats_dict.get("playoffSeed") or 1)    # US leagues rank by seed
            except Exception:
                rank = 1
            try:
                played = int(stats_dict.get("gamesPlayed") or 0)
            except Exception:
                played = 0
            try:
                points = int(stats_dict.get("points") or 0)
            except Exception:
                points = 0
            try:
                won = int(stats_dict.get("wins") or 0)
            except Exception:
                won = 0
            try:
                lost = int(stats_dict.get("losses") or 0)
            except Exception:
                lost = 0
            try:
                drawn = int(stats_dict.get("ties") or 0)
            except Exception:
                drawn = 0
            try:
                gf = int(stats_dict.get("pointsFor") or 0)
            except Exception:
                gf = 0
            try:
                ga = int(stats_dict.get("pointsAgainst") or 0)
            except Exception:
                ga = 0

            # Register in team index
            t_id = tm.get("id")
            if t_id:
                self._team_index[team_name.lower()] = (espn_sport, league, t_id, team_name)

            keeps_points = sideline_sport in ("football", "hockey")     # a record, not a points total, in the rest
            wins_n = stats_dict.get("wins")
            record = stats_dict.get("overall") or (
                "%d-%d" % (int(float(wins_n)), int(float(stats_dict.get("losses") or 0))) if wins_n not in (None, "") else None)
            out.append({
                "group": e.get("_group"),
                "record": record,
                "position": rank,
                "team": team_name,
                "played": played,
                "points": points if keeps_points else None,
                "won": won,
                "drawn": drawn,
                "lost": lost,
                "goals_for": gf,
                "goals_against": ga,
                "team_id": t_id,
            })

        out.sort(key=lambda r: r["position"])
        return out

    # ------------------------------------------------------- team_stats
    def team_stats(self, team):
        want = (team or "").strip().lower()
        if not want:
            return None

        # Check team index first
        meta = self._team_index.get(want)
        if not meta:
            for k, v in self._team_index.items():
                if want in k or k in want:
                    meta = v
                    break

        if meta:
            _, league, _, _ = meta
            table = self.standings(league)
            for row in table:
                t_name = row["team"].lower()
                if want in t_name or t_name in want:
                    return {
                        "team": row["team"],
                        "played": row["played"],
                        "won": row["won"],
                        "drawn": row["drawn"],
                        "lost": row["lost"],
                        "goals_for": row["goals_for"],
                        "goals_against": row["goals_against"],
                        "clean_sheets": None,
                        "possession": None,
                    }

        # Fallback: scan primary leagues
        for league in (self.soccer_leagues + self.basketball_leagues)[:6]:
            table = self.standings(league)
            for row in table:
                t_name = row["team"].lower()
                if want in t_name or t_name in want:
                    return {
                        "team": row["team"],
                        "played": row["played"],
                        "won": row["won"],
                        "drawn": row["drawn"],
                        "lost": row["lost"],
                        "goals_for": row["goals_for"],
                        "goals_against": row["goals_against"],
                        "clean_sheets": None,
                        "possession": None,
                    }

        return None

    # ------------------------------------------------------------ squad
    def squad(self, team):
        want = (team or "").strip().lower()
        if not want:
            return None

        # Look up team id from index or search
        meta = self._team_index.get(want)
        if not meta:
            for k, v in self._team_index.items():
                if want in k or k in want:
                    meta = v
                    break

        if not meta:
            # Query ESPN search for team
            res = self.search(team, kind="team")
            if res:
                team_hit = res[0]
                t_id = team_hit.get("id")
                # Try in primary leagues
                meta = ("soccer", "eng.1", t_id, team_hit.get("name"))

        if not meta:
            return None

        espn_sport, league, t_id, display_name = meta
        url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{league}/teams/{t_id}/roster"
        data = self._fetch_json(url, ttl=120)

        athletes = data.get("athletes") or []
        players = []
        for a in athletes:
            name = a.get("displayName")
            if not name:
                continue
            num = a.get("jersey")
            pos_raw = (a.get("position") or {}).get("name", "").lower()
            norm_pos = POS_NORMALIZATION.get(pos_raw, pos_raw or "attacker")
            players.append({"name": name, "number": num, "position": norm_pos})

        coaches = data.get("coach") or []
        coach_name = None
        if coaches:
            c0 = coaches[0]
            coach_name = c0.get("displayName") or f"{c0.get('firstName', '')} {c0.get('lastName', '')}".strip() or None

        return {
            "team": display_name,
            "coach": coach_name,
            "captain": None,
            "players": players,
        }

    # ------------------------------------------------------ top_scorers
    def top_scorers(self, competition):
        espn_sport, sideline_sport, league, _ = self._resolve_league(competition)
        url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{league}/statistics"
        data = self._fetch_json(url, ttl=120)

        stats_list = data.get("stats") or []
        target_cat = "goalsLeaders" if espn_sport == "soccer" else "points"
        cat = next((c for c in stats_list if target_cat in c.get("name", "")), None)
        if not cat and stats_list:
            cat = stats_list[0]

        if not cat:
            return []

        out = []
        for l in cat.get("leaders") or []:
            ath = l.get("athlete") or {}
            player_name = ath.get("displayName")
            if not player_name:
                continue
            tm = l.get("team") or ath.get("team") or {}
            team_name = tm.get("displayName") or tm.get("name")
            val = int(l.get("value") or 0)
            out.append({"player": player_name, "team": team_name, "goals": val})

        return out

    # ----------------------------------------------------- player_stats
    def _find_player(self, want, team=None):
        """The search hit for a player. Several people share a name: the one on the team asked about, else the one
        whose name matches exactly, else the first."""
        url = "https://site.api.espn.com/apis/search/v2?query=%s" % urllib.parse.quote(want)
        res = self._fetch_json(url, ttl=3600.0, strict=True)
        hits = [c for g in res.get("results") or [] if g.get("type") == "player" for c in g.get("contents") or []]
        if not hits:
            return None
        canon = lambda t: re.sub(r"[^a-z]", "", (t or "").lower())      # noqa: E731
        return next((c for c in hits if team and canon(team) and canon(team) in canon(c.get("subtitle"))), None) \
            or next((c for c in hits if canon(c.get("displayName")) == canon(want)), None) or hits[0]

    def news(self, team=None, competition=None, limit=5):
        """Headlines for a team, or a competition, or football in general, newest first, from ESPN's news feed."""
        want = (team or "").strip()
        if want:
            found = self._find_team(want.lower())
            if not found:
                return None
            sport, league, t_id, official = found
            url = "https://site.api.espn.com/apis/site/v2/sports/%s/%s/news?team=%s&limit=%d" % (sport, league or "all", t_id, limit)
            scope = official or want
        elif competition:
            sport, _sl, league, name = self._resolve_league(competition)
            url = "https://site.api.espn.com/apis/site/v2/sports/%s/%s/news?limit=%d" % (sport, league, limit)
            scope = name
        else:
            url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/news?limit=%d" % limit
            scope = "football"
        articles = self._fetch_json(url, strict=True).get("articles") or []
        out = [{"headline": a.get("headline"), "summary": a.get("description"), "published": a.get("published")}
               for a in articles if a.get("headline")]
        return {"scope": scope, "articles": out[:limit]} if out else None

    def player_profile(self, player, team=None):
        """Who a player is: name, age, nationality, position, club, shirt number. ESPN carries no honours or career
        titles, so `honours` is None and the caller must say it does not have them."""
        want = (player or "").strip()
        hit = self._find_player(want, team) if want else None
        if not hit:
            return None
        uid = hit.get("uid") or ""
        ath_id = uid.split(":")[-1] if ":" in uid else hit.get("id")
        sport = hit.get("sport") or "soccer"
        a = (self._fetch_json("https://site.web.api.espn.com/apis/common/v3/sports/%s/athletes/%s" % (sport, ath_id),
                              ttl=3600.0, strict=True).get("athlete")) or {}
        if not a:
            return None
        position = a.get("position") or {}
        club = a.get("team") or {}
        return {"name": a.get("displayName") or hit.get("displayName") or want, "age": a.get("age"),
                "nationality": a.get("citizenship"), "position": (position.get("displayName") or "").lower() or None,
                "team": club.get("displayName") or hit.get("subtitle"), "number": a.get("jersey") or None,
                "gender": (a.get("gender") or "").lower() or None, "sport": sport, "honours": None}

    # Competitions a player plays for his country, not his club. ESPN lists them all as one season.
    _NATIONAL = ("nations league", "world cup", "international", "european championship", "uefa euro", "copa america",
                 "africa cup", "asian cup", "gold cup", "qualif", "olympic")

    def _soccer_season(self, name, team, names, splits):
        """This season for the club and, separately, for his country: adding them is how a goal for Portugal
        became a goal for Paris Saint-Germain. ESPN gives starts, not appearances, so starts is what is said."""
        club = {"starts": 0, "goals": 0, "assists": 0}
        country = {"starts": 0, "goals": 0, "assists": 0}
        seen_club = seen_country = False
        for sp in splits:
            vals = dict(zip(names, sp.get("stats") or []))
            national = any(w in (sp.get("displayName") or "").lower() for w in self._NATIONAL)
            bucket = country if national else club
            seen_country, seen_club = seen_country or national, seen_club or not national
            for key, raw in (("starts", "starts"), ("goals", "totalGoals"), ("assists", "goalAssists")):
                try:
                    bucket[key] += int(vals.get(raw) or 0)
                except (ValueError, TypeError):
                    pass
        return {"name": name, "team": team, "starts": club["starts"] if seen_club else None,
                "goals": club["goals"] if seen_club else None, "assists": club["assists"] if seen_club else None,
                "international": dict(country) if seen_country else None}

    def player_stats(self, player, team=None):
        want = (player or "").strip()
        if not want:
            return None

        p_item = self._find_player(want, team)
        if not p_item:
            return None

        uid = p_item.get("uid") or ""
        ath_id = uid.split(":")[-1] if ":" in uid else p_item.get("id")
        sport = p_item.get("sport") or "soccer"
        disp_name = p_item.get("displayName") or want
        team_name = p_item.get("subtitle") or team

        # Fetch athlete overview
        ov_url = f"https://site.web.api.espn.com/apis/common/v3/sports/{sport}/athletes/{ath_id}/overview"
        ov_data = self._fetch_json(ov_url, ttl=120)

        st = ov_data.get("statistics") or {}
        names = st.get("names") or []
        splits = st.get("splits") or []

        if sport == "soccer":
            return self._soccer_season(disp_name, team_name, names, splits)

        apps, goals, assists = 0, 0, 0
        points, rebounds = None, None

        for sp in splits:
            stat_vals = dict(zip(names, sp.get("stats") or []))
            try:
                apps += int(stat_vals.get("starts") or stat_vals.get("gamesPlayed") or 0)
            except Exception:
                pass
            try:
                goals += int(stat_vals.get("totalGoals") or 0)
            except Exception:
                pass
            try:
                assists += int(stat_vals.get("goalAssists") or 0)
            except Exception:
                pass
            if "PTS" in stat_vals:
                try:
                    points = (points or 0) + int(stat_vals.get("PTS") or 0)
                except Exception:
                    pass
            if "REB" in stat_vals:
                try:
                    rebounds = (rebounds or 0) + int(stat_vals.get("REB") or 0)
                except Exception:
                    pass

        return {
            "name": disp_name,
            "team": team_name,
            "appearances": apps if apps > 0 else None,
            "goals": goals if goals > 0 else None,
            "assists": assists if assists > 0 else None,
            "points": points,
            "rebounds": rebounds,
        }

    # ------------------------------------------------------------- form
    def form(self, fixture_id):
        fid = str(fixture_id)
        meta = self._event_meta.get(fid)
        if meta:
            espn_sport, sideline_sport, league = meta
        else:
            fx = self.fixture(fid)
            if fx:
                sideline_sport = fx.get("sport")
                league = fx.get("league_id")
                espn_sport = _espn_sport(sideline_sport)
            else:
                return {}

        summary = self._fetch_summary(espn_sport, league, fid)
        l5 = summary.get("lastFiveGames") or []
        fx = self.fixture(fid) or {}
        home_side, away_side = fx.get("home"), fx.get("away")

        out = {}
        for item in l5:
            tm_name = (item.get("team") or {}).get("displayName")
            results = [e.get("gameResult") for e in item.get("events") or [] if e.get("gameResult")]
            form_str = "".join(reversed(results))
            if tm_name:
                if home_side and (home_side.lower() in tm_name.lower() or tm_name.lower() in home_side.lower()):
                    out["home"] = form_str
                elif away_side and (away_side.lower() in tm_name.lower() or tm_name.lower() in away_side.lower()):
                    out["away"] = form_str
                else:
                    if "home" not in out:
                        out["home"] = form_str
                    elif "away" not in out:
                        out["away"] = form_str

        return out

    # ----------------------------------------------------- head_to_head
    def head_to_head(self, fixture_id, limit=5):
        fid = str(fixture_id)
        meta = self._event_meta.get(fid)
        if meta:
            espn_sport, sideline_sport, league = meta
        else:
            fx = self.fixture(fid)
            if fx:
                sideline_sport = fx.get("sport")
                league = fx.get("league_id")
                espn_sport = _espn_sport(sideline_sport)
            else:
                return []

        summary = self._fetch_summary(espn_sport, league, fid)
        seasonseries = summary.get("seasonseries") or []
        out = []

        for series in seasonseries:
            for ev in series.get("events") or []:
                comps = ev.get("competitors") or []
                home_c = next((c for c in comps if c.get("homeAway") == "home"), {})
                away_c = next((c for c in comps if c.get("homeAway") == "away"), {})
                h_name = (home_c.get("team") or {}).get("displayName") or "Home"
                a_name = (away_c.get("team") or {}).get("displayName") or "Away"
                try:
                    h_score = int(home_c.get("score") or 0)
                    a_score = int(away_c.get("score") or 0)
                except Exception:
                    h_score, a_score = 0, 0
                out.append({"home": h_name, "away": a_name, "score": {"home": h_score, "away": a_score}, "date": ev.get("date")})

        return out[:limit]

    # ----------------------------------------------------------- search
    def search(self, query, kind="team"):
        q = (query or "").strip()
        if not q:
            return []

        url = f"https://site.api.espn.com/apis/search/v2?query={urllib.parse.quote(q)}"
        data = self._fetch_json(url, ttl=60)
        out = []

        for res in data.get("results") or []:
            res_type = res.get("type")
            if kind == "team" and res_type != "team":
                continue
            if kind == "player" and res_type != "player":
                continue

            for c in res.get("contents") or []:
                name = c.get("displayName")
                c_id = c.get("id")
                country = c.get("description") or c.get("subtitle") or "International"
                out.append({"kind": kind, "name": name, "id": c_id, "country": country})

        # Fallback to local known teams / competitions if search/v2 had no match
        if not out and kind == "team":
            for team in self.known_teams():
                if q.lower() in team.lower():
                    out.append({"kind": "team", "name": team, "id": team, "country": "International"})
        elif not out and kind == "competition":
            for c in self.competitions():
                if q.lower() in c["name"].lower():
                    out.append({"kind": "competition", "name": c["name"], "id": c["id"], "country": c.get("country")})

        return out

    # --------------------------------------------------------- injuries
    def injuries(self, fixture_id):
        fid = str(fixture_id)
        meta = self._event_meta.get(fid)
        if meta:
            espn_sport, sideline_sport, league = meta
        else:
            fx = self.fixture(fid)
            if fx:
                sideline_sport = fx.get("sport")
                league = fx.get("league_id")
                espn_sport = _espn_sport(sideline_sport)
            else:
                return []

        summary = self._fetch_summary(espn_sport, league, fid)
        if "injuries" not in summary:
            return None                      # the feed gave no injury report at all: that is not the same as none
        out = []
        inj_groups = summary.get("injuries") or []
        for group in inj_groups:
            team_name = (group.get("team") or {}).get("displayName")
            for inj in group.get("injuries") or []:
                ath = inj.get("athlete") or {}
                name = ath.get("displayName")
                details = inj.get("details") or {}
                reason = details.get("type") or inj.get("status") or "Injured"
                if name:
                    out.append({"player": name, "team": team_name, "reason": reason})
        return out

    # -------------------------------------------------------- officials
    def officials(self, fixture_id):
        fid = str(fixture_id)
        meta = self._event_meta.get(fid)
        if meta:
            espn_sport, sideline_sport, league = meta
        else:
            fx = self.fixture(fid)
            if fx:
                sideline_sport = fx.get("sport")
                league = fx.get("league_id")
                espn_sport = _espn_sport(sideline_sport)
            else:
                return {}

        summary = self._fetch_summary(espn_sport, league, fid)
        game_info = summary.get("gameInfo") or {}
        officials_list = game_info.get("officials") or []
        ref = officials_list[0].get("displayName") if officials_list else None
        return {"referee": ref, "yellows": None, "reds": None}

    # ------------------------------------------------- entity discovery
    def known_teams(self):
        teams = set()
        for fx in self.fixtures_today():
            if fx.get("home"):
                teams.add(fx["home"])
            if fx.get("away"):
                teams.add(fx["away"])
        return sorted(teams)

    def competitions(self, country=None):
        out = []
        for key, name, c_country in SOCCER_LEAGUES:
            if not country or country.lower() in c_country.lower():
                out.append({"id": key, "name": name, "country": c_country})
        for key, name, c_country in BASKETBALL_LEAGUES:
            if not country or country.lower() in c_country.lower():
                out.append({"id": key, "name": name, "country": c_country})
        for key, name, c_country in FOOTBALL_LEAGUES:
            if not country or country.lower() in c_country.lower():
                out.append({"id": key, "name": name, "country": c_country})
        for key, name, c_country in BASEBALL_LEAGUES:
            if not country or country.lower() in c_country.lower():
                out.append({"id": key, "name": name, "country": c_country})
        for key, name, c_country in HOCKEY_LEAGUES:
            if not country or country.lower() in c_country.lower():
                out.append({"id": key, "name": name, "country": c_country})
        return out

    # espn sport -> Sideline sport, for fixtures read from a team schedule
    _SIDELINE_SPORT = {"soccer": "football", "football": "american_football"}

    def _find_team(self, want):
        """(espn_sport, league, team_id) for a team name: from teams already seen, else one search request."""
        for name, (espn_sport, league, t_id, display) in list(self._team_index.items()):
            if name == want:
                return espn_sport, league, t_id, display
        words = " ".join(re.sub(r"[^\w\s]", " ", want).split())            # "bodo/glimt" -> "bodo glimt": ESPN's search finds nothing with the slash
        url = "https://site.web.api.espn.com/apis/search/v2?query=%s&limit=5&type=team" % urllib.parse.quote(words or want)
        for group in self._fetch_json(url, ttl=3600.0, strict=True).get("results") or []:
            for hit in group.get("contents") or []:
                match = re.search(r"~t:(\d+)", hit.get("uid") or "")
                slug = hit.get("defaultLeagueSlug") or ""
                if match and hit.get("sport") in ("soccer", "basketball", "football", "baseball", "hockey") \
                        and ".w." not in slug and "women" not in slug:
                    return hit["sport"], slug, match.group(1), hit.get("displayName")
        return None

    def _schedule_fixture(self, ev, espn_sport, default_league):
        """A team-schedule event in the shape of a scoreboard event, then through the usual parser."""
        comp = (ev.get("competitions") or [{}])[0]
        competitors = []
        for c in comp.get("competitors") or []:
            score = c.get("score")
            competitors.append(dict(c, score=score.get("displayValue") if isinstance(score, dict) else score))
        raw = dict(ev, status=comp.get("status") or {}, competitions=[dict(comp, competitors=competitors)])
        league = (ev.get("league") or {}).get("slug") or default_league
        return self._norm_fixture(raw, self._SIDELINE_SPORT.get(espn_sport, espn_sport), league)

    def _refreshed(self, fx):
        """The live version of a match in play: its own summary, with the schedule's other fields kept."""
        fid = str(fx["fixture_id"])
        self._fixture_by_id.pop(fid, None)
        try:
            fresh = self.fixture(fid)
        except ProviderUnavailable:
            return fx
        return dict(fx, **{k: v for k, v in (fresh or {}).items() if v not in (None, "")}) if fresh else fx

    def team_matches(self, team, days_back=30, days_ahead=30):
        """A team's recent and coming matches across every competition, from its own schedule: a search request
        for the team and one for its schedule, instead of a scoreboard per league per day."""
        want = (team or "").strip().lower()
        if not want:
            return None
        found = self._find_team(want)
        if found:
            espn_sport, league, t_id, official = found
            where = "all" if espn_sport == "soccer" else league          # soccer: every competition at once
            base = "https://site.api.espn.com/apis/site/v2/sports/%s/%s/teams/%s/schedule" % (espn_sport, where, t_id)
            # ESPN lists what has been played, or with fixture=true what is still to come, never both in one answer.
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as pool:
                played, coming = pool.map(lambda u: self._fetch_json(u, ttl=60.0, strict=True), (base, base + "?fixture=true"))
            now = datetime.datetime.now(datetime.timezone.utc)
            recent, upcoming, seen = [], [], set()
            for ev in (played.get("events") or []) + (coming.get("events") or []):
                if ev.get("id") in seen:
                    continue
                seen.add(ev.get("id"))
                fx = self._schedule_fixture(ev, espn_sport, league)
                if fx and fx.get("status") in IN_PLAY:
                    fx = self._refreshed(fx)                  # a schedule's clock for a match in play is stale
                ko = clock.kickoff(fx) if fx else None
                if not fx or ko is None or not now - datetime.timedelta(days=days_back) <= ko <= now + datetime.timedelta(days=days_ahead):
                    continue
                (recent if fx.get("status") in FINISHED else upcoming).append((ko, fx))
            if recent or upcoming:
                return {"team": official or team, "team_id": t_id,          # the official name, not the typo or nickname
                        "upcoming": [fx for _, fx in sorted(upcoming, key=lambda p: p[0])],
                        "recent": [fx for _, fx in sorted(recent, key=lambda p: p[0], reverse=True)]}
        return self._team_matches_scan(team)

    def _team_matches_scan(self, team):
        """The slow way, for a team the search cannot find: a scoreboard per league for each of five days."""
        want = (team or "").strip().lower()
        if not want:
            return None

        upcoming = []
        recent = []
        team_id = None

        for offset in (0,):                  # the search found no such team: today's list is the most worth trying
            for fx in self.fixtures_on(offset):
                h, a = (fx.get("home") or "").lower(), (fx.get("away") or "").lower()
                if want in h or want in a:
                    if want in h and fx.get("home_id"):
                        team_id = fx.get("home_id")
                    elif want in a and fx.get("away_id"):
                        team_id = fx.get("away_id")

                    if fx.get("status") in ("FT", "AET", "PEN"):
                        recent.append(fx)
                    else:
                        upcoming.append(fx)

        if not upcoming and not recent:
            return None
        return {"team": team, "team_id": team_id, "upcoming": upcoming, "recent": recent}
