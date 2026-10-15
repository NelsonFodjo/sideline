"""Regressions for the voice and simulator-UI bugs in docs/BUGS.md section 7 (VO-xx).

Same style as test_voice.py: doubles for every provider, no network, no credentials. The page's JavaScript
is run under Node where a fix lives in a function that can be lifted out on its own (as test_simulator.py
does for the speech detector); the rest of the page is checked by what its source says.
"""

import importlib
import io
import json
import math
import os
import shutil
import struct
import subprocess
import time
import urllib.request

import conftest  # noqa: F401  (puts the repo root on the path)

from simulator import voice

RATE = 16000
ROOT = os.path.join(os.path.dirname(__file__), "..")
PAGE = open(os.path.join(ROOT, "simulator", "index.html"), encoding="utf-8").read()
NODE = shutil.which("node")


def pcm_of(samples):
    return struct.pack("<%dh" % len(samples), *[max(-32768, min(32767, int(x))) for x in samples])


def tone(seconds, lead=0.5, tail=0.5, amp=6000):
    """`seconds` of a voiced tone between silences: a clip with that much speech in it, and no more."""
    out = [0] * int(RATE * lead)
    out += [amp * sum(math.sin(2 * math.pi * 140 * k * i / RATE) / k for k in range(1, 6)) / 2.2
            for i in range(int(RATE * seconds))]
    return pcm_of(out + [0] * int(RATE * tail))


def set_env(stt="auto", aws=False, have_sonic=False, groq="", tts="auto", cartesia="", elevenlabs=""):
    voice.STT_PROVIDER = stt
    voice.TTS_PROVIDER = tts
    voice._have_aws_credentials = lambda: aws
    voice._groq_key = lambda: groq
    voice._have_groq_key = lambda: bool(groq)
    voice._cartesia_key = lambda: cartesia
    voice._have_cartesia_key = lambda: bool(cartesia)
    voice._elevenlabs_key = lambda: elevenlabs
    voice._have_elevenlabs_key = lambda: bool(elevenlabs)
    voice.HAVE_SONIC = have_sonic
    voice.HAVE_BOTO3 = True
    voice._DISABLED.clear()


class FakeVoxtral:
    def __init__(self, text="Who is refereeing?", error=None, stream_error=None, stream=False):
        self.text, self.error, self.stream_error, self.requests = text, error, stream_error, []
        if stream:
            self.converse_stream = self._converse_stream

    def converse(self, **kw):
        self.requests.append(("converse", kw))
        if self.error:
            raise self.error
        return {"output": {"message": {"role": "assistant", "content": [{"text": self.text}]}},
                "usage": {"inputTokens": 40, "outputTokens": 6}}

    def _converse_stream(self, **kw):
        self.requests.append(("converse_stream", kw))
        if self.stream_error:
            raise self.stream_error
        return {"stream": [{"contentBlockDelta": {"delta": {"text": self.text}}},
                           {"metadata": {"usage": {"inputTokens": 40, "outputTokens": 6}}}]}


def no_network(*a, **k):
    raise AssertionError("no third-party request may be made here")


def node(script):
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def js(start, end):
    return PAGE[PAGE.index(start):PAGE.index(end)]


