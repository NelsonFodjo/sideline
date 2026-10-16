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

# Round 2: 100 more across five sports (15-16 October 2026). Each is asked as its own listener, so one answer cannot colour the next.
ROUND2 = [
    ("Basketball", q) for q in [
        "What was the score of the Rockets and Thunder game?", "Who won the Celtics game last night?",
        "How many points did Jalen Brunson score last night?", "Who led the Spurs in scoring against the Suns?",
        "Who started for the Heat against the Nets?", "Where are the Celtics in the Eastern Conference standings?",
        "When do the Celtics play next?", "What NBA games are on tonight?", "Which NBA game had the highest score last night?",
        "Who is injured on the Knicks?", "Tell me about Victor Wembanyama.", "How many assists did Jalen Brunson have last night?",
        "What's the Lakers' record this season?", "Did the Warriors win last night?", "What time do the Lakers play today?",
        "Show me the Thunder line-up.", "Who are the NBA's top scorers this season?", "How many fouls did the Knicks have last night?",
        "What's a triple-double?", "How long is an NBA quarter?"]] + [
    ("American football", q) for q in [
        "Who won the Denver Broncos and Seattle Seahawks game?", "Who scored the touchdowns in the Broncos and Seahawks game?",
        "What was the score at halftime of the Broncos and Seahawks game?", "What time do the Patriots play on Sunday?",
        "Who do the Jets play this week?", "What NFL games are on this weekend?", "Where are the Broncos in the standings?",
        "Who is the Broncos quarterback?", "Who are the Seahawks' starters?", "Tell me about Patrick Mahomes.",
        "How many rushing yards did the Broncos have against the Seahawks?", "What were the team stats for the Broncos and Seahawks game?",
        "Who is injured for the Texans?", "When do the Ravens play the Browns?", "Who is the NFL leader in rushing yards?",
        "What's a safety in football?", "How many players are on the field in American football?", "How long is an NFL game?",
        "Did the Seahawks win last night?", "Follow the Falcons and Bears game."]] + [
    ("Hockey", q) for q in [
        "What was the score of the Maple Leafs and Sabres game?", "Who won the Panthers and Canucks game?",
        "Who scored for the Lightning against the Kraken?", "Who had the most shots in the Senators and Islanders game?",
        "How many power plays did Vegas have against Calgary?", "Where are the Maple Leafs in the standings?",
        "When do the Maple Leafs play next?", "What NHL games are on tonight?", "Who is the Vegas Golden Knights goalie?",
        "Tell me about Connor McDavid.", "How many goals has Auston Matthews scored this season?",
        "Who started in goal for the Lightning against the Kraken?", "Show me the Panthers line-up.", "What's icing in hockey?",
        "How long is a hockey game?", "What's a power play?", "Did the Senators win?", "Who are the NHL's top scorers?",
        "Who is injured on the Maple Leafs?", "How many penalties did the Sabres have against the Maple Leafs?"]] + [
    ("Baseball", q) for q in [
        "What was the score of the Guardians and Rays game?", "Who won the Dodgers and Brewers game last night?",
        "Who hit home runs in the Dodgers and Brewers game?", "How many hits did the Brewers have against the Dodgers?",
        "Who pitched for the Dodgers last night?", "When is the next Dodgers game?", "Where are the Dodgers in the standings?",
        "What MLB games are on today?", "Tell me about Shohei Ohtani.", "How many home runs does Shohei Ohtani have this season?",
        "Who is injured on the Dodgers?", "What's the Dodgers line-up?", "What inning is it in the Dodgers game?", "What's a balk?",
        "How many innings are in a baseball game?", "What does RBI stand for?", "What's a save in baseball?",
        "Who is leading MLB in home runs?", "What's the series score between the Dodgers and the Brewers?", "Did the Rays win?"]] + [
    ("Football", q) for q in [
        "Who plays Arsenal on Sunday?", "What time is Leeds against Manchester United?", "Who is Arsenal's top scorer this season?",
        "Where is Manchester United in the Premier League table?", "Tell me about Bukayo Saka.", "Who is the manager of Arsenal?",
        "What's the Premier League table?", "Who are the top scorers in the Premier League?", "Who are Arsenal's goalkeepers?",
        "How have Leeds and Manchester United done against each other before?", "What's Nottingham Forest's recent form?",
        "Who is injured at Manchester United?", "What's on in La Liga today?", "What's on in Serie A today?",
        "How did Juventus do in the Europa League?", "What's the weather forecast for Brighton against Crystal Palace?",
        "What's on in the Bundesliga today?", "Any news about Arsenal?", "Tell me about Erling Haaland.",
        "What's the score of the Frosinone and Sassuolo game?"]]


def post(url, body, timeout=90, listener=None):
    headers = {"Content-Type": "application/json"}
    if listener:
        headers["X-Sideline-Listener"] = listener
    req = urllib.request.Request(url, json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="a range like 1-10")
    ap.add_argument("--set", choices=("football", "multisport", "round2"), default="football")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "CURIOSITY_QA.md"))
    args = ap.parse_args()
    questions = {"multisport": MULTISPORT, "round2": ROUND2}.get(args.set, QUESTIONS)
    lo, hi = 1, len(questions)
    if args.only:
        a, _, b = args.only.partition("-")
        lo, hi = int(a), int(b or a)

    try:                                                       # a server left over from an earlier run would answer with old code
        urllib.request.urlopen("http://127.0.0.1:%d/health" % PORT, timeout=1)
        sys.exit("port %d is already serving something (a leftover server?). Stop it first: lsof -iTCP:%d -sTCP:LISTEN" % (PORT, PORT))
    except (urllib.error.URLError, OSError):
        pass
    env = dict(os.environ, SIDELINE_PORT=str(PORT), SIDELINE_STATE="memory", SIDELINE_LOG_DIR="off")
    server = subprocess.Popen([sys.executable, "-m", "sideline"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import atexit
    atexit.register(lambda: server.poll() is None and server.terminate())
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
                        res = post(base + "/agent/chat", {"text": q, "tz_offset_minutes": 240},
                                   listener=("r2-%d" % n) if args.set == "round2" else None)
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
