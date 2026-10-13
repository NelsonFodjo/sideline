"""Speech in and speech out, for the simulator.

Sideline's product surface is MCP: a client such as Alexa+ would do the
listening and the talking, and the MCP server never touches audio. The simulator
is our own client, so it has to BE the voice. The browser captures audio and
posts it here; this module calls a provider; keys never reach the browser.

SPEECH OUT: Amazon Polly, its generative voice (the most natural) with the neural one as the fallback.
The page also needs speech marks, every word with its offset in milliseconds, so it can highlight each
word at the moment the voice reaches it; only the neural voice returns them, so they are fetched from it
and fitted to the generative audio. An answer is made in one piece, so the voice flows (see "speech out"
below). Without AWS credentials the page uses the browser's own voice.

SPEECH IN: models on Amazon Bedrock, so audio never leaves the AWS account. Measured head to head on 48
clips, clean and noisy (scripts/compare_stt.py; docs/SPEECH.md):

    1. Voxtral small  Mistral's speech model on Bedrock, through Converse: about 0.8 s, and every name right
    2. Nova Sonic     Amazon's, needs the streaming SDK (Python 3.12+): about 3.5 s, so only a fallback
    3. the browser's own recognition, the least accurate, used when neither works

A clip one provider fails goes to the next, so a throttle never leaves a listener unheard. Naming a provider
(SIDELINE_STT=sonic) uses it alone.

/voice/stt and /voice/tts are simulator support, not part of the MCP surface.
Nothing in sideline/tools/ knows they exist.
"""

import asyncio
import base64
import json
import logging
import os
import re

LOG = logging.getLogger("sideline.voice")

try:
    import boto3
    from botocore.config import Config as BotoConfig
    HAVE_BOTO3 = True
except ImportError:                                            # pragma: no cover
    boto3 = None
    BotoConfig = None
    HAVE_BOTO3 = False

# Nova Sonic hears speech directly. It needs the Bedrock bidirectional-streaming
# SDK (Python 3.12+), which boto3 does not provide; absent that, it is simply off.
try:
    from aws_sdk_bedrock_runtime.client import (
        AsyncBedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput)
    from aws_sdk_bedrock_runtime.config import AsyncBedrockRuntimeConfig
    from aws_sdk_bedrock_runtime.models import (
        BidirectionalInputPayloadPart, InvokeModelWithBidirectionalStreamInputChunk)
    from smithy_http.aio.crt import AWSCRTHTTPClient
    HAVE_SONIC = True
except ImportError:                                            # pragma: no cover
    HAVE_SONIC = False

REGION = os.environ.get("AWS_REGION", "us-east-1")

# --- speech out: British by default, because the listener is following English
# football and a matching accent is less jarring than a US voice reading
# "Ødegaard". Override with SIDELINE_POLLY_VOICE.
POLLY_VOICE = os.environ.get("SIDELINE_POLLY_VOICE", "Amy")
POLLY_ENGINE = os.environ.get("SIDELINE_POLLY_ENGINE", "generative").strip().lower()   # generative|neural

# --- speech in
STT_PROVIDER = os.environ.get("SIDELINE_STT", "auto")          # auto|voxtral|sonic|off
SONIC_MODEL = "amazon.nova-2-sonic-v1:0"
VOXTRAL_MODEL = "mistral.voxtral-small-24b-2507"     # speech in, text out, through Bedrock Converse
SAMPLE_RATE = 16000

# Words typed on screen while the listener is still speaking. Server-side
# recognition (Voxtral, Nova Sonic) only returns text once the clip ends, so for
# live typing the page also runs the browser's own recognition on the side,
# purely to show interim words, and replaces them with the server's more
# accurate transcript. The cost: that audio also reaches the browser vendor
# (Chrome and Edge send it to theirs). SIDELINE_LIVE_CAPTION=off keeps the
# audio with the chosen provider only, and nothing types until the clip ends.
LIVE_CAPTION = os.environ.get("SIDELINE_LIVE_CAPTION", "browser").strip().lower()

# Providers that failed in a way retrying will not fix (a bad key, access
# denied). Taken out of rotation so every utterance does not pay a failing
# round trip before falling back.
_DISABLED = set()

_polly = None


