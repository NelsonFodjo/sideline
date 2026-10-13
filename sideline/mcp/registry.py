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

from .. import sports

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
    "Start following a match so later questions need no context. Say: 'follow the Arsenal game', 'I'm watching Arsenal against Spurs', 'keep me updated on City', 'switch to Chelsea'. Only when they ask to follow. Not the score (get_match_state); not 'I support X' (set_favourites).",
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
    "The score and the clock, right now. Say: 'what's the score', 'how long left', 'who's winning', 'has it finished'. Not what happened (what_did_i_miss); not 'I'm watching X' or 'follow X' (follow_match).",
    _obj({"fixture_id": _fixture}),
    output_hint="score, minute, period, whether the match has finished",
    ui="mcp-apps://scoreboard",
)

tool(
    "get_fixtures",
    "What matches are on",
    "Which matches are on, with times. Say: 'which teams are playing', 'what's on today', 'what's live', 'any Premier League matches tonight'. Everything on, not one named team (get_schedule); matches, not players (get_lineups).",
    _obj({"when": {"type": "string", "enum": ["yesterday", "today", "tomorrow"],
                   "description": "Which day. Omit for today."},
          "competition": {"type": "string", "maxLength": 60,
                          "description": "A competition or country to narrow it to, e.g. "
                                         "'Premier League', 'Champions League', 'Spain'."},
          "live_only": {"type": "boolean",
                        "description": "Only matches under way now: 'what's live'."}}),
    output_hint="up to five matches, each with its time, and how many more there are",
)

tool(
    "get_match_report",
    "What happened in a match",
    "What happened in a match that was played or is on: result, goals, assists, cards, substitutions, VAR. No follow needed. Say: 'what happened in the Celtic game', 'who scored', 'any cards', 'who came on', 'how did it finish'. Set `part` when they ask for one thing. Not who played (get_lineups); not what you missed (what_did_i_miss).",
    _obj({"fixture_id": _fixture,
          "part": {"type": "string", "enum": ["all", "goals", "cards", "substitutions", "var"],
                   "description": "goals for 'who scored', cards for 'any cards' or 'sent off', substitutions for 'who came on', var for VAR. Omit only for the whole story."}}),
    output_hint="the result and goals, or one part in full: goals, cards, substitutions or VAR decisions",
)

tool(
    "get_match_preview",
    "Describe the match",
    "A rundown of one match: ground, kick-off time, weather, formations. Say: 'tell me about the match', 'where is it being played', 'what's the weather', 'when does it start'. Pass `team` if they name one. Not when a team plays (get_schedule).",
    _obj({"fixture_id": _fixture,
          "team": {"type": "string", "minLength": 2, "maxLength": 60,
                   "description": "A team the listener named, e.g. 'Arsenal', when they ask about "
                                  "a match they are not following. Omit to use the followed match."},
          "opponent": {"type": "string", "maxLength": 60,
                       "description": "The other team, if they named it."}}),
    output_hint="host, competition, ground and city, kick-off in the listener's time, weather, formations",
)

tool(
    "get_lineups",
    "Line-ups and formation",
    "The players in a match, played or not: starting eleven, formation, bench. Say: 'who's playing', 'who played in the Celtic Rangers game', 'what's the line-up', 'who's on the bench', 'what formation'. Not which matches are on (get_fixtures); not a whole squad (get_squad).",
    _obj({"fixture_id": _fixture,
          "team": {"type": "string", "maxLength": 60,
                   "description": "Limit to one side. Omit for both."}}),
    output_hint="starting eleven, formation, bench, captain, shirt numbers",
    ui="mcp-apps://lineups",
)

