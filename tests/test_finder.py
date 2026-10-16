"""Which match, team or player the listener means: any match that has been played, forks, picks and stale state.

A stub feed (invented teams, labelled as such) that can list a team's matches over the last months and the next weeks,
because that is what the real feed does and what the finder depends on. Time is pinned.
"""

import datetime

from conftest import make_ctx

from sideline import clock, finder
from simulator import agent
from sideline.language import bedrock
from sideline.mcp.errors import ToolError
from sideline.providers.base import CAPABILITIES, Provider
from sideline.state.store import Event
from sideline.tools import REGISTRY

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def fixture(i, home, away, days, score=(0, 0), status="FT", minute=0, comp="Invent League"):
    ko = NOW + datetime.timedelta(days=days)
    return {"fixture_id": i, "home": home, "away": away, "home_id": hash(home) % 1000, "away_id": hash(away) % 1000,
            "minute": minute if status not in ("FT", "NS") else (90 if status == "FT" else 0), "status": status,
            "score": {"home": score[0], "away": score[1]}, "kickoff": ko.isoformat(), "competition": comp}


MATCHES = [
    fixture(1, "Harbour FC", "Reef United", -3, (2, 1)),
    fixture(2, "Cove Town", "Harbour FC", -10, (0, 0)),
    fixture(3, "Reef United", "Harbour FC", -25, (3, 1)),
    fixture(4, "Harbour FC", "Cove Town", -4, (1, 0), comp="League"),
    fixture(5, "Cove Town", "Harbour FC", -5, (2, 2), comp="Cup"),
    fixture(6, "Harbour FC", "Cove Town", 4, status="NS"),
    fixture(7, "Reef United", "Harbour FC", 11, status="NS"),
]
EVENTS = {1: [Event.make(1, 12, "goal", player="A. Vale", team="Harbour FC", assist="B. Quill"),
              Event.make(1, 40, "card", player="C. Banner", team="Reef United", colour="yellow"),
              Event.make(1, 58, "goal", player="C. Banner", team="Reef United"),
              Event.make(1, 66, "substitution", player="D. Moss", player_off="E. Lowe", team="Harbour FC"),
              Event.make(1, 81, "goal", player="A. Vale", team="Harbour FC")]}


class Feed(Provider):
    name = "stub"
    capabilities = frozenset(CAPABILITIES)

    def fixtures_today(self):
        return []

    def fixtures_on(self, offset_days=0):
        return []

    def fixture(self, fixture_id):
        return next((dict(m) for m in MATCHES if m["fixture_id"] == fixture_id), None)

    def events(self, fixture_id, since_minute=0):
        return [Event(dict(e, id=e["id"] + "x")) for e in EVENTS.get(fixture_id, [])]

    def team_matches(self, team, days_back=90, days_ahead=45):
        if "harbour" not in team.lower():
            return None
        mine = [dict(m) for m in MATCHES if "Harbour FC" in (m["home"], m["away"])]
        done = sorted((m for m in mine if m["status"] == "FT"), key=lambda m: m["kickoff"], reverse=True)
        ahead = sorted((m for m in mine if m["status"] != "FT"), key=lambda m: m["kickoff"])
        return {"team": "Harbour FC", "team_id": hash("Harbour FC") % 1000, "upcoming": ahead, "recent": done}

    def squad(self, team):
        if "harbour" not in team.lower():
            return None
        return {"team": "Harbour FC", "coach": "R. Hale", "captain": "A. Vale", "players": [
            {"name": "A. Vale", "number": 9, "position": "attacker", "captain": True},
            {"name": "F. Marsh", "number": 1, "position": "goalkeeper", "captain": False},
            {"name": "G. Pike", "number": 4, "position": "defender", "captain": False},
            {"name": "H. Shaw", "number": 5, "position": "defender", "captain": False}]}

    def team_stats(self, team):
        if "harbour" not in team.lower():
            return None
        return {"team": "Harbour FC", "played": 8, "won": 5, "drawn": 2, "lost": 1, "goals_for": 14, "goals_against": 6,
                "clean_sheets": 3, "possession": 58.4, "corners_per_game": 5.1}


def ask(ctx, tool, args, who="ann"):
    return REGISTRY[tool](ctx, args, who)


