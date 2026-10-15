"""The developer log's server side: every answer says which model ran, how long each model call and each tool call took,
and what the tools were given. The page shows it behind a toggle; this proves the data is there and honest."""

from conftest import make_ctx

import test_fix_agent as base
from sideline.tools import REGISTRY

simulator_agent = base.agent


def main():
    ctx = make_ctx(start_minute=40)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "dev")
    ran = []
    model = base.Scripted(plan=[("get_match_state", {})], text="Arsenal lead one-nil.")
    real = base._with_model(model)
    try:
        out = simulator_agent.run(ctx, "What's the score?", "dev", base._counting_runner(ctx, ran), mcp_tools=base.CATALOG)
    finally:
        base._restore(real)
    d = out["debug"]
    assert out["generated_by"] in ("fast", "swarm-fast", "fast-path"), out["generated_by"]
    assert d["model_calls"] == [] and [t["name"] for t in d["tools"]] == ["get_match_state"], d
    assert d["tools"][0]["args"] == {} and d["tools"][0]["ok"] and d["tools"][0]["ms"] >= 0
    print("ok  a question the fast path answers shows no model call and one tool call, with its arguments and time")

    # a question that goes through the model: its calls, tokens and tools are all there
    model_q = base.Scripted(plan=[("get_match_state", {})], text="Arsenal lead one-nil.")
    real = base._with_model(model_q)
    try:
        out = simulator_agent.run(ctx, "So how are we getting on in this one, mate?", "dev", base._counting_runner(ctx, ran),
                                  mcp_tools=base.CATALOG)
    finally:
        base._restore(real)
    d = out["debug"]
    assert out["generated_by"] in ("nova", "bedrock-fast") and len(d["model_calls"]) >= 1, (out["generated_by"], d["model_calls"])
    assert all("ms" in c and "stop" in c for c in d["model_calls"]), d["model_calls"]
    assert d["tools"][0]["name"] == "get_match_state" and d["tools"][0]["ok"] is True, d["tools"]
    assert out["tool_results"][0]["args"] == {} and out["tool_results"][0]["ms"] >= 0
    print("ok  a model answer carries its model calls (%d) and its tool calls" % len(d["model_calls"]))

    # the prompt says what the listener follows, from the store (the agent's own memory is lost on a restart)
    sent = []
    follower = make_ctx(start_minute=40)
    REGISTRY["follow_match"](follower, {"team": "Arsenal"}, "p")
    prompt = simulator_agent._following(follower, "p")
    assert "following Arsenal against Tottenham" in prompt and "do not ask which match" in prompt, prompt
    assert simulator_agent._following(make_ctx(), "nobody") == "", "nothing followed: nothing claimed"
    print("ok  the model is told which match the listener follows, straight from the store")

    # the next question starts a fresh trace, it does not inherit the last one's calls
    model2 = base.Scripted(plan=[], text="Hello.")
    real = base._with_model(model2)
    try:
        out2 = simulator_agent.run(ctx, "thanks", "dev", base._counting_runner(ctx, ran), mcp_tools=base.CATALOG)
    finally:
        base._restore(real)
    assert len(out2["debug"]["model_calls"]) <= 1 and out2["debug"]["tools"] == [], out2["debug"]
    assert out2["debug"]["model_calls"] != d["model_calls"] or not d["model_calls"]
    print("ok  each question has its own trace")


if __name__ == "__main__":
    main()
    print("\ndev trace: all good")
