"""While a match is followed she reads the play out as it happens, and typing can replace talking.

Runs the page's real commentary and typing code in Node against stand-ins for the page, and checks the wiring in its source.
"""

import json
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = open(os.path.join(ROOT, "simulator", "index.html"), encoding="utf-8").read()

HARNESS = r"""
var log = [], store = {};
global.localStorage = { getItem(k){ return store[k]||null; }, setItem(k,v){ store[k]=v; } };
function el(){ return { textContent:"", value:"", onclick:null, setAttribute(){}, focus(){}, classList:{toggle(){},add(){},remove(){}},
  addEventListener(n,f){ this["on_"+n]=f; } }; }
var els = {}; function $(id){ return els[id] || (els[id] = el()); }
var document = { hidden:false, activeElement:null, body:{ classList:{ toggle(c,on){ log.push("body "+c+" "+on); } } },
  addEventListener(){} };
var speaking=false, paused=false, MODE="idle", sawVoice=false, capText="", armed=true, bargeTimer=null, FOLLOW=null;
function devRecord(e){ log.push("dev "+e.note); } function threadAdd(){} function say(t){ log.push("SAY "+t); }
function applyToolResult(){} function paint(){} function showSaid(t){ log.push("SAID "+t); }
function stopSpeaking(){ log.push("stopSpeaking"); } function stopListening(){ log.push("stopListening"); } function releaseMic(){ log.push("releaseMic"); }
function stopBargeSR(){} function setMode(m){ MODE=m; } function setQuiet(t){ log.push("QUIET "+t); }
function ensureMic(){ log.push("ensureMic"); return { then(f){ f(); } }; } function listen(){ log.push("LISTEN"); }
function measureStrip(){} function placeText(){} function fit(){} function wake(){} function retireAnswer(){} function ask(t){ log.push("ASK "+t); }
var calls = [];
var reply = null;
async function rpc(method, params){ calls.push(params.arguments); return { result: reply(params) }; }
%BLOCK%
var out = {};
(async function(){
  // 1. follow: a baseline from now, no speech
  FOLLOW = { fixture_id: 7, home: "A", away: "B" };
  reply = function(p){ return { structuredContent:{ cursor: 5, commentary: [] }, content:[{type:"text",text:"Nothing new in the commentary."}] }; };
  commEnsure(true); await new Promise(r=>setTimeout(r,20));
  out.baseline = { args: calls[0], cursor: comm.cursor, said: log.filter(l=>l.indexOf("SAY")===0) };

  // 2. a tick with new lines speaks them and moves the cursor
  reply = function(p){ return { structuredContent:{ cursor: 7, commentary:[{minute:30,text:"x"},{minute:31,text:"y"}] },
    content:[{type:"text",text:"On 30, Corner. On 31, Goal!"}] }; };
  log.length = 0; await commTick();
  out.speaks = { said: log.filter(l=>l.indexOf("SAY")===0), cursor: comm.cursor, args: calls[calls.length-1] };

  // 3. someone is talking: she waits and does not move the cursor
  speaking = true; log.length = 0; var n = calls.length; await commTick();
  out.waits = { asked: calls.length-n, cursor: comm.cursor, said: log.filter(l=>l.indexOf("SAY")===0) };
  speaking = false;

  // 4. the user speaks while the request is out: the lines are kept for next time
  reply = function(p){ sawVoice = true; return { structuredContent:{ cursor: 9, commentary:[{minute:40,text:"z"}] }, content:[{type:"text",text:"On 40, Z."}] }; };
  log.length = 0; await commTick(); sawVoice = false;
  out.keeps = { cursor: comm.cursor, said: log.filter(l=>l.indexOf("SAY")===0) };

  // 5. no commentary in this feed: after two refusals it reads out what happens instead
  commStop(); FOLLOW = { fixture_id: 8, home: "A", away: "B" };
  reply = function(p){ return { isError:true, structuredContent:{ reason:"no_commentary" }, content:[{type:"text",text:"none"}] }; };
  comm.fid = 8; comm.cursor = 0; await commTick(); await commTick();
  out.fallback = comm.fallback;
  reply = function(p){ return { structuredContent:{ event_count:1 }, content:[{type:"text",text:"A goal for A."}] }; };
  log.length = 0; await commTick();
  out.fallbackSaid = log.filter(l=>l.indexOf("SAY")===0);

  // 6. full time and stop following end it
  FOLLOW.over = true; commEnsure(false); out.overStopped = comm.t === null;

  // 7. switches by voice or by typing
  FOLLOW = { fixture_id: 9, home: "A", away: "B" };
  out.cmd = { off: localCommand("Stop the commentary"), on: localCommand("alexa, start commentary"),
    ordinary: localCommand("what's the score"), stopAlone: localCommand("stop") };
  out.saved = store.sideline_commentary;

  // 8. typing: the microphone goes off, answers are not spoken
  log.length = 0; setTyping(true);
  out.typingOn = { typing: TYPING, log: log.slice() };
  log.length = 0; setTyping(false);
  out.typingOff = { typing: TYPING, log: log.slice() };
  console.log(JSON.stringify(out)); process.exit(0);
})();
"""


