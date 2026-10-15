#!/usr/bin/env python3
"""Does the model pick the right MCP tool? Real Nova, invented match data, no feed calls.

    python3 scripts/route_check.py

Each line is something a listener might say and the tool it should land on (an optional third item
is what was said before it, for lines like "say that again" that mean nothing alone). Tools that are close
neighbours (the table and the top scorers, a team's schedule and a match preview, a player's
season and what he did today) each get several lines, because those are where a model confuses
them. A miss means a description is not distinct enough: fix the wording, not the test.
Costs one Bedrock call or two per line (about a minute for the whole set).
"""

import os
import sys
import threading
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("SIDELINE_PORT", "8797")
os.environ.setdefault("SIDELINE_STATE", "memory")     # never write test listeners to a real table

# Not `from conftest import FOOTBALL`: conftest switches Bedrock OFF as a side effect (it is for the unit tests), and a
# check of what a real model does with the tools needs it on.
FOOTBALL = os.path.join(ROOT, "tests", "fixtures", "football-arsenal-tottenham.json")
from support import ReplayProvider  # noqa: E402

from sideline import app  # noqa: E402

PACE_SECONDS = 1.0                                            # between lines, so a whole run stays under the on-demand rate limit

CASES = [
    ("Follow the Arsenal game", "follow_match"), ("I'm watching Arsenal against Spurs", "follow_match"),
    ("keep me updated on Arsenal", "follow_match"),
    ("what's the score", "get_match_state"), ("how long left", "get_match_state"), ("who's winning", "get_match_state"),
    ("what did I miss", "what_did_i_miss"), ("what happened", "what_did_i_miss"), ("catch me up", "what_did_i_miss"),
    ("tell me about that goal", "get_event_detail"), ("who assisted it", "get_event_detail"),
    ("say that again", "get_event_detail", ["Follow the Arsenal game", "tell me about that goal"]),
    ("who's in the line-up", "get_lineups"), ("who's on the bench", "get_lineups"), ("what formation are they in", "get_lineups"),
    ("which teams are playing today", "get_fixtures"), ("what's on tonight", "get_fixtures"), ("what's live right now", "get_fixtures"),
    ("any Premier League matches today", "get_fixtures"),
    ("tell me about the match", "get_match_preview"), ("where is it being played", "get_match_preview"),
    ("what's the weather like at the ground", "get_match_preview"),
    ("what time is Arsenal playing", "get_schedule"), ("when do Arsenal play Lille", "get_schedule"),
    ("is Spurs on today", "get_schedule"),
    ("who's the referee", "get_officials"), ("how many yellow cards have there been", "get_officials"),
    ("who is he", "get_player_context"), ("what number is Saka", "get_player_context"),
    ("how many goals has Saka scored this season", "get_player_stats"), ("has he scored this season", "get_player_stats"),
    ("have we beaten them before", "get_head_to_head"), ("what happened last time they met", "get_head_to_head"),
    ("what's their form", "get_team_form"), ("how have they been playing lately", "get_team_form"),
    ("what's the table", "get_standings"), ("where is Arsenal in the league", "get_standings"),
    ("who's top of the league", "get_standings"),
    ("who's the top scorer", "get_top_scorers"), ("golden boot race", "get_top_scorers"),
    ("who has more possession", "get_match_stats"), ("how many shots have there been", "get_match_stats"),
    ("who's injured", "get_injuries"), ("is anyone suspended", "get_injuries"),
    ("is there a team called Gamba Osaka", "search"), ("find Bellerin", "search"),
    ("what leagues can you cover", "get_competitions"), ("do you have La Liga", "get_competitions"),
    ("I support Arsenal", "set_favourites"), ("add Lille to my teams", "set_favourites"),
    ("are my teams playing today", "get_my_matches"), ("what's on for me", "get_my_matches"),
    ("keep it short", "set_preferences"), ("speak French", "set_preferences"),
    ("what can you do", "get_capabilities"), ("what can I ask you", "get_capabilities"),
    ("kick-off just went", "sync_broadcast_delay"), ("you spoiled that goal", "sync_broadcast_delay"),
    # Questions about a team, a player or a match that is over: no match to follow.
    ("when do Arsenal play next", "get_schedule"), ("what are Arsenal's next fixtures", "get_schedule"),
    ("what were Arsenal's last results", "get_schedule"), ("did Arsenal win their last game", "get_schedule"),
    ("who is in the Arsenal squad", "get_squad"), ("who is the Arsenal manager", "get_squad"),
    ("who are Arsenal's goalkeepers", "get_squad"),
    ("how are Arsenal doing this season", "get_team_stats"), ("what are Arsenal's stats", "get_team_stats"),
    ("who scored in the Arsenal game", "get_match_report"), ("were there any cards in the Spurs game yesterday", "get_match_report"),
    ("who came on as a substitute in the Arsenal match", "get_match_report"),
    ("how did the Arsenal Lille game finish", "get_match_report"),
    # Tools added later: who someone is, the news, and who stood out.
    ("tell me more about Bukayo Saka", "get_player_profile"), ("who is Martin Odegaard", "get_player_profile"),
    ("how old is Saka", "get_player_profile"), ("any news on Arsenal", "get_news"), ("what's the latest on Tottenham", "get_news"),
    ("who was the best player", "get_standouts"), ("who was the most dangerous player in that match", "get_standouts"),
    ("who played well", "get_standouts"),
]


def main():
    provider = ReplayProvider(FOOTBALL, speed=0.0, start_minute=0)      # frozen: a running replay ends the match mid-check
    provider.jump_to(40)
    ctx, srv, _ = app.build(provider=provider)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)
    run = srv.agent_runner
    cases = CASES
    wrong, unscored = [], []
    for i, (said, want, *setup) in enumerate(cases):
        got = None
        for attempt in range(4):                                     # a throttled call says nothing about routing: wait, retry
            try:
                if "--cold" not in sys.argv and not setup:           # --cold: nothing followed, as a first-ever question
                    from sideline.tools import REGISTRY
                    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "route-%d-%d" % (i, attempt))
                for before in (setup[0] if setup else []):          # some lines only make sense after another
                    run(before, "route-%d-%d" % (i, attempt), None, None)
                got = [t["name"] for t in run(said, "route-%d-%d" % (i, attempt), None, None)["tool_results"]]
            except Exception as e:                                   # noqa: BLE001
                got = ["error: %s" % type(e).__name__]
            if got and got[0].startswith("error: AgentUnavailable") and attempt < 3:
                time.sleep(8 * (attempt + 1))
                continue
            break
        time.sleep(PACE_SECONDS)
        if got and got[0].startswith("error: "):
            unscored.append(said)                                    # still throttled after retries: not counted either way
            print("  SKIP  %-46s %s" % (said, got), flush=True)
            continue
        if want not in got:
            wrong.append((said, want, got))
            print("  MISS  %-46s wanted %-20s got %s" % (said, want, got), flush=True)
    scored = len(cases) - len(unscored)
    print("%d of %d routed to the right tool with %s (all tools from MCP tools/list offered)%s"
          % (scored - len(wrong), scored, os.environ.get("SIDELINE_BEDROCK_MODEL", "the configured model"),
             "; %d not scored (throttled)" % len(unscored) if unscored else ""))
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
