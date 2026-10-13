"""Speech in and speech out, for the simulator.

Sideline's product surface is MCP: a client such as Alexa+ would do the
listening and the talking, and the MCP server never touches audio. The simulator
is our own client, so it has to BE the voice. The browser captures audio and
posts it here; this module calls a provider; keys never reach the browser.

SPEECH OUT: Amazon Polly (neural). It returns, alongside the audio, speech marks:
every word with its offset in milliseconds, which is what lets the page highlight
each word at exactly the moment the voice reaches it. The two calls (audio, marks)
run in parallel. Without AWS credentials the page uses the browser's own voice.

SPEECH IN: the providers below, best first, with a per-clip fallback. Measured
head to head (scripts/compare_stt.py, 48 clips, clean and noisy; docs/SPEECH.md):
Groq's hosted Whisper beat Nova Sonic on accuracy (3.7% against 8.5% word error
in noise) and speed (1.1 s against 4.2 s). Sonic stays inside the AWS account.

    1. Groq Whisper   only with GROQ_API_KEY: a third party, so audio leaves AWS
    2. Nova Sonic     Bedrock, needs the streaming SDK (Python 3.12+)
    3. the browser's own recognition, the least accurate, used when neither works

A clip one provider fails goes to the next, so a rate limit never leaves a
listener unheard. Naming a provider (SIDELINE_STT=sonic) uses it alone.

/voice/stt and /voice/tts are simulator support, not part of the MCP surface.
Nothing in sideline/tools/ knows they exist.
"""

import asyncio
import base64
import json
import logging
import os
import urllib.request

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
POLLY_ENGINE = "neural"

# --- speech in
STT_PROVIDER = os.environ.get("SIDELINE_STT", "auto")          # auto|groq|sonic|off
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "whisper-large-v3-turbo"
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
SONIC_MODEL = "amazon.nova-2-sonic-v1:0"
STT_LANGUAGE = "en"                    # Whisper takes ISO 639-1, not a locale
SAMPLE_RATE = 16000

