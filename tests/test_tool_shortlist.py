"""The agent shows a model a small set of tools per question. Every tool must be reachable from the way a listener asks.

Found by running real Bedrock models over 79 phrasings: the three tools added last (a player's profile, the news, who
stood out) were never offered, because the shortlist matched only words in a tool's NAME, so "tell me more about Saka"
could not find `get_player_profile`. The shortlist now reads the example phrases in each tool's own description."""

from sideline.mcp.registry import public_tools
import simulator.agent as agent

CATALOG = public_tools()
CASES = [
    ("tell me more about Bukayo Saka", "get_player_profile"), ("who is Martin Odegaard", "get_player_profile"),
    ("how old is Saka", "get_player_profile"), ("any news on Arsenal", "get_news"), ("what's the latest on Tottenham", "get_news"),
    ("who was the best player", "get_standouts"), ("who was the most dangerous player in that match", "get_standouts"),
    ("who played well", "get_standouts"), ("man of the match", "get_standouts"),
    ("who is the Arsenal manager", "get_squad"), ("who are Arsenal's goalkeepers", "get_squad"),
    ("I support Arsenal", "set_favourites"), ("add Lille to my teams", "set_favourites"),
    ("keep it short", "set_preferences"), ("speak French", "set_preferences"),
    ("is there a team called Gamba Osaka", "search"), ("do you have La Liga", "get_competitions"),
    ("how many yellow cards have there been", "get_officials"), ("who assisted it", "get_event_detail"),
    ("what's the weather like at the ground", "get_match_preview"), ("tell me about the match", "get_match_preview"),
    ("who's injured", "get_injuries"), ("what's their form", "get_team_form"), ("have we beaten them before", "get_head_to_head"),
    ("how many shots have there been", "get_match_stats"), ("golden boot race", "get_top_scorers"), ("what's the table", "get_standings"),
    ("kick-off just went", "sync_broadcast_delay"), ("what can you do", "get_capabilities"), ("has he scored this season", "get_player_stats"),
]


def main():
    missing = []
    for question, tool in CASES:
        offered = [t["name"] for t in agent._select_candidate_tools(question, CATALOG)]
        if tool not in offered:
            missing.append((question, tool, offered))
        assert len(offered) <= 10, (question, offered)
    assert not missing, "tools never offered for how a listener asks:\n" + "\n".join("  %r wants %s, offered %s" % m for m in missing)
    print("ok  all %d phrasings reach their tool, with at most 10 tools shown" % len(CASES))

    # a tool added tomorrow is reachable from its own description, with no table to extend
    novel = dict(CATALOG[0], name="get_trivia", description="Football trivia. Say: 'tell me a fun fact', 'give me some trivia'.")
    offered = [t["name"] for t in agent._select_candidate_tools("give me some trivia please", CATALOG + [novel])]
    assert "get_trivia" in offered, offered
    print("ok  a brand-new tool is offered as soon as its description gives examples")


if __name__ == "__main__":
    main()
    print("\ntool shortlist: all good")