tool(
    "what_did_i_miss",
    "Catch up on what happened",
    "What happened since the listener last heard anything. Say: 'what did I miss', 'what happened', 'catch me up', 'did I miss anything', 'fill me in'. The server knows the gap. Not just the score (get_match_state).",
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
    "Sync to what the listener HEARD on their broadcast, so Sideline never spoils it. They cannot see a clock, so they say what they just heard: 'kick-off just went', 'that's half time', 'they've just scored', 'the whistle's gone', or 'you spoiled that', 'are we in sync'. Pass it in `heard`. Only if someone beside them reads the clock out, use their_minute.",
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
    "Replay one moment: a goal, card, substitution or VAR decision. Say: 'tell me about that goal', 'who assisted', 'what was the card for', 'say that again', 'repeat that'. Not what you missed (what_did_i_miss).",
    _obj({"fixture_id": _fixture,
          "event_id": {"type": "string", "maxLength": 40,
                       "description": "Id from a previous answer, if known."},
          "minute": {"type": "integer", "minimum": 0, "maximum": 130,
                     "description": "Minute the listener referred to."},
          "kind": {"type": "string",
                   "enum": sports.event_kinds() + ["score", "any"],
                   "description": "Narrow by type when the listener said 'that goal' "
                                  "or 'that basket'. 'score' means whatever scores "
                                  "in this sport; kinds are per sport."}}),
    output_hint="one event, fully described, with the score before and after",
)

tool(
    "get_officials",
    "Referee and officials",
    "The referee, and the yellows and reds so far in the match being followed. Say: 'who's refereeing', 'who's the ref', 'how many yellows', 'anyone sent off'. Not who is injured (get_injuries). Cards in a match already played are get_match_report.",
    _obj({"fixture_id": _fixture}),
    output_hint="referee, assistants, VAR official, cards shown so far",
)

tool(
    "get_player_context",
    "Who a player is",
    "Who a player is and what he has done in this match. Say: 'who is he', 'what number is Saka', 'has he scored before' (pass 'he' as said). Not season totals (get_player_stats).",
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
    "How these two teams did when they last met. Say: 'have we beaten them before', 'what happened last time', 'our record against them'. Not recent form (get_team_form).",
    _obj({"fixture_id": _fixture,
          "limit": {"type": "integer", "minimum": 1, "maximum": 10,
                    "description": "How many past meetings. Default 5."}}),
    output_hint="recent results between the two sides",
)


_competition = {"type": "string", "maxLength": 60,
                "description": "A competition or league as the listener said it, e.g. 'Premier League'. "
                               "Omit to use the competition of the match they are following."}

tool(
    "search",
    "Find a team, player or competition",
    "Check a name: is there a team, player or competition called this? Say: 'is there a team called ...', 'find Gamba Osaka', 'who is Bellerin'. Not what a team is doing (get_schedule, get_standings).",
    _obj({"query": {"type": "string", "minLength": 2, "maxLength": 60,
                    "description": "The name as heard."},
          "kind": {"type": "string", "enum": ["team", "player", "competition"],
                   "description": "What is being looked for. Omit for a team."}}, ["query"]),
    output_hint="up to five matches, each with its country",
)

tool(
    "get_competitions",
    "What competitions I can cover",
    "Which competitions Sideline covers. Say: 'what leagues do you have', 'what can you cover', 'do you have La Liga'. Not today's matches (get_fixtures).",
    _obj({"country": {"type": "string", "maxLength": 40,
                      "description": "Narrow to a country, e.g. 'England'."}}),
    output_hint="the competitions, with their countries",
)

tool(
    "get_standings",
    "The league table",
    "The league table, or one team's place in it. Say: 'what's the table', 'who's top of the league', 'where is Arsenal in the league', 'how many points'. Not who scores most (get_top_scorers).",
    _obj({"competition": _competition,
          "team": {"type": "string", "maxLength": 60,
                   "description": "A team whose position the listener wants."}}),
    output_hint="the top of the table, or one team's position and points",
)

tool(
    "get_top_scorers",
    "The top scorers",
    "Who has scored most in a competition. Say: 'who's the top scorer', 'golden boot race'. Not the league table or who is top of it (get_standings); not one player's tally (get_player_stats).",
    _obj({"competition": _competition}),
    output_hint="the leading scorers with their teams and goals",
)

tool(
    "get_schedule",
    "When a team plays, and how it did",
    "A team's next matches, or its last results, no match needed. Say: 'when does Arsenal play', 'what time is Arsenal playing', 'when do Arsenal play Lille', 'is Spurs on today', 'next fixtures' (which next); 'last results', 'recent games', 'did they win' (which last). Always pass `team`. Not the whole day (get_fixtures).",
    _obj({"team": _team,
          "which": {"type": "string", "enum": ["next", "last"],
                    "description": "next (the default): the coming matches. last: the latest results with scores."},
          "opponent": {"type": "string", "maxLength": 60,
                       "description": "The other team, if they named it."}}, ["team"]),
    output_hint="the team's next matches with their times, or its last results with scores",
)

