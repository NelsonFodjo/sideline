"""What she answers and what she ignores: her own voice, a TV, a room, a cough.

Runs the page's real gate code in Node against stand-ins for the page, and checks the page's source for how it is wired.
"""

import json
import os
import re
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HARNESS = r"""
var log = [], now = 1000000, armed = true, paused = false;
global.localStorage = { getItem(){ return null; }, setItem(){} };
var realNow = Date.now; Date.now = function(){ return now; };
function devRecord(e){ log.push(e.note); }
function justWords(t){ return (t||"").replace(/\s+/g," ").trim(); }
var spoken = "";
function isAssistantEcho(h){ return spoken && spoken.toLowerCase().indexOf(h.toLowerCase())!==-1; }
function listen(){ log.push("LISTEN"); } function showSaid(t){ log.push("SAID "+t); } function ask(t){ log.push("ASK "+t); }
%STOP%
%LEADS%
%GATE%
var defaultOn = WAKE_ON; WAKE_ON = true;          // the gate itself is tested with the wake word on
var out = {};
function run(name, f){ log.length = 0; f(); out[name] = log.slice(); }

run("first question after go live, no name", function(){ openFollowUp(25000); heard("what's the score"); });
run("an answer just finished: carry on", function(){ openFollowUp(); heard("and who scored"); });
run("the window has closed: TV commentary", function(){ now += 60000; heard("he shoots and scores what a goal"); });
run("addressed outside the window", function(){ now += 60000; heard("Alexa, what's the score"); });
run("hey alexa", function(){ now += 60000; heard("Hey Alexa who scored"); });
run("only her name", function(){ now += 60000; heard("Alexa"); });
run("inside the window the name is removed", function(){ openFollowUp(); heard("Alexa, who scored"); });
run("a recogniser invention", function(){ openFollowUp(); heard("thanks for watching"); });
run("her own voice", function(){ spoken = "Paris Saint-Germain beat Manchester City 4 to 2"; openFollowUp(); heard("Manchester City 4 to 2"); spoken = ""; });
run("filler outside the window", function(){ now += 60000; WAKE_ON = false; heard("okay"); WAKE_ON = true; });
out.defaultOn = defaultOn;
out.barge = {
  stop: isBargeCommand("stop"), wait: isBargeCommand("wait which one"), named: isBargeCommand("Alexa what about spurs"),
  tvWords: isBargeCommand("he scores what a goal that is"), okay: isBargeCommand("okay arsenal lead"),
  echo: isBargeCommand("Arsenal lead one nil")
};
console.log(JSON.stringify(out));
"""


def extract(src, start, end):
    a = src.index(start)
    return src[a:src.index(end, a) + len(end)] if end else src[a:src.index("\n", a)]


def main():
    node = shutil.which("node")
    if not node:
        print("skip  node is not installed: the listening gate was not run")
        return
    page = open(os.path.join(ROOT, "simulator", "index.html"), encoding="utf-8").read()
    stop = extract(page, "var STOP_WORDS=", None)
    leads = extract(page, "function leadsWithStopWord(clean){", "\n}\n")
    gate = extract(page, "/* LISTENING GATE", "/* END LISTENING GATE */")
    js = HARNESS.replace("%STOP%", stop).replace("%LEADS%", leads).replace("%GATE%", gate)
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr[-800:]
    out = json.loads(r.stdout.strip().splitlines()[-1])

    assert out["first question after go live, no name"] == ["SAID what's the score", "ASK what's the score"]
    assert out["an answer just finished: carry on"] == ["SAID and who scored", "ASK and who scored"]
    tv = out["the window has closed: TV commentary"]
    assert "ASK" not in " ".join(tv) and any("not addressed" in x for x in tv) and "LISTEN" in tv, tv
    assert out["addressed outside the window"] == ["SAID what's the score", "ASK what's the score"], out["addressed outside the window"]
    assert out["hey alexa"][0] == "SAID who scored"
    assert "ASK" not in " ".join(out["only her name"]) and "LISTEN" in out["only her name"]
    assert out["inside the window the name is removed"] == ["SAID who scored", "ASK who scored"]
    assert "ASK" not in " ".join(out["a recogniser invention"])
    assert "ASK" not in " ".join(out["her own voice"]) and any("her own voice" in x for x in out["her own voice"])
    assert "ASK" not in " ".join(out["filler outside the window"])
    print("ok  she answers the first question and follow-ups, ignores TV talk outside the window, answers when addressed, "
          "and drops her own voice and recogniser inventions")

    assert out["defaultOn"] is False, "the wake word is off until she is told otherwise: she answers whatever she hears"
    b = out["barge"]
    assert b["stop"] and b["wait"] and b["named"], b
    assert not b["tvWords"] and not b["okay"] and not b["echo"], b
    print("ok  only a stop word or her name interrupts her: a commentator's words and 'okay' do not")

    assert "X-Run-Agent" not in page[page.index("async function handleClip"):page.index("async function handleClip") + 1500], \
        "the page decides the words are for her before any agent runs"
    assert "voicedTicks>=MIN_VOICED_TICKS" in page and "retireAnswer()" in page and "IDLE_MS=40000" in page
    print("ok  the agent runs only after the gate; a clip needs real speech; the old answer makes way; text leaves after 40 s")
    print("\nlistening gate: all good")


if __name__ == "__main__":
    main()