def _polly_client():
    global _polly
    if _polly is None:
        if not HAVE_BOTO3:
            return None
        _polly = boto3.client("polly", region_name=REGION,
                              config=BotoConfig(read_timeout=12, connect_timeout=3,
                                                retries={"max_attempts": 2}))
        LOG.info("polly ready: %s (%s) in %s", POLLY_VOICE, POLLY_ENGINE, REGION)
    return _polly


def _have_aws_credentials():
    """Can boto3 actually resolve credentials?

    Checked because reporting a provider we cannot use is worse than
    reporting none: the browser would stop using its own engine, post
    audio here, and get a 503 for every utterance. No network call -
    this reads the credential chain only.
    """
    if not HAVE_BOTO3:
        return False
    try:
        return boto3.Session().get_credentials() is not None
    except Exception:                                          # noqa: BLE001
        return False


def stt_order():
    """Providers that can be used right now, best first.

    A named provider (SIDELINE_STT=sonic) is used alone, never silently
    swapped for another, so a choice about where audio goes is respected.
    """
    aws = _have_aws_credentials()
    ok = {"voxtral": aws and HAVE_BOTO3, "sonic": aws and HAVE_SONIC}
    if STT_PROVIDER == "off":
        return []
    names = ["voxtral", "sonic"] if STT_PROVIDER == "auto" else [STT_PROVIDER]
    return [n for n in names if ok.get(n) and n not in _DISABLED]


def capabilities():
    """What the simulator should use. Asked once, at page load.

    Honest about what will actually work. The browser decides from this
    whether to post audio here or fall back to its own engine, so a
    hopeful answer here becomes a broken prototype there.
    """
    aws = _have_aws_credentials()

    order = stt_order()
    stt = order[0] if order else None

    tts = "polly" if aws else None
    out = {
        "stt": stt,                       # None -> browser recognition
        # "browser" -> also type interim words from the browser while the
        # listener speaks (only meaningful when recognition is server-side)
        "caption": "browser" if (stt and LIVE_CAPTION == "browser") else None,
        "tts": tts,                       # None -> browser speech synthesis
        "voice": POLLY_VOICE if tts else None,
        "engine": POLLY_ENGINE if tts else None,
    }
    # Say why, so the simulator can tell the user what to set rather
    # than silently being worse than it could be.
    if not stt:
        if STT_PROVIDER == "off":
            out["stt_hint"] = "speech-to-text disabled"
        elif not aws:
            out["stt_hint"] = "set AWS credentials (Bedrock) for better recognition than the browser"
        else:
            out["stt_hint"] = "no speech-to-text provider available"
    if not tts:
        out["tts_hint"] = ("install boto3" if not HAVE_BOTO3
                           else "no AWS credentials in the environment (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)")
    return out


def warm():
    """Open the connections the first answer needs, before anyone asks.

    The first Polly call took 1.5 s against 0.5 s afterwards (a cold client and
    TLS handshake), and the first answer is the one a person is waiting for.
    Never raises; failing to warm costs nothing but that first-call delay.
    """
    try:
        if _have_aws_credentials():
            synthesize("Ready.")
            from .language import bedrock
            if bedrock.available():
                bedrock.client()
    except Exception as e:                                     # noqa: BLE001
        LOG.debug("warm-up skipped: %s", e)


# ------------------------------------------------------------ speech out
# Polly's GENERATIVE voices are its most natural: they vary pace and stress the way a person does, where the
# neural ones read every sentence alike. They cannot return word timings, which the page needs to highlight
# each word as it is spoken, so the timings come from the neural voice for the same sentence and are fitted to
# the generative audio's exact length. The whole answer is made in one piece so the voice keeps its pace and
# stress from one sentence to the next; only an answer too long for one call is cut, at a sentence end.
_ABBREVIATIONS = {"st", "mr", "mrs", "ms", "dr", "vs", "v", "fc", "no", "jr", "sr", "u", "w"}
CHUNK_CHARS = 150          # Polly takes 3000 billed characters a call; an answer is nowhere near that
_MP3_KBPS = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
             2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
_MP3_HZ = {1: [44100, 48000, 32000], 2: [22050, 24000, 16000], 3: [11025, 12000, 8000]}


def _id3_size(b):
    """Bytes taken by an ID3v2 tag at the start of an MP3 (0 if there is none)."""
    if b[:3] == b"ID3" and len(b) > 10:
        return 10 + ((b[6] & 0x7F) << 21 | (b[7] & 0x7F) << 14 | (b[8] & 0x7F) << 7 | (b[9] & 0x7F))
    return 0


