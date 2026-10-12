"""Tool contracts.

READ THIS BEFORE EDITING A DESCRIPTION.

These descriptions are not documentation. Alexa+ reads them to decide
which tool a spoken sentence maps to, so they are product surface and
they are written for the model, not for us. Three rules we follow:

  1. Lead with the user intent, not the implementation.
       good: "What the listener missed while they were away."
       bad : "Returns events between last_told_at and now."
  2. Include the phrasings a listener actually uses. People say
     "what did I miss", "what happened", "catch me up", "did I miss
     anything" - all of which must land on the same tool.
  3. Say what the tool does NOT do, when two tools are close. Without
     that, get_match_state and what_did_i_miss compete for the same
     utterances and routing becomes a coin toss.

Every change here should be re-tested against the phrasings in
tests/test_routing_phrases.py.
"""

TOOLS = []


def tool(name, title, description, input_schema, output_hint=None, ui=None):
    spec = {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": input_schema,
    }
    if output_hint:
        spec["_outputHint"] = output_hint
    if ui:
        # MCP Apps extension. Alexa+ renders this on screened devices
        # (Echo Show, Fire TV). Voice-only devices ignore it, which is
        # why no tool is allowed to put essential information here and
        # nowhere else - see docs/ACCESSIBILITY.md.
        spec["_meta"] = {"ui": ui}
    TOOLS.append(spec)
    return spec


_obj = lambda props, required=(): {
    "type": "object",
    "properties": props,
    "required": list(required),
    "additionalProperties": False,
}

_team = {"type": "string", "minLength": 2, "maxLength": 60,
         "description": "Team name as the listener said it, e.g. 'Arsenal'."}
_fixture = {"type": "integer", "minimum": 1,
            "description": "Fixture id. Omit to use the match the listener is following."}


tool(
    "follow_match",
    "Follow a match",
    "Start following a football match for this listener so later questions "
    "need no context. Use when they say they want to follow, watch or keep "
    "up with a team or a game - 'follow the Arsenal game', 'I'm watching "
    "Arsenal Spurs', 'keep me updated on City'. Also use to switch to a "
    "different match. This does not report the score; use get_match_state "
    "for that.",
    _obj({"team": _team,
          "opponent": {"type": "string", "maxLength": 60,
                       "description": "The other team, if the listener named it."},
          "fixture_id": _fixture,
          "locale": {"type": "string", "maxLength": 16,
                     "description": "Device locale, e.g. 'en-GB'. Used only to pick "
                                    "a safe starting broadcast delay so we never "
                                    "spoil a goal before the listener's picture "
                                    "shows it."}}),
)

tool(
    "get_match_state",
    "Score and clock",
    "The score and how far through the match it is, right now. Use for "
    "'what's the score', 'how long left', 'is it still nil nil', 'who's "
    "winning', 'has it finished'. This answers only the current state - it "
    "does not list what has happened, so for 'what did I miss' or 'what "
    "happened' use what_did_i_miss instead.",
    _obj({"fixture_id": _fixture}),
    output_hint="score, minute, period, whether the match has finished",
    ui="mcp-apps://scoreboard",
)

tool(
    "get_lineups",
    "Line-ups and formation",
    "Who is playing, in what formation, and who is on the bench. Use for "
    "'who's playing', 'what's the line-up', 'who's starting', 'who's on the "
    "bench', 'what formation are we in', 'is X playing today'. Broadcast "
    "shows this once as a graphic before kick-off and never reads it aloud, "
    "so listeners ask for it often and late.",
    _obj({"fixture_id": _fixture,
          "team": {"type": "string", "maxLength": 60,
                   "description": "Limit to one side. Omit for both."}}),
    output_hint="starting eleven, formation, bench, captain, shirt numbers",
    ui="mcp-apps://lineups",
)

tool(
    "what_did_i_miss",
    "Catch up on what happened",
    "Everything that happened since this listener last heard anything, read "
    "back as one short catch-up. Use for 'what did I miss', 'what happened', "
    "'catch me up', 'did I miss anything', 'I just got back', 'fill me in'. "
    "The listener does not need to say how long they were away - the server "
    "knows when it last spoke to them. Prefer this over get_match_state "
    "whenever the listener is asking what HAPPENED rather than what the "
    "score IS.",
    _obj({"fixture_id": _fixture,
          "since_minute": {"type": "integer", "minimum": 0, "maximum": 130,
                           "description": "Only if the listener gave an explicit "
                                          "point, e.g. 'since half time'. Normally omit."},
          "full": {"type": "boolean",
                   "description": "The listener asked for everything after being "
                                  "offered the headlines - 'yes', 'the rest', "
                                  "'tell me everything'."}}),
    output_hint="one spoken paragraph covering the gap, plus the events behind it",
    ui="mcp-apps://catchup",
)

