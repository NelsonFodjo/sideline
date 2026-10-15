"""The listener's instructions about memory are obeyed.

Two tiers. The conversation is session memory, kept in the process: "forget that" ends it. What the MCP server keeps about
a listener (the match they follow, their teams, settings, what they heard) is durable: only "forget everything about me"
erases it, through the server's own tool. Neither takes a model call.
"""

from conftest import make_ctx

from simulator import agent

from sideline.language import bedrock
from sideline.mcp.registry import public_tools
from sideline.tools import REGISTRY


class Model(object):
    def __init__(self):
        self.calls = []

    def converse(self, **kw):
        self.calls.append(kw)
        return {"output": {"message": {"role": "assistant", "content": [{"text": "Saka is Arsenal's number seven."}]}}}


def main():
    ctx = make_ctx(start_minute=40)
    model = Model()
    saved = bedrock.available, bedrock.client
    bedrock.available = lambda: True
    bedrock.client = lambda: model
    run = lambda q, who="ann": agent.run(ctx, q, who, lambda n, a, l: REGISTRY[n](ctx, a, l), mcp_tools=public_tools())
    try:
        assert agent._forget_scope("forget that") == "conversation"
        assert agent._forget_scope("Please forget everything about me.") == "everything"
        assert agent._forget_scope("okay, start over") == "conversation"
        assert agent._forget_scope("delete my data") == "everything"
        for chat in ("I'll never forget that goal", "forget about the first half, what's the score", "what's the score",
                     "who scored first", "Saka was brilliant, start the second half"):
            assert agent._forget_scope(chat) is None, chat
        print("ok  'forget that' is recognised as an instruction; 'I'll never forget that goal' is just talk")

        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "ann")
        REGISTRY["set_preferences"](ctx, {"detail": "brief"}, "ann")
        run("Tell me about Saka")
        assert agent.CONVERSATIONS.get("ann"), "the exchange is remembered for the session"
        before = len(model.calls)

        out = run("forget that")
        assert out["generated_by"] == "forget" and out["text"].startswith("Okay, starting fresh."), out
        assert "Arsenal" in out["text"], "it says what it is still following"
        assert len(model.calls) == before, "no model call"
        assert agent.CONVERSATIONS.get("ann") == [] and agent.FOCUSES.topic("ann") == {}
        rec = ctx.store.listener("ann")
        assert rec["following"] and rec["detail"] == "brief", "'forget that' leaves what the server keeps untouched"
        print("ok  'forget that' clears the conversation and the topic, keeps what is followed and the settings, with no model call")

        out = run("forget everything about me")
        assert out["generated_by"] == "forget" and out["text"].startswith("Done. I've forgotten"), out
        assert not out["text"].startswith("{"), "it says the sentence, not the tool's record"
        assert out["tool_results"][0]["name"] == "set_preferences"
        rec = ctx.store.listener("ann")
        assert not rec["following"] and not rec.get("detail") and not rec["told_event_ids"], rec
        assert len(model.calls) == before
        print("ok  'forget everything about me' erases the stored profile through the MCP tool, with no model call")

        # another listener is not touched
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "bob")
        run("forget everything about me", "ann")
        assert ctx.store.listener("bob")["following"], "one listener's request is theirs alone"
        print("ok  forgetting is per listener")
    finally:
        bedrock.available, bedrock.client = saved
    print("\nforget: all good")


if __name__ == "__main__":
    main()
