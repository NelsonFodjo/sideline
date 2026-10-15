"""A fact about a match, team or player comes from a tool, never from what the model remembers.

Seen live: "tell me more about Nuno Mendes" was answered from the model's memory with no tool called. When the first reply
to a question that asks for a fact has no tool call, the agent asks again with a tool required (Converse toolChoice "any").
Chat and thanks are left to the model.
"""

from conftest import make_ctx

from simulator import agent

from sideline.language import bedrock
from sideline.mcp.registry import public_tools
from sideline.tools import REGISTRY


class Forgetful(object):
    """Answers from memory first; calls a tool only when one is required."""

    def __init__(self):
        self.calls = []

    def converse(self, **kw):
        self.calls.append(kw)
        required = "any" in (kw.get("toolConfig", {}).get("toolChoice") or {})
        done = any("toolResult" in b for m in kw["messages"] for b in m["content"] if isinstance(b, dict))
        if required and not done:
            return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {
                "toolUseId": "t1", "name": "get_match_state", "input": {"team": "Arsenal"}}}]}}}
        return {"output": {"message": {"role": "assistant", "content": [{"text": "Remembered from training data."}]}}}


def main():
    ctx = make_ctx(start_minute=40)
    saved = bedrock.available, bedrock.client
    bedrock.available = lambda: True
    run = lambda q, model: agent.run(ctx, q, "mem-%s" % q[:5], lambda n, a, l: REGISTRY[n](ctx, a, l),
                                     mcp_tools=public_tools())
    try:
        for q in ("Tell me more about Nuno Mendes.", "who is the manager", "How is Arsenal doing?"):
            model = Forgetful()
            bedrock.client = lambda: model
            out = run(q, model)
            assert out["tool_results"], (q, out)
            assert "toolChoice" in model.calls[1]["toolConfig"] and "toolChoice" not in model.calls[0]["toolConfig"], q
            assert "Remembered from training data" not in out["text"] or out["tool_results"], q
        print("ok  a question that asks for a fact is held to a tool when the model first answers from memory")

        for q in ("Are you still around?", "Thank you.", "That was stupid.", "Dan, what does he mean?"):
            model = Forgetful()
            bedrock.client = lambda: model
            out = run(q, model)
            assert not out["tool_results"] and len(model.calls) == 1, (q, len(model.calls))
        print("ok  chat and thanks are not forced to a tool")
    finally:
        bedrock.available, bedrock.client = saved
    print("\nno memory answers: all good")


if __name__ == "__main__":
    main()
