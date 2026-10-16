#!/usr/bin/env python3
"""Fifty questions a fan asks during a football match, put to the real thing: the server, the model and the live feed.

    python3 scripts/curiosity_check.py                         # asks all 50, writes docs/CURIOSITY_QA.md
    python3 scripts/curiosity_check.py --team "Lyon" --only 1-10

It starts its own server on a spare port (never the one you are using), with memory state so nothing touches a real
table, asks the questions in order as one listener (so "he" and "them" work), and records what she said, which MCP
tools answered, and how long it took. The QUESTIONS are about one real match, so edit TEAM and the names for the day.
Needs AWS credentials for the model. Costs one or two Bedrock calls per question.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PORT = 8798

# (group, question). Names are from Lyon 3-2 Crystal Palace (Europa League); change them for another match.
QUESTIONS = [
    ("The match", "Follow Lyon."),
    ("The match", "What's the score?"),
    ("The match", "Who scored?"),
    ("The match", "Who assisted Pino's goal?"),
    ("The match", "What were the stats?"),
    ("The match", "Who had the most shots?"),
    ("The match", "Who got booked?"),
    ("The match", "Who came on as a substitute?"),
    ("The match", "Was there a penalty in the game?"),
    ("The match", "Who was the referee?"),
    ("The match", "Who was the best player?"),
    ("The match", "What was Lyon's line-up?"),
    ("The match", "Who plays in goal for Lyon?"),
    ("The match", "What formation did Crystal Palace play?"),
    ("The match", "How many corners did Palace have?"),
    ("Players", "Tell me about Corentin Tolisso."),
    ("Players", "How old is Daichi Kamada?"),
    ("Players", "What position does Keito Nakamura play?"),
    ("Players", "Where is Ernest Nuamah from?"),
    ("Players", "What is Adam Wharton's shirt number?"),
    ("Players", "How many goals has Yeremy Pino scored this season?"),
    ("Players", "Is Tolisso injured?"),
    ("Players", "Who is injured at Crystal Palace?"),
    ("Players", "Who is Palace's top scorer this season?"),
    ("Players", "Who are the top scorers in the Europa League?"),
    ("Teams", "How is Lyon doing this season?"),
    ("Teams", "What's Crystal Palace's recent form?"),
    ("Teams", "When is Lyon's next match?"),
    ("Teams", "Where is Crystal Palace in the Europa League table?"),
    ("Teams", "Who is top of the Europa League?"),
    ("Teams", "Who is in Lyon's squad?"),
    ("Teams", "How have Lyon and Crystal Palace done against each other before?"),
    ("Teams", "What team stats does Lyon have this season?"),
    ("Teams", "Any news about Lyon?"),
    ("Teams", "Who is Lyon's manager?"),
    ("The day", "What else is on today?"),
    ("The day", "What time is Sydney FC playing?"),
    ("The day", "Show me the Europa League fixtures from yesterday."),
    ("The day", "Is there a game on right now?"),
    ("The day", "What's on tomorrow in the Premier League?"),
    ("Just curious", "How many trophies has Lyon won?"),
    ("Just curious", "Who is the best player in the world?"),
    ("Just curious", "What's the offside rule?"),
    ("Just curious", "How many substitutions are allowed in a match?"),
    ("Just curious", "What does VAR stand for?"),
    ("Just curious", "What is a 4-1-2-1-2 formation?"),
    ("Just curious", "How big is Lyon's stadium?"),
    ("Just curious", "Who won the Europa League last year?"),
    ("Just curious", "How long is a football match?"),
    ("Just curious", "What's the weather forecast for Lyon's next match?"),
]


# The same kind of curiosity across the other sports (matches of 15 October 2026: Knicks 122-120 Raptors, Broncos 17-14
# Seahawks, Vegas v Calgary live, Dodgers 4-6 Brewers). Change the names for the day.
MULTISPORT = [
    ("Basketball", "What was the score of the Knicks game last night?"),
    ("Basketball", "Who scored the most points in the Knicks game last night?"),
    ("Basketball", "Who started for the Knicks last night?"),
    ("Basketball", "How did the Raptors do last night?"),
    ("Basketball", "When do the Knicks play next?"),
    ("Basketball", "What's on in the NBA tonight?"),
    ("American football", "Who won the Broncos game last night?"),
    ("American football", "What happened in the Broncos game last night?"),
    ("American football", "When do the Broncos play next?"),
    ("American football", "What's on in the NFL this weekend?"),
    ("American football", "Who is the top passer in the NFL this season?"),
    ("Hockey", "What was the score of the Vegas Golden Knights and Calgary Flames game?"),
    ("Hockey", "Who scored in the Vegas Golden Knights and Calgary Flames game?"),
    ("Hockey", "Where are the Golden Knights in the standings?"),
    ("Hockey", "Who has scored the most goals for Vegas?"),
    ("Baseball", "Who won the Dodgers game last night?"),
    ("Baseball", "What was the Dodgers score last night?"),
    ("Baseball", "What does ERA mean?"),
    ("Across sports", "What sports do you cover?"),
    ("Across sports", "Which games are live right now?"),
    ("Across sports", "What's the difference between football and American football?"),
    ("Across sports", "Follow the Knicks."),
    ("Across sports", "What did I miss?"),
    ("Across sports", "What's the score?"),
]


def post(url, body, timeout=90):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="a range like 1-10")
    ap.add_argument("--set", choices=("football", "multisport"), default="football")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "CURIOSITY_QA.md"))
    args = ap.parse_args()
    questions = MULTISPORT if args.set == "multisport" else QUESTIONS
    lo, hi = 1, len(questions)
    if args.only:
        a, _, b = args.only.partition("-")
        lo, hi = int(a), int(b or a)

    env = dict(os.environ, SIDELINE_PORT=str(PORT), SIDELINE_STATE="memory", SIDELINE_LOG_DIR="off")
    server = subprocess.Popen([sys.executable, "-m", "sideline"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % PORT
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/health", timeout=1)
                break
            except Exception:                                  # noqa: BLE001
                time.sleep(0.5)
        else:
            sys.exit("the server did not start")
        time.sleep(4)                                          # let it warm up
        rows = []
        for n, (group, q) in enumerate(questions, 1):
            if not lo <= n <= hi:
                continue
            t = time.time()
            try:
                for attempt in range(3):                       # the model's account can throttle: wait and ask again
                    try:
                        res = post(base + "/agent/chat", {"text": q, "tz_offset_minutes": 240})
                        break
                    except urllib.error.HTTPError as e:
                        if e.code != 503 or attempt == 2:
                            raise
                        time.sleep(10)
                text = res.get("text") or ""
                tools = [r.get("name") for r in res.get("tool_results") or []]
                err = None
            except Exception as e:                             # noqa: BLE001
                text, tools, err = "", [], str(e)
            ms = round((time.time() - t) * 1000)
            rows.append({"n": n, "group": group, "q": q, "text": text, "tools": tools, "ms": ms, "error": err})
            print("%2d. %s\n    %s\n    [%s, %d ms]" % (n, q, text[:300], ", ".join(tools) or "no tool", ms), flush=True)
            time.sleep(1.0)
        with open(args.out + ".json", "w") as fh:
            json.dump(rows, fh, indent=1)
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