# Words typed on screen while the listener is still speaking. Server-side
# recognition (Groq, Nova Sonic) only returns text once the clip ends, so for
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
                              config=BotoConfig(read_timeout=6, connect_timeout=2,
                                                retries={"max_attempts": 1}))
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

    A named provider (SIDELINE_STT=groq) is used alone, never silently
    swapped for another, so a choice about where audio goes is respected.
    """
    aws = _have_aws_credentials()
    ok = {"groq": bool(GROQ_KEY), "sonic": aws and HAVE_SONIC}
    if STT_PROVIDER == "off":
        return []
    names = ["groq", "sonic"] if STT_PROVIDER == "auto" else [STT_PROVIDER]
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
        elif aws and not HAVE_SONIC and not GROQ_KEY:
            out["stt_hint"] = ("pip3 install aws-sdk-bedrock-runtime awscrt (Python 3.12+) "
                               "for Nova Sonic, or set GROQ_API_KEY")
        elif not aws and not GROQ_KEY:
            out["stt_hint"] = ("set AWS credentials (Nova Sonic) or GROQ_API_KEY "
                               "for better recognition than the browser")
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
def synthesize(text):
    """Audio plus word timings.

    Returns {"audio": base64 mp3, "marks": [{"time": ms, "start": char,
    "end": char, "value": word}], "voice": ...} or None to fall back.

    The marks are the point. Without them the simulator has to guess
    where the voice is; with them the highlight is exact.
    """
    c = _polly_client()
    if not c or not text:
        return None
    try:
        # Two independent calls (the audio, and the word timings). Run side
        # by side: one after the other they were 1.8 s of a listener's wait.
        from concurrent.futures import ThreadPoolExecutor

        def audio_call():
            return c.synthesize_speech(
                Text=text, OutputFormat="mp3", VoiceId=POLLY_VOICE,
                Engine=POLLY_ENGINE)["AudioStream"].read()

        def marks_call():
            return c.synthesize_speech(
                Text=text, OutputFormat="json", SpeechMarkTypes=["word"],
                VoiceId=POLLY_VOICE, Engine=POLLY_ENGINE)["AudioStream"].read()

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_mp3, f_marks = pool.submit(audio_call), pool.submit(marks_call)
            mp3, marks_raw = f_mp3.result(), f_marks.result()
        # Polly returns speech marks as newline-delimited JSON, one
        # object per mark - not a JSON array.
        marks = []
        for line in marks_raw.decode("utf-8").splitlines():
            line = line.strip()
            if line:
                marks.append(json.loads(line))

        return {"audio": base64.b64encode(mp3).decode("ascii"),
                "format": "mp3",
                "marks": marks,
                "voice": POLLY_VOICE,
                "engine": POLLY_ENGINE}
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
# Whisper left to itself turns a clip of clicks into "Thank you.", and every
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


def transcribe(audio_bytes, mime="audio/pcm", hint=""):
    """Audio in, text out. Returns {"text": ..., "provider": ...} or None.

    The browser sends raw 16 kHz mono PCM, which sidesteps MediaRecorder's
    container differences between browsers entirely (WebM in Chrome, MP4 in
    Safari). Nova Sonic streams it as is; Groq takes it wrapped as WAV. `hint` is vocabulary for the recogniser (see
    `vocabulary_hint`); only Whisper uses it.
    """
    if voiced_ms(audio_bytes) < GATE_MIN_VOICED_MS:
        # Clicks, a thump, or a room: nothing to transcribe, and nothing worth
        # a request. An empty text is an answer ("heard nothing"), not a failure.
        LOG.info("no sustained speech in this clip (%d bytes); not sent to a provider",
                 len(audio_bytes))
        return {"text": "", "provider": "gate"}
    for which in stt_order():
        if which == "groq":
            out = _transcribe_groq(audio_bytes, hint)
        else:
            out = _transcribe_sonic(audio_bytes, hint)
        if out is not None:
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

    Whisper's `prompt` biases it towards these spellings, which is the
    difference between "Ødegaard" and "oh the guard". Names come from our own
    event log and stored fixture, so this costs no feed requests.
    """
    from . import resolve
    # What the listener was just offered goes first: their next words are most
    # likely one of those, and Whisper weighs the start of its prompt most.
    offered = resolve.BOOK.labels(listener_id)
    names = resolve.match_names(ctx, listener_id, limit=max_names)
    hint = _BASE_HINT
    if offered:
        hint = "The listener is choosing between: %s. %s" % (", ".join(offered), hint)
    return (hint + " " + ", ".join(names)).strip()


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


def _multipart(fields, file_field, filename, content_type, data):
    import uuid
    boundary = "sideline" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, k, v)).encode("utf-8"))
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                  "Content-Type: %s\r\n\r\n" % (boundary, file_field, filename,
                                                  content_type)).encode("utf-8"))
    parts.append(data)
    parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


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


def _transcribe_groq(pcm_bytes, hint=""):
    """Groq-hosted Whisper. Standard library only, like the rest of the server.

    temperature 0 and a language: Whisper left to itself will guess the
    language from two seconds of audio and sometimes translate silence into a
    sentence. A clip too short to hold a word is dropped before it is sent.
    """
    import urllib.error
    import urllib.request

    from . import tls
    if len(pcm_bytes) < SAMPLE_RATE * 2 // 5:               # under 0.4 s
        return None
    fields = {"model": GROQ_MODEL, "language": STT_LANGUAGE, "temperature": "0",
              "response_format": "json"}
    if hint:
        fields["prompt"] = hint[:800]
    body, ctype = _multipart(fields, "file", "clip.wav", "audio/wav", _wav(pcm_bytes))
    req = urllib.request.Request(
        GROQ_URL, data=body, method="POST",
        headers={"Authorization": "Bearer " + GROQ_KEY, "Content-Type": ctype,
                 # Groq sits behind Cloudflare, which rejects the default
                 # Python-urllib agent.
                 "User-Agent": "sideline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=tls.context()) as r:
            text = (json.loads(r.read().decode("utf-8")).get("text") or "").strip()
    except urllib.error.HTTPError as e:
        LOG.warning("groq transcription failed: HTTP %s", e.code)
        if e.code in (401, 403):
            _DISABLED.add("groq")          # a bad key will not fix itself
        return None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        LOG.warning("groq transcription failed: %s", e)
        return None
    return {"text": text, "provider": "groq"}
