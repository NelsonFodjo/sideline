"""The correctness set: questions a listener asks, and what a truthful answer must and must not say.

Every expectation comes from the invented fixtures in tests/fixtures/ (read the events there to check one): Arsenal
against Tottenham has Saka scoring on 34, Son on 58 and Martinelli on 74; cards for Romero 12, Partey 45, Bissouma 51,
Van de Ven 81 and Jesus 90. Each case sets up a listener, positions the match, optionally ages the log (the
listener has been watching a while) and asks one tool. This is the baseline the benchmark (scripts/bench.py) and
every later optimisation must keep green. Add a case when a bug is found: the register is docs/BUGS.md.
"""

from conftest import BASKETBALL, FOOTBALL, age_events, make_ctx

from sideline.mcp.errors import ToolError
from sideline.poller import poll_once
from sideline.tools import REGISTRY

# aged: events were logged an hour ago (a listener who has watched a while). fresh: logged a moment ago.
# delay=None keeps the default delay a follower gets; delay=0 is a listener with no delay.
ARSENAL = dict(replay=FOOTBALL, follow="Arsenal")
HARBOUR = dict(replay=BASKETBALL, follow="Harbour")

CASES = [
    # name, setup, minute, age_seconds, delay, tool, args, must say, must not say
    # --- the score is the score on THEIR screen
    ("score at 64'", ARSENAL, 64, 3600, None, "get_match_state", {}, ["Arsenal 1, Tottenham 1"], ["Arsenal 2"]),
    ("a goal just logged is not spoiled", ARSENAL, 74, None, None, "get_match_state", {},
     ["Arsenal 1, Tottenham 1"], ["Arsenal 2", "Martinelli"]),
    ("...and is told once the delay has passed", ARSENAL, 74, 46, None, "get_match_state", {},
     ["Arsenal 2, Tottenham 1"], []),
    ("no delay, no holding back", ARSENAL, 74, None, 0, "get_match_state", {}, ["Arsenal 2, Tottenham 1"], []),
    # --- catch-up
    ("what did I miss, first ask at 64'", ARSENAL, 64, 3600, None, "what_did_i_miss", {},
     ["Saka", "Son"], ["Martinelli"]),
    ("what did I miss, goal not yet on screen", ARSENAL, 74, None, None, "what_did_i_miss", {}, [], ["Martinelli"]),
    # --- tools that read the event log must not spoil either
    ("match report does not spoil", ARSENAL, 74, None, None, "get_match_report", {}, ["Saka", "Son"], ["Martinelli"]),
    ("event detail: the latest goal on screen", ARSENAL, 74, None, None, "get_event_detail", {"kind": "goal"},
     ["Son scored on 58"], ["Martinelli"]),
    ("player context does not spoil", ARSENAL, 74, None, None, "get_player_context", {"player": "Martinelli"},
     ["Martinelli"], ["scored on 74"]),
    ("player context after the delay", ARSENAL, 74, 46, None, "get_player_context", {"player": "Martinelli"},
     ["scored on 74"], []),
    ("officials do not count a card still to reach them", ARSENAL, 81, None, None, "get_officials", {},
     ["Michael Oliver", "3 yellows"], ["4 yellows"]),
    # --- plain facts
    ("referee and cards at 64'", ARSENAL, 64, 3600, None, "get_officials", {}, ["Michael Oliver", "3 yellows"], []),
    ("yellow cards at full time", ARSENAL, 90, 3600, None, "get_officials", {}, ["5 yellows"], []),
    ("line-ups", ARSENAL, 64, 3600, None, "get_lineups", {}, ["4-3-3", "4-2-3-1", "Raya", "Vicario"], []),
    ("who is Saka", ARSENAL, 64, 3600, None, "get_player_context", {"player": "Saka"},
     ["number 7", "scored on 34"], []),
    ("that goal", ARSENAL, 64, 3600, None, "get_event_detail", {"kind": "goal"}, ["Son scored on 58"], []),
    ("head to head", ARSENAL, 64, 3600, None, "get_head_to_head", {}, ["Last 5 meetings"], []),
    ("who is injured", ARSENAL, 64, 3600, None, "get_injuries", {}, ["Gabriel Jesus", "Romero", "suspended"], []),
    ("the table", ARSENAL, 64, 3600, None, "get_standings", {}, ["Arsenal", "20 points", "Tottenham", "18 points"], []),
    ("possession", ARSENAL, 64, 3600, None, "get_match_stats", {}, ["Possession", "Arsenal 62"], []),
    ("team form", ARSENAL, 64, 3600, None, "get_team_form", {"team": "Arsenal"}, ["Arsenal recently"], []),
    # --- another sport, another clock
    ("basketball score at 30'", HARBOUR, 30, 3600, 0, "get_match_state", {}, ["8", "10"], ["Arsenal"]),
    ("basketball: who is he after the ejection", HARBOUR, 36, 3600, 0, "get_player_context", {"player": "he"},
     ["Leo Banner", "ejected"], []),
    # --- honesty: say so rather than guess
    ("a feed that cannot do it says so", ARSENAL, 64, 3600, None, "get_squad", {"team": "Arsenal"},
     ["doesn't provide that"], []),
    ("an unknown team is not guessed at", dict(replay=FOOTBALL, follow=None), 0, None, None, "follow_match",
     {"team": "Zzyzx Rovers"}, ["can't find a match for Zzyzx Rovers"], ["Arsenal"]),
]


def run_case(case):
    name, setup, minute, age, delay, tool, args, must, must_not = case
    ctx = make_ctx(start_minute=0, replay=setup["replay"])
    who = "listener-%d" % abs(hash(name))
    if setup["follow"]:
        REGISTRY["follow_match"](ctx, {"team": setup["follow"]}, who)
        if delay is not None:
            rec = ctx.store.listener(who)
            rec["broadcast_offset"] = delay
            ctx.store.save_listener(rec)
    ctx.provider.jump_to(minute)
    poll_once(ctx)
    if age:
        age_events(ctx, age)
    try:
        spoken = REGISTRY[tool](ctx, args, who)[0]
    except ToolError as e:
        spoken = e.spoken
    for want in must:
        assert want in spoken, "%s: expected %r in: %s" % (name, want, spoken)
    for banned in must_not:
        assert banned not in spoken, "%s: %r must not be said: %s" % (name, banned, spoken)
    return spoken


def main():
    for case in CASES:
        run_case(case)
        print("ok  " + case[0])
    print("\n%d questions answered truthfully" % len(CASES))


if __name__ == "__main__":
    main()