tool(
    "sync_broadcast_delay",
    "Stay behind my picture",
    "Line Sideline up with what the listener is actually hearing, so it "
    "never gets ahead of their broadcast and spoils something. Streams "
    "run 20 to 45 seconds behind the real match. The listener cannot see "
    "a clock, so they tell us what they just HEARD: use this whenever "
    "they say 'kick-off just went', 'that's half time', 'they've just "
    "scored', 'the whistle's gone', 'the second half has started' - pass "
    "the moment in `heard`. Also use for 'you're ahead of my telly', 'you "
    "spoiled that', 'are we in sync', and when somebody beside them reads "
    "the clock out.",
    _obj({"heard": {"type": "string",
                    "enum": ["kickoff", "half_time", "second_half",
                             "full_time", "goal"],
                    "description": "The moment the listener just heard on their "
                                   "broadcast. This is the normal path - it needs "
                                   "no screen and nobody's help."},
          "their_minute": {"type": "integer", "minimum": 0, "maximum": 130,
                           "description": "Only when a sighted person nearby reads "
                                          "the clock out loud."},
          "offset_seconds": {"type": "integer", "minimum": 0, "maximum": 900,
                             "description": "Seconds behind, if stated directly."},
          "check": {"type": "boolean",
                    "description": "Report how far behind we are holding."},
          "clear": {"type": "boolean",
                    "description": "Only if they explicitly want everything live."},
          "fixture_id": _fixture}),
    output_hint="the offset now in force and where it came from",
)

tool(
    "get_event_detail",
    "Detail of one moment",
    "Full detail of a single thing that happened - a goal, a card, a "
    "substitution, a VAR decision. Use for 'tell me about that goal', 'who "
    "assisted it', 'what was the card for', 'who came off', 'say that "
    "again'. Live commentary never lets a listener go back; this does.",
    _obj({"fixture_id": _fixture,
          "event_id": {"type": "string", "maxLength": 40,
                       "description": "Id from a previous answer, if known."},
          "minute": {"type": "integer", "minimum": 0, "maximum": 130,
                     "description": "Minute the listener referred to."},
          "kind": {"type": "string",
                   "enum": ["goal", "card", "substitution", "var", "any"],
                   "description": "Narrow by type when the listener said 'that goal'."}}),
    output_hint="one event, fully described, with the score before and after",
)

tool(
    "get_officials",
    "Referee and officials",
    "The referee, the assistants, and how many cards have been shown. Use "
    "for 'who's refereeing', 'who's the ref', 'how many yellows', 'has "
    "anyone been sent off', 'who's on VAR'. Named once in a pre-match "
    "graphic and then almost never mentioned again, so listeners cannot "
    "find this out any other way.",
    _obj({"fixture_id": _fixture}),
    output_hint="referee, assistants, VAR official, cards shown so far",
)

tool(
    "get_player_context",
    "Who a player is",
    "Background on a player in this match - position, shirt number, club, "
    "and what they have done in this game. Use for 'who is he', 'who was "
    "that', 'what number is Saka', 'has he scored before', 'where does he "
    "play'. Sighted viewers get this from the on-screen caption; this is "
    "that caption, spoken. If the listener says 'he' or 'that player' "
    "rather than a name, pass the pronoun through as-is - the server "
    "resolves it from what just happened on the pitch.",
    _obj({"player": {"type": "string", "minLength": 2, "maxLength": 60,
                     "description": "Name as the listener said it; partial is fine. "
                                    "Or a bare pronoun - 'he', 'that player' - "
                                    "which the server resolves from recent events."},
          "fixture_id": _fixture},
         ["player"]),
    output_hint="position, number, team, involvement in this match",
)

tool(
    "get_head_to_head",
    "Past meetings",
    "How these two teams have done against each other recently. Use for "
    "'have we beaten them before', 'what happened last time', 'what's our "
    "record against them'. The kind of thing a friend on the sofa says "
    "during a lull.",
    _obj({"fixture_id": _fixture,
          "limit": {"type": "integer", "minimum": 1, "maximum": 10,
                    "description": "How many past meetings. Default 5."}}),
    output_hint="recent results between the two sides",
)


def public_tools():
    """Tool list as sent to Alexa+ on tools/list.

    Internal hints are stripped: `_outputHint` is for our own docs and the
    model does not need it.
    """
    out = []
    for t in TOOLS:
        spec = {k: v for k, v in t.items() if not k.startswith("_outputHint")}
        out.append(spec)
    return out


def by_name(name):
    for t in TOOLS:
        if t["name"] == name:
            return t
    return None
