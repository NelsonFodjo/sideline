"""Sportmonks football (API v3), the live feed.

The token is read from SPORTMONKS_TOKEN and sent in the Authorization header, so it never
appears in a URL or a log. This provider turns the vendor's shapes into ours (see base.py):
minutes are integers with stoppage split off, a missed penalty is not a goal, a second yellow is
a red, and a refused request is an error with the vendor's own words, never "no such match".

Includes are Sportmonks' way of embedding related data: one fixture request carries the
participants, scores, state, venue, events, lineups and formations, so a followed match costs
one request per poll.

Checked against the live service on a real finished match (2026-10-12): the fixture, goals with
assists, substitutions (`player_name` came on, `related_player_name` went off), cards, VAR notes
(`addition`), line-ups and formations, referee, statistics, head to head, standings, top scorers,
injuries (`sidelined`), form (a team's fixtures between two dates) and a player's season. Not yet
seen during a match in play: the free plan's four leagues had none on. The tests pin the shapes
with invented data; `make verify-data` is how to check again.
"""

import datetime
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import tls
from ..status import FINISHED, OVER
from .base import Provider, ProviderUnavailable

LOG = logging.getLogger("sideline.provider")
BASE = "https://api.sportmonks.com/v3/football"
TIMEOUT = 8
HOURLY_CALLS = 180          # the free plan, per kind of data (rate_limit in every response says what is left)

FIXTURE_INCLUDES = "participants;league.country;venue;state;scores;periods"
DETAIL_INCLUDES = FIXTURE_INCLUDES + ";events.type;lineups;formations;referees.referee"

# Fallback type ids (Sportmonks' public type list), used only when an event carries no
# `type` object with a developer name.
_EVENT_TYPE_IDS = {10: "var", 14: "goal", 15: "owngoal", 16: "penalty", 17: "missedpenalty",
                   18: "substitution", 19: "yellowcard", 20: "redcard", 21: "yellowredcard"}
_LINEUP_STARTER, _LINEUP_BENCH = 11, 12


_LABEL_ONLY = re.compile(r"^(\d+(st|nd|rd|th)\s+)?(yellow|red|second yellow)\s*-?\s*cards?$", re.I)


def _kind(event):
    """The event's kind as one lowercase word: goal, owngoal, penalty, yellowcard, var ..."""
    t = event.get("type") or {}
    name = (t.get("developer_name") or t.get("code") or "").replace("_", "").replace(" ", "").lower()
    return name or _EVENT_TYPE_IDS.get(event.get("type_id"), "")


def _status(state):
    """Sportmonks' state, as the short codes the rest of Sideline already speaks (NS, 1H, HT, 2H, FT ...)."""
    s = state or {}
    name = ((s.get("developer_name") or s.get("short_name") or s.get("name") or "")
            .upper().replace(" ", "_"))
    if not name:
        return None
    for needle, code in (("NOT_STARTED", "NS"), ("POSTPONED", "PST"), ("CANCEL", "CANC"),
                         ("ABANDON", "ABD"), ("SUSPEND", "SUSP"), ("INTERRUPT", "INT"),
                         ("PENALT", "P"), ("EXTRA", "ET"), ("1ST", "1H"), ("FIRST", "1H"),
                         ("2ND", "2H"), ("SECOND", "2H"), ("HALF_TIME", "HT"), ("HALFTIME", "HT"),
                         ("BREAK", "HT"), ("AET", "AET"), ("FT_PEN", "PEN"), ("FINISHED", "FT"),
                         ("FULL_TIME", "FT"), ("INPLAY", "LIVE")):
        if needle in name:
            return code
    return {"NS": "NS", "HT": "HT", "FT": "FT", "TBA": "NS"}.get(name, name)


