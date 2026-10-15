"""The sixteen tools beyond the core eleven: discovery, tables, statistics, people, favourites.

Run against the invented fixture through the test double. Pinned here: what each says (numbers said as
words, times in the listener's clock), that a missing thing is said and never guessed, that favourites are
only what the listener gave, that tools are listed only where the feed can answer them, and that the voice
agent can be held to the core eleven.
"""

import datetime
import os

from conftest import make_ctx

from sideline import clock
from sideline.mcp import registry
from sideline.mcp.errors import ToolError
from sideline.tools import REGISTRY, ordinal

UTC = datetime.timezone.utc


def run(ctx, name, listener="ann", **args):
    return REGISTRY[name](ctx, args, listener)


def declines(ctx, name, listener="ann", **args):
    try:
        REGISTRY[name](ctx, args, listener)
    except ToolError as e:
        return e
    raise AssertionError("%s should have declined: %r" % (name, args))


def main():
    real_now = clock.now
    clock.now = lambda: datetime.datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
    try:
        ctx = make_ctx(start_minute=40)
        run(ctx, "follow_match", team="Arsenal")
        rec = ctx.store.listener("ann"); rec["tz_offset_minutes"] = 240; rec["tz_name"] = "Indian/Mauritius"
        ctx.store.save_listener(rec)

        # numbers as words
        assert [ordinal(n) for n in (1, 2, 3, 10, 11, 12, 21, 22, 23, 101)] == [
            "first", "second", "third", "tenth", "11th", "12th", "21st", "22nd", "23rd", "101st"]

        # ---------------------------------------------------------- discover
        spoken, s, _ = run(ctx, "search", query="Arsenal")
        assert spoken == "I found these: Arsenal (Inventland), Arsenal W (Inventland).", spoken
        assert run(ctx, "search", query="Saka", kind="player")[0] == "I found this: Bukayo Saka (Inventland)."
        assert declines(ctx, "search", query="Zzzzz").spoken == "I couldn't find a team called Zzzzz."
        spoken, _, _ = run(ctx, "get_competitions")
        assert spoken == "I can cover 2 competitions: Premier League (Inventland), Invented Cup (Inventland).", spoken
        assert declines(ctx, "get_competitions", country="Nowhere").detail["reason"] == "no_match"
        print("ok  search and competitions: the closest names, with countries; nothing found is said")

        from sideline.tools import no_team
        ctx.provider.known_teams = lambda: ["Celtic", "Rangers", "Brøndby IF"]
        assert no_team(ctx, "Selltic").spoken == "I can't find Selltic. Did you mean Celtic?"
        assert no_team(ctx, "Ranjers").detail["did_you_mean"] == "Rangers"
        assert "Did you mean" not in no_team(ctx, "Arsenal").spoken, "a real team that is not covered is not 'corrected'"
        del ctx.provider.known_teams
        print("ok  a misheard team name is offered the covered team it sounds like, never silently swapped")

        # ---------------------------------------------------------- standings and scorers
        spoken, s, _ = run(ctx, "get_standings")                    # the followed match's competition
        assert spoken == ("The Premier League table: First, Arsenal, 20 points. Second, Tottenham, 18 points. "
                          "Third, Chelsea, 15 points. Fourth, Villa, 14 points. Fifth, Brighton, 12 points."), spoken
        spoken, _, _ = run(ctx, "get_standings", team="Everton")
        assert spoken == "In the Premier League, Everton are sixth with 1 point from 8 games. Arsenal lead with 20 points.", spoken
        assert run(ctx, "get_standings", team="Arsenal")[0].startswith("In the Premier League, Arsenal are first with 20 points")
        assert declines(ctx, "get_standings", team="Nobody").detail["reason"] == "no_match"
        assert declines(ctx, "get_standings", competition="La Liga").spoken == "I can't see a table for La Liga."
        spoken, _, _ = run(ctx, "get_top_scorers")
        assert spoken == ("Top scorers in the Premier League: Bukayo Saka, Arsenal, 7 goals. "
                          "Son Heung-min, Tottenham, 6 goals. A Third, Chelsea, 1 goal."), spoken
        fresh = make_ctx(start_minute=40)
        assert declines(fresh, "get_standings", "nobody").detail["reason"] == "no_competition", \
            "no match followed and none named: it asks which competition"
        # a team named with no competition and no match followed: its league is found from its own matches
        fresh.provider.team_matches = lambda team, **kw: {"team": team, "recent": [
            {"competition": "Invented Cup"}, {"competition": "Premier League"}], "upcoming": []}
        spoken, _, _ = run(fresh, "get_standings", "nobody", team="Arsenal")
        assert spoken.startswith("In the Premier League, Arsenal are first with 20 points"), spoken
        fresh.provider.team_matches = lambda team, **kw: None
        assert declines(fresh, "get_standings", "nobody", team="Arsenal").detail["reason"] == "no_competition"
        print("ok  the table (said as first, second...), one team's place, the top scorers; no competition asks which")

        # ---------------------------------------------------------- schedule
        spoken, s, _ = run(ctx, "get_schedule", team="Arsenal")
        assert spoken.startswith("Arsenal, in Mauritius time: Arsenal against Tottenham"), spoken
        assert declines(ctx, "get_schedule", team="Zzyzx").spoken.endswith("yesterday, today or tomorrow.")
        print("ok  a team's schedule: its matches in the window with times, the zone said once")

        # top scorers of one team
        assert run(ctx, "get_top_scorers", team="Chelsea")[0] == "Chelsea's top scorers in the Premier League: A Third, Chelsea, 1 goal.", \
            run(ctx, "get_top_scorers", team="Chelsea")[0]
        assert declines(ctx, "get_top_scorers", team="Everton").detail["reason"] == "no_match"

        # stop following
        spoken, s, _ = run(ctx, "follow_match", stop=True)
        assert spoken == "Okay, I've stopped following Arsenal against Tottenham." and s["stopped"], spoken
        assert ctx.store.listener("ann")["following"] is None
        assert run(ctx, "follow_match", stop=True)[0] == "You aren't following a match."
        run(ctx, "follow_match", team="Arsenal")
        print("ok  a team's top scorers; stop following, said once and then plainly")

        # following a team whose next match is days away: it is followed, and said to be not started
        later = {"fixture_id": 9001, "home": "Everton", "away": "Villa", "minute": 0, "status": "NS", "score": {"home": 0, "away": 0},
                 "competition": "Premier League", "country": "Inventland",
                 "kickoff": (clock.now() + datetime.timedelta(days=5)).isoformat()}
        far = make_ctx(start_minute=0)
        far.provider.capabilities = set(far.provider.capabilities) | {"team_matches"}
        far.provider.team_matches = lambda team, **kw: {"team": team, "upcoming": [later], "recent": []}
        far.provider.fixture = (lambda real: lambda fid: later if fid == 9001 else real(fid))(far.provider.fixture)
        spoken, s, _ = run(far, "follow_match", team="Everton")
        assert spoken.startswith("Following Everton against Villa. Not started yet."), spoken
        assert far.store.listener("ann")["following"] == 9001
        print("ok  follow a team with no match within a day: its next match is followed, however far off")

        # ---------------------------------------------------------- the match, by the numbers
        spoken, s, _ = run(ctx, "get_match_stats")
        assert spoken == ("These are live numbers, a moment ahead of your picture. "      # the listener follows a match in play
                          "Possession: Arsenal 62 percent, Tottenham 38 percent. "
                          "Shots, with those on target in brackets: Arsenal 12 (6), Tottenham 5 (2). "
                          "Corners: Arsenal 5, Tottenham 2. Fouls: Arsenal 9, Tottenham 11. "
                          "The feed gives no expected goals for this match."), spoken
        assert [r["metric"] for r in s["table"]][:3] == ["Possession (%)", "Total shots (on target)",
                                                          "Expected goals (xG)"], s["table"]
        spoken, _, _ = run(ctx, "get_injuries")
        assert spoken == "Out for Arsenal: Gabriel Jesus (knee injury). Out for Tottenham: Cristian Romero (suspended).", spoken
        assert run(ctx, "get_injuries", team="Tottenham")[0] == "Out for Tottenham: Cristian Romero (suspended)."
        try:                                  # a team that is not in this match, nor playing, is not guessed at
            run(ctx, "get_injuries", team="Chelsea")
            raise AssertionError("Chelsea is not playing")
        except ToolError as e:
            assert "Chelsea" in e.spoken, e.spoken
        spoken, _, _ = run(ctx, "get_team_form")
        assert spoken == ("Arsenal recently: won, won, drew, lost, won. Tottenham recently: lost, drew, won, won, won."), spoken
        spoken, _, _ = run(ctx, "get_player_stats", player="Saka")
        assert spoken == "Bukayo Saka for Arsenal this season: 9 appearances, 7 goals and 4 assists.", spoken
        assert declines(ctx, "get_player_stats", player="Nobody Atall").detail["reason"] == "no_match"
        print("ok  stats, injuries, form and a player's season, in words; a missing thing is said, not guessed")

        # ---------------------------------------------------------- favourites
        assert declines(ctx, "get_my_matches").detail["reason"] == "no_favourites"
        assert run(ctx, "set_favourites", action="list")[0] == "You haven't told me any teams yet."
        spoken, s, _ = run(ctx, "set_favourites", action="add", teams=["Arsenal", " Lille "])
        assert spoken == "Okay, I'll remember Arsenal, Lille. Your teams: Arsenal, Lille.", spoken
        run(ctx, "set_favourites", action="add", teams=["arsenal"])
        assert s["favourites"] == ["Arsenal", "Lille"] and ctx.store.listener("ann")["favourites"] == ["Arsenal", "Lille"], \
            "no duplicates, kept for next time"
        assert run(ctx, "set_favourites", action="remove", teams=["lille"])[0] == "Okay, I've forgotten lille. Your teams: Arsenal."
        assert declines(ctx, "set_favourites", action="add").detail["reason"] == "needs_teams"
        spoken, s, _ = run(ctx, "get_my_matches")
        assert spoken.startswith("Today, in Mauritius time: Arsenal against Tottenham"), spoken
        run(ctx, "set_favourites", action="clear")
        assert ctx.store.listener("ann")["favourites"] == []
        run(ctx, "set_favourites", action="add", teams=["Everton"])
        assert declines(ctx, "get_my_matches").spoken == "None of your teams are playing today."
        print("ok  favourites: added once, removed, listed, cleared; my matches finds them with times; none on is said")

        # ---------------------------------------------------------- preferences
        assert run(ctx, "set_preferences", detail="brief")[0] == "Okay, I'll keep answers brief."
        assert ctx.store.listener("ann")["detail"] == "brief"
        run(ctx, "set_preferences", language="French")
        assert ctx.store.listener("ann")["language"] == "French", "what_did_i_miss already reads this"
        assert run(ctx, "set_preferences", language="English")[0] == "Okay, I'll answer in English."
        assert ctx.store.listener("ann")["language"] is None
        assert declines(ctx, "set_preferences").detail["reason"] == "needs_choice"
        from simulator import agent
        assert "brief answers" in agent._preference(ctx, "ann") and agent._preference(ctx, "nobody") == ""
        print("ok  preferences are remembered, reach the agent's instructions, and 'English' resets the language")

        # ---------------------------------------------------------- what can you do
        spoken, s, _ = run(ctx, "get_capabilities")
        assert "league tables" in spoken and "remembering your teams" in spoken and "football" in s["sports"]
        assert "get_standings" in s["tools"] and len(s["tools"]) == 30
        print("ok  capabilities are read from the tools actually offered")

        # ---------------------------------------------------------- tools follow the feed
        try:
            registry.limit_to({"fixtures", "events", "lineups", "officials", "stats"})
            offered = {t["name"] for t in registry.public_tools()}
            assert "get_match_stats" in offered and "get_standings" not in offered and "get_injuries" not in offered
            assert "set_favourites" in offered and "get_capabilities" in offered, "tools that need no feed stay"
            assert "league tables" not in run(ctx, "get_capabilities")[0], "capabilities follow the feed"
            core = {t["name"] for t in registry.public_tools(core_only=True)}
            assert core <= set(registry.CORE_TOOLS) and "get_match_stats" not in core and len(core) <= 11
            registry.limit_to(None)
            assert len(registry.public_tools()) == 30 and len(registry.public_tools(core_only=True)) == 11
        finally:
            registry.limit_to(None)
        assert len(agent._bedrock_tools(registry.public_tools())) == 30
        print("ok  a feed without a capability does not offer its tools; the Nova host offers the complete MCP catalog")

        # ---------------------------------------------------------- a feed without it
        class Bare(type(ctx.provider)):
            def standings(self, competition):
                raise NotImplementedError
        ctx.provider.__class__ = Bare
        assert declines(ctx, "get_standings", competition="Premier League").detail["reason"] == "not_supported"
    finally:
        clock.now = real_now
    print("\nmore tools: all good")


if __name__ == "__main__":
    main()
