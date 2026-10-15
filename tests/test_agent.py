"""Nova's Bedrock tool-use loop reuses the MCP contracts and tool registry."""

import json
import threading
import time
import urllib.error
import urllib.request

from conftest import make_ctx

from simulator import agent

from sideline.language import bedrock
from sideline.mcp import server as mcp_server
from sideline.mcp.registry import public_tools
from sideline.tools import REGISTRY

PORT = 8796
BASE = "http://127.0.0.1:%d" % PORT


class FakeBedrock:
    def __init__(self):
        self.calls = []
        self.final_text = "I'm following Arsenal against Tottenham."
        self.tool_uses = [{
            "toolUseId": "call-1",
            "name": "follow_match",
            "input": {"team": "Arsenal"},
        }]
        self._next_tool = True
        self.step = 0

    @property
    def next_tool(self):
        return self._next_tool

    @next_tool.setter
    def next_tool(self, value):
        self._next_tool = value
        self.step = 0

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self._next_tool and self.step == 0:
            self.step = 1
            return {"output": {"message": {
                "role": "assistant",
                "content": [{"toolUse": item} for item in self.tool_uses],
            }}}
        return {"output": {"message": {
            "role": "assistant",
            "content": [{"text": self.final_text}],
        }}}


def _post(path, payload, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(
        BASE + path, json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def _tool_results(call):
    return [
        block["toolResult"]
        for message in call["messages"]
        for block in message.get("content", [])
        if isinstance(block, dict) and "toolResult" in block
    ]


def _message_text(call):
    return "\n".join(
        block["text"]
        for message in call["messages"]
        for block in message.get("content", [])
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    )


def main():
    ctx = make_ctx(start_minute=40)
    model = FakeBedrock()
    catalog = public_tools()
    original_available, original_client = bedrock.available, bedrock.client
    bedrock.available = lambda: True
    bedrock.client = lambda: model
    try:
        result = agent.run(
            ctx, "Follow Arsenal, please.", "agent-listener",
            lambda name, args, listener: REGISTRY[name](ctx, args, listener),
            mcp_tools=catalog, mcp_instructions="Prefer what_did_i_miss for catch-up.")
        assert result["generated_by"] == "nova"
        assert "following Arsenal" in result["text"]
        assert result["tool_results"][0]["name"] == "follow_match"
        assert result["tool_results"][0]["structured"]["fixture_id"] == 1208341
        offered = model.calls[0]["toolConfig"]["tools"]
        assert [item["toolSpec"]["name"] for item in offered] == [
            item["name"] for item in catalog]
        assert offered[0]["toolSpec"]["name"] == "follow_match"
        assert offered[0]["toolSpec"]["inputSchema"]["json"] == agent._model_schema(catalog[0]["inputSchema"])
        system_prompt = model.calls[0]["system"][0]["text"]
        assert "Start following a match" in offered[0]["toolSpec"]["description"]
        assert "Not the score (get_match_state)" in offered[0]["toolSpec"]["description"]
        assert "All available tool descriptions and schemas are already provided" in system_prompt
        assert "Prefer what_did_i_miss for catch-up." in system_prompt
        assert 200 <= model.calls[0]["inferenceConfig"]["maxTokens"] <= 400, "room for complete sentences, still voice-sized"
        assert "toolChoice" not in model.calls[0]["toolConfig"], "the model decides whether a tool is needed"
        assert any(item["toolUseId"] == "call-1" for item in _tool_results(model.calls[1]))
        print("ok  Nova receives the full MCP catalog and schemas before selecting tools")

        model.calls[:] = []
        model.tool_uses = [
            {"toolUseId": "call-state", "name": "get_match_state", "input": {"team": "Arsenal"}},
            {"toolUseId": "call-officials", "name": "get_officials", "input": {"team": "Arsenal"}},
        ]
        model.next_tool = True
        combined = agent.run(
            ctx, "What's the score and who is refereeing?", "multi-listener",
            lambda name, args, listener: REGISTRY[name](ctx, args, listener),
            mcp_tools=catalog)
        assert [item["name"] for item in combined["tool_results"]] == [
            "get_match_state", "get_officials"], combined["tool_results"]
        final_tool_results = [
            item for item in _tool_results(model.calls[1])
            if item["toolUseId"] in ("call-state", "call-officials")
        ]
        assert [item["toolUseId"] for item in final_tool_results] == [
            "call-state", "call-officials"], final_tool_results
        assert "Combine the tool results into one concise" in _message_text(model.calls[1])
        print("ok  Nova requests two tools in one response and gets both results together to compose")

        model.calls[:] = []
        model.tool_uses = [{
            "toolUseId": "unselected-call",
            "name": "not_in_catalog",
            "input": {},
        }]
        model.next_tool = True
        attempted = []
        rejected = agent.run(
            ctx, "What's the score?", "unselected-listener",
            lambda name, args, listener: attempted.append(name) or REGISTRY[name](ctx, args, listener),
            mcp_tools=catalog)
        assert not attempted, attempted
        assert rejected["tool_results"][0]["name"] == "not_in_catalog"
        assert "not available" in rejected["tool_results"][0]["spoken"]
        assert any(
            item["status"] == "error"
            for item in _tool_results(model.calls[1])
            if item["toolUseId"] == "unselected-call"
        )
        print("ok  the host refuses a tool name absent from the current MCP catalog")

        model.calls[:] = []
        model.tool_uses = [{
            "toolUseId": "call-1",
            "name": "follow_match",
            "input": {"team": "Arsenal"},
        }]
        model.next_tool = True
        direct = agent.run(ctx, "Follow Arsenal, please.", "direct-listener",
                           lambda name, args, listener: REGISTRY[name](ctx, args, listener))
        assert direct["generated_by"] == "nova" and len(model.calls) == 2, (direct["generated_by"], len(model.calls))
        assert direct["text"] == model.final_text
        print("ok  even a short tool answer returns to Nova for natural phrasing")

        model.next_tool = False
        followup = agent.run(
            ctx, "What about that match?", "agent-listener",
            lambda name, args, listener: REGISTRY[name](ctx, args, listener))
        assert followup["text"]
        assert model.calls[-1]["messages"][0]["content"][0]["text"] == "Follow Arsenal, please."
        assert model.calls[-1]["messages"][1]["content"][0]["text"] == result["text"]
        print("ok  recent conversation turns are supplied for natural follow-ups")

        calls_before = len(model.calls)
        model.next_tool = False
        model.final_text = "Hello! What would you like to know?"
        cleaned = agent.run(
            ctx, "hello", "reasoning-listener",
            lambda name, args, listener: REGISTRY[name](ctx, args, listener))
        assert cleaned["text"] == model.final_text
        assert cleaned["generated_by"] == "nova" and not cleaned["tool_results"]
        assert len(model.calls) == calls_before + 1, "the model handles greetings and conversational turns"
        assert "toolConfig" in model.calls[-1], "the model decides if the greeting needs a tool"
        assert agent.CONVERSATIONS.get("reasoning-listener")[-1]["content"][0]["text"] == cleaned["text"]
        assert agent._listener_answer(
            "<thinking>private</thinking>") == ""
        assert agent._listener_answer("<thinking>private") == ""
        print("ok  model-emitted thinking tags are removed before display, speech, and history")

        for conversational_turn, expected in (
                ("Are you still around?", "I'm here. What's on your mind?"),
                ("That was stupid.", "Sorry, I missed the mark. What were you asking about?"),
                ("Thank you.", "You're welcome.")):
            model.calls[:] = []
            model.next_tool = False
            model.final_text = expected
            social = agent.run(
                ctx, conversational_turn, "social-listener",
                lambda name, args, listener: REGISTRY[name](ctx, args, listener))
            assert social["text"] == expected and social["generated_by"] == "nova"
            assert not social["tool_results"] and len(model.calls) == 1, (conversational_turn, model.calls)

        model.calls[:] = []
        model.next_tool = False
        model.final_text = "Dan means the point he was making about the match."
        social = agent.run(
            ctx, "Dan, what does he mean?", "social-listener",
            lambda name, args, listener: REGISTRY[name](ctx, args, listener))
        assert social["text"] == model.final_text and not social["tool_results"]
        assert len(model.calls) == 1 and "toolConfig" in model.calls[0]
        print("ok  social and context-dependent conversation are model-led, not phrase-scripted")

        call_count = len(model.calls)
        spoken, catchup, _ = REGISTRY["what_did_i_miss"](
            ctx, {}, "agent-listener", agent_mode=True)
        assert spoken == "" and catchup["events"]
        assert len(model.calls) == call_count, "agent catch-up must not invoke a second model"
        print("ok  catch-up gives Nova event facts without a nested model/template summary")

        invalid = agent._execute_tool(
            "get_event_detail", {"minute": "forty"}, "agent-listener",
            lambda *_: None, {spec["name"]: spec for spec in catalog})
        assert invalid[1] is True
        print("ok  model tool arguments are validated against the MCP input schema")
    finally:
        bedrock.available, bedrock.client = original_available, original_client

    bedrock.available = lambda: False
    try:
        try:
            agent.run(ctx, "What's the score?", "agent-listener",
                      lambda name, args, listener: REGISTRY[name](ctx, args, listener))
        except agent.AgentUnavailable:
            pass
        else:
            raise AssertionError("the agent must not return a canned fallback")
        bedrock.available = lambda: True          # Bedrock on: failure is reported, not hidden
        try:
            bedrock.catchup([], ctx.provider.fixture(1208341), 0, 0)
        except bedrock.BedrockUnavailable:
            pass
        else:
            raise AssertionError("with Bedrock on, a catch-up must not fall back to a template")
        print("ok  with Bedrock on, failure is reported instead of returning a canned answer")
    finally:
        bedrock.available = original_available

    seen = {}

    def runner(question, listener_id, tz=None, cut=None, name=None):
        seen.update(tz=tz, cut=cut, name=name)
        return {"text": question, "generated_by": "nova", "tool_results": [
            {"name": "get_match_state", "structured": {"fixture_id": 1208341}}
        ]}

    srv = mcp_server.serve(
        "127.0.0.1", PORT, lambda *_: None, lambda _: "agent-listener",
        ["localhost", "127.0.0.1"], agent_runner=runner)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    try:
        status, result = _post("/agent/chat", {"text": "What's the score?"})
        assert status == 200 and result["generated_by"] == "nova"
        assert _post("/agent/chat", {"text": ""})[0] == 400
        _post("/agent/chat", {"text": "and him?", "tz_offset_minutes": 240, "tz_name": "Indian/Mauritius",
                              "interrupted": "Hartlepool host   Newcastle"})
        assert seen == {"tz": 240, "cut": "Hartlepool host Newcastle", "name": "Indian/Mauritius"}, seen
        _post("/agent/chat", {"text": "x1", "tz_offset_minutes": 9999, "interrupted": 5, "tz_name": "../etc/passwd; drop"})
        assert seen == {"tz": None, "cut": None, "name": None}, "out-of-range, non-text or odd values are ignored"
        print("ok  the listener's zone and 'I cut in here' reach the agent; nonsense is dropped")
        assert _post("/agent/chat", {"text": "hello"}, "https://evil.example")[0] == 403
        print("ok  /agent/chat validates input and enforces the MCP origin allow-list")
    finally:
        srv.shutdown()
        srv.server_close()

    disabled = mcp_server.serve(
        "127.0.0.1", PORT, lambda *_: None, lambda _: "agent-listener",
        ["*"])
    threading.Thread(target=disabled.serve_forever, daemon=True).start()
    time.sleep(0.2)
    try:
        assert _post("/agent/chat", {"text": "What's the score?"})[0] == 503
        print("ok  agent endpoint reports an explicit unavailable response when unconfigured")
    finally:
        disabled.shutdown()
        disabled.server_close()
    # The model receives the real error and owns the spoken response.
    from sideline.mcp.errors import ToolError
    real = "The match data feed said: rateLimit: Too many requests. Your rate limit is 10 requests per minute. Try again shortly."

    def refusing(name, args, listener):
        raise ToolError(real, {"reason": "provider_unavailable", "problem": "rateLimit"})
    model2 = FakeBedrock()
    model2.final_text = "I couldn't reach the match feed. Would you like me to try again?"
    bedrock.available = lambda: True
    bedrock.client = lambda: model2
    out = agent.run(ctx, "Follow Arsenal, please.", "err-listener", refusing)
    assert out["text"] == model2.final_text and out["generated_by"] == "nova" and len(model2.calls) == 2, out
    error_context = next(item for item in _tool_results(model2.calls[1])
                         if item["toolUseId"] == "call-1")
    assert error_context["status"] == "error" and "rateLimit" in error_context["content"][0]["text"]
    print("ok  a feed error and its details return to Nova for a conversational response")

    # A match is followed only when the listener asked. A model that guesses is refused.
    ran = []
    model3 = FakeBedrock()          # its first move is always follow_match
    bedrock.client = lambda: model3
    agent.run(ctx, "Tell me about the Arsenal match", "guess-listener",
              lambda name, args, listener: ran.append(name) or REGISTRY[name](ctx, args, listener))
    assert "follow_match" not in ran, ran
    assert any(item["status"] == "error" for item in _tool_results(model3.calls[1]))
    assert agent._asked_to_follow("Follow Arsenal") and agent._asked_to_follow("I'm watching the Spurs game")
    assert agent._asked_to_follow("Arsenal against Lille (fixture_id 5)") and not agent._asked_to_follow("When is Arsenal playing?")
    print("ok  follow_match is refused unless the listener asked to follow, or chose an offered match")
    from simulator.agent import _without_invented_id as strip
    assert strip({"fixture_id": 9999, "team": "Arsenal"}, "tell me about the match") == {"team": "Arsenal"}, "invented"
    assert strip({"fixture_id": 7}, "Arsenal against Lille (fixture_id 7)") == {"fixture_id": 7}, "the handoff's own id"
    assert strip({"fixture_id": 8}, "Arsenal against Lille (fixture_id 7)") == {}, "a different id is invented"
    assert strip({"team": "Arsenal"}, "x") == {"team": "Arsenal"} and strip(None, "x") is None
    print("ok  an id the listener did not give is dropped; the handoff's own id is kept")
    fill = agent._fill_arguments
    assert fill("get_match_report", {"team": "Celtic"}, "Who came on as a substitute?") == {"team": "Celtic", "part": "substitutions"}
    assert fill("get_match_report", {}, "Any cards?")["part"] == "cards" and fill("get_match_report", {}, "who scored")["part"] == "goals"
    assert fill("get_match_report", {}, "was there a VAR check")["part"] == "var"
    assert fill("get_match_report", {}, "What happened in the game?") == {}, "no part said, none set: the whole story"
    assert fill("get_match_report", {"part": "goals"}, "any cards") == {"part": "goals"}, "what the model passed is kept"
    assert fill("get_squad", {"team": "x"}, "any cards") == {"team": "x"}
    print("ok  an argument the model leaves out but the question gives away is filled in, never overriding the model")
    class Busy(Exception):
        response = {"Error": {"Code": "ServiceUnavailableException"}}

    class Flaky:
        def __init__(self, error):
            self.calls, self.error = 0, error

        def converse(self, **kw):
            self.calls += 1
            if self.calls == 1:
                raise self.error
            return {"ok": True}
    saved_client, saved_wait = bedrock.client, agent.BUSY_RETRY_SECONDS
    agent.BUSY_RETRY_SECONDS = 0
    try:
        flaky = Flaky(Busy())
        bedrock.client = lambda: flaky
        assert agent._converse(x=1) == {"ok": True} and flaky.calls == 2, "a capacity refusal is tried once more"
        other = Flaky(ValueError("bad request"))
        bedrock.client = lambda: other
        try:
            agent._converse(x=1)
            raise AssertionError("an ordinary error is not retried")
        except ValueError:
            assert other.calls == 1
    finally:
        bedrock.client, agent.BUSY_RETRY_SECONDS = saved_client, saved_wait
    print("ok  a Bedrock 'capacity limit' or 'slow down' is retried once; any other error is not")
    assert agent._listener_answer("<response> No games on Sunday. </response>") == "No games on Sunday."
    assert agent._plain_strings({"team": "&quot;Celtic&quot;", "opponent": " 'Rangers' ", "n": 3, "l": ["&amp;x"]}) == \
        {"team": "Celtic", "opponent": "Rangers", "n": 3, "l": ["&x"]}
    nocomp = agent._without_invented_competition
    assert nocomp({"competition": "Premier League"}, "What are the next matches?") == {}, "taken from a description's example"
    assert nocomp({"competition": "Premier League", "when": "today"}, "Any Premier League games today?") == {"competition": "Premier League", "when": "today"}
    assert nocomp({"competition": "Superliga"}, "Who is top of the Danish Superliga?") == {"competition": "Superliga"}
    assert nocomp({"team": "Celtic"}, "x") == {"team": "Celtic"} and nocomp(None, "x") is None
    print("ok  a competition the listener did not say is dropped; one they said is kept")
    bedrock.available, bedrock.client = original_available, original_client

    # A small model invents weather when asked for it; weather is only said if a tool gave it.
    from simulator import agent as agent_mod
    assert agent_mod._invents_weather("Partly cloudy with a high of 15\u00b0C", [])
    assert agent_mod._invents_weather("There is a chance of rain.", [{"spoken": "Arsenal host Lille."}])
    assert not agent_mod._invents_weather("Arsenal host Lille at 11 PM.", [])
    assert not agent_mod._invents_weather("clear skies, 12 degrees",
                                          [{"structured": {"weather": {"sky": "clear skies"}}}])
    assert not agent_mod._invents_weather("The train leaves at nine", []), "whole words only"
    assert agent_mod._denies_live("Sorry, but I can't provide real-time updates or the current state of any match.")
    assert agent_mod._denies_live("I'm unable to give live scores.") and not agent_mod._denies_live("Arsenal host Lille.")
    print("ok  weather the model made up (no tool gave it) is caught; weather from a tool is allowed")
    print("ok  'I can't provide real-time updates' is recognised, and the model is told it can")
    print("\nagent: all good")


if __name__ == "__main__":
    main()
