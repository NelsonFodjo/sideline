"""ESPN multi-sport live feed provider.

Public CDN endpoints, zero authentication, real-time updates across multiple sports
including Football (Soccer), Basketball (NBA), American Football (NFL), Baseball (MLB),
and Hockey (NHL).

Normalises ESPN scoreboards and match summaries into Sideline's unified Fixture,
Event, Lineup, and Stats shapes conforming to Provider (see base.py) and SportProfile (see sports/).
"""

import datetime
import json
import logging
import re
import time
import urllib.parse
import urllib.request

from ..state.store import Event
from .base import Provider, ProviderUnavailable

LOG = logging.getLogger("sideline.provider.espn")
TIMEOUT = 6

try:
    import urllib3
    _ESPN_POOL = urllib3.PoolManager(maxsize=16, num_pools=4)
except Exception:
    _ESPN_POOL = None

# Supported sports and default leagues: (key, display_name, country, sport_category)
SOCCER_LEAGUES = [
    ("uefa.champions", "UEFA Champions League", "International"),
    ("eng.1", "English Premier League", "England"),
    ("esp.1", "La Liga", "Spain"),
    ("ita.1", "Serie A", "Italy"),
    ("ger.1", "Bundesliga", "Germany"),
    ("fra.1", "Ligue 1", "France"),
    ("usa.1", "Major League Soccer", "USA"),
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

SOCCER_STAT_MAP = {
    "possessionPct": "possession",
    "totalShots": "shots",
    "shotsOnTarget": "shots_on_target",
    "wonCorners": "corners",
    "foulsCommitted": "fouls",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
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
        "player_stats", "team_matches", "team_stats", "squad"
    })

    def __init__(self, soccer_leagues=None, basketball_leagues=None, football_leagues=None,
                 baseball_leagues=None, hockey_leagues=None, cache_seconds=10):
        self.soccer_leagues = soccer_leagues or [k for k, _, _ in SOCCER_LEAGUES]
        self.basketball_leagues = basketball_leagues or [k for k, _, _ in BASKETBALL_LEAGUES]
        self.football_leagues = football_leagues or [k for k, _, _ in FOOTBALL_LEAGUES]
        self.baseball_leagues = baseball_leagues or [k for k, _, _ in BASEBALL_LEAGUES]
        self.hockey_leagues = hockey_leagues or [k for k, _, _ in HOCKEY_LEAGUES]
        self.cache_seconds = cache_seconds
        self._cache = {}
        self._event_meta = {}  # event_id -> (espn_sport, sideline_sport, league)
        self._team_index = {}  # team_name_lower -> (espn_sport, league, team_id, display_name)
        self._fixture_by_id = {}  # fid -> (timestamp, fixture_dict)

    # ------------------------------------------------------------- http
    def _fetch_json(self, url, ttl=None):
        hit = self._cache.get(url)
        now = time.time()
        if hit and (now - hit[0]) < (ttl or self.cache_seconds):
            return hit[1]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sideline/2.0",
            "Accept": "application/json",
        }
        if _ESPN_POOL is not None:
            try:
                resp = _ESPN_POOL.request("GET", url, headers=headers, timeout=TIMEOUT)
                data = json.loads(resp.data.decode("utf-8"))
                self._cache[url] = (now, data)
                return data
            except Exception as e:
                LOG.warning("ESPN pool request failed for %s: %s", url, e)
                if hit:
                    return hit[1]

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._cache[url] = (now, data)
                return data
        except Exception as e:
            LOG.warning("ESPN request failed for %s: %s", url, e)
            if hit:
                return hit[1]
            return {}

    # --------------------------------------------------------- fixtures
    def _fetch_scoreboard(self, sport, league, date_str=None):
        url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
        if date_str:
            url += f"?dates={date_str}"
        return self._fetch_json(url, ttl=30.0)

    def _fetch_summary(self, sport, league, event_id):
        espn_sport = "soccer" if sport in ("football", "soccer") else sport
        url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_sport}/{league}/summary?event={event_id}"
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

    def fixtures_on(self, offset_days=0, sport=None):
        target_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=offset_days)
        date_str = target_date.strftime("%Y%m%d")
        cache_key = (offset_days, sport, date_str)
        now = time.time()
        hit = getattr(self, "_fixtures_cache", {}).get(cache_key)
        if hit and (now - hit[0]) < 60.0:
            return hit[1]

        league_tasks = []
        # Soccer fixtures
        if not sport or sport in ("football", "soccer"):
            for league in self.soccer_leagues:
                league_tasks.append(("soccer", "football", league))

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
                doc = self._fetch_scoreboard(espn_s, lg, date_str)
                items = []
                for ev in doc.get("events") or []:
                    fx = self._norm_fixture(ev, sideline_s, lg)
                    if fx:
                        items.append(fx)
                return items
            except Exception:
                return []

        out = []
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(16, len(league_tasks) or 1)) as pool:
            for sub_list in pool.map(_fetch_one_league, league_tasks):
                out.extend(sub_list)

        if not hasattr(self, "_fixtures_cache"):
            self._fixtures_cache = {}
        self._fixtures_cache[cache_key] = (now, out)
        return out

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
        espn_sport = "soccer" if sport == "football" else sport
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
                espn_sport = "soccer" if sideline_sport == "football" else sideline_sport
            else:
                return []

        summary = self._fetch_summary(espn_sport, league, fid)
        if sideline_sport == "basketball":
            return self._basketball_events(fid, summary, since_minute)
        return self._soccer_events(fid, summary, since_minute)

    def _soccer_events(self, fid, summary, since_minute):
        out = []
        key_events = summary.get("keyEvents") or []
        for ke in key_events:
            t = ke.get("type") or {}
            text_type = t.get("text", "")
            clock_obj = ke.get("clock") or {}
            display = clock_obj.get("displayValue") or "0'"
            m_match = re.search(r"(\d+)(?:\+(\d+))?", display)
            minute = int(m_match.group(1)) if m_match else 0
            stoppage = int(m_match.group(2)) if m_match and m_match.group(2) else 0

            if minute <= since_minute:
                continue

            participants = ke.get("participants") or []
            player_name = None
            team_name = None
            if participants:
                p0 = participants[0]
                player_name = p0.get("athlete", {}).get("displayName") or p0.get("displayName")
                team_name = p0.get("team", {}).get("displayName")

            text = ke.get("text") or ""

            # Fallback extraction from text if participants missing
            if not player_name:
                m_goal = re.search(r"([A-Z][\w\s\-]+)\s*\(([^)]+)\)\s*(?:right|left|header|penalty)", text, re.I | re.UNICODE)
                if m_goal:
                    player_name = m_goal.group(1).strip()
                    team_name = m_goal.group(2).strip()

            # Goals
            if "Goal" in text_type:
                assist_name = None
                m_ast = re.search(r"Assisted by ([\w\s\-]+)\.", text, re.UNICODE)
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

            # Substitutions
            elif "Substitution" in text_type:
                m_sub = re.search(r"([\w\s\-]+) replaces ([\w\s\-]+)", text, re.UNICODE)
                on_p = m_sub.group(1).strip() if m_sub else player_name or "Unknown"
                off_p = m_sub.group(2).strip() if m_sub else "Unknown"
                out.append(self.mk_sub(fid, minute, on=on_p, off=off_p, team=team_name or "", stoppage=stoppage))

            # VAR
            elif "VAR" in text_type or "VAR" in text:
                out.append(self.mk_var(fid, minute, decision=text[:80], player=player_name, team=team_name, stoppage=stoppage))

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
                espn_sport = "soccer" if sideline_sport == "football" else sideline_sport
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
            numbers = {}
            for ath_wrap in r.get("roster") or []:
                ath = ath_wrap.get("athlete") or {}
                name = ath.get("displayName")
                if not name:
                    continue
                num = ath.get("jersey")
                numbers[name] = num
                if ath_wrap.get("starter"):
                    starters.append(name)
                else:
                    bench.append(name)
            formation = r.get("formation")
            out[team_name] = {"formation": formation, "xi": starters, "bench": bench, "numbers": numbers, "coach": None}
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
                espn_sport = "soccer" if sideline_sport == "football" else sideline_sport
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
                entries.extend(st.get("entries") or [])
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
                rank = int(stats_dict.get("rank") or 1)
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

            out.append({
                "position": rank,
                "team": team_name,
                "played": played,
                "points": points,
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
    def player_stats(self, player, team=None):
        want = (player or "").strip()
        if not want:
            return None

        # Search for athlete
        url = f"https://site.api.espn.com/apis/search/v2?query={urllib.parse.quote(want)}"
        res = self._fetch_json(url, ttl=60)
        p_item = None
        for r_group in res.get("results") or []:
            if r_group.get("type") == "player":
                for c in r_group.get("contents") or []:
                    p_item = c
                    break
            if p_item:
                break

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
            "appearances": apps if apps > 0 else 1,
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
                espn_sport = "soccer" if sideline_sport == "football" else sideline_sport
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
                espn_sport = "soccer" if sideline_sport == "football" else sideline_sport
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
                espn_sport = "soccer" if sideline_sport == "football" else sideline_sport
            else:
                return []

        summary = self._fetch_summary(espn_sport, league, fid)
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
                espn_sport = "soccer" if sideline_sport == "football" else sideline_sport
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

    def team_matches(self, team, days_back=30, days_ahead=30):
        want = (team or "").strip().lower()
        if not want:
            return None

        upcoming = []
        recent = []
        team_id = None

        for offset in (0, 1, 2, -1, -2):
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