def _iso(raw):
    """Sportmonks' "2026-10-13 19:00:00" (UTC) as ISO 8601, or None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.datetime.fromtimestamp(raw, datetime.timezone.utc).isoformat()
    try:
        return datetime.datetime.strptime(str(raw)[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone.utc).isoformat()
    except ValueError:
        return str(raw)


class SportmonksProvider(Provider):
    name = "sportmonks"

    def __init__(self, token, cache_seconds=12):
        self.token = token
        self.cache_seconds = cache_seconds
        self._cache = {}

    # ------------------------------------------------------------ http
    def _get(self, path, _ttl=None, **params):
        """Cached GET. The cache is a correctness measure: every call counts against the hourly limit."""
        key = (path, tuple(sorted(params.items())))
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < (_ttl or self.cache_seconds):
            return hit[1]

        url = "%s/%s?%s" % (BASE, path.lstrip("/"), urllib.parse.urlencode(params, safe=";,."))
        req = urllib.request.Request(url, headers={"Authorization": self.token,
                                                   "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=tls.context()) as r:
                doc = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable(self._http_problem(e))
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            LOG.warning("provider %s failed: %s", path, e)
            raise ProviderUnavailable(str(e))
        limit = doc.get("rate_limit") or {}
        if limit.get("remaining") is not None and limit["remaining"] < 20:
            LOG.warning("sportmonks: %s calls left this hour for %s (resets in %ss)",
                        limit["remaining"], limit.get("requested_entity"), limit.get("resets_in_seconds"))
        self._cache[key] = (time.time(), doc)
        return doc

    @staticmethod
    def _http_problem(e):
        """The vendor's own words, so the listener hears what happened and not a guess."""
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:                                    # noqa: BLE001
            body = {}
        message = body.get("message") or body.get("error") or ""
        if isinstance(message, dict):
            message = json.dumps(message)
        if e.code == 429:
            try:
                minutes = max(1, int(body.get("retry_after")) // 60)
            except (TypeError, ValueError):
                minutes = None
            return "rateLimit: %s%s" % (message or "Too many requests this hour",
                                        " Try again in about %d minutes." % minutes if minutes else "")
        if e.code in (401, 403):
            return "token: %s" % (message or "Sportmonks refused the token (HTTP %d)" % e.code)
        return "HTTP %d: %s" % (e.code, message or e.reason)

    @staticmethod
    def _data(doc):
        data = doc.get("data")
        return data if data is not None else []

    # ----------------------------------------------------------- reads
    def fixture(self, fixture_id):
        doc = self._get("fixtures/%s" % fixture_id, include=DETAIL_INCLUDES)
        raw = doc.get("data")
        return self._norm_fixture(raw) if isinstance(raw, dict) else None

    def fixtures_today(self):
        return self.fixtures_on(0)

    def fixtures_on(self, offset_days=0):
        """One day's fixtures (UTC), for the leagues the plan covers. One request, kept five minutes."""
        day = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=offset_days)).strftime("%Y-%m-%d")
        doc = self._get("fixtures/date/%s" % day, _ttl=300, include=FIXTURE_INCLUDES)
        return [self._norm_fixture(i) for i in self._data(doc) if isinstance(i, dict)]

    def events(self, fixture_id, since_minute=0):
        raw = self._detail(fixture_id)
        teams = self._sides(raw)
        out = []
        for e in raw.get("events") or []:
            ev = self._norm_event(fixture_id, e, teams)
            if ev and ev["minute"] > since_minute:
                out.append(ev)
        return out

    def lineups(self, fixture_id):
        raw = self._detail(fixture_id)
        sides = self._sides(raw)
        formations = {f.get("participant_id"): f.get("formation") for f in raw.get("formations") or []}
        out = {}
        for p in raw.get("participants") or []:
            out[p.get("name")] = {"formation": formations.get(p.get("id")), "xi": [], "numbers": {},
                                  "bench": [], "coach": None}
        for row in raw.get("lineups") or []:
            team = sides.get(row.get("team_id"))
            name = row.get("player_name")
            if team is None or not name:
                continue
            if row.get("type_id") == _LINEUP_STARTER:
                out[team]["xi"].append(name)
                out[team]["numbers"][name] = row.get("jersey_number")
            elif row.get("type_id") == _LINEUP_BENCH:
                out[team]["bench"].append(name)
        return {t: v for t, v in out.items() if v["xi"] or v["bench"] or v["formation"]}

    def officials(self, fixture_id):
        raw = self._detail(fixture_id)
        referee = None
        for entry in raw.get("referees") or []:
            who = entry.get("referee") if isinstance(entry.get("referee"), dict) else entry
            referee = (who.get("display_name") or who.get("common_name") or who.get("name")
                       or who.get("fullname"))
            if referee:
                break
        return {"referee": referee, "venue": (raw.get("venue") or {}).get("name")}

    def head_to_head(self, fixture_id, limit=5):
        fx = self.fixture(fixture_id)
        if not fx or not fx.get("home_id") or not fx.get("away_id"):
            return []
        doc = self._get("fixtures/head-to-head/%s/%s" % (fx["home_id"], fx["away_id"]),
                        _ttl=1800, include="participants;scores;state")
        past = [self._norm_fixture(i) for i in self._data(doc) if isinstance(i, dict)]
        past = [f for f in past if f["fixture_id"] != fx["fixture_id"]]
        past.sort(key=lambda f: f.get("kickoff") or "", reverse=True)
        return past[:limit]

    # ---- the optional reads
    capabilities = frozenset({"fixtures", "events", "lineups", "officials", "h2h", "stats", "search",
                              "competitions", "standings", "top_scorers", "injuries", "form", "player_stats", "team_matches",
                              "team_stats", "squad"})

    def _hits(self, path, kind, query):
        doc = self._get("%s/search/%s" % (path, urllib.parse.quote(query)), _ttl=3600)
        return [{"kind": kind, "name": i.get("display_name") or i.get("name") or i.get("common_name"),
                 "id": i.get("id"), "country": None} for i in self._data(doc) if isinstance(i, dict)]

    def search(self, query, kind="team"):
        return self._hits({"team": "teams", "player": "players", "competition": "leagues"}.get(kind, "teams"),
                          kind, query)

    def competitions(self, country=None):
        doc = self._get("leagues", _ttl=3600, include="country")
        out = [{"id": i.get("id"), "name": i.get("name"),
                "country": (i.get("country") or {}).get("name") if isinstance(i.get("country"), dict) else None}
               for i in self._data(doc) if isinstance(i, dict)]
        if country:
            out = [c for c in out if country.lower() in (c.get("country") or "").lower()]
        return out

    def _team(self, name):
        """The team a name means: one named exactly beats a longer name that merely contains it."""
        from .. import resolve
        hits = [h for h in self.search(name, "team") if h.get("id")]
        want = resolve.words(name)
        exact = [h for h in hits if resolve.words(h["name"]) == want]
        return (exact or hits or [None])[0]

    def team_matches(self, team, days_back=90, days_ahead=45):
        """A team's matches around now: what is coming, and how the last ones finished (one request, kept ten minutes)."""
        found = self._team(team)
        if not found:
            return None
        today = datetime.datetime.now(datetime.timezone.utc).date()
        doc = self._get("fixtures/between/%s/%s/%s" % (today - datetime.timedelta(days=days_back),
                                                     today + datetime.timedelta(days=days_ahead), found["id"]),
                        _ttl=600, include=FIXTURE_INCLUDES)
        every = [self._norm_fixture(i) for i in self._data(doc) if isinstance(i, dict)]
        done = sorted((f for f in every if f["status"] in FINISHED), key=lambda f: f.get("kickoff") or "", reverse=True)
        ahead = sorted((f for f in every if f["status"] not in OVER), key=lambda f: f.get("kickoff") or "")
        return {"team": found["name"], "team_id": found["id"], "upcoming": ahead, "recent": done}

    def squad(self, team):
        """A team's players (name, shirt number, position), its captain and its manager."""
        found = self._team(team)
        if not found:
            return None
        rows = self._data(self._get("squads/teams/%s" % found["id"], _ttl=1800, include="player.position"))
        players = []
        for r in rows:
            who = r.get("player") or {}
            name = who.get("display_name") or who.get("common_name") or who.get("name")
            if name:
                players.append({"name": name, "number": r.get("jersey_number"),
                                "position": ((who.get("position") or {}).get("name") or "").lower() or None,
                                "captain": bool(r.get("captain"))})
        coach = None
        try:
            team_doc = self._get("teams/%s" % found["id"], _ttl=1800, include="coaches.coach").get("data") or {}
            for c in team_doc.get("coaches") or []:
                if c.get("active") and isinstance(c.get("coach"), dict):
                    coach = c["coach"].get("display_name") or c["coach"].get("common_name")
                    break
        except ProviderUnavailable:
            pass
        captain = next((p["name"] for p in players if p["captain"]), None)
        return {"team": found["name"], "coach": coach, "captain": captain, "players": players}

    def team_stats(self, team):
        """This season's record for a team: games, results, goals, clean sheets, possession."""
        found = self._team(team)
        if not found:
            return None
        raw = self._get("teams/%s" % found["id"], _ttl=600, include="statistics.details.type").get("data") or {}
        seasons = [s for s in raw.get("statistics") or [] if s.get("has_values") and s.get("details")]
        if not seasons:
            return None
        latest = max(seasons, key=lambda s: s.get("season_id") or 0)
        got = {(d.get("type") or {}).get("developer_name"): d.get("value") or {} for d in latest["details"]}

        def count(name):
            v = got.get(name) or {}
            return (v.get("all") or v).get("count")
        return {"team": raw.get("name") or found["name"], "played": (got.get("GAMES_PLAYED") or {}).get("total"),
                "won": count("WIN"), "drawn": count("DRAW"), "lost": count("LOST"),
                "goals_for": count("GOALS"), "goals_against": count("GOALS_CONCEDED"),
                "clean_sheets": count("CLEANSHEET"),
                "possession": (got.get("BALL_POSSESSION") or {}).get("average"),
                "corners_per_game": (got.get("CORNERS") or {}).get("average")}

    def _season(self, competition):
        """The current season id of a competition named in words, or None."""
        want = " ".join(competition.lower().split())
        doc = self._get("leagues", _ttl=3600, include="currentSeason")
        for i in self._data(doc):
            if isinstance(i, dict) and (i.get("name") or "").lower() == want:
                return (i.get("currentseason") or i.get("currentSeason") or {}).get("id")
        for i in self._data(doc):
            if isinstance(i, dict) and want in (i.get("name") or "").lower():
                return (i.get("currentseason") or i.get("currentSeason") or {}).get("id")
        return None

    def standings(self, competition):
        season = self._season(competition)
        if not season:
            return None
        doc = self._get("standings/seasons/%s" % season, _ttl=600, include="participant")
        return [{"position": r.get("position"), "team": (r.get("participant") or {}).get("name"),
                 "played": None, "points": r.get("points")} for r in self._data(doc) if isinstance(r, dict)]

    def top_scorers(self, competition):
        season = self._season(competition)
        if not season:
            return None
        doc = self._get("topscorers/seasons/%s" % season, _ttl=600, include="player;participant",
                        filters="seasontopscorerTypes:208")
        return [{"player": (r.get("player") or {}).get("display_name") or (r.get("player") or {}).get("name"),
                 "team": (r.get("participant") or {}).get("name"), "goals": r.get("total") or 0}
                for r in self._data(doc) if isinstance(r, dict)]

    def injuries(self, fixture_id):
        """Players ruled out, from the fixture's `sidelined` (a long injury stays until its end date)."""
        raw = self._get("fixtures/%s" % fixture_id,
                        include="participants;sidelined.sideline.player;sidelined.sideline.type").get("data") or {}
        teams = self._sides(raw)
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        out = []
        for entry in raw.get("sidelined") or []:
            s = entry.get("sideline") or {}
            if s.get("completed") or (s.get("end_date") and s["end_date"] < today):
                continue
            who = s.get("player") or {}
            name = (who.get("display_name") or who.get("name") or who.get("common_name") or "").strip()
            if name:
                out.append({"player": name, "team": teams.get(entry.get("participant_id")),
                            "reason": (s.get("type") or {}).get("name")})
        return out

    def form(self, fixture_id):
        """Each side's last five finished results before this match, as W/D/L (oldest first)."""
        fx = self.fixture(fixture_id)
        if not fx or not fx.get("kickoff"):
            return None
        end = datetime.datetime.fromisoformat(fx["kickoff"]).date()
        start = end - datetime.timedelta(days=90)
        out = {}
        for side, team_id in (("home", fx.get("home_id")), ("away", fx.get("away_id"))):
            if not team_id:
                out[side] = ""
                continue
            doc = self._get("fixtures/between/%s/%s/%s" % (start, end, team_id), _ttl=1800,
                            include="participants;scores;state")
            past = [self._norm_fixture(i) for i in self._data(doc) if isinstance(i, dict)]
            past = [f for f in past if f["fixture_id"] != fx["fixture_id"] and f["status"] in ("FT", "AET", "PEN")
                    and (f.get("kickoff") or "") < fx["kickoff"]]
            past.sort(key=lambda f: f["kickoff"])
            letters = []
            for f in past[-5:]:
                mine, theirs = (f["score"]["home"], f["score"]["away"]) if f["home_id"] == team_id \
                    else (f["score"]["away"], f["score"]["home"])
                letters.append("W" if mine > theirs else "L" if mine < theirs else "D")
            out[side] = "".join(letters)
        return out if any(out.values()) else None

    def player_stats(self, player, team=None):
        """This season's appearances, goals and assists for the best name match, from the latest season listed."""
        from .. import resolve
        hits = self._data(self._get("players/search/%s" % urllib.parse.quote(player), _ttl=3600))
        want = player.lower().split()
        scored = sorted(((resolve.similarity(want, (h.get("display_name") or h.get("name") or "").lower().split()), h)
                         for h in hits if isinstance(h, dict)), key=lambda p: -p[0])
        if not scored or scored[0][0] < 0.6:
            return None
        best = scored[0][1]
        raw = self._get("players/%s" % best["id"], _ttl=600, include="statistics.details.type").get("data") or {}
        seasons = [s for s in raw.get("statistics") or [] if s.get("details")]
        if not seasons:
            return None
        latest = max(seasons, key=lambda s: s.get("season_id") or 0)
        got = {(d.get("type") or {}).get("developer_name"): (d.get("value") or {}).get("total")
               for d in latest["details"]}
        return {"name": best.get("display_name") or best.get("name"), "team": None,
                "goals": got.get("GOALS"), "assists": got.get("ASSISTS"), "appearances": got.get("APPEARANCES")}

    _STAT_KEYS = {"BALLPOSSESSION": "possession", "SHOTSTOTAL": "shots", "SHOTSONTARGET": "shots_on_target",
                  "CORNERS": "corners", "FOULS": "fouls", "YELLOWCARDS": "yellow_cards",
                  "REDCARDS": "red_cards", "OFFSIDES": "offsides"}

    def match_stats(self, fixture_id):
        raw = self._get("fixtures/%s" % fixture_id, include="participants;statistics.type").get("data") or {}
        teams = self._sides(raw)
        out = {}
        for s in raw.get("statistics") or []:
            t = s.get("type") or {}
            key = self._STAT_KEYS.get((t.get("developer_name") or t.get("code") or "").replace("_", "").upper())
            value = (s.get("data") or {}).get("value", s.get("value"))
            if key and value is not None:
                out.setdefault(teams.get(s.get("participant_id")), {})[key] = value
        return out

    # ------------------------------------------------------ normalising
    def _detail(self, fixture_id):
        raw = self._get("fixtures/%s" % fixture_id, include=DETAIL_INCLUDES).get("data")
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _sides(raw):
        """participant id -> team name, and "home"/"away" -> the same, for one fixture."""
        out = {}
        for p in raw.get("participants") or []:
            out[p.get("id")] = p.get("name")
            out[(p.get("meta") or {}).get("location")] = p.get("name")
        return out

    @staticmethod
    def _minute(raw):
        """The match minute: the ticking period's clock, else what the state implies."""
        periods = raw.get("periods") or []
        ticking = [p for p in periods if p.get("ticking")]
        if ticking:
            return int(ticking[-1].get("minutes") or 0)
        status = _status(raw.get("state"))
        if status == "HT":
            return 45
        if status in ("FT", "AET", "PEN"):
            return int(max([p.get("minutes") or 0 for p in periods] + [90]))
        return 0

    def _norm_fixture(self, raw):
        parts = {(p.get("meta") or {}).get("location"): p for p in raw.get("participants") or []}
        home, away = parts.get("home") or {}, parts.get("away") or {}
        goals = {"home": 0, "away": 0}
        for s in raw.get("scores") or []:
            if s.get("description") == "CURRENT":
                side = (s.get("score") or {}).get("participant")
                if side in goals:
                    goals[side] = (s.get("score") or {}).get("goals") or 0
        league = raw.get("league") or {}
        country = league.get("country") or {}
        venue = raw.get("venue") or {}
        return {
            "fixture_id": raw.get("id"),
            "home": home.get("name"), "away": away.get("name"),
            "home_id": home.get("id"), "away_id": away.get("id"),
            "minute": self._minute(raw),
            "status": _status(raw.get("state")),
            "score": goals,
            "venue": venue.get("name"),
            "city": venue.get("city_name"),
            "competition": league.get("name"),
            "league_id": league.get("id"),
            "round": None,
            "country": country.get("name") if isinstance(country, dict) else None,
            "kickoff": _iso(raw.get("starting_at_timestamp") or raw.get("starting_at")),
        }

    def _norm_event(self, fixture_id, raw, teams):
        kind = _kind(raw)
        minute = int(raw.get("minute") or 0)
        stoppage = int(raw.get("extra_minute") or 0)
        team = teams.get(raw.get("participant_id"))
        player, other = raw.get("player_name"), raw.get("related_player_name")
        note = (raw.get("addition") or raw.get("info") or "").strip()
        if _LABEL_ONLY.match(note):                  # "1st Yellowcard" restates the card: it is not a reason
            note = ""

        if kind in ("goal", "owngoal", "penalty"):
            detail = {"owngoal": "own goal", "penalty": "penalty"}.get(kind, "")
            return self.mk_goal(fixture_id, minute, player, team, assist=other if kind == "goal" else None,
                                detail=detail, stoppage=stoppage)
        if kind in ("yellowcard", "redcard", "yellowredcard"):
            colour = "red" if kind in ("redcard", "yellowredcard") else "yellow"
            return self.mk_card(fixture_id, minute, player, team, colour,
                                reason=note[:1].lower() + note[1:], stoppage=stoppage)
        if kind in ("substitution", "sub"):
            # Sportmonks: player_name is the player who came on, related_player_name the one replaced.
            return self.mk_sub(fixture_id, minute, on=player, off=other, team=team, stoppage=stoppage)
        if kind in ("var", "varcard"):
            return self.mk_var(fixture_id, minute, decision=note or "reviewed", player=player,
                               team=team, stoppage=stoppage)
        return None            # a missed penalty, a shootout kick, anything that is not news
