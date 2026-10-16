"""A name the football pool lacks is never 'Did you mean...?': names from other sports must go through to the tools."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SIDELINE_STATE"] = "memory"

from sideline import resolve   # noqa: E402


def main():
    pool = ["Atlanta Hawks", "Boston Bruins", "Partick Thistle", "Texas State", "Fulham", "Western Sydney Wanderers", "Real Potosi"]
    for q in ["Who won the Denver Broncos and Seattle Seahawks game?", "How many points did Jalen Brunson score?",
              "Tell me about Patrick Mahomes.", "Who is injured for the Texans?", "What was the score of the Vegas and Calgary Flames game?",
              "How did the Raptors do last night?", "Where are the Celtics in the Eastern Conference standings?"]:
        out = resolve.snap("x", q, names=pool)
        assert not out["clarify"], (q, out["suggestion"])
    print("ok  names from other sports are not turned into 'Did you mean...?'")
    out = resolve.snap("x", "what is the score of the Arsenl game", names=["Arsenal", "Chelsea"])
    assert "Arsenal" in out["agent_text"], out
    print("ok  a close miss is still repaired outright")
    print("\nno false clarify: all good")


if __name__ == "__main__":
    main()