# ------------------------------------------------------------------ voice.py
def test_aws_only_by_default():                                           # VO-05
    saved = os.environ.pop("SIDELINE_LIVE_CAPTION", None)
    try:
        importlib.reload(voice)
        assert voice.LIVE_CAPTION == "off", "live caption sends audio to the browser vendor: off unless chosen"
    finally:
        if saved is not None:
            os.environ["SIDELINE_LIVE_CAPTION"] = saved
    set_env(aws=True, have_sonic=True, groq="k", cartesia="c", elevenlabs="e")
    assert voice.stt_order() == ["voxtral", "sonic"], "a Groq key alone must not send audio outside AWS"
    caps = voice.capabilities()
    assert caps["stt"] == "voxtral" and caps["tts"] == "polly" and caps["caption"] is None, caps
    set_env(aws=False, groq="k", cartesia="c", elevenlabs="e")
    assert voice.stt_order() == [] and voice.capabilities()["tts"] == "browser"
    set_env(stt="groq", groq="k")
    assert voice.stt_order() == ["groq"], "named, it is used"
    set_env(tts="cartesia", cartesia="c")
    assert voice.active_tts_provider() == "cartesia"

    # auto with third-party keys set: the answer text goes to Polly, never to Cartesia or ElevenLabs
    real = urllib.request.urlopen
    urllib.request.urlopen = no_network
    real_client = voice._polly_client
    try:
        set_env(aws=True, cartesia="c", elevenlabs="e")
        voice._polly_client = lambda: None
        assert voice.synthesize("Arsenal lead.") is None
    finally:
        urllib.request.urlopen, voice._polly_client = real, real_client
    assert "audio stays in the AWS account" in " ".join(voice.__doc__.split())
    assert "only when named" in voice.__doc__ or "only\nwhen named" in voice.__doc__
    print("ok  VO-05 auto is AWS only (Voxtral, Sonic, Polly); Groq/Cartesia/ElevenLabs only when named; caption off")


def test_hint_echo_only_for_hinted_and_lists():                           # VO-06
    hint = voice._BASE_HINT + " Real Madrid, Manchester United, Hartlepool, Newcastle United U21"
    for name in ("Real Madrid", "Manchester United", "Real Madrid.", "Newcastle United U21"):
        assert not voice.echoes_hint(name, hint), name
    assert voice.echoes_hint("Hartlepool, Newcastle U21", hint), "a list of names nobody said is still noise"
    set_env(aws=True)
    voice._voxtral = FakeVoxtral(text="Real Madrid")
    out = voice.transcribe(tone(1.0), "audio/pcm", hint)
    assert out == {"text": "Real Madrid", "provider": "voxtral"}, out
    voice._voxtral = FakeVoxtral(text="Hartlepool, Newcastle U21")
    out = voice.transcribe(tone(1.0), "audio/pcm", hint)
    assert out["text"] == "Hartlepool, Newcastle U21", "Voxtral never sees the hint, so it cannot be echoing it"

    async def sonic_echo(pcm, hint=""):
        return "Hartlepool, Newcastle U21"
    real = voice._sonic_hear
    try:
        set_env(stt="sonic", aws=True, have_sonic=True)
        voice._sonic_hear = sonic_echo
        assert voice.transcribe(tone(1.0), "audio/pcm", hint) == {"text": "", "provider": "sonic"}
    finally:
        voice._sonic_hear = real
    print("ok  VO-06 a team's name is an answer; the echo rule is a list, and only for recognisers given the hint")


