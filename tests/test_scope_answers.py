"""What the feed cannot carry is said plainly and at once, and rules and meanings are answered without tools."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SIDELINE_STATE"] = "memory"

from simulator import agent   # noqa: E402


def main():
    out = [
        "How many trophies has Lyon won?", "How many league titles have Arsenal won?", "How big is Lyon's stadium?",
        "What is the capacity of Anfield stadium?", "Who is the best player in the world?", "Who's the greatest footballer ever?",
        "Who won the Europa League last year?", "Who won the Champions League in 2019?",
    ]
    for q in out:
        said = agent._out_of_scope(q)
        assert said and said.startswith(("I don't have", "That's a matter of opinion")), (q, said)
    print("ok  honours, stadium size, 'the best in the world' and past winners are said plainly, with what she can do instead")

    data = [
        "How many points did Jalen Brunson score last night?", "How many fouls did the Knicks have last night?",
        "How long is left in the game?", "How many hits did the Brewers have against the Dodgers?",
        "Who won the Lyon game?", "Who won last night?", "What's the weather like at the stadium?", "Who scored for Lyon?",
        "How many goals has Pino scored this season?", "Where is Lyon in the table?", "Which ground is the Lyon game at?",
    ]
    for q in data:
        assert agent._out_of_scope(q) is None, "a question the data can answer is never turned away: " + q
    print("ok  questions the data can answer are not turned away")

    general = ["What's a triple-double?", "How long is an NBA quarter?", "How long is an NFL game?", "What's a power play?",
               "How many innings are in a baseball game?", "What's a safety in football?", "What's a save in baseball?",
               "What's the offside rule?", "What does VAR stand for?", "How many substitutions are allowed in a match?",
               "What is a 4-1-2-1-2 formation?", "How long is a football match?"]
    for q in general:
        assert agent._GENERAL_KNOWLEDGE.search(q) and not agent._asks_for_a_fact(q), q
    print("ok  rules and meanings are answered without a tool, and are not held to one")
    print("\nscope answers: all good")


if __name__ == "__main__":
    main()
