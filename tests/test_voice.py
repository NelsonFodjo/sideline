"""Speech in: which AWS model is used (Voxtral, then Nova Sonic), what is sent to it, and what happens when it fails.

No network and no credentials: the Bedrock clients are doubles. Real recognition accuracy is not tested here;
`make stt-check` and `make compare-stt` do that against the real service.
"""

import io
import json
import wave

from conftest import make_ctx

from simulator import voice
from sideline.state.store import Event
from sideline.tools import REGISTRY

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


class FakeVoxtral:
    """A Bedrock runtime client that answers Converse the way Voxtral does, and records the request."""

    def __init__(self, text=" Who is refereeing? ", error=None):
        self.text, self.error, self.requests = text, error, []

    def converse(self, **kw):
        self.requests.append(kw)
        if self.error:
            raise self.error
        return {"output": {"message": {"role": "assistant", "content": [{"text": self.text}]}},
                "usage": {"inputTokens": 40, "outputTokens": 6}}


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


def main():
    pcm = pcm_of(speech_like(1.5))

    # ------------------------------------------------------ choosing
    # auto is AWS only (VO-05): a Groq key in the environment never sends audio to Groq unless it is named.
    set_env(groq="test-key", aws=True, have_sonic=True)
    assert voice.stt_order() == ["voxtral", "sonic"]
    assert voice.capabilities()["stt"] == "voxtral"
    set_env(groq="test-key", aws=False)
    assert voice.stt_order() == []

    # When Groq is not configured, AWS Bedrock order applies
    set_env(aws=True, have_sonic=True)
    assert voice.stt_order() == ["voxtral", "sonic"]
    assert voice.capabilities()["stt"] == "voxtral"
    set_env(aws=True, have_sonic=False)
    assert voice.stt_order() == ["voxtral"], "no streaming SDK: Voxtral still works (it needs only boto3)"
    set_env(aws=False, have_sonic=True)
    caps = voice.capabilities()
    assert caps["stt"] is None and "AWS credentials" in caps["stt_hint"], caps
    set_env(stt="off", aws=True, have_sonic=True)
    assert voice.stt_order() == []
    print("ok  auto order is Voxtral, then Nova Sonic (Bedrock only); Groq only when named")

    # naming a provider means that provider, and never a silent swap
    set_env(stt="groq", groq="", aws=True, have_sonic=True)
    assert voice.stt_order() == [], "groq forced but no key: not Voxtral"
    set_env(stt="groq", groq="test-key", aws=True, have_sonic=True)
    assert voice.stt_order() == ["groq"]
    set_env(stt="sonic", aws=True, have_sonic=False)
    assert voice.stt_order() == [], "sonic forced but not installed: not Voxtral"
    set_env(stt="voxtral", aws=True, have_sonic=True)
    assert voice.stt_order() == ["voxtral"]
    set_env(stt="voxtral", aws=False, have_sonic=True)
    assert voice.stt_order() == [], "no AWS credentials: nothing to name"
    print("ok  a provider named in SIDELINE_STT is used alone")

    # live captions: off by default (VO-05); when switched on, only meaningful with server recognition
    set_env(aws=True)
    voice.LIVE_CAPTION = "browser"
    assert voice.capabilities()["caption"] == "browser"
    voice.LIVE_CAPTION = "off"
    assert voice.capabilities()["caption"] is None, "off keeps audio with the chosen provider"
    voice.LIVE_CAPTION = "browser"
    set_env(aws=False)
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
    set_env(aws=True)
    fake = FakeVoxtral()
    voice._voxtral = fake
    out = voice.transcribe(pcm_of(typing), "audio/pcm")
    assert out == {"text": "", "provider": "gate"} and not fake.requests, \
        "a clip of clicks must never reach a provider (a recogniser turns it into 'Thank you.')"
    out = voice.transcribe(pcm_of(mixed), "audio/pcm")
    assert out["provider"] == "voxtral" and fake.requests, "speech with typing in the background is sent"
    print("ok  clicks and thumps are not speech: typing is dropped before any request, speech over typing is kept")

    # ------------------------------------------------------ the request
    set_env(aws=True)
    fake = FakeVoxtral()
    voice._voxtral = fake
    hint = voice._BASE_HINT + " Arsenal, Saka, Ødegaard"
    out = voice.transcribe(pcm, "audio/pcm", hint)
    assert out == {"text": "Who is refereeing?", "provider": "voxtral"}, out
    req = fake.requests[0]
    assert req["modelId"] == voice.VOXTRAL_MODEL and "system" not in req, "a system message is refused alongside audio"
    blocks = req["messages"][0]["content"]
    assert "audio" in blocks[0] and "text" in blocks[1], "the audio comes BEFORE the instruction"
    assert "Ødegaard" not in blocks[1]["text"] and "Do not answer" in blocks[1]["text"], \
        "no vocabulary in the prompt: a chat model echoes a list of names and answers from it"
    w = wave.open(io.BytesIO(blocks[0]["audio"]["source"]["bytes"]))
    assert blocks[0]["audio"]["format"] == "wav" and (w.getnchannels(), w.getframerate(), w.getnframes()) == (1, 16000, len(pcm) // 2)
    assert req["inferenceConfig"]["temperature"] == 0
    print("ok  PCM goes up as a WAV, audio first, an instruction that forbids answering, no vocabulary and no system message")

    # Noise is never text: a label for a sound is dropped, whichever model wrote it.
    for label, want in (("[SOUND]", ""), ("[Music]", ""), ("(applause) [inaudible]", ""), ("*cough*", ""),
                        ("\u266a \u266a", ""), ("Who is [inaudible] refereeing?", "Who is refereeing?"),
                        ("What's the score? [SOUND]", "What's the score?"), (".", "")):
        assert voice.only_words(label) == want, (label, voice.only_words(label))
    voice._voxtral = FakeVoxtral(text="[SOUND]")
    out = voice.transcribe(pcm_of(mixed), "audio/pcm")
    assert out == {"text": "", "provider": "voxtral"}, "a clip heard as a sound is 'heard nothing', not a question"
    print("ok  [SOUND], [Music], (applause), *cough* and the like are dropped: noise is never shown or acted on")

    # too short to hold a word: never sent
    fake.requests[:] = []
    assert voice.transcribe(b"\0" * 100, "audio/pcm") == {"text": "", "provider": "gate"}
    assert not fake.requests
    print("ok  a clip shorter than 0.4 s is dropped before it costs a request")

    # A model that talks about the clip instead of writing it down is not a transcript.
    voice._voxtral = FakeVoxtral(text="Alright, so I'm going to ask you a question. " * 8)
    assert voice._transcribe_voxtral(pcm) is None, "far more words than a 1.5 s clip can hold"
    print("ok  a reply with more words than the clip holds is dropped, not spoken to the listener")

    # ---------------------------------------- failures and the fallback chain, per clip
    set_env(aws=True, have_sonic=True)
    long_pcm = pcm_of(speech_like(1.5))
    calls = []

    async def sonic_ok(pcm, hint=""):
        calls.append("sonic")
        return "who is refereeing"

    voice._sonic_hear = sonic_ok
    voice._voxtral = FakeVoxtral(error=RuntimeError("ThrottlingException: slow down"))
    out = voice.transcribe(long_pcm)
    assert out == {"text": "who is refereeing", "provider": "sonic"} and calls == ["sonic"]
    assert voice.stt_order() == ["voxtral", "sonic"], "a throttle is temporary: Voxtral stays in rotation"
    voice._voxtral = FakeVoxtral(text="  ")
    calls[:] = []
    out = voice.transcribe(long_pcm)
    assert out == {"text": "", "provider": "voxtral"} and not calls, \
        "silence is an answer, not a failure: do not pay for a second opinion"
    voice._voxtral = FakeVoxtral(error=RuntimeError("AccessDeniedException: not authorized"))
    voice.transcribe(long_pcm)
    assert voice.stt_order() == ["sonic"], "access denied will not fix itself: Voxtral leaves the rotation"
    print("ok  a clip Voxtral fails goes to Sonic; silence is not a failure; AccessDenied takes it out of rotation")
    import importlib
    importlib.reload(voice)               # restore the real _sonic_hear

    # failover: a permission error removes Sonic, a blip does not
    async def denied(pcm, hint=""):
        raise RuntimeError("AccessDeniedException: not authorized")

    async def blip(pcm, hint=""):
        raise RuntimeError("connection reset")

    async def hears(pcm, hint=""):
        hears.hint = hint
        return "who is refereeing"
    set_env(stt="sonic", aws=True, have_sonic=True)
    voice._sonic_hear = blip
    assert voice.transcribe(long_pcm) is None and voice.stt_order() == ["sonic"]
    voice._sonic_hear = denied
    assert voice.transcribe(long_pcm) is None and voice.stt_order() == []
    set_env(stt="sonic", aws=True, have_sonic=True)
    voice._sonic_hear = hears
    assert voice.transcribe(long_pcm, hint="Saka") == {"text": "who is refereeing",
                                                       "provider": "sonic"}
    assert hears.hint == "Saka"
    print("ok  Sonic: a blip falls back for one clip, AccessDenied takes it out of rotation, the hint is passed")

    # ------------------------------------------------------ Groq request & errors
    import urllib.error
    import urllib.request
    real_urlopen = urllib.request.urlopen
    try:
        sent = {}

        def mock_urlopen(req, timeout=None, context=None):
            sent["url"] = req.full_url
            sent["headers"] = dict(req.headers)
            sent["body"] = req.data

            class MockResp:
                def read(self):
                    return json.dumps({"text": "Who is refereeing?"}).encode("utf-8")

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    pass

            return MockResp()

        urllib.request.urlopen = mock_urlopen
        set_env(stt="groq", groq="test-secret")
        out = voice.transcribe(long_pcm, "audio/pcm", hint="Arsenal, Saka, Ødegaard")
        assert out == {"text": "Who is refereeing?", "provider": "groq"}, out
        assert sent["url"] == voice.GROQ_URL
        assert sent["headers"]["Authorization"] == "Bearer test-secret"
        assert b"whisper-large-v3-turbo" in sent["body"]
        assert b"Arsenal, Saka" in sent["body"]
        assert b"RIFF" in sent["body"]

        # 429: temporary rate limit
        def mock_429(req, timeout=None, context=None):
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))

        urllib.request.urlopen = mock_429
        assert voice.transcribe(long_pcm) is None
        assert "groq" not in voice._DISABLED

        # 401: auth failure disables Groq for this run
        def mock_401(req, timeout=None, context=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

        urllib.request.urlopen = mock_401
        assert voice.transcribe(long_pcm) is None
        assert "groq" in voice._DISABLED
        print("ok  Groq: fast ASR with vocabulary hint, 429 retries, 401 disables for run")
    finally:
        urllib.request.urlopen = real_urlopen

    # ------------------------------------------------------ vocabulary
    set_env(aws=True)
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

    # A recogniser prints its own vocabulary when it is given noise: team names nobody said.
    hint = voice._BASE_HINT + " Hartlepool, Newcastle United U21"
    assert voice.echoes_hint("Hartlepool, Newcastle U21", hint), "the names alone are an echo"
    assert not voice.echoes_hint("Newcastle United U21.", hint), "one team's full name is an answer (VO-06)"
    assert not voice.echoes_hint("Follow Hartlepool", hint), "a real command is kept"
    assert not voice.echoes_hint("Who is refereeing?", hint), "a real question is kept"
    assert not voice.echoes_hint("", hint) and not voice.echoes_hint("Hartlepool", "")
    assert not voice.echoes_hint("Hartlepool", hint), "one bare name could be the answer to 'which team?'"
    offered = "The listener is choosing between: Hartlepool, Newcastle United U21. " + hint
    assert not voice.echoes_hint("Hartlepool", offered), "after an offer a bare name IS the answer"
    print("ok  noise that a recogniser turns into its own vocabulary is dropped")

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
    assert voice.speakable("Alexa+,") == "Alexa-plus," and voice.speakable("MCP") == "MCP", "Polly already says MCP letter by letter, a second faster than M-C-P"
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
    # ------------------------------------------------------ TTS capabilities & providers
    set_env(tts="browser")
    assert voice.capabilities()["tts"] == "browser"
    # auto stays inside AWS (VO-05): a third-party key alone is not a choice to use it
    set_env(tts="auto", cartesia="cart-key")
    assert voice.capabilities()["tts"] == "browser"
    set_env(tts="auto", elevenlabs="eleven-key", aws=True)
    assert voice.capabilities()["tts"] == "polly"
    set_env(tts="cartesia", cartesia="cart-key")
    assert voice.capabilities()["tts"] == "cartesia"
    set_env(tts="elevenlabs", elevenlabs="eleven-key")
    assert voice.capabilities()["tts"] == "elevenlabs"
    set_env(tts="auto", aws=True)
    assert voice.capabilities()["tts"] == "polly"
    set_env(tts="auto", aws=False)
    assert voice.capabilities()["tts"] == "browser"

    # Elevenlabs mock synthesis
    real_urlopen = urllib.request.urlopen
    try:
        def mock_el_urlopen(req, timeout=None, context=None):
            class MockResp:
                def read(self):
                    return json.dumps({
                        "audio_base64": "ZXhhbXBsZQ==",
                        "alignment": {
                            "characters": ["A", "r", "s", "e", "n", "a", "l"],
                            "character_start_times_seconds": [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3],
                            "character_end_times_seconds": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35],
                        }
                    }).encode("utf-8")
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    pass
            return MockResp()

        urllib.request.urlopen = mock_el_urlopen
        set_env(tts="elevenlabs", elevenlabs="test-key")
        res = voice.synthesize("Arsenal")
        assert res["provider"] == "elevenlabs"
        assert res["audio"] == "ZXhhbXBsZQ=="
        assert len(res["marks"]) == 1 and res["marks"][0]["value"] == "Arsenal"
    finally:
        urllib.request.urlopen = real_urlopen
    print("ok  TTS selection: AWS Polly by default, browser without AWS; Cartesia/ElevenLabs only when named")

    print("\nvoice: all good")


if __name__ == "__main__":
    main()
