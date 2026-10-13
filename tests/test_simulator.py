"""The simulator has to be able to reach the server it demos.

It once could not: opened from disk it sends `Origin: null`, which the
Origin allow-list (correctly) refuses, so its first call, `initialize`,
got a 403. Now the server serves the page and the page is same-origin.
"""

import json
import threading
import time
import urllib.error
import urllib.request

from conftest import make_ctx

from sideline.mcp import server as mcp_server
from sideline.tools import REGISTRY

PORT = 8795
BASE = "http://127.0.0.1:%d" % PORT


def check_vad(page):
    """The browser's speech detector, run under Node on realistic frame sequences.

    Frames are the ~60 ms analysis ticks: (rms, harsh) where harsh is the share
    of energy above 5 kHz. Speech is moderately loud and not harsh; a key press
    is loud for a frame or two and very harsh; a thump is loud but low.
    """
    import json
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        print("skip  speech detector (node is not installed)")
        return
    start = page.index("/* VAD:begin */")
    end = page.index("/* VAD:end */")
    script = page[start:end] + """
    function run(frames, st){
      st = st || vadNew(); var out = [];
      frames.forEach(function(f){ out.push(vadStep(st, f[0], f[1])); });
      return {st: st, out: out};
    }
    var quiet = function(n){ var a=[]; for(var i=0;i<n;i++) a.push([0.004,0.1]); return a; };
    var speech = function(n, rms){ var a=[]; for(var i=0;i<n;i++) a.push([rms||0.05,0.08]); return a; };
    var click = [0.14, 0.62];
    var res = {};

    var r = run(quiet(10).concat(speech(12)));
    res.speechSustained = r.out.slice(10).some(function(o){return o.sustained;});
    res.speechFirstAt = r.out.slice(10).findIndex(function(o){return o.sustained;});

    // typing: a key about every 125 ms, so a click every other frame
    var typing = [];
    for (var i = 0; i < 80; i++) typing.push(i % 2 === 0 ? click : [0.004, 0.1]);
    r = run(quiet(10).concat(typing));
    res.typingNeverSustained = !r.out.some(function(o){return o.sustained;});

    // fast typing: clicks in consecutive frames
    var fast = [];
    for (var j = 0; j < 80; j++) fast.push(j % 5 === 4 ? [0.004, 0.1] : click);
    r = run(quiet(10).concat(fast));
    res.fastTypingNeverSustained = !r.out.some(function(o){return o.sustained;});

    // a thump on the desk: loud, low, over in two frames
    r = run(quiet(10).concat([[0.25, 0.04], [0.2, 0.04]], quiet(10)));
    res.thumpNeverSustained = !r.out.some(function(o){return o.sustained;});

    // speaking while typing: a key every 8th frame inside the speech
    var mixed = [];
    for (var k = 0; k < 40; k++) mixed.push(k % 8 === 7 ? click : [0.05, 0.08]);
    r = run(quiet(10).concat(mixed));
    res.speechOverTypingSustained = r.out.slice(10).some(function(o){return o.sustained;});

    // the room: a long utterance must not raise the bar out of reach of the next one
    var st = vadNew();
    run(quiet(15).concat(speech(83, 0.1)), st);
    res.floorAfterLongSpeech = st.noise * 3.2;
    run(quiet(25), st);
    res.noiseAfterSilence = st.noise;

    // a steady hum is learned rather than treated as speech forever
    st = vadNew();
    var hum = []; for (var h = 0; h < 600; h++) hum.push([0.02, 0.2]);
    r = run(quiet(10).concat(hum), st);
    res.humStillActiveAtEnd = r.out[r.out.length - 1].active;

    // nothing is judged before the room has been listened to
    r = run(speech(6));
    res.warmupHoldsBack = !r.out.some(function(o){return o.sustained;});
    console.log(JSON.stringify(res));
    """
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["speechSustained"] and res["speechFirstAt"] <= 5, res
    assert res["typingNeverSustained"], "typing every ~125 ms must never count as speech"
    assert res["fastTypingNeverSustained"], "fast typing must not either"
    assert res["thumpNeverSustained"], "a desk thump is loud but short"
    assert res["speechOverTypingSustained"], "talking while typing is still talking"
    assert res["floorAfterLongSpeech"] < 0.05 and res["noiseAfterSilence"] < 0.008, res
    assert not res["humStillActiveAtEnd"], "a steady hum is learned, then ignored"
    assert res["warmupHoldsBack"], res
    print("ok  speech detector: typing, fast typing and a thump never start a turn; speech does, even with keys in it")


