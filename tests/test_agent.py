"""Nova's Bedrock tool-use loop reuses the MCP contracts and tool registry."""

import json
import threading
import time
import urllib.error
import urllib.request

from conftest import make_ctx

from sideline.language import agent, bedrock
from sideline.mcp import server as mcp_server
from sideline.tools import REGISTRY

PORT = 8796
BASE = "http://127.0.0.1:%d" % PORT


class FakeBedrock:
    def __init__(self):
        self.calls = []
        self.final_text = "I'm following Arsenal against Tottenham."

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {"output": {"message": {
                "role": "assistant",
                "content": [{"toolUse": {
                    "toolUseId": "call-1",
                    "name": "follow_match",
                    "input": {"team": "Arsenal"},
                }}],
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


def main():
    ctx = make_ctx(start_minute=40)
    model = FakeBedrock()
    original_available, original_client = bedrock.available, bedrock.client
    bedrock.available = lambda: True
    bedrock.client = lambda: model
    try:
        result = agent.run(
            ctx, "Follow Arsenal, please.", "agent-listener",
            lambda name, args, listener: REGISTRY[name](ctx, args, listener))
        assert result["generated_by"] == "nova"
        assert "following Arsenal" in result["text"]
        assert result["tool_results"][0]["name"] == "follow_match"
        assert result["tool_results"][0]["structured"]["fixture_id"] == 1208341
        assert model.calls[0]["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
        system_prompt = model.calls[0]["system"][0]["text"]
        assert "output only the answer to the listener" in system_prompt
        assert "Never say what you are thinking" in system_prompt
        assert model.calls[0]["inferenceConfig"]["maxTokens"] <= 220
        assert model.calls[1]["messages"][2]["content"][0]["toolResult"]["toolUseId"] == "call-1"
        assert model.calls[0]["toolConfig"]["toolChoice"] == {"any": {}}, "a match question must start with a tool"
        assert "toolChoice" not in model.calls[1]["toolConfig"], "after a tool, the model chooses freely"
        print("ok  Nova receives MCP schemas, calls a registered tool, and uses its result")

        followup = agent.run(
            ctx, "What about that match?", "agent-listener",
            lambda name, args, listener: REGISTRY[name](ctx, args, listener))
        assert followup["text"]
        assert model.calls[2]["messages"][0]["content"][0]["text"] == "Follow Arsenal, please."
        assert model.calls[2]["messages"][1]["content"][0]["text"] == result["text"]
        print("ok  recent conversation turns are supplied for natural follow-ups")

        model.final_text = (
            "<thinking>The user has greeted me. I will respond naturally "
            "without claiming live match knowledge.</thinking> Hello! "
            "How can I assist you today?")
        cleaned = agent.run(
            ctx, "hello", "reasoning-listener",
            lambda name, args, listener: REGISTRY[name](ctx, args, listener))
        assert cleaned["text"] == "Hello! How can I assist you today?"
        assert "<thinking>" not in cleaned["text"]
        assert "toolChoice" not in model.calls[-1]["toolConfig"], "a greeting needs no tool"
        assert agent._is_chitchat("hello") and agent._is_chitchat("Thanks!") and agent._is_chitchat("hi there")
        assert not agent._is_chitchat("tell me about the Arsenal match") and not agent._is_chitchat("What time is it?")
        assert agent.CONVERSATIONS.get("reasoning-listener")[-1]["content"][0]["text"] == cleaned["text"]
        assert agent._listener_answer(
            "<thinking>private</thinking>") == ""
        assert agent._listener_answer("<thinking>private") == ""
        print("ok  model-emitted thinking tags are removed before display, speech, and history")

        call_count = len(model.calls)
        spoken, catchup, _ = REGISTRY["what_did_i_miss"](
            ctx, {}, "agent-listener", agent_mode=True)
        assert spoken == "" and catchup["events"]
        assert len(model.calls) == call_count, "agent catch-up must not invoke a second model"
        print("ok  catch-up gives Nova event facts without a nested model/template summary")

        invalid = agent._execute_tool(
            "get_event_detail", {"minute": "forty"}, "agent-listener",
            lambda *_: None)
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
    # The listener hears the real error, not a model's apology for it.
    from sideline.mcp.errors import ToolError
    real = "The match data feed said: rateLimit: Too many requests. Your rate limit is 10 requests per minute. Try again shortly."

    def refusing(name, args, listener):
        raise ToolError(real, {"reason": "provider_unavailable", "problem": "rateLimit"})
    model2 = FakeBedrock()
    bedrock.available = lambda: True
    bedrock.client = lambda: model2
    out = agent.run(ctx, "Follow Arsenal, please.", "err-listener", refusing)
    assert out["text"] == real and out["generated_by"] == "tool" and len(model2.calls) == 1, out
    print("ok  a feed error is spoken as it is, with no model call to reword it")

    # A match is followed only when the listener asked. A model that guesses is refused.
    ran = []
    model3 = FakeBedrock()          # its first move is always follow_match
    bedrock.client = lambda: model3
    agent.run(ctx, "Tell me about the Arsenal match", "guess-listener",
              lambda name, args, listener: ran.append(name) or REGISTRY[name](ctx, args, listener))
    assert "follow_match" not in ran, ran
    assert model3.calls[1]["messages"][2]["content"][0]["toolResult"]["status"] == "error"
    assert agent._asked_to_follow("Follow Arsenal") and agent._asked_to_follow("I'm watching the Spurs game")
    assert agent._asked_to_follow("Arsenal against Lille (fixture_id 5)") and not agent._asked_to_follow("When is Arsenal playing?")
    print("ok  follow_match is refused unless the listener asked to follow, or chose an offered match")
    from sideline.language.agent import _without_invented_id as strip
    assert strip({"fixture_id": 9999, "team": "Arsenal"}, "tell me about the match") == {"team": "Arsenal"}, "invented"
    assert strip({"fixture_id": 7}, "Arsenal against Lille (fixture_id 7)") == {"fixture_id": 7}, "the handoff's own id"
    assert strip({"fixture_id": 8}, "Arsenal against Lille (fixture_id 7)") == {}, "a different id is invented"
    assert strip({"team": "Arsenal"}, "x") == {"team": "Arsenal"} and strip(None, "x") is None
    print("ok  an id the listener did not give is dropped; the handoff's own id is kept")
    bedrock.available, bedrock.client = original_available, original_client

    # A small model invents weather when asked for it; weather is only said if a tool gave it.
    from sideline.language import agent as agent_mod
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
