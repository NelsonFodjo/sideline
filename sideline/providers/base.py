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


class Provider:
    name = "base"

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