tool(
    "get_squad",
    "A team's players",
    "A team's players, with no match needed. Say: 'who is in the Celtic squad', 'who's their goalkeeper', 'who's the manager', 'who's the captain', 'list their defenders'. Always pass `team`; add `position` for names. Not who starts this match (get_lineups); not one player (get_player_stats).",
    _obj({"team": _team,
          "position": {"type": "string", "enum": ["goalkeeper", "defender", "midfielder", "attacker"],
                       "description": "Only if they asked for one position, to hear the names."}}, ["team"]),
    output_hint="how many players by position with the manager and captain, or the names in one position",
)

tool(
    "get_team_stats",
    "A team's season",
    "A team's season so far, with no match needed: games, wins, draws, defeats, goals, clean sheets, possession. Say: 'how are Arsenal doing this season', 'Arsenal's stats', 'how many goals have they scored'. Always pass `team`. Not this match (get_match_stats); not the table (get_standings).",
    _obj({"team": _team}, ["team"]),
    output_hint="games, results, goals for and against, clean sheets and possession this season",
)

tool(
    "get_match_stats",
    "Match statistics",
    "The match numbers. Say: 'who has more possession', 'how many shots', 'corners', 'who's dominating'. Not the score (get_match_state).",
    _obj({"fixture_id": _fixture,
          "team": {"type": "string", "maxLength": 60,
                   "description": "A team whose match the listener means, if not the followed one."}}),
    output_hint="possession, shots, shots on target, corners, fouls and cards for each side",
)

tool(
    "get_player_stats",
    "A player's season so far",
    "A player's season totals. Say: 'has he scored this season', 'how many goals has Saka got', 'how many appearances'. Not his shirt number or who he is, or what he did today (get_player_context).",
    _obj({"player": {"type": "string", "minLength": 2, "maxLength": 60,
                     "description": "The player as the listener said it."},
          "team": {"type": "string", "maxLength": 60, "description": "Their team, if said."}}, ["player"]),
    output_hint="goals, assists and appearances this season",
)

tool(
    "get_injuries",
    "Who is injured or suspended",
    "Who is ruled out of the match, and why. Say: 'who's injured', 'any injuries', 'who is suspended', 'is he fit'. Not who is starting (get_lineups).",
    _obj({"fixture_id": _fixture,
          "team": {"type": "string", "maxLength": 60, "description": "Limit to one side."}}),
    output_hint="each absent player with the reason",
)

tool(
    "get_team_form",
    "A team's recent form",
    "How a team has been doing lately, as won, drawn, lost: pass `team`, or omit it for the two sides in the match. Say: 'what's their form', 'how have they been playing'. Not scores or dates of results (get_schedule which last); not past meetings (get_head_to_head).",
    _obj({"fixture_id": _fixture,
          "team": {"type": "string", "maxLength": 60, "description": "A team whose form is wanted, with no match needed."}}),
    output_hint="each side's last results as won, drawn or lost",
)

tool(
    "set_favourites",
    "Remember my teams",
    "Remember or forget the teams the listener supports. Say: 'I support Arsenal', 'my team is Spurs', 'add Lille', 'forget Chelsea', 'clear my teams'. 'I support X' is not 'follow X' (follow_match). Only names they said.",
    _obj({"action": {"type": "string", "enum": ["add", "remove", "clear", "list"],
                     "description": "Add or remove teams, clear them all, or read them back."},
          "teams": {"type": "array", "items": {"type": "string", "maxLength": 60}, "maxItems": 10,
                    "description": "The team names, as said. Not needed for clear or list."}}, ["action"]),
    output_hint="the listener's teams after the change",
)

tool(
    "get_my_matches",
    "Matches for my teams",
    "Which of the listener's remembered teams are playing. Say: 'are my teams playing', 'what's on for me'. Not a team they name now (get_schedule); not 'keep me updated on X' (follow_match).",
    _obj({"when": {"type": "string", "enum": ["yesterday", "today", "tomorrow"],
                   "description": "Which day. Omit for today."}}),
    output_hint="each favourite team's match in the window, with its time",
)

