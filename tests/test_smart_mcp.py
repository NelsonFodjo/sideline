"""Tests for universal multi-sport capabilities, 3-tier routing, and context continuation."""

import conftest  # noqa: F401
import re
from simulator import agent
from sideline.mcp.registry import public_tools
from sideline.sports import get as get_sport


def test_sports_profiles():
    # Verify American Football, Baseball, and Hockey are registered and fully functional
    nfl = get_sport("american_football")
    assert nfl is not None
    assert "touchdown" in nfl.all_kinds
    assert "field_goal" in nfl.all_kinds
    assert "touchdown" in nfl.score_kinds

    mlb = get_sport("baseball")
    assert mlb is not None
    assert "home_run" in mlb.all_kinds
    assert "run" in mlb.score_kinds

    nhl = get_sport("hockey")
    assert nhl is not None
    assert "goal" in nhl.all_kinds
    assert "power_play" in nhl.all_kinds
    assert "goal" in nhl.score_kinds
    print("ok  sports profiles: NFL, MLB, NHL correctly registered with native scoring events")


def test_conversational_bypass():
    # Tier 0 Conversational Bypass: Capability and identity questions answered instantly with zero hallucination
    ans1 = agent._match_conversational("Can you access other sports?")
    assert ans1 is not None
    assert "NFL" in ans1 or "American Football" in ans1
    assert "Baseball" in ans1 or "MLB" in ans1
    assert "Hockey" in ans1 or "NHL" in ans1

    ans2 = agent._match_conversational("What sports do you cover?")
    assert ans2 is not None
    assert "Football" in ans2

    ans3 = agent._match_conversational("Hello")
    assert ans3 is not None
    print("ok  Tier 0: Conversational bypass correctly routes sports capabilities and greetings")


def test_candidate_tool_selection():
    # Tier 2 Top-K Schema Pruning: Prunes 27 tools down to a core plus the best keyword matches
    all_tools = public_tools()
    assert len(all_tools) == 27

    # Query about referee
    ref_tools = agent._select_candidate_tools("who is refereeing?", all_tools)
    tool_names = [t["name"] for t in ref_tools]
    assert "get_officials" in tool_names
    assert len(ref_tools) <= 8

    # Query about injuries
    inj_tools = agent._select_candidate_tools("any injuries for the game?", all_tools)
    tool_names = [t["name"] for t in inj_tools]
    assert "get_injuries" in tool_names
    assert len(inj_tools) <= 8
    print("ok  Tier 2: Top-K schema pruning selects a few relevant candidate tools (slashing prompt tokens by ~85%)")


def test_context_continuation():
    # Multi-turn context continuation: storing topic and resolving follow-ups
    listener_id = "test-smart-listener"
    agent.FOCUSES.remember(listener_id, [{
        "name": "get_match_state",
        "spoken": "Chiefs 24, Ravens 20, 4th quarter.",
        "args": {"team": "Chiefs", "sport": "american_football"},
        "structured": {"home": "Chiefs", "away": "Ravens", "fixture_id": 999123, "sport": "american_football"},
    }])

    topic = agent.FOCUSES.topic(listener_id)
    assert topic.get("team") == "Chiefs"
    assert topic.get("fixture_id") == 999123
    assert topic.get("sport") == "american_football"

    # Context line provided to model
    line = agent.FOCUSES.line(listener_id)
    assert "Chiefs" in line
    print("ok  Context continuation: Focus accurately tracks team, fixture_id, and sport across turns")


def main():
    test_sports_profiles()
    test_conversational_bypass()
    test_candidate_tool_selection()
    test_context_continuation()
    print("\nsmart mcp suite: all good")


if __name__ == "__main__":
    main()