def mp3_seconds(b):
    """The exact length of an MP3 in seconds, from its frame headers (Polly's are constant bitrate)."""
    i, total, n = _id3_size(b), 0.0, len(b)
    while i + 4 <= n:
        if b[i] == 0xFF and (b[i + 1] & 0xE0) == 0xE0:
            version = {3: 1, 2: 2, 0: 3}.get((b[i + 1] >> 3) & 3)         # MPEG 1, 2 or 2.5
            layer3 = ((b[i + 1] >> 1) & 3) == 1
            rate, hz_i, pad = (b[i + 2] >> 4) & 15, (b[i + 2] >> 2) & 3, (b[i + 2] >> 1) & 1
            if version and layer3 and 0 < rate < 15 and hz_i < 3:
                kbps, hz = _MP3_KBPS[1 if version == 1 else 2][rate], _MP3_HZ[version][hz_i]
                total += (1152 if version == 1 else 576) / float(hz)
                i += (144 if version == 1 else 72) * kbps * 1000 // hz + pad
                continue
        i += 1
    return total


def speakable(token):
    """One written token as it should be said. One for one, so word positions never shift."""
    m = re.fullmatch(r"Alexa\+([,.;:!?]*)", token)
    if m:                                                   # "Alexa+" is said "Alexa plus"
        return "Alexa-plus%s" % m.group(1)
    m = re.fullmatch(r"([Uu])(\d{2})([,.;:!?]*)", token)
    if m:                                                   # "U21" is "under twenty-one", not "you twenty-one"
        return "under-%s%s" % (m.group(2), m.group(3))
    return token


def _sentence_ranges(text, tokens):
    """Token index ranges, one per sentence: a full stop, ! or ? ends one when a capital follows,
    except after an abbreviation or an initial ("St. Mirren", "A. Saka")."""
    ranges, start = [], 0
    for i, (a, b) in enumerate(tokens):
        word = text[a:b]
        if i + 1 < len(tokens) and word[-1:] in ".!?":
            stem = word.rstrip(".!?").lower()
            nxt = text[tokens[i + 1][0]:tokens[i + 1][0] + 1]
            if nxt.isupper() or nxt.isdigit():
                if word[-1] != "." or (stem not in _ABBREVIATIONS and len(stem) > 1):
                    ranges.append((start, i + 1))
                    start = i + 1
    ranges.append((start, len(tokens)))
    return [r for r in ranges if r[1] > r[0]]


def _chunk_ranges(ranges, text, tokens, limit=CHUNK_CHARS):
    """Sentence ranges joined into stretches of at most `limit` characters.

    A voice reads a whole answer with one continuous pace and pitch, where sentences made one at a
    time each start afresh and the joins sound like a list. So an answer is made in one piece, and
    only one too long for that is cut, at a sentence end.
    """
    chunks = []
    for lo, hi in ranges:
        size = tokens[hi - 1][1] - tokens[lo][0]
        if chunks and (tokens[hi - 1][1] - tokens[chunks[-1][0]][0]) <= limit and size <= limit:
            chunks[-1] = (chunks[-1][0], hi)
        else:
            chunks.append((lo, hi))
    return chunks


def _marks_fitted(raw_marks, n_tokens, duration_ms):
    """Start time in ms for each of `n_tokens` words. Polly's own word marks when they line up one for
    one with the words, scaled to the audio's real length; otherwise the words spread evenly."""
    if n_tokens and len(raw_marks) == n_tokens:
        last = raw_marks[-1]["time"] + max(250, 60 * len(raw_marks[-1].get("value", "")))
        scale = max(0.5, min(2.0, (duration_ms - 120.0) / float(last))) if last else 1.0
        return [m["time"] * scale for m in raw_marks]
    step = duration_ms / float(max(1, n_tokens))
    return [i * step for i in range(n_tokens)]


def _one_sentence(client, sentence):
    """(mp3 bytes, word marks, engine used) for one sentence. A voice or region without the generative
    engine falls back to neural for that sentence, with the neural voice's own exact timings."""
    def audio(engine):
        return client.synthesize_speech(Text=sentence, OutputFormat="mp3", VoiceId=POLLY_VOICE,
                                        Engine=engine)["AudioStream"].read()

    def marks():
        raw = client.synthesize_speech(Text=sentence, OutputFormat="json", SpeechMarkTypes=["word"],
                                       VoiceId=POLLY_VOICE, Engine="neural")["AudioStream"].read()
        # Polly returns speech marks as newline-delimited JSON, one object per mark - not an array.
        return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_marks = pool.submit(marks)
        if POLLY_ENGINE == "generative":
            try:
                mp3 = audio("generative")
                return mp3, f_marks.result(), "generative"
            except Exception as e:                                  # noqa: BLE001
                LOG.warning("polly generative voice unavailable (%s); using neural", e)
        return audio("neural"), f_marks.result(), "neural"


