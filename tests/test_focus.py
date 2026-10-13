"""The conversation's topic: what "they", "him" and "that match" mean on the next turn."""

from conftest import make_ctx

from sideline.language import agent, bedrock
from sideline.tools import REGISTRY


class Scripted:
    """A model that makes the tool call it is told to, then answers; records every system prompt."""

    def __init__(self):
        self.systems, self.plan = [], []

    def converse(self, **kw):
        self.systems.append(kw["system"][0]["text"])
        last = kw["messages"][-1]["content"][0]
        if "toolResult" not in last and self.plan:
            name, args = self.plan.pop(0)
            return {"output": {"message": {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": "t%d" % len(self.systems), "name": name, "input": args}}]}}}
        return {"output": {"message": {"role": "assistant", "content": [{"text": "Okay."}]}}}


def main():
    ctx = make_ctx(start_minute=40)
    model, real = Scripted(), (bedrock.available, bedrock.client)
    bedrock.available, bedrock.client = (lambda: True), (lambda: model)
    run_tool = lambda name, args, who: REGISTRY[name](ctx, args, who)
    try:
        model.plan = [("follow_match", {"team": "Arsenal"})]
        agent.run(ctx, "Follow Arsenal please.", "focus-a", run_tool)
        assert "last talking about" not in model.systems[0], "nothing is assumed before anything was said"
        model.plan = []
        agent.run(ctx, "And what about their form?", "focus-a", run_tool)
        assert "Arsenal against Tottenham" in model.systems[-1] and "the team Arsenal" in model.systems[-1], model.systems[-1]
        print("ok  the next turn is told what was just talked about: the match and the team, from the tool results")

        model.plan = [("get_player_stats", {"player": "Saka"})]
        agent.run(ctx, "How many goals has Saka got this season?", "focus-a", run_tool)
        model.plan = []
        agent.run(ctx, "And his assists?", "focus-a", run_tool)
        assert "the player Saka" in model.systems[-1], model.systems[-1]
        print("ok  a player named last turn is the 'him' of the next")

        model.plan = [("get_player_context", {"player": "he"})]
        agent.run(ctx, "Who is he?", "focus-b", run_tool)
        model.plan = []
        agent.run(ctx, "Okay.", "focus-b", run_tool)
        assert "the player he" not in model.systems[-1].lower(), "a pronoun is never a topic"
        print("ok  a pronoun never becomes the topic")

        # Moving to another match drops the old player; a stranger gets nothing.
        agent.FOCUSES.remember("focus-c", [{"args": {"player": "Saka"}, "structured": {"home": "A", "away": "B"}}])
        agent.FOCUSES.remember("focus-c", [{"args": {}, "structured": {"home": "C", "away": "D"}}])
        line = agent.FOCUSES.line("focus-c")
        assert "C against D" in line and "Saka" not in line and agent.FOCUSES.line("nobody") == ""
        print("ok  a new match drops the old player; a stranger has no topic")

        agent.FOCUS_TTL_SECONDS = -1
        assert agent.FOCUSES.line("focus-c") == ""
        agent.FOCUS_TTL_SECONDS = 600
        print("ok  the topic expires")
    finally:
        bedrock.available, bedrock.client = real

    print("\nfocus: all good")


if __name__ == "__main__":
    main()