def _extract():
    a = PAGE.index("/* ============================================================== live commentary + typing */")
    b = PAGE.index('$("match").addEventListener("click"', a)
    return PAGE[a:b]


def main():
    node = shutil.which("node")
    if not node:
        print("skip  node is not installed: the commentary harness did not run")
        return
    code = HARNESS.replace("%BLOCK%", _extract())
    proc = subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    assert out["baseline"]["args"] == {"fixture_id": 7, "part": "commentary", "since_line": -1, "key_only": True}, out["baseline"]
    assert out["baseline"]["cursor"] == 5 and out["baseline"]["said"] == [], "joining a match starts from now: nothing is read"
    print("ok  following a match starts the commentary from now, without reading the past")

    assert out["speaks"]["args"]["since_line"] == 5 and out["speaks"]["cursor"] == 7, out["speaks"]
    assert out["speaks"]["said"] == ["SAY On 30, Corner. On 31, Goal!"], out["speaks"]
    print("ok  new lines are spoken, then the cursor moves past them")

    assert out["waits"]["asked"] == 0 and out["waits"]["cursor"] == 7 and out["waits"]["said"] == [], out["waits"]
    assert out["keeps"]["cursor"] == 7 and out["keeps"]["said"] == [], "she must never talk over the listener: " + str(out["keeps"])
    print("ok  she never talks over anyone: lines wait, and the cursor stays so none are lost")

    assert out["fallback"] is True and out["fallbackSaid"] == ["SAY A goal for A."], out
    print("ok  a feed with no commentary falls back to reading out what happens")

    assert out["overStopped"] is True
    print("ok  full time ends the commentary")

    assert out["cmd"] == {"off": True, "on": True, "ordinary": False, "stopAlone": False}, out["cmd"]
    assert out["saved"] == "on"
    print("ok  'stop commentary' and 'start commentary' are switches, handled without the model; other speech is not")

    on = out["typingOn"]
    assert on["typing"] is True and "stopListening" in on["log"] and "releaseMic" in on["log"], on
    off = out["typingOff"]
    assert off["typing"] is False and "ensureMic" in off["log"] and "LISTEN" in off["log"], off
    print("ok  typing turns the microphone off, and talking turns it back on")

    # wiring
    assert "if(TYPING){ finishSpeaking(spans); return; }" not in PAGE, "typing turns the microphone off, not her voice: she reads the answer aloud"
    assert "!armed||speaking||!mic||paused||TYPING" in PAGE, "the microphone stays off in typing mode"
    assert "if(localCommand(text)) return;" in PAGE
    assert "commEnsure(changed)" in PAGE and "commStop(); followLabel()" in PAGE
    assert 'id="typebar"' in PAGE and 'id="typeToggle"' in PAGE and 'id="commToggle"' in PAGE
    assert "Following \\u00b7 live" not in PAGE and "Following · live" not in PAGE, "'live' is shown by the eye's colour, not written"
    assert "PALETTE.live" in PAGE
    print("ok  wired: typing mutes the microphone and not her voice, a live match turns the eye warm instead of writing 'live'")
    print("\nlive commentary: all good")


if __name__ == "__main__":
    main()