def synthesize(text):
    """Audio plus word timings.

    Returns {"audio": base64 mp3, "marks": [{"time": ms, "start": char, "end": char, "value": word}],
    "voice": ..., "engine": ...} or None to fall back to the browser's voice. One mark per word of the
    text as written, positioned in the text as written, so the page can highlight each word as it is said.
    """
    if not text or not text.strip():
        return None
    try:
        c = _polly_client()
        if not c:
            return None
        tokens = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        ranges = _chunk_ranges(_sentence_ranges(text, tokens), text, tokens)
        spoken = [" ".join(speakable(text[a:b]) for a, b in tokens[lo:hi]) for lo, hi in ranges]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(spoken))) as pool:
            made = list(pool.map(lambda s: _one_sentence(c, s), spoken))

        audio, marks, offset, engines = [], [], 0.0, set()
        for (lo, hi), (mp3, raw_marks, engine) in zip(ranges, made):
            engines.add(engine)
            body = mp3[_id3_size(mp3):]                             # one stream: no tags between sentences
            duration = mp3_seconds(body) * 1000.0
            for (a, b), t in zip(tokens[lo:hi], _marks_fitted(raw_marks, hi - lo, duration)):
                marks.append({"time": int(offset + t), "start": a, "end": b, "value": text[a:b]})
            audio.append(body)
            offset += duration
        return {"audio": base64.b64encode(b"".join(audio)).decode("ascii"),
                "format": "mp3",
                "marks": marks,
                "voice": POLLY_VOICE,
                "engine": "generative" if engines == {"generative"} else "neural" if engines == {"neural"}
                else "mixed"}
    except Exception as e:                                     # noqa: BLE001
        LOG.warning("polly unavailable, browser speech will be used: %s", e)
        return None


# ------------------------------------------------------------- speech in
# --- is there speech in this clip at all? ---------------------------------
# Keystrokes, a mug set down, a door: each is a burst of a few milliseconds that
# an energy gate takes for speech. Speech is different in one simple way: it is
# *sustained*. Words are tens of milliseconds to hundreds of milliseconds of
# continuous sound; a key click is under 30 ms and a thump under 100. So count
# only stretches of loud 20 ms frames that last, and require enough of them.
# A recogniser left to itself turns a clip of clicks into "Thank you.", and every
# clip that reaches a provider costs a request, so this runs first.
GATE_FRAME_MS = 20
GATE_MIN_RUN = 4            # 80 ms of continuous sound before it counts as voiced
GATE_MIN_VOICED_MS = 160    # "no" and "two" are about this long; a thump is not


