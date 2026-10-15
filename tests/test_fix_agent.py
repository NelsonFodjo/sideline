"""Regression tests for the simulator agent fixes (docs/BUGS.md, AG-01 to AG-22).

The model here is scripted and records nothing called `calls`, so the agent behaves as it does in production: the
greeting bypass, the read-only shortcuts, tool pruning and the one-tool bypass are all switched on.
"""

import json
import threading
import time
import urllib.error

from conftest import make_ctx

from sideline.app import resolve_listener, tool_runner
from sideline.language import agent, bedrock
from sideline.mcp import server as mcp_server
from sideline.mcp.client import McpClient
from sideline.mcp.registry import public_tools
from sideline.tools import REGISTRY

CATALOG = public_tools()
SPECS = {spec["name"]: spec for spec in CATALOG}


class Scripted(object):
    """Makes the tool calls it is told to, then answers. Records every request in .seen (not .calls)."""

    def __init__(self, plan=None, text="Okay.", stop="end_turn", always_tool=None):
        self.plan, self.text, self.stop, self.always_tool = list(plan or []), text, stop, always_tool
        self.seen = []

    def converse(self, **kw):
        self.seen.append(kw)
        if self.always_tool and "toolConfig" in kw:
            # three calls a turn, for ever: it runs into the tool-call cap part-way through a turn
            name, args = self.always_tool
            return {"stopReason": "tool_use", "output": {"message": {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": "t%d-%d" % (len(self.seen), i), "name": name, "input": args}}
                for i in range(3)]}}}
        if self.plan and "toolConfig" in kw:
            name, args = self.plan.pop(0)
            return {"stopReason": "tool_use", "output": {"message": {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": "t%d" % len(self.seen), "name": name, "input": args}}]}}}
        return {"stopReason": self.stop, "output": {"message": {"role": "assistant", "content": [{"text": self.text}]}}}


def _with_model(model):
    real = bedrock.available, bedrock.client
    bedrock.available, bedrock.client = (lambda: True), (lambda: model)
    return real


def _restore(real):
    bedrock.available, bedrock.client = real


def _counting_runner(ctx, ran, agent_mode=True):
    def run(name, args, who):
        ran.append(name)
        if agent_mode and name == "what_did_i_miss":
            return REGISTRY[name](ctx, args, who, agent_mode=True)
        return REGISTRY[name](ctx, args, who)
    return run


def _tool_results(kw):
    return [b["toolResult"] for m in kw["messages"] for b in m.get("content", [])
            if isinstance(b, dict) and "toolResult" in b]


def test_catchup_fetched_once():
    # AG-01: the catch-up moves the "told" marker, so it may run once per question, and only by the model's choice.
    ctx = make_ctx(start_minute=12)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "miss")
    ctx.provider.jump_to(64)
    ran = []
    model = Scripted(plan=[("what_did_i_miss", {})], text="Arsenal lead two-nil: Saka scored twice.")
    real = _with_model(model)
    try:
        out = agent.run(ctx, "What did I miss?", "miss", _counting_runner(ctx, ran), mcp_tools=CATALOG)
    finally:
        _restore(real)
    assert ran == ["what_did_i_miss"], ran
    assert out["generated_by"] == "nova" and out["text"] == model.text, out
    told = json.loads(_tool_results(model.seen[1])[0]["content"][0]["text"])
    assert told["ok"] and told["data"]["events"], "the model got the events the single call consumed"
    print("ok  AG-01 'what did I miss' runs the catch-up exactly once, and the model gets its events")

    for question in ("What happened to Saka?", "Tell me everything about Arsenal", "Who's playing?",
                     "Follow Arsenal", "Keep it short please"):
        plan = agent._fast_plan(question, SPECS, {"team": "Arsenal"}, ctx)
        assert plan is None or plan[0] not in agent.STATEFUL_TOOLS, (question, plan)
    print("ok  AG-01 no shortcut ever runs a tool that changes listener state")


def test_tool_shortlist():
    # AG-02 / AG-03 / AG-20: real names only, whole words, a stable sorted order.
    live = set(SPECS)
    for question, wanted in (("What's the table?", "get_standings"), ("Who is the top scorer?", "get_top_scorers"),
                             ("The kick-off just went", "sync_broadcast_delay"), ("I support Arsenal", "set_favourites"),
                             ("Are my teams playing?", "get_my_matches"), ("Who's in the Celtic squad?", "get_squad"),
                             ("Who's refereeing?", "get_officials"), ("What's their form?", "get_team_form")):
        names = [t["name"] for t in agent._select_candidate_tools(question, CATALOG)]
        assert wanted in names, (question, names)
        assert set(names) <= live and names == sorted(names) and len(names) <= 8, names
        assert names == [t["name"] for t in agent._select_candidate_tools(question, CATALOG)], "deterministic"
    prefer = [t["name"] for t in agent._select_candidate_tools("I prefer brief answers", CATALOG)]
    assert "get_officials" not in prefer, "'ref' is not a word in 'prefer'"
    lyon = [t["name"] for t in agent._select_candidate_tools("How did Lyon do?", CATALOG)]
    assert "follow_match" not in lyon and "get_lineups" not in lyon, lyon
    assert set(agent._select_candidate_tools("anything", [SPECS["get_standings"]])[0]) and \
        [t["name"] for t in agent._select_candidate_tools("table", [SPECS["get_standings"]])] == ["get_standings"]
    for gone in ("_FAST_INTENTS", "SWARM_AGENTS", "SubAgent"):
        assert not hasattr(agent, gone), gone
    assert "get_table" not in open(agent.__file__).read()
    print("ok  AG-02/03 the shortlist comes from the live catalog, matches whole words, and is sorted")

    schema = agent._model_schema(SPECS["get_match_state"]["inputSchema"])
    flat = json.dumps(schema)
    assert "maxLength" not in flat and "minimum" not in flat and "enum" in flat and schema["properties"]["team"]
    print("ok  AG-20 the model's schema keeps only the keywords it needs")


def test_fast_paths():
    ctx = make_ctx(start_minute=40)
    ctx.provider.known_teams = lambda: ["Arsenal", "Tottenham Hotspur", "Inter Milan", "Internacional"]

    # AG-04: only arguments the schema has
    assert agent._schema_args("get_fixtures", {"team": "Arsenal", "when": "today", "fixture_id": 3}, SPECS) == {"when": "today"}
    assert agent._fast_plan("What's on today?", SPECS, {"team": "Arsenal", "fixture_id": 7, "sport": "football"}, ctx) \
        == ("get_fixtures", {}), "nothing from the topic is injected"
    assert agent._fast_plan("What Premier League games are on today?", SPECS, {}, ctx) == \
        ("get_fixtures", {"competition": "Premier League"})
    assert agent._fast_plan("What's the Premier League score?", SPECS, {}, ctx) is None
    assert agent._fast_plan("What's the Premier League table?", SPECS, {}, ctx) == \
        ("get_standings", {"competition": "Premier League"})
    print("ok  AG-04 shortcut arguments are only those the tool's schema has")

    # AG-05: "next game" is get_schedule, and needs a team
    assert agent._fast_plan("When's the next game?", SPECS, {"team": "Arsenal"}, ctx) == \
        ("get_schedule", {"which": "next", "team": "Arsenal"})
    assert agent._fast_plan("When's the next game?", SPECS, {}, ctx) is None
    assert agent._fast_plan("When do Arsenal play next?", SPECS, {}, ctx) == \
        ("get_schedule", {"which": "next", "team": "Arsenal"})
    print("ok  AG-05 'next game' asks get_schedule for the next match, never get_fixtures(when=next)")

    # AG-09: whole-utterance patterns; anything less plain goes to the model
    for question in ("Who won the golden boot last season?", "Who is the manager of Celtic?", "Celtic squad",
                     "What happened to Saka?", "Who is out of contract?", "What's the score and who is refereeing?",
                     "Did they win the league?", "What's the interested score?"):
        assert agent._fast_plan(question, SPECS, {}, ctx) is None, question
    assert agent._fast_plan("Hey Sideline, what's the score?", SPECS, {}, ctx) == ("get_match_state", {})
    assert agent._fast_plan("Who's refereeing today?", SPECS, {}, ctx) == ("get_officials", {})
    print("ok  AG-09 shortcuts fire only on a plain, whole question; ambiguous ones go to the model")

    # AG-21: team names are whole words
    assert agent._known_team(ctx, "interested") is None
    assert agent._known_team(ctx, "inter") == "Inter Milan"
    assert agent._known_team(ctx, "spurs") is None, "never guessed"
    print("ok  AG-21 'Inter' is not found in 'interested'")

    # AG-22: whole fixture ids only
    assert agent._without_invented_id({"fixture_id": 1}, "Arsenal (fixture_id 12)") == {}
    assert agent._without_invented_id({"fixture_id": 12}, "Arsenal (fixture_id 12)") == {"fixture_id": 12}
    print("ok  AG-22 'fixture_id 1' does not vouch for '(fixture_id 12)'")

    # A shortcut that works says the tool's own sentence with no model call
    model = Scripted()
    real = _with_model(model)
    try:
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "fast")
        out = agent.run(ctx, "What's the score?", "fast", lambda n, a, w: REGISTRY[n](ctx, a, w), mcp_tools=CATALOG)
        assert out["generated_by"] == "fast" and not model.seen and "Arsenal" in out["text"], out
        # and one that fails is handed to the model, never read out
        out = agent.run(ctx, "Who's refereeing?", "fast", lambda n, a, w: (_ for _ in ()).throw(
            urllib.error.URLError("refused")), mcp_tools=CATALOG)
        assert out["generated_by"] == "nova" and len(model.seen) == 1 and "refused" not in out["text"], out
    finally:
        _restore(real)
    print("ok  a plain question is answered by its tool alone; a failed shortcut falls back to the model")


def test_conversational_and_how_many():
    # AG-07
    assert agent._match_conversational("Hello!") and agent._match_conversational("Thank you very much.")
    for question in ("Hey, what's the score?", "Thanks, who scored?", "What sports are on today?",
                     "Hi, who is winning?", "What are you doing about Arsenal?"):
        assert agent._match_conversational(question) is None, question
    print("ok  AG-07 greetings are answered only when the whole utterance is one")

    # AG-08
    topic = {"last_tool": "get_fixtures", "total": 5, "when": "today", "competition_name": "Premier League"}
    assert agent._how_many("How many games is that?", topic) == "That's 5 matches in the Premier League today."
    assert agent._how_many("How many yellow cards?", topic) is None
    assert agent._how_many("How many matches?", dict(topic, last_tool="get_match_state")) is None
    assert agent._how_many("How many matches today?", dict(topic, when="tomorrow")) is None
    assert agent._how_many("How many matches?", dict(topic, when="on Saturday", fixtures_kind="finished",
                                                       competition_name="")) == "That's 5 finished matches on Saturday."
    print("ok  AG-08 'how many' repeats a fixture count only right after a fixture list, with its own day")


def test_errors_never_spoken():
    ctx = make_ctx(start_minute=40)
    # AG-06: bad arguments go back to the model and are never the answer
    model = Scripted(plan=[("get_fixtures", {"when": "next"})], text="Here's what's coming up.")
    real = _with_model(model)
    try:
        out = agent.run(ctx, "Show me the upcoming matches in a while", "err", lambda n, a, w: REGISTRY[n](ctx, a, w),
                        mcp_tools=CATALOG)
    finally:
        _restore(real)
    assert out["generated_by"] == "nova" and "must be one of" not in out["text"], out
    record = out["tool_results"][0]
    assert record["is_error"] and not record["spoken"], record
    sent = json.loads(_tool_results(model.seen[1])[0]["content"][0]["text"])
    assert "must be one of" in sent["error"] and "spoken" not in sent, sent
    assert agent._spoken_from_tools([record]) == ""
    print("ok  AG-06 a validation error reaches the model to fix, never the listener")

    # AG-14: a transport failure is a tool error, not an exception
    def broken(name, args, who):
        raise urllib.error.URLError("connection refused")
    content, is_err, record = agent._execute_tool("get_match_state", {}, "err", broken, SPECS)
    assert is_err and record["is_error"] and not record["spoken"] and "refused" not in content, (content, record)
    for exc in (RuntimeError("MCP error"), TimeoutError("slow"), ValueError("bad json")):
        assert agent._execute_tool("get_match_state", {}, "err", lambda *a: (_ for _ in ()).throw(exc), SPECS)[1]
    model = Scripted(plan=[("get_match_state", {})], text="I couldn't reach the match feed just now.")
    real = _with_model(model)
    try:
        out = agent.run(ctx, "Score in the Arsenal game please, quickly", "err", broken, mcp_tools=CATALOG)
        assert out["text"] == model.text and out["tool_results"][0]["is_error"], out
        try:
            agent.run(ctx, "Anything?", "err", broken, mcp_tools=[{"no": "name"}])
        except agent.AgentUnavailable:
            pass
        else:
            raise AssertionError("an unexpected failure must leave as AgentUnavailable (503), not a 500")
    finally:
        _restore(real)
    print("ok  AG-14 transport errors become a tool error; anything unexpected is AgentUnavailable")

    # AG-11: tools' own words used as a fallback are not cut to three sentences
    both = agent._spoken_from_tools([{"spoken": "One. Two. Three."}, {"spoken": "Four."},
                                     {"spoken": "Bad args", "is_error": True}])
    assert both == "One. Two. Three. Four.", both
    print("ok  AG-11 tool sentences are not truncated when joined")


def test_limits_and_truncation():
    ctx = make_ctx(start_minute=40)
    # AG-12: a model that never stops calling tools still gets a final answer, from a call with no tools
    model = Scripted(always_tool=("get_match_state", {"team": "Arsenal"}), text="Arsenal lead one-nil.")
    real = _with_model(model)
    try:
        out = agent.run(ctx, "Keep checking the Arsenal match state over and over", "cap",
                        lambda n, a, w: REGISTRY[n](ctx, a, w), mcp_tools=CATALOG)
    finally:
        _restore(real)
    last = model.seen[-1]
    assert out["text"] == "Arsenal lead one-nil." and "toolConfig" not in last, out
    assert all(isinstance(b, dict) and "text" in b for m in last["messages"] for b in m["content"]), \
        "a call without toolConfig carries no toolUse/toolResult blocks"
    roles = [m["role"] for m in last["messages"]]
    assert roles[-1] == "user" and all(a != b for a, b in zip(roles, roles[1:])), roles
    assert len(out["tool_results"]) <= agent.MAX_TOOL_CALLS
    print("ok  AG-12 at the tool-call cap, one final call without tools gives the answer")

    # AG-13: a cut answer is trimmed to whole sentences; the budget has room for them
    assert agent.MAX_TOKENS >= 200
    model = Scripted(text="Arsenal lead two-nil. Saka scored both, the second a curling", stop="max_tokens")
    real = _with_model(model)
    try:
        out = agent.run(ctx, "Tell me something about Arsenal please, mate", "cut", lambda n, a, w: REGISTRY[n](ctx, a, w),
                        mcp_tools=CATALOG)
        assert out["text"] == "Arsenal lead two-nil.", out
        assert model.seen[0]["inferenceConfig"]["maxTokens"] == agent.MAX_TOKENS
        model.text = "<thinking>The listener wants the score so I will call"
        try:
            agent.run(ctx, "Tell me something about Arsenal please, mate", "cut", lambda n, a, w: None,
                      mcp_tools=CATALOG)
        except agent.AgentUnavailable:
            pass
        else:
            raise AssertionError("a reply that is only cut-off reasoning has nothing to say")
    finally:
        _restore(real)
    assert agent._complete_sentences("It's 1-0. Saka") == "It's 1-0."
    assert agent._complete_sentences("No full stop here") == ""
    print("ok  AG-13 an answer cut by the token limit is trimmed to whole sentences")


def test_expiry():
    # AG-16: a stored topic and history from yesterday are not today's context
    ctx = make_ctx()
    rec = ctx.store.listener("old")
    rec["topic"] = {"team": "Celtic", "fixture_id": 9, "at": int(time.time()) - 86400}
    rec["history"] = [{"role": "user", "text": "Celtic?", "at": int(time.time()) - 86400},
                      {"role": "assistant", "text": "Celtic won.", "at": int(time.time()) - 86400}]
    ctx.store.save_listener(rec)
    assert agent.FOCUSES.topic("old", store=ctx.store) == {}
    assert agent.FOCUSES.line("old", store=ctx.store) == ""
    assert agent.CONVERSATIONS.get("old", store=ctx.store) == []
    rec["topic"] = {"team": "Celtic", "at": int(time.time()) - 30}
    rec["history"] = [dict(h, at=int(time.time()) - 30) for h in rec["history"]]
    ctx.store.save_listener(rec)
    assert agent.FOCUSES.topic("old", store=ctx.store) == {"team": "Celtic"}
    assert len(agent.CONVERSATIONS.get("old", store=ctx.store)) == 2
    agent.FOCUSES.remember("fresh", [{"name": "get_standings", "args": {"team": "Celtic"}, "structured": {}}],
                           store=ctx.store)
    assert ctx.store.listener("fresh")["topic"]["at"] > time.time() - 5, "the stored topic says when"
    print("ok  AG-16 stored topic and history expire; a fresh one is kept")


def test_mcp_client_lock():
    # AG-15: one slow tool call does not hold up another
    ctx = make_ctx(start_minute=40)
    inner = tool_runner(ctx)

    def slow(name, args, listener_id, agent=False):
        if name == "get_capabilities":
            time.sleep(0.6)
        return inner(name, args, listener_id, agent=agent)
    srv = mcp_server.serve("127.0.0.1", 0, slow, resolve_listener, ["localhost", "127.0.0.1"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = McpClient("http://127.0.0.1:%d/mcp" % srv.server_address[1], timeout=5)
    try:
        client.discover("ann")
        done = {}
        t = threading.Thread(target=lambda: client.call("get_capabilities", {}, "ann"))
        t.start()
        time.sleep(0.1)
        began = time.time()
        client.call("get_fixtures", {}, "ann")
        done["fast"] = time.time() - began
        t.join()
        assert done["fast"] < 0.4, done
        print("ok  AG-15 a slow tool call no longer blocks another listener's call")

        # None and malformed answers are failures, not crashes
        client._post = lambda *a, **k: ("sid", None)
        try:
            client.call("get_match_state", {}, "ann")
        except RuntimeError:
            pass
        else:
            raise AssertionError("an empty answer must raise a RuntimeError")
        print("ok  AG-15 an empty tools/call response is a clear failure")
    finally:
        srv.shutdown()
        srv.server_close()

    # concurrent first calls open one session, not several
    srv = mcp_server.serve("127.0.0.1", 0, tool_runner(ctx), resolve_listener, ["localhost", "127.0.0.1"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = McpClient("http://127.0.0.1:%d/mcp" % srv.server_address[1], timeout=5)
    try:
        inits = []
        real_init = client._rpc

        def counting(method, *a, **k):
            if method == "initialize":
                inits.append(1)
            return real_init(method, *a, **k)
        client._rpc = counting
        threads = [threading.Thread(target=lambda: client.call("get_capabilities", {}, "ann")) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(inits) == 1, inits
        print("ok  AG-15 concurrent first calls share one initialize")
    finally:
        srv.shutdown()
        srv.server_close()


def test_prompt():
    system = agent.SYSTEM
    for must in ("commentator", "Never invent", "behind live", "never read out errors", "1 to 3 short"):
        assert must in system, must
    assert len(system) < 1800, len(system)
    print("ok  the system prompt asks for a warm, truthful, spoiler-safe commentator, and stays compact")


def main():
    test_catchup_fetched_once()
    test_tool_shortlist()
    test_fast_paths()
    test_conversational_and_how_many()
    test_errors_never_spoken()
    test_limits_and_truncation()
    test_expiry()
    test_mcp_client_lock()
    test_prompt()
    print("\nagent fixes: all good")


if __name__ == "__main__":
    main()
