"""Sport profiles: the product is not football-only.

Football is the sport Sideline launched with and every other suite covers
it. This one proves the seam is real by running the whole stack (store,
poller, tools, spoiler guard) on a second sport, basketball, from an
INVENTED fixture (data/replay/harbour-reef-basketball.json), alongside
football on the same server.
"""

from conftest import age_events, BASKETBALL, FOOTBALL, make_ctx

from sideline import sports, sync
from sideline.language import templates
from sideline.poller import poll_once
from sideline.tools import REGISTRY

BOTH = [FOOTBALL, BASKETBALL]
HAWKS, ROCKETS = "Harbour Hawks", "Reef Rockets"


def run(ctx, who, name, **args):
    return REGISTRY[name](ctx, args, who)


def main():
    # ------------------------------------------------ the registry
    assert sports.resolve(None).key == "football"
    assert sports.resolve("nonsense").key == "football"
    assert sports.resolve({"sport": "basketball"}).key == "basketball"
    assert sports.resolve({"home": "no sport key"}).key == "football", \
        "feeds that predate profiles must stay football"
    kinds = sports.event_kinds()
    assert "goal" in kinds and "basket" in kinds
    print("ok  profiles resolve; an unlabelled fixture is football; kinds:", kinds)

    # -------------------------------------------- scoring is the sport's
    bb = sports.get("basketball")
    evs = [{"minute": 2, "kind": "basket", "team": HAWKS, "points": 3},
           {"minute": 3, "kind": "basket", "team": ROCKETS, "points": 2},
           {"minute": 4, "kind": "basket", "team": HAWKS, "points": 1},
           {"minute": 5, "kind": "basket", "team": HAWKS, "points": 2,
            "superseded_by": "x"},
           {"minute": 6, "kind": "foul", "team": ROCKETS}]
    assert bb.score_from(evs, HAWKS) == {"home": 4, "away": 2}
    assert bb.score_from(evs, HAWKS, up_to_minute=3) == {"home": 3, "away": 2}
    fb = sports.get("football")
    assert fb.score_from([{"minute": 1, "kind": "goal", "team": "A"}], "A") == \
        {"home": 1, "away": 0}
    print("ok  points per event; overturned scores and non-scores add nothing")

    # ------------------------------------------------ phrasing
    assert bb.when(30) == "with 6 minutes left in the third quarter"
    assert bb.when(35) == "with 1 minute left in the third quarter"
    assert bb.when(12) == "at the start of the second quarter"
    assert bb.when(48) == "in overtime"
    fx = {"home": HAWKS, "away": ROCKETS, "score": {"home": 54, "away": 51},
          "minute": 30, "status": "live", "sport": "basketball"}
    assert templates.say_match_state(fx) == (
        "Harbour Hawks 54, Reef Rockets 51, with 6 minutes left in the third quarter.")
    assert templates.say_score(dict(fx, score={"home": 50, "away": 50})) == \
        "Harbour Hawks and Reef Rockets, level at 50"
    three = {"kind": "basket", "minute": 9, "player": "Marcus Vale", "points": 3}
    assert templates.say_event(three, sport="basketball") == \
        "Marcus Vale hit a three with 3 minutes left in the first quarter"
    # football is untouched by any of this
    assert templates.when(34) == "on 34"
    print("ok  basketball says time and scores its own way; football unchanged")

    # --------------------------------- the whole stack on a basketball game
    ctx = make_ctx(start_minute=0, replay=BOTH)
    fixtures = ctx.provider.fixtures_today()
    assert {f["sport"] for f in fixtures} == {"football", "basketball"}

    fan, bball = "listener-football", "listener-basketball"
    spoken, structured, _ = run(ctx, bball, "follow_match", team="Harbour")
    assert structured["fixture_id"] == 9100001
    assert "waiting for tip-off" in spoken or "Not started" in spoken, spoken
    assert "Tell me when you hear tip-off" in spoken, spoken
    run(ctx, fan, "follow_match", team="Arsenal")
    print("ok  two listeners, two sports, one server:", spoken)

    # a long absence is read as headlines: threes, not every layup
    ctx.provider.jump_to(30)
    ctx.__dict__.pop("next_read", None)        # the poller waits between reads before tip-off; real time has passed
    poll_once(ctx)
    age_events(ctx)
    spoken, structured, _ = run(ctx, bball, "what_did_i_miss")
    assert structured["mode"] == "milestones", structured["mode"]
    assert "hit a three" in spoken and "Want the rest" in spoken, spoken
    assert "foul" not in spoken and "timeout" not in spoken, spoken
    assert "dunk" not in spoken, "a two is not a headline in basketball"
    assert structured["score"] == {"home": 8, "away": 10}, structured["score"]
    print("ok  basketball headlines are threes:", spoken)

    spoken, structured, _ = run(ctx, bball, "what_did_i_miss", full=True)
    said = {e["kind"] for e in structured["events"]}
    assert {"foul", "timeout", "substitution"} <= said, said
    assert "set up by Dario Quill" in spoken or "timeout" in spoken, spoken
    print("ok  'the rest' returns what the headlines skipped:", sorted(said))

    # football listener on the same server still gets football
    spoken, _, _ = run(ctx, fan, "get_match_state")
    assert "minutes in" in spoken and "quarter" not in spoken, spoken
    print("ok  the football listener still hears football:", spoken)

    # --------------------------------------- a review overturns a basket
    ctx.provider.jump_to(33)
    poll_once(ctx)
    evs = ctx.store.events(9100001)
    waved = [e for e in evs if e["kind"] == "basket" and e["minute"] == 31][0]
    assert waved["superseded_by"], "the review must supersede the basket"
    assert [e for e in evs if e["id"] == waved["id"]], "and must not delete it"
    score = ctx.provider.fixture(9100001)["score"]
    assert score == {"home": 8, "away": 10}, score
    spoken, structured, _ = run(ctx, bball, "what_did_i_miss")
    flagged = [e for e in structured["events"] if e["kind"] == "basket"
               and "later disallowed" in (e.get("detail") or "")]
    assert flagged, structured["events"]
    print("ok  replay review supersedes the basket without deleting it")

    # ------------------------------------------------- the other tools
    spoken, _, _ = run(ctx, bball, "get_lineups", team="Harbour")
    assert spoken.startswith("Harbour Hawks start Marcus Vale"), spoken
    assert "in goal" not in spoken and "formation" not in spoken, spoken

    spoken, structured, _ = run(ctx, bball, "get_officials")
    assert "crew chief" in spoken
    assert structured["officials"]["fouls_called"] == 2
    assert structured["officials"]["technicals"] == 1
    assert "yellows_shown" not in structured["officials"]
    print("ok  line-ups and officials in basketball terms:", spoken)

    spoken, structured, _ = run(ctx, bball, "get_event_detail", kind="score")
    assert structured["event"]["kind"] == "basket", structured["event"]
    print("ok  'that basket' resolves through the sport:", spoken)

    # "who is he": the sport decides what 'just happened' means
    ctx.provider.jump_to(36)
    poll_once(ctx)
    age_events(ctx)
    spoken, structured, _ = run(ctx, fan, "get_event_detail", kind="score")
    assert structured["event"]["kind"] == "goal", structured["event"]
    print("ok  'that goal' resolves to a goal in football:", spoken)
    spoken, structured, _ = run(ctx, bball, "get_player_context", player="he")
    assert structured["player"]["name"] == "Leo Banner", structured["player"]
    assert "just got ejected" in spoken, spoken
    print("ok  pronoun resolved from the last event in play:", spoken)

    # ----------------------------------------- the spoiler guard
    # Heard half time, 70 seconds of real match after the 24:00 mark.
    # Football puts half time at 45:00, so the same call there would be
    # an impossible negative; here it is a measurable delay.
    off, note = sync.estimate_from_anchor(ctx, 9100001, "half_time",
                                          real_now_seconds=24 * 60 + 70)
    assert note == "anchor:half_time" and off == 98, (off, note)
    from sideline.mcp.errors import ToolError
    try:
        run(ctx, bball, "sync_broadcast_delay")
        raise AssertionError("expected a prompt for an anchor")
    except ToolError as e:
        assert "tip-off" in str(e) and "basket going in" in str(e), str(e)
    print("ok  anchors use the sport's clock (half time at 24:00):", off, "s")

    # --------------------------------- sport preferences and access
    # Setting sport preference
    spoken, structured, _ = run(ctx, "sport-user", "set_preferences", sport="basketball")
    assert "focus on basketball" in spoken.lower(), spoken
    assert ctx.store.listener("sport-user")["sport"] == "basketball"

    # Following without a team prompts for the sport when not set
    try:
        run(ctx, "new-user", "follow_match")
        raise AssertionError("expected sport prompt when not following and no team given")
    except ToolError as e:
        assert e.detail["reason"] == "needs_sport" and "basketball or football" in str(e)

    # Calling follow_match with a sport choice
    spoken, structured, _ = run(ctx, "new-user", "follow_match", sport="basketball")
    assert "set for basketball" in spoken.lower()
    assert ctx.store.listener("new-user")["sport"] == "basketball"
    print("ok  asking for sport first: preference, prompt on cold start, and sport filtering")

    print("\nsports: all good")


if __name__ == "__main__":
    main()
