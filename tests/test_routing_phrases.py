"""Tool descriptions are product surface.

Alexa+ picks a tool by reading the descriptions in registry.py. We
cannot test the real router here, but we CAN assert that the phrasings
real listeners use are actually present in the descriptions - which is
the thing that breaks silently when somebody tidies the wording.

If you edit a description, run this.
"""

from sideline.mcp.registry import by_name

EXPECTED = {
    "what_did_i_miss": ["what did i miss", "what happened", "catch me up",
                        "did i miss anything", "fill me in"],
    "get_match_state": ["what's the score", "how long left", "who's winning"],
    "get_lineups": ["who's playing", "line-up", "bench", "formation"],
    "get_officials": ["who's refereeing", "who's the ref", "yellows"],
    "get_event_detail": ["tell me about that goal", "who assisted", "say that again"],
    "get_player_context": ["who is he", "what number", "has he scored before"],
    "get_head_to_head": ["have we beaten them before", "last time"],
    "follow_match": ["follow the", "keep me updated"],
    # These are what a BLIND listener can actually say. The tool must not
    # ask them to read a clock on screen; the assertion below keeps it so.
    "sync_broadcast_delay": ["kick-off just went", "that's half time",
                             "they've just scored", "the whistle's gone",
                             "in sync", "spoiled"],
}


def main():
    for tool, phrases in EXPECTED.items():
        desc = by_name(tool)["description"].lower()
        for p in phrases:
            assert p in desc, "%s is missing the phrasing %r" % (tool, p)
        print("ok  %-20s %d phrasings present" % (tool, len(phrases)))

    # The sync tool must lead with what the listener HEARS. Reading a
    # clock is a fallback for a sighted person nearby, never the premise.
    sync_desc = by_name("sync_broadcast_delay")["description"].lower()
    assert "heard" in sync_desc and "cannot see a clock" in sync_desc
    assert sync_desc.index("heard") < sync_desc.index("reads the clock"), \
        "the audio path must come before the sighted-companion fallback"
    print("ok  sync tool leads with hearing, not seeing")

    # A pronoun must route to get_player_context, not be dropped.
    assert "'he'" in by_name("get_player_context")["description"]
    print("ok  pronoun handling is declared in the description")

    # The two tools most likely to be confused must disambiguate
    # themselves explicitly.
    assert "what_did_i_miss" in by_name("get_match_state")["description"]
    assert "get_match_state" in by_name("what_did_i_miss")["description"]
    print("ok  score vs catch-up disambiguated in both directions")

    print("\nrouting phrases: all good")


if __name__ == "__main__":
    main()