def voiced_ms(pcm_bytes):
    """Milliseconds of sustained sound in 16 kHz mono 16-bit PCM."""
    import array
    n = len(pcm_bytes) // 2
    if n < SAMPLE_RATE // 10:
        return 0
    samples = array.array("h")
    samples.frombytes(pcm_bytes[:n * 2])
    if samples.itemsize != 2:                                  # pragma: no cover
        return 0
    size = SAMPLE_RATE * GATE_FRAME_MS // 1000
    rms = []
    for i in range(0, n - size + 1, size):
        frame = samples[i:i + size]
        rms.append((sum(x * x for x in frame) / float(size)) ** 0.5)
    if not rms:
        return 0
    # The room's own level: the quiet fifth of the clip. Loud means louder
    # than that by a margin, so a noisy room does not count as speech.
    quiet = sorted(rms)[len(rms) // 5]
    threshold = max(300.0, 3.0 * quiet)
    total = run = 0
    for r in rms + [0.0]:
        if r > threshold:
            run += 1
        else:
            if run >= GATE_MIN_RUN:
                total += run
            run = 0
    return total * GATE_FRAME_MS


_NON_SPEECH = re.compile(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|<[^>]*>|\*[^*]*\*|[\u266a\u266b]+")


def only_words(text):
    """The words in a transcript, without descriptions of noise.

    Recognisers write non-speech in brackets ("[SOUND]", "[Music]", "[inaudible]", "(applause)", "*cough*"). That
    describes a sound; nobody said it, and it must never reach the screen or the agent. "" when no words remain.
    """
    text = " ".join(_NON_SPEECH.sub(" ", text or "").split())
    return text if re.search(r"[A-Za-z0-9\u00C0-\u024F]", text) else ""


def transcribe(audio_bytes, mime="audio/pcm", hint=""):
    """Audio in, text out. Returns {"text": ..., "provider": ...} or None.

    The browser sends raw 16 kHz mono PCM, which sidesteps MediaRecorder's
    container differences between browsers entirely (WebM in Chrome, MP4 in
    Safari). Voxtral takes it wrapped as WAV; Nova Sonic streams it as is. `hint` is vocabulary for the
    recogniser (see `vocabulary_hint`).
    """
    if voiced_ms(audio_bytes) < GATE_MIN_VOICED_MS:
        # Clicks, a thump, or a room: nothing to transcribe, and nothing worth
        # a request. An empty text is an answer ("heard nothing"), not a failure.
        LOG.info("no sustained speech in this clip (%d bytes); not sent to a provider",
                 len(audio_bytes))
        return {"text": "", "provider": "gate"}
    for which in stt_order():
        if which == "voxtral":
            out = _transcribe_voxtral(audio_bytes, hint)
        else:
            out = _transcribe_sonic(audio_bytes, hint)
        if out is not None:
            out = dict(out, text=only_words(out.get("text")))
            if out.get("text") and echoes_hint(out["text"], hint):
                LOG.info("transcript %r is the recogniser echoing its own vocabulary hint "
                         "(noise, not speech); dropped", out["text"])
                out = dict(out, text="")
            return out                     # heard something, or heard nothing: done
        LOG.info("%s gave no result for this clip; trying the next provider", which)
    return None


# Everything a listener says to Sideline is about the same few things; telling
# the recogniser so is the cheapest accuracy there is.
_BASE_HINT = ("Questions about a live football or basketball match. "
              "What's the score? Who's playing? What did I miss? "
              "Who is refereeing? Kick-off, half time, VAR, penalty, substitution, "
              "line-up, head to head.")


def vocabulary_hint(ctx, listener_id, max_names=24):
    """Teams and players from the match this listener follows.

    The vocabulary biases the recogniser towards these spellings, which is the
    difference between "Ødegaard" and "oh the guard". Names come from our own
    event log and stored fixture, so this costs no feed requests.
    """
    from . import resolve
    # What the listener was just offered goes first: their next words are most
    # likely one of those, and the start of a prompt weighs most.
    offered = resolve.BOOK.labels(listener_id)
    names = resolve.match_names(ctx, listener_id, limit=max_names)
    try:
        # Then the teams on today, so "Arsenal" is not heard as "asana" by a listener who
        # has not followed anything yet. Costs no request: the date list is already cached.
        names += [n for n in resolve.teams_today_ranked(ctx) if n not in names]
    except Exception:                                      # noqa: BLE001  a hint is a courtesy
        pass
    # A recogniser spells what it hears: give it the plain-letter form of an accented name
    # too ("Sønderjyske" and "Sonderjyske", "København" and "Kobenhavn").
    names = names[:40]
    names += [f for f in (resolve._fold(n) for n in names) if f and f not in {n.lower() for n in names}][:8]
    hint = _BASE_HINT
    if offered:
        hint = "The listener is choosing between: %s. %s" % (", ".join(offered), hint)
    return (hint + " " + ", ".join(names)).strip()


def echoes_hint(text, hint):
    """Is this transcript only the recogniser reading its own vocabulary back?

    A recogniser, given a vocabulary and a clip of noise, tends to print the vocabulary: a room
    of background sound became "Hartlepool, Newcastle U21", team names nobody said.
    A transcript of two or more words made up only of names from the hint, with none
    of the question words, is that echo. Not applied while the listener has been offered a choice,
    because then a bare name is exactly the right answer.
    """
    if not hint or hint.startswith("The listener is choosing between"):
        return False
    words = re.findall(r"[a-z0-9']+", text.lower())
    if len(words) < 2:
        return False            # one name is a plausible answer ("Arsenal", to "which team?"); noise prints several
    tail = hint[len(_BASE_HINT):].lower() if hint.startswith(_BASE_HINT) else hint.lower()
    base = set(re.findall(r"[a-z0-9']+", _BASE_HINT.lower()))
    names = set(re.findall(r"[a-z0-9']+", tail)) - base
    return all(w in names for w in words)


def _wav(pcm_bytes):
    """Raw 16 kHz mono PCM as a WAV file."""
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm_bytes)
    return buf.getvalue()


def _sonic_credentials():
    """Resolved through boto3, so profiles, containers and instance roles work,
    not just environment variables. Called per request: temporary credentials
    expire."""
    c = boto3.Session().get_credentials()
    if c is None:
        return {}
    f = c.get_frozen_credentials()
    out = {"aws_access_key_id": f.access_key, "aws_secret_access_key": f.secret_key}
    if f.token:
        out["aws_session_token"] = f.token
    return out


async def _sonic_hear(pcm_bytes, hint=""):
    """Stream one clip to Nova Sonic and return what it heard the user say.

    Sonic is a conversation model: it will also try to answer. We tell it to
    say one word and stop reading at its first reply, so the cost of each
    transcript is the audio in plus a token or two out. It decides the speaker
    has finished by hearing silence, so 2 s of silence follows the clip.
    """
    import base64
    import uuid
    cfg = await AsyncBedrockRuntimeConfig.resolve(
        endpoint_uri="https://bedrock-runtime.%s.amazonaws.com" % REGION,
        region=REGION, transport=AWSCRTHTTPClient(), **_sonic_credentials())
    client = AsyncBedrockRuntimeClient(config=cfg)
    stream = await client.invoke_model_with_bidirectional_stream(
        InvokeModelWithBidirectionalStreamOperationInput(model_id=SONIC_MODEL))
    pn, sc, uc = ("p" + uuid.uuid4().hex[:6], "s" + uuid.uuid4().hex[:6],
                  "u" + uuid.uuid4().hex[:6])

    async def send(ev):
        await stream.input_stream.send(InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=json.dumps({"event": ev}).encode())))

    system = ("You are the ears of a live sports companion. Whatever you hear, reply "
              "with the single word OK. Never answer questions.")
    if hint:
        system += " Names you may hear: %s" % hint[:600]
    await send({"sessionStart": {"inferenceConfiguration": {
        "maxTokens": 16, "topP": 0.9, "temperature": 0.0}}})
    await send({"promptStart": {"promptName": pn,
        "textOutputConfiguration": {"mediaType": "text/plain"},
        "audioOutputConfiguration": {"mediaType": "audio/lpcm", "sampleRateHertz": 24000,
            "sampleSizeBits": 16, "channelCount": 1, "voiceId": "matthew",
            "encoding": "base64", "audioType": "SPEECH"}}})
    await send({"contentStart": {"promptName": pn, "contentName": sc, "type": "TEXT",
        "interactive": False, "role": "SYSTEM",
        "textInputConfiguration": {"mediaType": "text/plain"}}})
    await send({"textInput": {"promptName": pn, "contentName": sc, "content": system}})
    await send({"contentEnd": {"promptName": pn, "contentName": sc}})
    await send({"contentStart": {"promptName": pn, "contentName": uc, "type": "AUDIO",
        "interactive": True, "role": "USER", "audioInputConfiguration": {
            "mediaType": "audio/lpcm", "sampleRateHertz": SAMPLE_RATE,
            "sampleSizeBits": 16, "channelCount": 1, "audioType": "SPEECH",
            "encoding": "base64"}}})

    heard = []

    async def reader():
        output = await stream.await_output()
        while True:
            r = await output[1].receive()
            if r is None:
                return
            if not r.value or not r.value.bytes_:
                continue
            ev = json.loads(r.value.bytes_.decode("utf-8"))["event"]
            if "textOutput" in ev:
                t = ev["textOutput"]
                if t.get("role") == "USER":
                    heard.append(t["content"])
                else:
                    return                  # its first reply: the user turn is done

    task = asyncio.ensure_future(reader())
    padded = pcm_bytes + b"\0" * (SAMPLE_RATE * 2 * 2)
    try:
        for i in range(0, len(padded), 1024):
            await send({"audioInput": {"promptName": pn, "contentName": uc,
                "content": base64.b64encode(padded[i:i + 1024]).decode()}})
            await asyncio.sleep(0.005)
        await asyncio.wait_for(task, timeout=12)
    finally:
        task.cancel()

        async def goodbye():
            await send({"contentEnd": {"promptName": pn, "contentName": uc}})
            await send({"promptEnd": {"promptName": pn}})
            await send({"sessionEnd": {}})
        # Politeness only. Bounded, because a wedged stream must never turn a
        # timeout into a hang: the caller's wait_for waits for this to finish.
        try:
            await asyncio.wait_for(goodbye(), timeout=2)
        except Exception:                                      # noqa: BLE001
            pass
    return " ".join(heard).strip()