def main():
    ctx = make_ctx(start_minute=40)
    srv = mcp_server.serve("127.0.0.1", PORT,
                           lambda n, a, l: REGISTRY[n](ctx, a, l),
                           lambda h: "sim-listener", ["localhost", "127.0.0.1"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)

    with urllib.request.urlopen(BASE + "/") as r:
        page = r.read().decode("utf-8")
        assert r.status == 200 and "text/html" in r.headers["Content-Type"]
    # The page opens an MCP session and lists the tools; the agent it talks to
    # (/agent/chat) makes every tools/call through sideline/mcp/client.py.
    assert '"initialize"' in page and '"tools/list"' in page and "Mcp-Session-Id" in page
    assert '"/agent/chat"' in page and "LIVE_MODE" not in page
    assert "webkitSpeechRecognition" in page and "startBrowserRecognition" in page
    assert "server speech recognition unavailable; switching to browser" in page
    assert "Please repeat." in page
    # The page says what it is: a simulated Alexa+, talking to an MCP server, never Alexa+ itself.
    assert "simulated Alexa+" in page and "say(INTRO)" in page and "MCP server for live sports" in page
    intro = page[page.index("var INTRO="):page.index('$("begin").onclick')]
    assert "I\\u2019m a simulated Alexa+" in intro and "real matches" in intro and "what did I miss" in intro \
        and "spoil a goal" in intro and "talk over me" in intro, intro
    assert 'name:"alexa-plus-simulator"' in page
    # Noise labels from a recogniser ("[SOUND]") never reach the screen or the agent.
    assert "function justWords" in page and page.count("justWords(") >= 6, "applied to every path that shows or sends text"
    import shutil
    import subprocess
    if shutil.which("node"):
        fn = page[page.index("function justWords"):page.index("function liveSaid")]
        cases = [("[SOUND]", ""), ("[Music]", ""), ("(applause)", ""), ("*cough*", ""), ("\u266a", ""), (".", ""),
                 ("Who is [inaudible] refereeing?", "Who is refereeing?"), ("what's the score", "what's the score")]
        script = fn + "\nconsole.log(JSON.stringify(%s.map(function(c){return justWords(c[0]);})));" % json.dumps(cases)
        got = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20).stdout)
        assert got == [w for _, w in cases], got
    # One sentence at a time: the answer is split into its first sentence and the rest, both asked for at once.
    assert "function speechParts" in page and "function playChain" in page and "speakGen++" in page
    assert page.count("fetchSpeech(") >= 2 and "playPolly" not in page
    if shutil.which("node"):
        fn = page[page.index("var ABBR="):page.index("function fetchSpeech")]
        cases = ["Celtic have 29 players: 3 goalkeepers, 10 defenders. The manager is Martin O'Neill. The captain is Callum McGregor.",
                 "It's at St. Mirren Park, in Paisley. Kick-off is today at 9 PM, in about 3 hours. Forecast cloudy.",
                 "Okay. Motherwell against Celtic, on 11 October: Full time. Celtic 2, Motherwell 0. Camilo Duran scored on 9.",
                 "A. Saka scored on 34, left foot from inside the box. Son scored on 58, right foot from the edge.",
                 "Short answer.", "Yes. It is.", "One sentence only with no full stop at all"]
        script = fn + "\nconsole.log(JSON.stringify(%s.map(speechParts)));" % json.dumps(cases)
        got = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=20).stdout)
        for text, parts in zip(cases, got):
            assert parts[0]["base"] == 0 and parts[0]["text"] == text[:len(parts[0]["text"])], parts
            if len(parts) == 2:
                assert text[parts[1]["base"]:] == parts[1]["text"], "marks of the second part land in the whole text"
                assert parts[0]["text"].rstrip()[-1] in ".!?"
        assert len(got[0]) == 2 and got[0][0]["text"].endswith("29 players: 3 goalkeepers, 10 defenders.")
        assert len(got[1]) == 2 and got[1][0]["text"].endswith("Paisley."), "no split at St."
        assert len(got[2]) == 2 and got[2][0]["text"].endswith("Full time."), "a short 'Okay.' joins the next sentence"
        assert len(got[3]) == 2 and got[3][0]["text"].endswith("inside the box."), "no split at an initial"
        assert [len(g) for g in got[4:]] == [1, 1, 1], "short answers are one request"
    print("ok  an answer is split into its first sentence and the rest (not at St. or an initial); both asked for at once")
    # The space bar pauses (and resumes); an in-flight answer is kept.
    assert 'e.code==="Space"' in page
    # The zone and "I cut in here" ride along with a question; noise stays off the caption.
    assert 'id="hint"' in page and "to pause" in page, "the footer says how to pause"
    assert "function hideMatch" in page and "else hideMatch()" in page and "var aboutMatch" in page, "no match data, no match header"
    assert "fadeSaid(false); hideMatch();" in page, "the teams leave with the text after a minute"
    assert "IDLE_MS=60000" in page, "the text leaves a minute after the last word"
    # A noise is not a word: a barge-in needs about 360 ms of speech, the voice ducks at the first
    # sign and comes back if it was noise, the start of the word is kept, and only the eye remains
    # after a minute of quiet.
    assert "if(over>=6){" in page and "duck(true)" in page and "duck(false)" in page, "the interruption rule"
    assert "preroll=carry" in page and "pcmChunks=preroll||[]" in page, "the start of a word is kept"
    assert "body.calm .hud,body.calm .wire,body.calm .stage{opacity:0" in page and "classList.add(\"calm\")" in page
    assert "tz_offset_minutes" in page and "interrupted:takeCut()" in page and "if(t && sawVoice)" in page and "pendingAnswer" in page
    assert "startLiveCaption" in page and 'caps.caption!=="browser"' in page
    print("ok  GET / serves the simulator, and it is an MCP client (initialize/tools/list/tools/call)")

    with urllib.request.urlopen(BASE + "/?anything=1") as r:
        assert r.status == 200 and "text/html" in r.headers["Content-Type"]
    print("ok  a query string does not change the route")

    with urllib.request.urlopen(BASE + "/voice/capabilities") as r:
        caps = json.loads(r.read())
    assert not any(k.endswith("_hint") for k in caps), caps
    assert "aws configure" not in page and "AWS_ACCESS_KEY_ID" not in page
    print("ok  no setup hints reach the page: not in the capabilities JSON, not in the page")

    def post(origin, payload):
        h = {"Content-Type": "application/json"}
        if origin:
            h["Origin"] = origin
        req = urllib.request.Request(BASE + "/mcp", json.dumps(payload).encode(), h)
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, dict(r.headers), json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), None

    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                       "clientInfo": {"name": "sim", "version": "1"}}}

    code, headers, doc = post(BASE, init)          # what the served page sends
    assert code == 200 and headers.get("Mcp-Session-Id"), (code, headers)
    assert doc["result"]["protocolVersion"] == "2025-11-25"
    print("ok  the page's own origin can initialize and gets a session")

    assert post("null", init)[0] == 403
    assert post("https://evil.example", init)[0] == 403
    print("ok  Origin: null and foreign origins are still refused (the allow-list stays strict)")

    def voice(path, origin, body=b"{}"):
        h = {"Content-Type": "application/json"}
        if origin:
            h["Origin"] = origin
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + path, body, h), timeout=3) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    # The speech endpoints spend AWS credits, so another page must not be able to call them.
    assert voice("/voice/tts", "https://evil.example") == 403
    assert voice("/voice/stt", "null") == 403
    assert voice("/voice/tts", BASE) != 403, "the page's own origin is let through"
    try:
        assert voice("/voice/stt", BASE, b"x" * (13 * 1024 * 1024)) == 413, "an oversized clip is refused unread"
    except (ConnectionError, urllib.error.URLError):
        pass                    # the server may hang up before the client finishes sending: also a refusal
    req = urllib.request.Request(BASE + "/voice/capabilities", headers={"Origin": "https://evil.example"})
    try:
        urllib.request.urlopen(req, timeout=3)
        raise AssertionError("a foreign origin read the capabilities")
    except urllib.error.HTTPError as e:
        assert e.code == 403
    print("ok  the speech endpoints refuse foreign origins and oversized clips")

    check_vad(page)
    srv.shutdown()
    print("\nsimulator: all good")


if __name__ == "__main__":
    main()
