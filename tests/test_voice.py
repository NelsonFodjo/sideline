"""Speech in: which provider is used, and what is sent to Groq's Whisper.

No network and no keys: urllib is patched. Real recognition accuracy is not
tested here (and cannot be without a key); `make stt-check` does a round trip
with a real provider.
"""

import io
import json
import urllib.error
import urllib.request
import wave

from conftest import make_ctx

from sideline import voice
from sideline.state.store import Event
from sideline.tools import REGISTRY

SENT = {}
RATE = 16000


def speech_like(seconds=1.0, amp=6000, seed=1):
    """Voiced, word-shaped sound: harmonics under a rising and falling envelope."""
    import math
    import random
    rnd = random.Random(seed)
    out, t, n = [], 0, int(RATE * seconds)
    while t < n:
        word, gap = int(RATE * rnd.uniform(.18, .45)), int(RATE * rnd.uniform(.06, .14))
        f0 = rnd.uniform(110, 190)
        for i in range(min(word, n - t)):
            env = math.sin(math.pi * i / word) ** 0.7
            out.append(int(amp * env * sum(math.sin(2 * math.pi * f0 * k * (t + i) / RATE) / k
                                           for k in range(1, 9)) / 2.2))
        t += word
        out += [0] * gap
        t += gap
    return out[:n]


def keyboard(seconds=1.0, every=0.12, seed=3):
    """White-noise clicks a few milliseconds long, about eight a second."""
    import random
    rnd = random.Random(seed)
    n = int(RATE * seconds)
    out = [int(rnd.gauss(0, 60)) for _ in range(n)]
    pos = 0
    while pos < n:
        ln = int(RATE * 0.012)
        for i in range(ln):
            if pos + i < n:
                out[pos + i] += int(rnd.gauss(0, 20000) * (1 - i / ln))
        pos += int(RATE * every * rnd.uniform(.7, 1.3))
    return out


def pcm_of(samples):
    import struct
    return struct.pack("<%dh" % len(samples), *[max(-32768, min(32767, x)) for x in samples])


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def ok_urlopen(req, timeout=None, context=None):
    SENT.update(url=req.full_url, headers={k.lower(): v for k, v in req.header_items()},
                body=req.data, context=context)
    return Resp(json.dumps({"text": " Who is refereeing? "}).encode())


def set_env(stt="auto", groq="", aws=False, have_sonic=False):
    voice.STT_PROVIDER, voice.GROQ_KEY = stt, groq
    voice._have_aws_credentials = lambda: aws
    voice.HAVE_SONIC = have_sonic
    voice._DISABLED.clear()