tool(
    "set_preferences",
    "How I like answers",
    "How the listener likes answers, and in which language. Say: 'keep it short', 'give me more detail', 'speak French', 'back to normal'.",
    _obj({"detail": {"type": "string", "enum": ["brief", "normal", "full"],
                     "description": "How much to say."},
          "language": {"type": "string", "maxLength": 30,
                       "description": "The language to answer in, e.g. 'French'. 'English' to reset."}}),
    output_hint="what was remembered",
)

tool(
    "get_capabilities",
    "What I can do right now",
    "What Sideline can do. Say: 'what can you do', 'what can I ask', 'help'. Only when the listener is unsure what to ask; not to repeat an answer (get_event_detail).",
    _obj({}),
    output_hint="the things this feed supports, in words",
)

# Any match tool can be pointed at a match that is not the followed one, one already played included: the listener names a
# team (and the other side, a day or a date) and sideline/finder.py works out which match they mean, or lists the options.
_REF = {"team": {"type": "string", "maxLength": 60,
                 "description": "A team, to pick its match when that is not the one being followed."},
        "opponent": {"type": "string", "maxLength": 60, "description": "The other team, if they named it."},
        "when": {"type": "string", "enum": ["last", "next", "yesterday", "today", "tomorrow"],
                 "description": "Which of that team's matches: the last one played, the next, or a day."},
        "date": {"type": "string", "maxLength": 10, "description": "A day as YYYY-MM-DD, if they gave one."}}
MATCH_TOOLS = ("get_match_state", "get_lineups", "get_officials", "get_match_stats", "get_injuries", "get_event_detail",
               "get_player_context", "get_head_to_head", "get_match_preview", "get_match_report")
for _spec in TOOLS:
    if _spec["name"] in MATCH_TOOLS:
        for _k, _v in _REF.items():
            _spec["inputSchema"]["properties"].setdefault(_k, _v)

# What a tool needs from the feed behind it. A tool whose need is missing is not listed.
TOOL_REQUIRES = {
    "follow_match": "fixtures", "get_match_state": "fixtures", "get_match_preview": "fixtures",
    "get_fixtures": "fixtures", "get_schedule": "fixtures", "get_my_matches": "fixtures",
    "what_did_i_miss": "events", "get_event_detail": "events",
    "get_lineups": "lineups", "get_player_context": "lineups", "get_officials": "officials",
    "get_head_to_head": "h2h", "get_match_stats": "stats", "get_injuries": "injuries",
    "get_team_form": "form", "get_standings": "standings", "get_top_scorers": "top_scorers",
    "get_player_stats": "player_stats", "search": "search", "get_competitions": "competitions",
    "get_squad": "squad", "get_team_stats": "team_stats", "get_match_report": "events",
}

# The core eleven: the small set a voice agent can be held to, and the ones the spoiler guard and catch-up are built on.
CORE_TOOLS = ("follow_match", "get_match_state", "get_lineups", "what_did_i_miss", "get_event_detail",
              "get_officials", "get_player_context", "get_head_to_head", "sync_broadcast_delay",
              "get_match_preview", "get_fixtures")

_AVAILABLE = None          # None: every tool. Otherwise the capabilities the feed has.


def limit_to(capabilities):
    """List only the tools the feed behind this server can answer (None lists them all)."""
    global _AVAILABLE
    _AVAILABLE = None if capabilities is None else frozenset(capabilities)


def available(name):
    need = TOOL_REQUIRES.get(name)
    return need is None or _AVAILABLE is None or need in _AVAILABLE


def public_tools(core_only=False):
    """Tool list as sent to Alexa+ on tools/list.

    Internal hints are stripped: `_outputHint` is for our own docs and the
    model does not need it.
    """
    out = []
    for t in TOOLS:
        if not available(t["name"]) or (core_only and t["name"] not in CORE_TOOLS):
            continue
        spec = {k: v for k, v in t.items() if not k.startswith("_outputHint")}
        out.append(spec)
    return out


def by_name(name):
    for t in TOOLS:
        if t["name"] == name:
            return t
    return None