def declined(ctx, tool, args, who="ann"):
    try:
        ask(ctx, tool, args, who)
    except ToolError as e:
        return e
    raise AssertionError("expected a ToolError from %s %s" % (tool, args))


def main():
    real_now = clock.now
    clock.now = lambda: NOW
    try:
        ctx = make_ctx()
        ctx.provider = Feed()
        rec = ctx.store.listener("ann")
        rec["tz_offset_minutes"] = 240
        ctx.store.save_listener(rec)

        # 1. Nothing is followed and nothing is on, and a played match can still be asked about, with everything.
        spoken, s, _ = ask(ctx, "get_match_report", {"team": "Harbour FC", "when": "last"})
        assert "Harbour FC against Reef United" in spoken and "Vale" in spoken and "Banner" in spoken, spoken
        assert "2" in spoken and "1" in spoken and "also 1 card and 1 substitution" in spoken, spoken
        assert s["verbatim"] and s["fixture_id"] == 1
        assert ctx.store.events(1), "the feed's events are kept once read"
        print("ok  a played match is reported in full with nothing followed:", spoken[:90] + "...")

        # 2. One part, by name.
        spoken, _, _ = ask(ctx, "get_match_report", {"team": "Harbour FC", "when": "last", "part": "cards"})
        assert spoken.startswith("Cards in Harbour FC against Reef United") and "Banner" in spoken, spoken
        spoken, _, _ = ask(ctx, "get_match_report", {"fixture_id": 1, "part": "substitutions"})
        assert "Moss" in spoken and "Lowe" in spoken, spoken
        spoken, _, _ = ask(ctx, "get_match_report", {"fixture_id": 3, "part": "goals"})
        assert spoken.startswith("There were no goals in Reef United against Harbour FC"), spoken
        print("ok  goals, cards, substitutions by name; a part with nothing in it says so")

        # 3. The other tools work on a match that has been played, with no follow.
        spoken, _, _ = ask(ctx, "get_match_state", {"team": "Harbour FC", "when": "last"})
        assert "Full time" in spoken and "Harbour FC" in spoken, spoken
        spoken, _, _ = ask(ctx, "get_event_detail", {"team": "Harbour FC", "opponent": "Reef United", "kind": "goal"})
        assert "Vale" in spoken, spoken
        print("ok  the score and one moment of a match already played, with nothing followed")

        # 4. The other side narrows it; two near ones are a FORK, listed with their scores and days, not guessed.
        spoken, s, _ = ask(ctx, "get_match_state", {"team": "Harbour FC", "opponent": "Reef United"})
        assert s["fixture_id"] == 1, "of three, the nearest played"
        fork = declined(ctx, "get_match_report", {"team": "Harbour FC", "opponent": "Cove Town"})
        assert fork.detail["reason"] == "ambiguous" and fork.detail["fork"] and len(fork.detail["candidates"]) == 2, fork.detail
        assert {c["fixture_id"] for c in fork.detail["candidates"]} == {4, 5}, "a question about what happened prefers played matches"
        assert fork.spoken.startswith("I can see more than one Harbour FC match. Which one: 1, ") and "Cove Town 2, Harbour FC 2, on 9 October" in fork.spoken \
            and "Harbour FC 1, Cove Town 0, on 10 October" in fork.spoken, fork.spoken
        three = declined(ctx, "get_match_state", {"team": "Harbour FC", "opponent": "Cove Town"})
        assert len(three.detail["candidates"]) == 3, "with no preference the next match is as near as the last"
        print("ok  two plausible matches are a numbered fork with scores and days:", fork.spoken[:100])

        # 5. When or a date picks one.
        _, s, _ = ask(ctx, "get_match_state", {"team": "Harbour FC", "when": "next"})
        assert s["fixture_id"] == 6, "the next, not a later one"
        day = (NOW + datetime.timedelta(days=-10)).date().isoformat()
        _, s, _ = ask(ctx, "get_match_state", {"team": "Harbour FC", "date": day})
        assert s["fixture_id"] == 2
        # a day with no team named: that day's matches, however far back
        by_day = lambda off: [dict(m) for m in MATCHES
                              if (datetime.datetime.fromisoformat(m["kickoff"]).date() - NOW.date()).days == off]
        ctx.provider.fixtures_on = by_day
        _, s, _ = ask(ctx, "get_match_state", {"date": day})
        assert s["fixture_id"] == 2, "the match on that day, with no team said"
        ctx.provider.fixtures_on = lambda off: []
        miss = declined(ctx, "get_match_state", {"team": "Harbour FC", "date": "2026-01-02"})
        assert "can't find a match on 2 January for Harbour FC" in miss.spoken and "I do see" in miss.spoken, miss.spoken
        _, s, _ = ask(ctx, "get_match_state", {"team": "Harbour FC", "opponent": "Cove Town", "when": "last"})
        assert s["fixture_id"] == 4, "'last' ranks played matches latest first"
        print("ok  'next', 'last' and a date each pick their match; a date with none says what is there")

        # 6. A team the feed does not have.
        e = declined(ctx, "get_match_report", {"team": "Xyzzy"})
        assert "Xyzzy" in e.spoken and "match" not in e.spoken.split(".")[0].replace("can't find a match", ""), e.spoken
        print("ok  an unknown team is said so, not 'that match'")

        # 7. Team questions need no match at all.
        spoken, s, _ = ask(ctx, "get_schedule", {"team": "Harbour FC"})
        assert spoken.startswith("Harbour FC next") and "Cove Town" in spoken and "Reef United" in spoken, spoken
        spoken, s, _ = ask(ctx, "get_schedule", {"team": "Harbour FC", "which": "last"})
        assert spoken.startswith("Harbour FC's last 5 results:") and "Harbour FC 2, Reef United 1" in spoken, spoken
        assert len(s["form"]) == 5
        spoken, _, _ = ask(ctx, "get_team_form", {"team": "Harbour FC"})
        assert spoken.startswith("Harbour FC recently:") and "won" in spoken
        spoken, _, _ = ask(ctx, "get_team_stats", {"team": "Harbour FC"})
        assert spoken.startswith("Harbour FC this season: 8 games, won 5, drew 2, lost 1. 14 goals scored and 6 conceded. 3 clean sheets. About 58 percent") , spoken
        spoken, _, _ = ask(ctx, "get_squad", {"team": "Harbour FC"})
        assert "4 players: 1 goalkeeper, 2 defenders and 1 attacker" in spoken and "R. Hale as manager" in spoken and "captain is A. Vale" in spoken, spoken
        spoken, _, _ = ask(ctx, "get_squad", {"team": "Harbour FC", "position": "defender"})
        assert spoken == "Harbour FC's defenders: G. Pike, number 4, H. Shaw, number 5.", spoken
        assert declined(ctx, "get_squad", {"position": "defender"}).spoken == "Which team's squad?"
        print("ok  squad, season stats, next games, last results and form need a team and no match")

        # 8. A followed match the feed has never heard of is forgotten, once, instead of failing for ever.
        rec = ctx.store.listener("stale")
        rec["following"] = 999999
        ctx.store.save_listener(rec)
        e = declined(ctx, "get_match_state", {}, "stale")
        assert e.spoken.startswith("I'm not following a match right now") and e.detail["forgot"] == 999999
        assert ctx.store.listener("stale")["following"] is None
        e = declined(ctx, "get_match_state", {}, "stale")
        assert e.detail["reason"] == "no_fixture"
        print("ok  a followed match the feed does not know is forgotten, and the listener is told what is true")

        # 9. No broadcast delay is applied to a match that has been played.
        rec = ctx.store.listener("watcher")
        rec["broadcast_offset"] = 300
        ctx.store.save_listener(rec)
        _, s, _ = ask(ctx, "get_match_state", {"team": "Harbour FC", "when": "last"}, "watcher")
        assert s["minute"] == 90 and s["score"] == {"home": 2, "away": 1}, s
        print("ok  the spoiler guard holds back a match in play, never one that is over")

        # 9b. A follow-up that names no match means the one they were just asking about; nothing is ever picked for them.
        ask(ctx, "get_match_report", {"team": "Harbour FC", "when": "last"}, "chat")
        spoken, s, _ = ask(ctx, "get_match_report", {"part": "substitutions"}, "chat")
        assert s["fixture_id"] == 1 and "Moss" in spoken, "'who came on?' after the Harbour game is about the Harbour game"
        fresh = declined(ctx, "get_match_report", {}, "nobody-asked")
        assert fresh.detail["reason"] == "no_fixture", "nothing named, nothing followed, nothing discussed: it asks"
        import time as _time
        later = _time.time() + 3600
        real = _time.time
        _time.time = lambda: later
        try:
            assert declined(ctx, "get_match_report", {}, "chat").detail["reason"] == "no_fixture", "an hour later it has moved on"
        finally:
            _time.time = real
        print("ok  a follow-up that names no match means the last one they asked about, for ten minutes; never one they did not ask")

        # 9c. A model that does not know the year writes last year's: the day is moved to the year that is nearest.
        for written, want in (("2025-09-20", "2026-09-20"), ("2026-10-11", "2026-10-11"), ("2024-10-16", "2026-10-16"),
                              ("2027-10-10", "2026-10-10")):
            assert str(finder.Reference({"date": written}).date) == want, (written, finder.Reference({"date": written}).date)
        _, s, _ = ask(ctx, "get_match_report", {"team": "Harbour FC", "date": "2025-10-11"})
        assert s["fixture_id"] == 1, "'the 11th of October' with last year's year still finds the match played on the 11th"
        print("ok  a date written with the wrong year still finds the match: the day is what was said")

        # 9d. An unknown team is a question back, not a dead end.
        for tool in ("get_squad", "get_team_stats", "get_schedule", "get_match_report"):
            e = declined(ctx, tool, {"team": "Team Squad"})
            assert e.spoken == "I can't find a team called Team Squad. Which team do you mean?", (tool, e.spoken)
        print("ok  'Team Squad' is not a team: Sideline asks which team, whatever the tool")

        # 9e. A team outside the leagues the plan covers is not "unknown": it is not covered, and that is said.
        ctx.provider.competitions = lambda country=None: [
            {"id": 1, "name": "Superliga", "country": "Denmark"}, {"id": 2, "name": "Premiership", "country": "Scotland"},
            {"id": 3, "name": "Premiership Play-Offs", "country": "Scotland"}]
        try:
            e = declined(ctx, "get_squad", {"team": "Arsenal"})
            assert e.spoken == ("I can't find Arsenal in the leagues I cover: Superliga (Denmark) and Premiership (Scotland). "
                                "Which team do you mean?"), e.spoken
            assert e.detail["covered"] == ["Superliga (Denmark)", "Premiership (Scotland)"]
        finally:
            del ctx.provider.competitions
        print("ok  a team outside the covered leagues is said to be outside them, with which ones are covered")

        # 10. A fork is remembered with the question; the pick answers it.
        class Scripted(object):
            def __init__(self):
                self.plan, self.seen = [], []

            def converse(self, **kw):
                self.seen.append(kw["messages"][-1]["content"][0])
                last = kw["messages"][-1]["content"][0]
                if "toolResult" not in last and self.plan:
                    name, args = self.plan.pop(0)
                    return {"output": {"message": {"role": "assistant", "content": [
                        {"toolUse": {"toolUseId": "t%d" % len(self.seen), "name": name, "input": args}}]}}}
                return {"output": {"message": {"role": "assistant", "content": [{"text": "Okay."}]}}}
        model, real = Scripted(), (bedrock.available, bedrock.client)
        bedrock.available, bedrock.client = (lambda: True), (lambda: model)
        run_tool = lambda name, args, who: REGISTRY[name](ctx, args, who)       # noqa: E731
        try:
            model.plan = [("get_match_report", {"team": "Harbour FC", "opponent": "Cove Town"})]
            out = agent.run(ctx, "What happened against Cove Town?", "pick", run_tool)
            assert out["generated_by"] == "nova" and out["text"] == "Okay.", out
            declined_result = model.seen[1]
            assert declined_result["toolResult"]["status"] == "error"
            assert "I can see more than one Harbour FC match" in declined_result["toolResult"]["content"][0]["text"]
            model.plan = [("get_match_report", {"fixture_id": 4})]
            agent.run(ctx, "The second one (fixture_id 4)", "pick", run_tool)
            assert any('earlier question: "What happened against Cove Town?"' in (m.get("text") or "") for m in model.seen), model.seen
            model.plan = []
            model.seen[:] = []
            agent.run(ctx, "Who is the manager of Harbour FC?", "pick", run_tool)
            assert all("earlier question" not in (m.get("text") or "") for m in model.seen), "the pick is used once"
        finally:
            bedrock.available, bedrock.client = real
        seen_systems = []

        class Spy(object):
            def converse(self, **kw):
                seen_systems.append(kw["system"][0]["text"])
                return {"output": {"message": {"role": "assistant", "content": [{"text": "Okay."}]}}}
        bedrock.available, bedrock.client = (lambda: True), (lambda: Spy())
        try:
            agent.run(ctx, "What day is it?", "ann", run_tool)
        finally:
            bedrock.available, bedrock.client = real
        assert "Today is Wednesday 14 October 2026." in seen_systems[0], seen_systems[0][-120:]
        assert "Saturday is 2026-10-17" in seen_systems[0] and "Tuesday is 2026-10-20" in seen_systems[0], "the next week, spelled out"
        agent.FOCUSES.set_pending("p2", "a question")
        assert agent.FOCUSES.take_pending("p2") == "a question" and agent.FOCUSES.take_pending("p2") is None
        print("ok  a fork is read out, the question is remembered, and the pick answers it (once)")
    finally:
        clock.now = real_now

    # A server built with a test provider never writes to a real table, whatever SIDELINE_STATE says.
    import os
    from sideline import app
    from sideline.state import MemoryStore
    os.environ["SIDELINE_PORT"] = "0"
    real_state = app.CONFIG.state, app.CONFIG.port
    app.CONFIG.state, app.CONFIG.port = "dynamo", 0
    try:
        ctx2, srv, _ = app.build(provider=Feed())
        assert isinstance(ctx2.store, MemoryStore), type(ctx2.store)
        srv.server_close()
    finally:
        app.CONFIG.state, app.CONFIG.port = real_state
    print("ok  a server built on invented test data can only use memory: it can never touch a real table")

    # The finder's scoring on its own.
    cands = [dict(m) for m in MATCHES]
    ref = finder.Reference({"team": "Harbour FC", "when": "last"})
    scored = finder.score_all(cands, ref, None, 240, now=NOW)
    assert [f["fixture_id"] for _, f in scored][:2] == [1, 4] and scored[0][0] == 1.0 and scored[1][0] == 0.5 and all(
        finder.kind(f) != "coming" for _, f in scored), [(round(s, 2), f["fixture_id"]) for s, f in scored]
    assert finder.decide(scored)[0] == "one"
    assert finder.decide([(0.9, cands[0]), (0.85, cands[1])])[0] == "fork"
    assert finder.decide([(0.9, cands[0]), (0.3, cands[1])])[0] == "one" and finder.decide([])[0] == "none"
    live = dict(cands[0], status="2H", minute=61)
    assert finder.kind(live) == "live" and finder.kind(cands[5]) == "coming" and finder.kind(cands[0]) == "played"
    assert finder.Reference({}).open_ended and not finder.Reference({"team": "x"}).open_ended
    assert finder.Reference({"when": "never"}).when is None and finder.Reference({"date": "2026-13-45"}).date is None
    # The match they were just asking about outranks a close rival, so "what's the score?" needs no fork
    open_ref = finder.Reference({"team": "Harbour FC"})
    plain = finder.score_all(cands, open_ref, None, 240, now=NOW)
    top_two = [f["fixture_id"] for _, f in plain][:2]
    assert finder.decide(plain)[0] == "fork", "without it the two nearest are a fork"
    talked = finder.score_all(cands, open_ref, None, 240, now=NOW, discussed=top_two[1])
    assert talked[0][1]["fixture_id"] == top_two[1] and finder.decide(talked)[0] == "one", [(round(x, 2), f["fixture_id"]) for x, f in talked]
    print("ok  the match just discussed outranks a close rival, so a plain follow-up is not a fork")
    print("ok  scoring: 'last' ranks the played matches 1, one half, ...; a clear winner is used, a close pair is a fork")

    print("\nfinder: all good")


if __name__ == "__main__":
    main()
