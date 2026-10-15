"""Match data providers.

A provider turns somebody's sports API into our internal Event shape.
The fixture it returns carries a `sport` key (absent means football); the
event kinds it emits are that sport's (see sideline/sports/).
Nothing above this layer knows which vendor we are using, so another feed
(or a test double: tests/support.py) can stand in for it.

Contract:

    fixtures_today()             -> [fixture dicts]
    fixture(fixture_id)          -> fixture dict | None
    events(fixture_id, since=0)  -> [Event]
    lineups(fixture_id)          -> {team: {...}}
    officials(fixture_id)        -> {...}
    head_to_head(fixture_id, n)  -> [past results]
    fixtures_on(offset_days)     -> [fixture dicts] for today, tomorrow (1) or yesterday (-1)

Normalising rules, which exist because every vendor gets these wrong in
a different way:

  * Minute is an integer. Stoppage time "45+2" becomes 45 with
    `stoppage: 2`, because a listener asking "when was that" wants to
    hear "just before half time", not "forty five plus two".
  * A goal that VAR overturns is NOT deleted. It gets a second event of
    kind "var" and the original is marked superseded. A listener who
    heard the goal needs to be told it was chalked off.
  * Own goals and penalties are goals with a `detail`, not separate
    kinds. Otherwise every consumer has to know three kinds mean "the
    score changed".
"""

from ..state.store import Event


class ProviderUnavailable(Exception):
    """The data feed refused or could not be reached (key, quota, plan, network).

    Raised by providers; the MCP layer turns it into a spoken decline.
    """


# What a feed can supply. Tools are listed only when the feed behind them can answer, so the
# model is never offered a tool that would fail. (Whether a feed's PLAN allows a thing is a
# separate matter: a refusal is spoken in the vendor's own words.)
CAPABILITIES = ("fixtures", "events", "lineups", "officials", "h2h", "form", "stats",
                "injuries", "search", "competitions", "standings", "top_scorers", "player_stats",
                "team_matches", "team_stats", "squad", "player_profile", "news")


class Provider:
    name = "base"
    capabilities = frozenset({"fixtures", "events", "lineups", "officials"})

    def fixtures_today(self):
        raise NotImplementedError

    def fixture(self, fixture_id):
        raise NotImplementedError

    def events(self, fixture_id, since_minute=0):
        raise NotImplementedError

    def lineups(self, fixture_id):
        raise NotImplementedError

    def officials(self, fixture_id):
        raise NotImplementedError

    def head_to_head(self, fixture_id, limit=5):
        return []

    # Optional reads. A provider that implements one lists it in `capabilities`.
    def search(self, query, kind="team"):
        """[{"kind": "team"|"player"|"competition", "name", "id", "country"}] for a name."""
        raise NotImplementedError

    def competitions(self, country=None):
        """[{"id", "name", "country"}] the feed covers (a free plan covers a few)."""
        raise NotImplementedError

    def standings(self, competition):
        """[{"position", "team", "played", "points"}] for a competition named in words, or None."""
        raise NotImplementedError

    def top_scorers(self, competition):
        """[{"player", "team", "goals"}] for a competition named in words, or None."""
        raise NotImplementedError

    def match_stats(self, fixture_id):
        """{team: {"possession": 62, "shots": 12, "shots_on_target": 6, "corners": 5, ...}}"""
        raise NotImplementedError

    def news(self, team=None, competition=None, limit=5):
        """{"scope": what the headlines are about, "articles": [{"headline", "summary", "published" (ISO)}]} or None."""
        raise NotImplementedError

    def player_profile(self, player, team=None):
        """{"name", "age", "nationality", "position", "team", "number", "honours": None or [titles]} or None."""
        raise NotImplementedError

    def player_stats(self, player, team=None):
        """{"name", "team", "goals", "assists", "appearances", ...} for this season, or None."""
        raise NotImplementedError

    def injuries(self, fixture_id):
        """[{"player", "team", "reason"}] ruled out of this match."""
        raise NotImplementedError

    def form(self, fixture_id):
        """{"home": "WWDLW", "away": "LDWWW"}: each side's recent results, W/D/L."""
        raise NotImplementedError

    def team_matches(self, team, days_back=90, days_ahead=45):
        """{"team", "upcoming": [fixtures soonest first], "recent": [finished fixtures latest first]} or None."""
        raise NotImplementedError

    def known_teams(self):
        """The names of the teams in the competitions covered (for "did you mean"), or raise NotImplementedError."""
        raise NotImplementedError

    def squad(self, team):
        """{"team", "coach", "captain", "players": [{"name", "number", "position"}]} or None."""
        raise NotImplementedError

    def team_stats(self, team):
        """{"team", "played", "won", "drawn", "lost", "goals_for", "goals_against", "clean_sheets", ...} or None."""
        raise NotImplementedError

    def fixtures_on(self, offset_days=0):
        """Fixtures `offset_days` from today (0, 1, -1), or [] where the feed cannot see that day."""
        return self.fixtures_today() if offset_days == 0 else []

    # --------------------------------------------------------- helpers
    @staticmethod
    def mk_goal(fixture_id, minute, player, team, assist=None, detail=None,
                score_before=None, score_after=None, stoppage=0):
        return Event.make(fixture_id, minute, "goal", player=player, team=team,
                          assist=assist, detail=detail or "",
                          score_before=score_before, score_after=score_after,
                          stoppage=stoppage)

    @staticmethod
    def mk_card(fixture_id, minute, player, team, colour, reason=None, stoppage=0):
        return Event.make(fixture_id, minute, "card", player=player, team=team,
                          colour=colour, reason=reason or "", stoppage=stoppage)

    @staticmethod
    def mk_sub(fixture_id, minute, on, off, team, stoppage=0):
        return Event.make(fixture_id, minute, "substitution", player=on,
                          player_off=off, team=team, stoppage=stoppage)

    @staticmethod
    def mk_var(fixture_id, minute, decision, player=None, team=None,
               overturns=None, stoppage=0):
        return Event.make(fixture_id, minute, "var", decision=decision,
                          player=player, team=team, overturns=overturns,
                          stoppage=stoppage)