def main():
    pcm = pcm_of(speech_like(1.5))

    # ------------------------------------------------------ choosing
    # Measured: Groq beat Nova Sonic on accuracy and speed, so with a key it
    # leads; Sonic is next, then the browser.
    set_env(groq="k", aws=True, have_sonic=True)
    assert voice.stt_order() == ["groq", "sonic"]
    assert voice.capabilities()["stt"] == "groq"
    set_env(groq="", aws=True, have_sonic=True)
    assert voice.stt_order() == ["sonic"], "no key: nothing leaves AWS"
    set_env(groq="", aws=True, have_sonic=False)
    caps = voice.capabilities()
    assert voice.stt_order() == [] and "aws-sdk-bedrock-runtime" in caps["stt_hint"], caps
    set_env(groq="k")
    assert voice.stt_order() == ["groq"]
    set_env(groq="", aws=False, have_sonic=True)
    caps = voice.capabilities()
    assert caps["stt"] is None and "GROQ_API_KEY" in caps["stt_hint"]
    set_env(stt="off", groq="k", aws=True, have_sonic=True)
    assert voice.stt_order() == []
    print("ok  auto order is Groq (with a key), Nova Sonic, then the browser; no key means nothing leaves AWS")

    # naming a provider means that provider, and never a silent swap
    set_env(stt="sonic", groq="k", aws=True, have_sonic=False)
    assert voice.stt_order() == [], "sonic forced but not installed: not Groq"
    set_env(stt="groq", groq="", aws=True, have_sonic=True)
    assert voice.stt_order() == [], "groq forced but no key: not Sonic"
    set_env(stt="groq", groq="k", aws=True, have_sonic=True)
    assert voice.stt_order() == ["groq"]
    print("ok  a provider named in SIDELINE_STT is used alone")

    # live captions: on by default when recognition is server-side, switchable
    set_env(groq="k")
    voice.LIVE_CAPTION = "browser"
    assert voice.capabilities()["caption"] == "browser"
    voice.LIVE_CAPTION = "off"
    assert voice.capabilities()["caption"] is None, "off keeps audio with the chosen provider"
    voice.LIVE_CAPTION = "browser"
    set_env(groq="", aws=False)
    assert voice.capabilities()["caption"] is None, "browser recognition already types live"
    print("ok  live captions follow server recognition, and SIDELINE_LIVE_CAPTION=off disables them")

    # ------------------------------------------- keyboard noise is not speech
    sp = speech_like(2.0)
    typing = keyboard(2.0)
    assert voice.voiced_ms(pcm_of(sp)) >= 1000, voice.voiced_ms(pcm_of(sp))
    assert voice.voiced_ms(pcm_of(typing)) == 0, "typing alone must not count as speech"
    mixed = [a + b for a, b in zip(sp, typing)]
    assert voice.voiced_ms(pcm_of(mixed)) >= 1000, "speaking while typing is still speech"
    thump = [int(3000 * __import__("math").sin(2 * 3.14159 * 90 * i / RATE))
             if 8000 < i < 9600 else 0 for i in range(RATE * 2)]
    assert voice.voiced_ms(pcm_of(thump)) < voice.GATE_MIN_VOICED_MS, "a 100 ms thump"
    assert voice.voiced_ms(pcm_of([0] * RATE * 2)) == 0
    set_env(groq="k", aws=True, have_sonic=True)
    urllib.request.urlopen = ok_urlopen
    SENT.clear()
    out = voice.transcribe(pcm_of(typing), "audio/pcm")
    assert out == {"text": "", "provider": "gate"} and not SENT, \
        "a clip of clicks must never reach a provider (Whisper turns it into 'Thank you.')"
    out = voice.transcribe(pcm_of(mixed), "audio/pcm")
    assert out["provider"] == "groq" and SENT, "speech with typing in the background is sent"
    print("ok  clicks and thumps are not speech: typing is dropped before any request, speech over typing is kept")

    # ---------------------------------------- the fallback chain, per clip
    set_env(groq="k", aws=True, have_sonic=True)
    long_pcm = pcm_of(speech_like(1.5))
    calls = []

    async def sonic_ok(pcm, hint=""):
        calls.append("sonic")
        return "who is refereeing"

    def groq_fails(pcm, hint=""):
        calls.append("groq")
        return None

    def groq_hears_nothing(pcm, hint=""):
        calls.append("groq")
        return {"text": "", "provider": "groq"}
    voice._sonic_hear = sonic_ok
    voice._transcribe_groq = groq_fails
    out = voice.transcribe(long_pcm)
    assert out == {"text": "who is refereeing", "provider": "sonic"} and calls == ["groq", "sonic"]
    voice._transcribe_groq = groq_hears_nothing
    calls[:] = []
    out = voice.transcribe(long_pcm)
    assert out == {"text": "", "provider": "groq"} and calls == ["groq"], \
        "silence is an answer, not a failure: do not pay for a second opinion"
    print("ok  a clip Groq fails goes to Sonic; a clip Groq hears nothing in does not")
    import importlib
    importlib.reload(voice)               # restore the real _transcribe_groq / _sonic_hear

    # failover: a permission error removes Sonic, a blip does not
    async def denied(pcm, hint=""):
        raise RuntimeError("AccessDeniedException: not authorized")

    async def blip(pcm, hint=""):
        raise RuntimeError("connection reset")

    async def hears(pcm, hint=""):
        hears.hint = hint
        return "who is refereeing"
    set_env(aws=True, have_sonic=True)
    voice._sonic_hear = blip
    assert voice.transcribe(long_pcm) is None and voice.stt_order() == ["sonic"]
    voice._sonic_hear = denied
    assert voice.transcribe(long_pcm) is None and voice.stt_order() == []
    set_env(aws=True, have_sonic=True)
    voice._sonic_hear = hears
    assert voice.transcribe(long_pcm, hint="Saka") == {"text": "who is refereeing",
                                                       "provider": "sonic"}
    assert hears.hint == "Saka"
    assert voice.transcribe(b"\0" * 100) == {"text": "", "provider": "gate"}, \
        "a clip under 0.4 s is never sent"
    print("ok  Sonic: a blip falls back for one clip, AccessDenied takes it out of rotation, the hint is passed")

    # ------------------------------------------------------ the request
    set_env(groq="secret-key")
    urllib.request.urlopen = ok_urlopen
    out = voice.transcribe(pcm, "audio/pcm", hint="Arsenal, Saka, Ødegaard")
    assert out == {"text": "Who is refereeing?", "provider": "groq"}, out
    body = SENT["body"].decode("latin-1")
    assert SENT["headers"]["authorization"] == "Bearer secret-key"
    assert SENT["headers"]["user-agent"] == "sideline/1.0"
    for needle in ('name="model"', voice.GROQ_MODEL, 'name="language"', "\r\nen\r\n",
                   'name="temperature"', "\r\n0\r\n", 'name="prompt"'):
        assert needle in body, needle
    assert "Ødegaard".encode("utf-8").decode("latin-1") in body
    assert SENT["context"] is not None, "TLS must go through sideline.tls"
    wav_start = SENT["body"].index(b"RIFF")
    w = wave.open(io.BytesIO(SENT["body"][wav_start:SENT["body"].index(b"\r\n--", wav_start)]))
    assert (w.getnchannels(), w.getframerate(), w.getnframes()) == (1, 16000, len(pcm) // 2)
    print("ok  PCM goes up as a WAV with model, language, temperature 0 and the vocabulary prompt")

    # too short to hold a word: never sent
    SENT.clear()
    assert voice.transcribe(b"\0" * 100, "audio/pcm") == {"text": "", "provider": "gate"}
    assert not SENT
    print("ok  a clip shorter than 0.4 s is dropped before it costs a request")

    # ------------------------------------------------------ failures
    def failing(code):
        def f(req, timeout=None, context=None):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b""))
        return f
    urllib.request.urlopen = failing(429)
    assert voice.transcribe(pcm) is None
    assert voice.capabilities()["stt"] == "groq", "a rate limit is temporary"
    urllib.request.urlopen = failing(401)
    assert voice.transcribe(pcm) is None
    assert voice.capabilities()["stt"] is None, "a rejected key will not fix itself"
    print("ok  429 falls back for that clip only; 401 takes Groq out of rotation")

    # ------------------------------------------------------ vocabulary
    set_env(groq="k")
    ctx = make_ctx(start_minute=0)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "v")
    fid = ctx.store.listener("v")["following"]
    ctx.store.append_event(Event.make(fid, 5, "goal", player="Martin Ødegaard",
                                      team="Arsenal", assist="Bukayo Saka"))
    hint = voice.vocabulary_hint(ctx, "v")
    assert "Arsenal" in hint and "Martin Ødegaard" in hint and "Bukayo Saka" in hint
    assert "what did i miss" in hint.lower()
    assert "Martin Ødegaard" in voice.vocabulary_hint(ctx, "v", max_names=24)
    assert voice.vocabulary_hint(ctx, "nobody").startswith("Questions about")
    # Someone who has followed nothing still gets the teams on today, so Arsenal is not heard as "asana".
    assert "Arsenal" in voice.vocabulary_hint(ctx, "nobody") and "Tottenham" in voice.vocabulary_hint(ctx, "nobody")
    # An accented name is also given in plain letters, which is how a recogniser spells what it hears.
    ctx.provider.fixtures_on = lambda off: [{"fixture_id": 9, "home": "Sønderjyske Fodbold", "away": "FC København",
                                             "status": "NS", "kickoff": "2026-10-13T19:00:00+00:00"}] if off == 0 else []
    hint = voice.vocabulary_hint(ctx, "nobody")
    assert "Sønderjyske Fodbold" in hint and "sonderjyske fodbold" in hint and "fc kobenhavn" in hint, hint
    print("ok  the prompt carries the followed match's teams and players, and a stranger gets the basics")

    # Whisper prints its own prompt when it is given noise: team names nobody said.
    hint = voice._BASE_HINT + " Hartlepool, Newcastle United U21"
    assert voice.echoes_hint("Hartlepool, Newcastle U21", hint), "the names alone are an echo"
    assert voice.echoes_hint("Newcastle United U21.", hint)
    assert not voice.echoes_hint("Follow Hartlepool", hint), "a real command is kept"
    assert not voice.echoes_hint("Who is refereeing?", hint), "a real question is kept"
    assert not voice.echoes_hint("", hint) and not voice.echoes_hint("Hartlepool", "")
    assert not voice.echoes_hint("Hartlepool", hint), "one bare name could be the answer to 'which team?'"
    offered = "The listener is choosing between: Hartlepool, Newcastle United U21. " + hint
    assert not voice.echoes_hint("Hartlepool", offered), "after an offer a bare name IS the answer"
    # Whisper's own doubt: probably silence and not confident is a hallucinated segment.
    doc = {"text": "Thanks for watching Hartlepool", "segments": [
        {"text": " Thanks for watching", "no_speech_prob": 0.9, "avg_logprob": -1.4},
        {"text": " who is refereeing", "no_speech_prob": 0.05, "avg_logprob": -0.2}]}
    assert voice._spoken_text(doc) == "who is refereeing", voice._spoken_text(doc)
    assert voice._spoken_text({"text": " hello there "}) == "hello there", "no segments: the text as is"
    print("ok  noise that Whisper turns into its own hint, or into a doubted segment, is dropped")

    # ------------------------------------------------------ speech out: natural voice, exact timings
    import base64

    def frames(n, id3=False):
        """n MPEG-2 layer III frames at 48 kbps and 24 kHz: 24 ms each (576 / 24000), 144 bytes."""
        head = b"\xff\xf3\x64\x00"
        tag = b"ID3\x04\x00\x00\x00\x00\x00\x04abcd" if id3 else b""
        return tag + (head + b"\x00" * 140) * n
    assert abs(voice.mp3_seconds(frames(100)) - 2.4) < 1e-6 and abs(voice.mp3_seconds(frames(100, id3=True)) - 2.4) < 1e-6
    assert voice.mp3_seconds(b"") == 0 and voice.mp3_seconds(b"not audio at all") == 0
    assert voice._id3_size(frames(1, id3=True)) == 14 and voice._id3_size(frames(1)) == 0
    print("ok  an MP3's exact length is read from its frames, with or without an ID3 tag")

    txt = "Arsenal host Lille. It's at St. Mirren Park, in Paisley! A. Saka scored. Newcastle United U21 won 3-0."
    toks = [(m.start(), m.end()) for m in __import__("re").finditer(r"\S+", txt)]
    spans = [" ".join(txt[a:b] for a, b in toks[lo:hi]) for lo, hi in voice._sentence_ranges(txt, toks)]
    assert spans == ["Arsenal host Lille.", "It's at St. Mirren Park, in Paisley!", "A. Saka scored.",
                     "Newcastle United U21 won 3-0."], spans
    assert voice.speakable("U21") == "under-21" and voice.speakable("U19,") == "under-19," and voice.speakable("Uruguay") == "Uruguay"
    assert voice.speakable("Arsenal") == "Arsenal" and voice.speakable("U2") == "U2"
    print("ok  sentences split at . ! ? before a capital, not after St. or an initial; U21 is said 'under 21'")

    even = voice._marks_fitted([], 4, 2000)
    assert even == [0, 500, 1000, 1500], "no usable marks: the words spread evenly"
    fitted = voice._marks_fitted([{"time": 0, "value": "a"}, {"time": 500, "value": "bb"}, {"time": 1000, "value": "ccc"}], 3, 1700)
    assert fitted[0] == 0 and fitted[1] < fitted[2] < 1700, fitted
    print("ok  word timings are fitted to the audio's real length, or spread evenly when the words do not line up")

    class FakePolly:
        """Sentence in, frames out (one per character), and one word mark per word. Generative can be made to fail."""
        def __init__(self, fail_generative=False):
            self.fail, self.calls = fail_generative, []

        def synthesize_speech(self, Text, OutputFormat, VoiceId, Engine, SpeechMarkTypes=None):
            self.calls.append((Engine, OutputFormat, Text))
            if OutputFormat == "mp3":
                if Engine == "generative" and self.fail:
                    raise RuntimeError("ValidationException: not supported")
                return {"AudioStream": io.BytesIO(frames(len(Text), id3=True))}
            words = Text.split()
            lines, t = [], 0
            for w in words:
                lines.append(json.dumps({"time": t, "type": "word", "value": w}))
                t += 24 * (len(w) + 1)
            return {"AudioStream": io.BytesIO("\n".join(lines).encode())}

    real_client, real_engine = voice._polly_client, voice.POLLY_ENGINE
    try:
        text = "Arsenal host Lille. It's at St. Mirren Park."
        for fail, want_engine in ((False, "generative"), (True, "neural")):
            fake = FakePolly(fail_generative=fail)
            voice._polly_client = lambda f=fake: f
            voice.POLLY_ENGINE = "generative"
            out = voice.synthesize(text)
            assert out["engine"] == want_engine and out["format"] == "mp3", out["engine"]
            marks = out["marks"]
            assert [m["value"] for m in marks] == text.split(), "one mark per word as written"
            assert all(text[m["start"]:m["end"]] == m["value"] for m in marks), "positioned in the text as written"
            assert [m["time"] for m in marks] == sorted(m["time"] for m in marks), "in order"
            audio = base64.b64decode(out["audio"])
            assert voice._id3_size(audio) == 0, "one stream, no tags"
            assert abs(voice.mp3_seconds(audio) - len(text) * 0.024) < 1e-6, "the whole answer is one piece of audio"
            assert sum(1 for c in fake.calls if c[1] == "mp3" and c[0] == "generative") == 1, "one call, so the voice flows"
        # Only an answer too long for one call is cut, and at a sentence end.
        long_text = " ".join("Arsenal host Lille at ground number %d." % i for i in range(60))
        fake = FakePolly()
        voice._polly_client = lambda f=fake: f
        voice.POLLY_ENGINE = "generative"
        out = voice.synthesize(long_text)
        calls = sum(1 for c in fake.calls if c[1] == "mp3")
        assert calls > 1 and [m["value"] for m in out["marks"]] == long_text.split(), calls
        voice.POLLY_ENGINE = "neural"
        fake = FakePolly()
        voice._polly_client = lambda: fake
        assert voice.synthesize(text)["engine"] == "neural" and not any(c[0] == "generative" for c in fake.calls)
        voice._polly_client = lambda: None
        assert voice.synthesize(text) is None and voice.synthesize("") is None

        def no_such_profile():
            raise RuntimeError("The config profile (123456789012) could not be found")
        voice._polly_client = no_such_profile
        assert voice.synthesize(text) is None, "a client that cannot be built means the browser voice, not a crashed request"
    finally:
        voice._polly_client, voice.POLLY_ENGINE = real_client, real_engine
    print("ok  the natural voice, an answer in one piece: one mark per word as written, a generative failure falls back to neural, neural on request")

    print("\nvoice: all good")


if __name__ == "__main__":
    main()