def test_hallucination_filter_whisper_short_only():                       # VO-08
    set_env(aws=True)
    for said in ("Thank you.", "Goodbye", "You"):
        voice._voxtral = FakeVoxtral(text=said)
        out = voice.transcribe(tone(1.0), "audio/pcm")
        assert out["text"] == said, (said, out)

    def groq_says(text):
        def fake(req, timeout=None, context=None):
            class R:
                def read(self):
                    return json.dumps({"text": text}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass
            return R()
        return fake
    real = urllib.request.urlopen
    try:
        urllib.request.urlopen = groq_says("Thank you.")
        set_env(stt="groq", groq="k")
        assert voice.transcribe(tone(1.0), "audio/pcm")["text"] == "Thank you.", "a real 'Thank you' is kept"
        short = tone(0.25)
        assert voice.voiced_ms(short) >= voice.GATE_MIN_VOICED_MS
        assert voice.transcribe(short, "audio/pcm")["text"] == "", "Whisper's habit on a near-empty clip"
    finally:
        urllib.request.urlopen = real
    assert "cleanT===\"thank you\"" not in PAGE, "the page no longer drops these words for every provider"
    print("ok  VO-08 'Thank you'/'Goodbye'/'You' are kept; only Whisper on a near-empty clip is filtered")


def test_disabled_expires_and_validation_does_not_count():                # VO-10
    set_env(stt="sonic", aws=True, have_sonic=True)

    async def invalid(pcm, hint=""):
        raise RuntimeError("ValidationException: audio chunk malformed")

    async def denied(pcm, hint=""):
        raise RuntimeError("AccessDeniedException: not authorized")
    real = voice._sonic_hear
    try:
        voice._sonic_hear = invalid
        assert voice.transcribe(tone(1.0)) is None
        assert voice.stt_order() == ["sonic"], "one bad clip must not take Sonic out"
        voice._sonic_hear = denied
        assert voice.transcribe(tone(1.0)) is None and voice.stt_order() == []
        assert voice._DISABLED["sonic"] > time.monotonic() + voice.DISABLE_SECONDS - 5
        voice._DISABLED["sonic"] = time.monotonic() - 1                 # ten minutes later
        assert voice.stt_order() == ["sonic"], "rotated credentials recover without a restart"
    finally:
        voice._sonic_hear = real
    print("ok  VO-10 a ValidationException is per clip; disabled providers come back after DISABLE_SECONDS")


def test_marks_failure_keeps_audio():                                     # VO-11
    frames = lambda n: (b"\xff\xf3\x64\x00" + b"\x00" * 140) * n     # noqa: E731

    class Polly:
        def __init__(self):
            self.calls = []

        def synthesize_speech(self, Text, OutputFormat, VoiceId, Engine, SpeechMarkTypes=None):
            self.calls.append((Engine, OutputFormat))
            if OutputFormat == "json":
                raise RuntimeError("ThrottlingException: marks")
            return {"AudioStream": io.BytesIO(frames(len(Text)))}
    real_client, real_engine = voice._polly_client, voice.POLLY_ENGINE
    try:
        set_env(tts="polly", aws=True)
        fake = Polly()
        voice._polly_client = lambda: fake
        voice.POLLY_ENGINE = "generative"
        out = voice.synthesize("Arsenal lead one nil.")
        assert out and out["engine"] == "generative", out
        assert [m["value"] for m in out["marks"]] == "Arsenal lead one nil.".split()
        assert [c for c in fake.calls if c[1] == "mp3"] == [("generative", "mp3")], "no wasted neural call"
    finally:
        voice._polly_client, voice.POLLY_ENGINE = real_client, real_engine
    print("ok  VO-11 failing speech marks keep the audio; word timings are spread over its real length")


def test_bad_input_never_raises():                                        # VO-26 (voice.py side)
    set_env(tts="polly", aws=True)
    assert voice.synthesize(123) is None and voice.synthesize(None) is None and voice.synthesize(["a"]) is None

    class Broken:
        def __getattr__(self, name):
            raise RuntimeError("store down")
    assert voice.vocabulary_hint(Broken(), "v") == voice._BASE_HINT
    print("ok  VO-26 non-text to TTS and a failing vocabulary lookup return quietly instead of raising")


def test_small_ones():                                                    # VO-27
    # SIDELINE_TTS=browser means no Polly call
    real_client = voice._polly_client
    try:
        set_env(tts="browser", aws=True)
        voice._polly_client = lambda: (_ for _ in ()).throw(AssertionError("Polly called in browser mode"))
        assert voice.synthesize("Arsenal lead.") is None
    finally:
        voice._polly_client = real_client
    # a streaming error that would happen again is not retried (no second paid request)
    set_env(aws=True)
    fake = FakeVoxtral(stream=True, stream_error=RuntimeError("ThrottlingException: slow down"))
    voice._voxtral = fake
    assert voice._transcribe_voxtral(tone(1.0)) is None
    assert [r[0] for r in fake.requests] == ["converse_stream"], fake.requests
    fake = FakeVoxtral(stream=True, stream_error=RuntimeError(
        "ValidationException: This model does not support streaming"))
    voice._voxtral = fake
    assert voice._transcribe_voxtral(tone(1.0)) == {"text": "Who is refereeing?", "provider": "voxtral"}
    assert [r[0] for r in fake.requests] == ["converse_stream", "converse"]
    # one audit line per transcript: the server writes it, not Groq's adapter too
    from sideline import audit
    seen, real_record, real_open = [], audit.record, urllib.request.urlopen

    def fake_open(req, timeout=None, context=None):
        class R:
            def read(self):
                return b'{"text": "who scored"}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass
        return R()
    try:
        audit.record = lambda kind, **f: seen.append(kind)
        urllib.request.urlopen = fake_open
        set_env(stt="groq", groq="k")
        assert voice.transcribe(tone(1.0))["text"] == "who scored"
        assert "stt" not in seen, seen
    finally:
        audit.record, urllib.request.urlopen = real_record, real_open
    print("ok  VO-27 browser TTS makes no Polly call; stream errors are not paid twice; STT audited once")


# --------------------------------------------------------------- index.html
def test_page_source():
    assert 'id="sr" role="status" aria-live="polite"' in PAGE                                        # VO-03
    set_quiet = js("function setQuiet(t){", "/* The underline glides")
    assert "announce(t)" in set_quiet, "status lines (paused, can't reach the server) reach the live region"
    assert "announce(text)" in js("async function say(", "/* Play part 0 now")
    # VO-04 / VO-19: per-clip fallback, failures counted, a client timeout, and 'still working'
    clip = js("var sttFails=0", "function showSaid")
    assert "STT_MAX_FAILS=3" in clip and "STT_TIMEOUT_MS=15000" in clip and "signal:ctl.signal" in clip
    assert "stillWorking" in clip and "sttFails=0;" in clip
    # VO-02: the header is encoded, never the raw answer text
    assert '"X-Interrupted":interruptedHeader(takeCut())' in PAGE and '"X-Interrupted":takeCut()' not in PAGE
    # VO-07: an answer the server already made is rendered even while paused
    chat = clip[clip.index("if(doc.chat){"):clip.index("renderAgentAnswer(doc.chat")]
    assert "if(paused) return;" not in chat
    assert "pendingQuestion" in js("function setPaused", "document.addEventListener(\"keydown\"")
    # VO-13: no race against the permission prompt; the button comes back on failure
    audio = js("async function openAudio", "/* ============================================================== state")
    assert "Promise.race" not in audio
    begin = js('$("begin").onclick', "/* Ask the server what it can do")
    assert '$("begin").disabled=false' in begin and "introStarted=false" in begin
    # VO-14: pause stops the microphone's tracks
    assert "releaseMic();" in js("function setPaused", "document.addEventListener(\"keydown\"")
    assert "t.stop()" in js("function releaseMic", "async function openAudio")
    # VO-15: say() stops what was speaking and listening first; a stale utterance cannot end a new one;
    # an aborted request is not "I can't get an answer"
    assert "stopListening(); stopSpeaking();" in js("async function say(", "/* Play part 0 now")
    bs = js("function browserSay", "var idleT=null")
    assert "var gen=speakGen" in bs and bs.count("if(gen!==speakGen) return;") >= 3
    assert 'e.name==="AbortError"' in js("async function ask", "function applyToolResult")
    # VO-16: a refused play() falls back to the browser's voice
    chain = js("function playChain", "var hasBoundary=false")
    assert "played.catch(sayRestInBrowser)" in chain and "el.onerror=sayRestInBrowser" in chain
    assert "finishSpeaking(spans,done); });" not in chain
    # VO-20: connected before the intro is said
    assert "if(await connect()) say(INTRO);" in begin and "connPromise" not in begin
    # VO-23: the subtitles toggle shows focus, and Space on a button presses it
    assert ".sub-toggle-btn:focus-visible{" in PAGE and "outline:none" not in PAGE[PAGE.index(".sub-toggle-btn{"):
                                                                                 PAGE.index(".sub-toggle-btn:hover")]
    assert 'closest("button,input,textarea,select,[contenteditable]")' in PAGE
    print("ok  page: live region, status announced, STT timeout and per-clip fallback, paused answers kept,"
          " mic released, say() stops first, play() fallback, connect before intro, focus visible")


def test_js_tts_retry():                                                  # VO-01, VO-27 (ttsCache)
    if not NODE:
        print("skip  VO-01 under node (node is not installed)")
        return
    fn = js("var ttsCache={}", "async function say(")
    script = "var BASE='';var calls=0,mode='fail';" + """
    global.fetch=function(){ calls++;
      if(mode==='fail') return Promise.resolve({ok:false,status:503,json:function(){return Promise.resolve({})}});
      return Promise.resolve({ok:true,json:function(){return Promise.resolve({audio:'AAA',marks:[]})}}); };
    """ + fn + """
    var res={};
    var timer=setTimeout(function(){ res.hung=true; console.log(JSON.stringify(res)); process.exit(0); },5000);
    fetchSpeech('Hello there.').then(function(){ res.first='resolved'; },function(){ res.first='rejected'; })
    .then(function(){
      res.callsAfterFirst=calls; res.cachedAfterFailure=!!ttsCache['Hello there.'];
      return fetchSpeech('Hello there.').catch(function(){});
    }).then(function(){
      res.callsAfterSecond=calls; mode='ok';
      var a=fetchSpeech('Fine.'), b=fetchSpeech('Fine.');
      res.samePromise=(a===b);
      return a;
    }).then(function(doc){
      res.audio=doc.audio;
      for(var i=0;i<40;i++) fetchSpeech('line '+i);
      res.cacheSize=Object.keys(ttsCache).length;
      clearTimeout(timer); console.log(JSON.stringify(res));
    });
    """
    res = node(script)
    assert not res.get("hung"), "a failed TTS request must settle, never hang (VO-01)"
    assert res["first"] == "rejected" and res["callsAfterFirst"] == 2, res
    assert not res["cachedAfterFailure"] and res["callsAfterSecond"] == 4, "a failure is not cached"
    assert res["samePromise"] and res["audio"] == "AAA"
    assert res["cacheSize"] <= 24, res
    assert "browserSay(text,spans);" in js("async function say(", "/* Play part 0 now"), \
        "after the final failure the browser's voice says the answer"
    print("ok  VO-01 a failed TTS retry rejects (no deadlock), is not cached, and the cache is bounded")


def test_js_interrupted_header():                                         # VO-02
    if not NODE:
        print("skip  VO-02 under node (node is not installed)")
        return
    fn = js("function interruptedHeader", "/* Server recognition.")
    intro = PAGE[PAGE.index("var INTRO="):PAGE.index("var introStarted")]
    script = fn + intro + """
    var long=new Array(200).join('’ — “ ');
    var emoji=new Array(150).join('a')+'😀😀';
    var out={intro:interruptedHeader(INTRO), long:interruptedHeader(long), emoji:interruptedHeader(emoji),
             none:interruptedHeader(undefined)};
    out.introBack=decodeURIComponent(out.intro); out.introRaw=INTRO;
    out.longBack=decodeURIComponent(out.long).length;
    console.log(JSON.stringify(out));
    """
    res = node(script)
    for k in ("intro", "long", "emoji"):
        assert all(32 <= ord(c) < 127 for c in res[k]), "a header must be plain ASCII: " + k
    assert res["introBack"] == res["introRaw"][:300]
    assert res["longBack"] == 300 and res["none"] == ""
    print("ok  VO-02 the interrupted text is percent-encoded and capped at 300 characters (curly quotes, emoji)")


def test_js_stop_words():                                                 # VO-17
    if not NODE:
        print("skip  VO-17 under node (node is not installed)")
        return
    fn = js("var currentSpokenText", "function stopBargeSR") + js("function leadsWithStopWord",
                                                                    "function triggerWordBargeIn")
    script = fn + """
    currentSpokenText="Okay, Arsenal lead one nil. Saka scored on 34 minutes.";
    console.log(JSON.stringify([
      shouldBargeIn("okay arsenal lead"),     // our own voice through the speakers
      shouldBargeIn("okay"),                  // echo of the first word
      shouldBargeIn("stop"),
      shouldBargeIn("wait, which one?"),
      shouldBargeIn("hold on"),
      shouldBargeIn("who is the referee"),
      shouldBargeIn("the referee said wait"), // stop word not at the start, but a real question: 2+ words
      leadsWithStopWord("so are we okay"),
      leadsWithStopWord("Stop.")
    ]));
    """
    res = node(script)
    assert res == [False, False, True, True, True, True, True, False, True], res
    print("ok  VO-17 stop words count only at the start; Sideline's own 'Okay, ...' never cuts it off")


def test_js_stt_fallback():                                               # VO-04
    if not NODE:
        print("skip  VO-04 under node (node is not installed)")
        return
    fn = js("var sttFails=0", "async function handleClip")
    script = """
    var BASE='', paused=false, armed=true, speaking=false, pendingAnswer=null, pendingQuestion=null;
    var caps={stt:'voxtral',tts:'polly'}, SR=function(){}, useBrowserSTT=false, said=[], asked=[];
    var el={innerHTML:''}; function $(){ return el; }
    function say(t){ said.push(t); } function setQuiet(){} function showSaid(){} function ask(t){ asked.push(t); }
    var capsStt='voxtral';
    global.fetch=function(){ return Promise.resolve({ok:true,json:function(){ return Promise.resolve({stt:capsStt}); }}); };
    console.warn=function(){};
    """ + fn + """
    (async function(){
      var out={};
      await sttFailed(new Error('HTTP 503'),false,'');
      out.afterOne={stt:caps.stt, said:said.slice()};
      await sttFailed(new Error('HTTP 503'),false,'who scored for arsenal');
      out.usedCaption=asked.slice();
      await sttFailed(new Error('HTTP 503'),false,'');
      out.afterThree={stt:caps.stt, browser:useBrowserSTT, last:said[said.length-1]};
      caps.stt='voxtral'; sttFails=0; capsStt=null; said=[];
      await sttFailed(new Error('HTTP 503'),false,'');
      out.unavailable={stt:caps.stt, last:said[said.length-1]};
      caps.stt='voxtral'; sttFails=0; capsStt='voxtral'; said=[];
      await sttFailed(new Error('aborted'),true,'who scored');
      out.timeout={stt:caps.stt, said:said.slice(), asked:asked.length};
      console.log(JSON.stringify(out));
    })();
    """
    res = node(script)
    assert res["afterOne"]["stt"] == "voxtral" and "say it again" in res["afterOne"]["said"][0], res
    assert res["usedCaption"] == ["who scored for arsenal"], "the clip's own caption, not lost"
    assert res["afterThree"]["stt"] is None and res["afterThree"]["browser"] is True
    assert "switching to browser speech recognition" in res["afterThree"]["last"]
    assert res["unavailable"]["stt"] is None, "the server says no recogniser is left: switch at once"
    assert res["timeout"]["stt"] == "voxtral" and "too long" in res["timeout"]["said"][0]
    assert res["timeout"]["asked"] == 1, "a timed-out clip is not re-asked from the caption (the server may be answering)"
    print("ok  VO-04 one failed clip falls back for that clip; three in a row, or no recogniser left, switch")


def main():
    test_aws_only_by_default()
    test_hint_echo_only_for_hinted_and_lists()
    test_hallucination_filter_whisper_short_only()
    test_disabled_expires_and_validation_does_not_count()
    test_marks_failure_keeps_audio()
    test_bad_input_never_raises()
    test_small_ones()
    test_page_source()
    test_js_tts_retry()
    test_js_interrupted_header()
    test_js_stop_words()
    test_js_stt_fallback()
    print("\nfix voice: all good")


if __name__ == "__main__":
    main()
