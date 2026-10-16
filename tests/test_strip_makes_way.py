"""The score strip goes the moment an unrelated question is asked, not after the answer.

Runs the page's real relevance check in Node on the questions from a real session, and checks the wiring.
"""

import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = open(os.path.join(ROOT, "simulator", "index.html"), encoding="utf-8").read()


def main():
    node = shutil.which("node")
    if not node:
        print("skip  node is not installed: the strip harness did not run")
        return
    block = PAGE[PAGE.index("var MATCH_WORDS="):PAGE.index("function stripMakesWay(")]
    code = block + """
var M = {home:"Manchester City", away:"Paris Saint-Germain", events:[{player:"Erling Haaland"}]};
var qs = ["When was it?", "Who scored?", "What about Haaland?", "Show me the line-ups", "How did City do?",
          "How are you?", "What can you do?", "Speak faster", "What's on today in the NBA?", "Tell me about Sydney FC",
          "Yeah, he's not here and he has a meeting at 2."];
console.log(JSON.stringify(qs.map(aboutShownMatch)));
"""
    proc = subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out[:5] == [True, True, True, True, True], out
    print("ok  a question about the match on the strip keeps it: 'when was it?', 'who scored?', a player, the line-ups, 'City'")
    assert out[5:] == [False] * 6, out
    print("ok  anything else and it goes at once: 'how are you?', 'speak faster', another league, another team, the room talking")
    ask = PAGE[PAGE.index("async function ask("):PAGE.index("async function ask(") + 200]
    assert "stripMakesWay(text);" in ask, "decided when the question is asked, before the answer"
    print("ok  wired into ask(), before localCommand and before the model, so page-only replies clear it too")
    print("\nstrip makes way: all good")


if __name__ == "__main__":
    main()