def _transcribe_sonic(pcm_bytes, hint=""):
    """Nova Sonic as the ears. Returns {"text", "provider"} or None.

    Runs the async SDK in its own loop inside the request thread. A permission or model-access error takes it out of
    rotation (it will not fix itself); a timeout or blip falls back for this
    clip only.
    """
    if len(pcm_bytes) < SAMPLE_RATE * 2 // 5:               # under 0.4 s
        return None
    try:
        loop = asyncio.new_event_loop()
        try:
            text = loop.run_until_complete(
                asyncio.wait_for(_sonic_hear(pcm_bytes, hint), timeout=20))
        finally:
            loop.close()
    except Exception as e:                                     # noqa: BLE001
        msg = "%s %s" % (type(e).__name__, e)
        if any(w in msg for w in ("AccessDenied", "UnrecognizedClient", "ValidationException",
                                  "ResourceNotFound", "SubscriptionRequired")):
            _DISABLED.add("sonic")
            LOG.warning("nova sonic unavailable, disabled for this run: %s", msg[:200])
        else:
            LOG.warning("nova sonic transcription failed: %s", msg[:200])
        return None
    return {"text": text, "provider": "sonic"}


_voxtral = None


def _transcribe_voxtral(pcm_bytes, hint="", model=None):   # `hint` is accepted and not sent: see below
    """Mistral's Voxtral on Bedrock as the ears: audio in, the words out, all inside the AWS account.

    Through Converse with an audio block. Two things learned the hard way: the audio goes BEFORE the
    instruction (the other way round it answers the question it hears, or invents one), and a
    system message is refused alongside audio. A model that talks about the audio instead of writing
    it down is caught by length: more words than the clip could hold is not a transcript.
    """
    global _voxtral
    if len(pcm_bytes) < SAMPLE_RATE * 2 // 5:               # under 0.4 s
        return None
    # No vocabulary goes in the prompt, on purpose. Given a list of team names, this chat model printed the list for
    # "The first one." and answered questions from it ("The score is Arsenal 1..."): measured on twelve clips, 0
    # failures without the names and up to 2 with them. Misheard names are repaired afterwards (resolve.py).
    instruction = ("Transcribe the speech in this audio word for word. Output only the words spoken. "
                   "Do not answer or comment on it.")
    try:
        if _voxtral is None:
            _voxtral = boto3.client("bedrock-runtime", region_name=REGION,
                                    config=BotoConfig(read_timeout=12, connect_timeout=3, retries={"max_attempts": 1}))
        resp = _voxtral.converse(
            modelId=model or VOXTRAL_MODEL,
            messages=[{"role": "user", "content": [{"audio": {"format": "wav", "source": {"bytes": _wav(pcm_bytes)}}},
                                                   {"text": instruction}]}],
            inferenceConfig={"maxTokens": 80, "temperature": 0})
        text = " ".join(b.get("text", "") for b in resp["output"]["message"]["content"]).strip().strip('"').strip()
        from . import audit
        usage = resp.get("usage") or {}
        audit.record("tokens", source="speech", model=model or VOXTRAL_MODEL,
                     input=int(usage.get("inputTokens") or 0), output=int(usage.get("outputTokens") or 0))
    except Exception as e:                                     # noqa: BLE001
        msg = "%s %s" % (type(e).__name__, e)
        if any(w in msg for w in ("AccessDenied", "UnrecognizedClient", "ResourceNotFound", "not authorized",
                                  "Authentication failed")):
            _DISABLED.add("voxtral")
            LOG.warning("voxtral unavailable, disabled for this run: %s", msg[:200])
        else:
            LOG.warning("voxtral transcription failed: %s", msg[:200])
        return None
    seconds = len(pcm_bytes) / float(SAMPLE_RATE * 2)
    if len(text.split()) > 4 * seconds + 4:                  # talking about the clip, not writing it down
        LOG.warning("voxtral returned more words than the clip holds; dropped")
        return None
    return {"text": text, "provider": "voxtral"}
