"""Speech in and speech out, for the simulator.

Sideline's product surface is MCP: a client such as Alexa+ would do the
listening and the talking, and the MCP server never touches audio. The simulator
is our own client, so it has to BE the voice. The browser captures audio and
posts it here; this module calls a provider; keys never reach the browser.

WHERE AUDIO AND TEXT GO. By default (SIDELINE_STT=auto, SIDELINE_TTS=auto, SIDELINE_LIVE_CAPTION=off) only AWS
services are used: Bedrock hears the listener, Polly speaks, so the listener's audio stays in the AWS account.
Groq (speech in), Cartesia and ElevenLabs (speech out) are third-party services outside AWS: they are used only
when named (SIDELINE_STT=groq, SIDELINE_TTS=cartesia or elevenlabs), never because a key happens to be set.
Without AWS credentials the page falls back to the browser's own engines, which may send audio to the browser
vendor; the page says so.

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
(SIDELINE_STT=sonic, or SIDELINE_STT=groq for Whisper on Groq, outside AWS) uses it alone.

/voice/stt and /voice/tts are simulator support, not part of the MCP surface.
Nothing in sideline/tools/ knows they exist.
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
import urllib.error
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

# --- speech out: AWS Polly by default; Cartesia Sonic or ElevenLabs Flash (third parties, outside AWS) only
# when named; browser (<15ms) when there are no AWS credentials.
TTS_PROVIDER = os.environ.get("SIDELINE_TTS", "auto").strip().lower()  # auto|browser|cartesia|elevenlabs|polly|off
ELEVENLABS_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
POLLY_VOICE = os.environ.get("SIDELINE_POLLY_VOICE", "Amy")
POLLY_ENGINE = os.environ.get("SIDELINE_POLLY_ENGINE", "generative").strip().lower()   # generative|neural


def _cartesia_key():
    return os.environ.get("CARTESIA_API_KEY", "")


def _have_cartesia_key():
    return bool(_cartesia_key())


def _elevenlabs_key():
    return os.environ.get("ELEVENLABS_API_KEY", "")


def _have_elevenlabs_key():
    return bool(_elevenlabs_key())


def active_tts_provider():
    """Which TTS provider should be active.

    Options:
      - 'browser': ultra-low latency (<15ms), 0 server overhead, native word boundaries.
      - 'cartesia': Cartesia Sonic SSE (40-80ms) with word timestamps. Outside AWS: only when named.
      - 'elevenlabs': ElevenLabs Flash v2.5 (~75ms) with character/word timestamps. Outside AWS: only when named.
      - 'polly': Amazon Polly generative/neural voice on AWS.
      - None / off: disabled.

    'auto' stays inside AWS: Polly when credentials resolve, else the browser's voice. A Cartesia or
    ElevenLabs key in the environment never sends the answer text to that company on its own.
    """
    if TTS_PROVIDER == "off":
        return None
    if TTS_PROVIDER == "browser":
        return "browser"
    if TTS_PROVIDER == "cartesia":
        return "cartesia" if _have_cartesia_key() else None
    if TTS_PROVIDER == "elevenlabs":
        return "elevenlabs" if _have_elevenlabs_key() else None
    if TTS_PROVIDER == "polly":
        return "polly" if _have_aws_credentials() else None

    # auto mode: AWS only
    if _have_aws_credentials():
        return "polly"
    return "browser"


STT_PROVIDER = os.environ.get("SIDELINE_STT", "auto")          # auto (Bedrock only)|groq|voxtral|sonic|off
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"
SONIC_MODEL = "amazon.nova-2-sonic-v1:0"
# Voxtral Small (24B), the model measured in docs/SPEECH.md (0.0% word error clean, 1.4% noisy, every name right). Mini (3B)
# was eliminated there and later shipped by mistake: it ANSWERS what it hears ("Who scored in the Lyon game?" came back as
# "I don't have real-time or up-to-date information"), which is where "I'm sorry, I can't understand that" questions came from.
VOXTRAL_MODEL = "mistral.voxtral-small-24b-2507"
SAMPLE_RATE = 16000


def _groq_key():
    return os.environ.get("GROQ_API_KEY", "")


def _have_groq_key():
    return bool(_groq_key())

# Words typed on screen while the listener is still speaking. Server-side
# recognition (Voxtral, Nova Sonic) only returns text once the clip ends, so for
# live typing the page also runs the browser's own recognition on the side,
# purely to show interim words, and replaces them with the server's more
# accurate transcript. The cost: that audio also reaches the browser vendor
# (Chrome and Edge send it to theirs). So it is OFF by default: the audio stays
# with the chosen provider, and nothing types until the clip ends.
# SIDELINE_LIVE_CAPTION=browser turns it on, knowingly.
LIVE_CAPTION = os.environ.get("SIDELINE_LIVE_CAPTION", "off").strip().lower()

# Providers that failed in a way retrying soon will not fix (a bad key, access
# denied). Taken out of rotation for a while, so every utterance does not pay a
# failing round trip before falling back; tried again after DISABLE_SECONDS, so
# rotated credentials or newly granted model access recover without a restart.
# name -> time.monotonic() at which it may be tried again.
DISABLE_SECONDS = 600
_DISABLED = {}


def _disable(name, why=""):
    _DISABLED[name] = time.monotonic() + DISABLE_SECONDS
    LOG.warning("%s unavailable, out of rotation for %d s: %s", name, DISABLE_SECONDS, str(why)[:200])


def _is_disabled(name):
    until = _DISABLED.get(name)
    if until is None:
        return False
    if time.monotonic() >= until:
        _DISABLED.pop(name, None)
        return False
    return True

_polly = None


def _polly_client():
    global _polly
    if _polly is None:
        if not HAVE_BOTO3:
            return None
        _polly = boto3.client("polly", region_name=REGION,
                              config=BotoConfig(read_timeout=12, connect_timeout=3,
                                                retries={"total_max_attempts": 2}))
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
    'auto' is Bedrock only (Voxtral, then Nova Sonic): audio stays in the AWS
    account. Groq is outside AWS and is used only when named.
    """
    groq = _have_groq_key()
    aws = _have_aws_credentials()
    ok = {"groq": groq, "voxtral": aws and HAVE_BOTO3, "sonic": aws and HAVE_SONIC}
    if STT_PROVIDER == "off":
        return []
    names = ["voxtral", "sonic"] if STT_PROVIDER == "auto" else [STT_PROVIDER]
    return [n for n in names if ok.get(n) and not _is_disabled(n)]


def capabilities():
    """What the simulator should use. Asked once, at page load.

    Honest about what will actually work. The browser decides from this
    whether to post audio here or fall back to its own engine, so a
    hopeful answer here becomes a broken prototype there.
    """
    aws = _have_aws_credentials()

    order = stt_order()
    stt = order[0] if order else None

    tts = active_tts_provider()
    voice_name = None
    engine_name = None
    if tts == "polly":
        voice_name = POLLY_VOICE
        engine_name = POLLY_ENGINE
    elif tts == "elevenlabs":
        voice_name = ELEVENLABS_VOICE
        engine_name = "flash_v2_5"
    elif tts == "cartesia":
        voice_name = "sonic"
        engine_name = "sonic-3.5"
    elif tts == "browser":
        voice_name = "browser"
        engine_name = "native"

    out = {
        "stt": stt,                       # None -> browser recognition
        # "browser" -> also type interim words from the browser while the
        # listener speaks (only meaningful when recognition is server-side)
        "caption": "browser" if (stt and LIVE_CAPTION == "browser") else None,
        "tts": tts,                       # None or "browser" -> browser speech synthesis
        "voice": voice_name,
        "engine": engine_name,
    }
    # Say why, so the simulator can tell the user what to set rather
    # than silently being worse than it could be.
    if not stt:
        if STT_PROVIDER == "off":
            out["stt_hint"] = "speech-to-text disabled"
        elif STT_PROVIDER == "groq" and not _have_groq_key():
            out["stt_hint"] = "set GROQ_API_KEY in .env for Groq Whisper"
        elif not aws:
            out["stt_hint"] = ("set AWS credentials (Bedrock) for speech recognition "
                               "(or SIDELINE_STT=groq with GROQ_API_KEY, outside AWS)")
        else:
            out["stt_hint"] = "no speech-to-text provider available"
    if not tts:
        out["tts_hint"] = "speech output disabled"
    elif tts == "browser":
        out["tts_hint"] = "using instant browser native speech synthesis (<15ms)"
    return out


def warm():
    """Open the connections the first answer needs, before anyone asks.

    The first Polly call took 1.5 s against 0.5 s afterwards (a cold client and
    TLS handshake), and the first answer is the one a person is waiting for.
    Never raises; failing to warm costs nothing but that first-call delay.
    """
    try:
        if _have_aws_credentials() and active_tts_provider() == "polly":
            synthesize("Ready.")
            from sideline.language import bedrock
            if bedrock.available():
                bedrock.client()
                # A first request pays for the connection and the TLS handshake: let that be the server's, not the
                # first listener's (about a second saved on the first question).
                try:
                    bedrock._converse("Reply with one word.", "ready", max_tokens=2)
                except Exception:                                  # noqa: BLE001
                    pass
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
    m = re.fullmatch(r"(\d{1,3})\+(\d{1,2})['\u2019]([,.;:!?]*)", token)
    if m:                                                   # "90+3'" is "ninety plus three", the minute
        return "%s-plus-%s%s" % (m.group(1), m.group(2), m.group(3))
    m = re.fullmatch(r"(\d{1,3})['\u2019]([,.;:!?]*)", token)
    if m:                                                   # "73'" is "the seventy-third minute", not "seventy-three feet"
        return "%s-minute%s" % (_ordinal(int(m.group(1))), m.group(2))
    m = re.fullmatch(r"(\d{1,3})[-\u2013](\d{1,3})([,.;:!?]*)", token)
    if m:                                                   # a score, "3-2": never "three minus two"
        return "%s-to-%s%s" % (m.group(1), m.group(2), m.group(3))
    m = re.fullmatch(r"Q([1-4])([,.;:!?]*)", token)
    if m:                                                   # a basketball or NFL quarter
        return "%s-quarter%s" % (_ORDINAL_WORDS[int(m.group(1))], m.group(2))
    m = re.fullmatch(r"P([1-3])([,.;:!?]*)", token)
    if m:                                                   # a hockey period
        return "%s-period%s" % (_ORDINAL_WORDS[int(m.group(1))], m.group(2))
    return token


_ORDINAL_WORDS = {1: "first", 2: "second", 3: "third", 4: "fourth"}


def _ordinal(n):
    """73 -> "73rd": a digit string a voice reads as an ordinal."""
    if 10 <= n % 100 <= 20:
        return "%dth" % n
    return "%d%s" % (n, {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


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

    def marks_or_none(f):
        # Word timings are a nicety for the highlight; the audio is the answer. Failing marks must not
        # throw the audio away: with none, the words are spread over the audio's real length (_marks_fitted).
        try:
            return f.result()
        except Exception as e:                                      # noqa: BLE001
            LOG.warning("polly speech marks unavailable (%s); word timings estimated", e)
            return []

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_marks = pool.submit(marks)
        if POLLY_ENGINE == "generative":
            mp3 = None
            try:
                mp3 = audio("generative")
            except Exception as e:                                  # noqa: BLE001
                LOG.warning("polly generative voice unavailable (%s); using neural", e)
            if mp3 is not None:
                return mp3, marks_or_none(f_marks), "generative"
        return audio("neural"), marks_or_none(f_marks), "neural"


def _synthesize_cartesia(text):
    """Cartesia Sonic via SSE streaming with add_timestamps=True (40-80ms)."""
    key = _cartesia_key()
    if not key or not text or not text.strip():
        return None
    url = "https://api.cartesia.ai/tts/sse"
    payload = json.dumps({
        "model_id": "sonic-3.5",
        "transcript": text,
        "voice": {"mode": "id", "id": "a0e99841-438c-4a64-b679-ae501e7d6091"},
        "output_format": {"container": "mp3", "sample_rate": 44100, "bit_rate": 128000},
        "language": "en",
        "add_timestamps": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "X-API-Key": key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json",
            "User-Agent": "Sideline/1.0",
        },
    )
    from sideline.tls import context
    try:
        audio_chunks = []
        raw_starts = []
        with urllib.request.urlopen(req, context=context(), timeout=5) as resp:
            for line in resp:
                line = line.strip()
                if not line.startswith(b"data: "):
                    continue
                evt_raw = line[6:]
                if evt_raw == b"[DONE]":
                    break
                try:
                    evt = json.loads(evt_raw.decode("utf-8"))
                    if evt.get("type") == "chunk" and evt.get("data"):
                        audio_chunks.append(base64.b64decode(evt["data"]))
                    elif evt.get("type") == "timestamps" and evt.get("word_timestamps"):
                        wt = evt["word_timestamps"]
                        raw_starts.extend(wt.get("start", []))
                except Exception:
                    pass
        if not audio_chunks:
            return None
        tokens = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\S+", text)]
        marks = []
        for i, (start, end, word) in enumerate(tokens):
            t_sec = raw_starts[i] if i < len(raw_starts) else (i * 0.3)
            marks.append({
                "time": int(t_sec * 1000),
                "start": start,
                "end": end,
                "value": word,
            })
        full_audio = b"".join(audio_chunks)
        return {
            "audio": base64.b64encode(full_audio).decode("ascii"),
            "format": "mp3",
            "marks": marks,
            "voice": "sonic",
            "engine": "sonic-3.5",
            "provider": "cartesia",
        }
    except Exception as e:
        LOG.warning("cartesia tts failed: %s", e)
        return None


def _synthesize_elevenlabs(text):
    """ElevenLabs Flash v2.5 with character timestamps mapped to words (~75ms)."""
    key = _elevenlabs_key()
    if not key or not text or not text.strip():
        return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}/with-timestamps"
    payload = json.dumps({
        "text": text,
        "model_id": "eleven_flash_v2_5",
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "User-Agent": "Sideline/1.0",
        },
    )
    from sideline.tls import context
    try:
        with urllib.request.urlopen(req, context=context(), timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            audio_b64 = data.get("audio_base64", "")
            alignment = data.get("alignment") or {}
            char_starts = alignment.get("character_start_times_seconds") or []
            tokens = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\S+", text)]
            marks = []
            for start, end, word in tokens:
                t_sec = char_starts[start] if start < len(char_starts) else 0.0
                marks.append({
                    "time": int(t_sec * 1000),
                    "start": start,
                    "end": end,
                    "value": word,
                })
            return {
                "audio": audio_b64,
                "format": "mp3",
                "marks": marks,
                "voice": ELEVENLABS_VOICE,
                "engine": "flash_v2_5",
                "provider": "elevenlabs",
            }
    except Exception as e:
        LOG.warning("elevenlabs tts failed: %s", e)
        return None


def _synthesize_polly(text):
    """Amazon Polly dual-call (generative audio + neural word marks)."""
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
                else "mixed",
                "provider": "polly"}
    except Exception as e:                                     # noqa: BLE001
        LOG.warning("polly unavailable, browser speech will be used: %s", e)
        return None


def synthesize(text):
    """Audio plus word timings.

    Returns {"audio": base64 mp3, "marks": [{"time": ms, "start": char, "end": char, "value": word}],
    "voice": ..., "engine": ...} or None to fall back to the browser's voice.
    """
    if not isinstance(text, str):
        LOG.warning("tts asked for a %s, not text; refused", type(text).__name__)
        return None
    if not text.strip():
        return None
    prov = active_tts_provider()
    if prov == "cartesia":
        res = _synthesize_cartesia(text)
        if res:
            return res
    elif prov == "elevenlabs":
        res = _synthesize_elevenlabs(text)
        if res:
            return res
    elif prov in ("browser", None):
        return None                  # the browser's own voice was chosen (or speech is off): no AWS call
    return _synthesize_polly(text)


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


_WHISPER_HALLUCINATIONS = {
    "thank you", "thank you.", "thank you very much.", "thanks for watching.",
    "thanks for watching", "bye.", "bye", "goodbye.", "goodbye",
    "subtitles by", "translated by", "amara.org", "you", "silence", "the", "."
}
# Whisper (Groq) writes one of those for a clip with almost no speech in it. Only then is it dropped: a
# listener who really says "Thank you" or "Goodbye" speaks for longer than this, and other recognisers
# (Voxtral, Nova Sonic) do not have the habit, so their "Thank you" is always kept.
WHISPER_HALLUCINATION_MAX_VOICED_MS = 400

# Recognisers that are given the vocabulary hint, and so can read it back on a clip of noise. Voxtral is not
# given it (see _transcribe_voxtral), so its transcript of team names is what was said.
_HINTED = ("groq", "sonic")


# Voxtral is a chat model given audio. On a clip it cannot make out it sometimes ANSWERS instead of transcribing: "I'm sorry,
# I can't understand that. Could you please repeat or clarify what you said?" reached the agent as a question four times in
# one day's log. An apology followed by "can't ..." is the assistant's sentence, not the listener's. (A listener who says
# "could you repeat that" is kept: only the apology-and-inability shape, or talk about "the audio", is dropped.)
_ASSISTANT_REPLY = re.compile(
    r"^\W*(?:i'?m sorry|i am sorry|sorry|i apologi[sz]e|unfortunately)\b.{0,60}?\b(?:can'?t|cannot|can not|unable to|not able to|"
    r"couldn'?t|could not|don'?t understand)\b.{0,40}?\b(?:understand|process|assist|help|hear|transcribe|make out|catch)\b"
    r"|\b(?:the|this|your) audio (?:content|clip|file|provided)\b|\bas an ai\b|\bi can'?t assist with that\b", re.I)


def assistant_reply(text):
    """Is this transcript the recogniser talking (an apology, a refusal), not words the listener said?"""
    return bool(text and _ASSISTANT_REPLY.search(text))


def repeated_phrase(text):
    """ "Bonjour. Bonjour. Bonjour.", "Yeah. Yeah. Yeah.", "Oh. Oh.": a recogniser on room noise repeats one short phrase.
    True when every sentence is the same and it is said three times or more, or twice when it is only a sound ("oh", "um").
    "No, no, no" is kept: it is how people say no. "Arsenal. Arsenal." is kept: a name said twice is a name."""
    parts = [p.strip() for p in re.split(r"[.!?,]+\s*", (text or "").lower().strip()) if p.strip()]
    if len(parts) < 2 or len(set(parts)) != 1 or parts[0] == "no":
        return False
    return len(parts) >= 3 or parts[0] in _SOUNDS


_SOUNDS = {"oh", "uh", "um", "ah", "hmm", "mm", "huh", "er", "erm"}


def transcribe(audio_bytes, mime="audio/pcm", hint=""):
    """Audio in, text out. Returns {"text": ..., "provider": ...} or None.

    The browser sends raw 16 kHz mono PCM, which sidesteps MediaRecorder's
    container differences between browsers entirely (WebM in Chrome, MP4 in
    Safari). Voxtral takes it wrapped as WAV; Nova Sonic streams it as is. `hint` is vocabulary for the
    recogniser (see `vocabulary_hint`).
    """
    voiced = voiced_ms(audio_bytes)
    if voiced < GATE_MIN_VOICED_MS:
        # Clicks, a thump, or a room: nothing to transcribe, and nothing worth
        # a request. An empty text is an answer ("heard nothing"), not a failure.
        LOG.info("no sustained speech in this clip (%d bytes); not sent to a provider",
                 len(audio_bytes))
        return {"text": "", "provider": "gate"}
    for which in stt_order():
        if which == "groq":
            out = _transcribe_groq(audio_bytes, hint)
        elif which == "voxtral":
            out = _transcribe_voxtral(audio_bytes, hint)
        else:
            out = _transcribe_sonic(audio_bytes, hint)
        if out is not None:
            clean_txt = only_words(out.get("text"))
            if (which == "groq" and voiced < WHISPER_HALLUCINATION_MAX_VOICED_MS
                    and clean_txt.lower().strip().rstrip(".!?") in _WHISPER_HALLUCINATIONS):
                LOG.info("transcript %r is a Whisper silence/noise hallucination (%d ms voiced); dropped",
                         clean_txt, voiced)
                clean_txt = ""
            if clean_txt and assistant_reply(clean_txt):
                LOG.info("transcript %r is the recogniser replying, not speech; dropped", clean_txt)
                clean_txt = ""
            elif clean_txt and repeated_phrase(clean_txt):
                LOG.info("transcript %r is one phrase repeated (a recogniser on noise); dropped", clean_txt)
                clean_txt = ""
            out = dict(out, text=clean_txt)
            if out.get("text") and which in _HINTED and echoes_hint(out["text"], hint):
                LOG.info("transcript %r is the recogniser echoing its own vocabulary hint "
                         "(noise, not speech); dropped", out["text"])
                out = dict(out, text="")
            return out                     # heard something, or heard nothing: done
        LOG.info("%s gave no result for this clip; trying the next provider", which)
    return None


# Everything a listener says to Sideline is about the same few things; telling
# the recogniser so is the cheapest accuracy there is.
_BASE_HINT = ("Questions about live sports, football, soccer, and basketball matches. "
              "What's the score? What matches are on today? Which match already finished? "
              "Previous matches, results, scores from today, who won, who is playing? "
              "What did I miss? Who is refereeing? Kick-off, full time, half time, VAR, "
              "penalty, substitution, line-up, head to head, schedule, Tierney.")


def vocabulary_hint(ctx, listener_id, max_names=24):
    """Teams and players from the match this listener follows.

    The vocabulary biases the recogniser towards these spellings, which is the
    difference between "Ødegaard" and "oh the guard". Names come from our own
    event log and stored fixture, so this costs no feed requests.
    """
    try:
        return _vocabulary_hint(ctx, listener_id, max_names)
    except Exception as e:                                 # noqa: BLE001  a hint is a courtesy, never a failure
        LOG.warning("vocabulary hint unavailable (%s); using the base hint", e)
        return _BASE_HINT


def _vocabulary_hint(ctx, listener_id, max_names):
    from sideline import resolve
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
    of background sound became "Hartlepool, Newcastle U21", team names nobody said. That echo is a
    LIST: two or more separated items, each made only of name words from the hint, with none of the
    question words. One name, however many words ("Real Madrid", "Manchester United"), is a plausible
    answer and is kept. Only meaningful for a recogniser that was given the hint (see _HINTED). Not
    applied while the listener has been offered a choice, because then a bare name is exactly the
    right answer.
    """
    if not hint or not text or hint.startswith("The listener is choosing between"):
        return False
    items = [i for i in re.split(r"[,;/]|\s-\s|\.\s", text.lower()) if re.search(r"[a-z0-9]", i)]
    if len(items) < 2:
        return False            # one name is a plausible answer ("Real Madrid", to "which team?"); noise prints a list
    tail = hint[len(_BASE_HINT):].lower() if hint.startswith(_BASE_HINT) else hint.lower()
    base = set(re.findall(r"[a-z0-9']+", _BASE_HINT.lower()))
    names = set(re.findall(r"[a-z0-9']+", tail)) - base
    return all(w in names for i in items for w in re.findall(r"[a-z0-9']+", i))


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


def _transcribe_groq(pcm_bytes, hint=""):
    """Whisper on Groq (whisper-large-v3-turbo). Fast, dedicated ASR (~200ms).

    Takes raw 16 kHz mono PCM wrapped in a 44-byte WAV header. Domain vocabulary
    and team/player names from sideline.resolve are passed via `prompt` to bias proper nouns.
    """
    import urllib.error
    import urllib.request
    from sideline import tls

    key = _groq_key()
    if not key or len(pcm_bytes) < SAMPLE_RATE * 2 // 5:      # under 0.2 s (16-bit samples: 2 bytes each)
        return None

    boundary = "----sideline%s" % os.urandom(8).hex()
    wav_bytes = _wav(pcm_bytes)

    def part(name, value):
        return ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                % (boundary, name, value)).encode("utf-8")

    body_parts = [
        ('--%s\r\nContent-Disposition: form-data; name="file"; '
         'filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'
         % boundary).encode("utf-8"),
        wav_bytes, b"\r\n",
        part("model", GROQ_MODEL),
        part("response_format", "json"),
        part("temperature", "0"),
        part("language", "en"),
    ]
    if hint:
        body_parts.append(part("prompt", hint[:800]))
    body_parts.append(("--%s--\r\n" % boundary).encode("utf-8"))
    body = b"".join(body_parts)

    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "multipart/form-data; boundary=" + boundary,
                 "User-Agent": "sideline/1.0"})
    try:
        ctx = tls.context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            doc = json.loads(r.read().decode("utf-8"))
        text = (doc.get("text") or "").strip()
        # Not audited here: the /voice/stt handler records every transcript once, whichever provider made it.
        return {"text": text, "provider": "groq"}
    except urllib.error.HTTPError as he:
        LOG.warning("groq whisper HTTP error %s: %s", he.code, he.reason)
        if he.code == 401:
            _disable("groq", "authentication failed (401)")
        return None
    except Exception as e:                                     # noqa: BLE001
        LOG.warning("groq whisper failed: %s", e)
        return None


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
    transport = AWSCRTHTTPClient()
    cfg = await AsyncBedrockRuntimeConfig.resolve(
        endpoint_uri="https://bedrock-runtime.%s.amazonaws.com" % REGION,
        region=REGION, transport=transport, **_sonic_credentials())
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
        try:
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
        except (asyncio.CancelledError, Exception):
            pass

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
        try:
            await transport.close()
        except Exception:                                      # noqa: BLE001
            pass
    return " ".join(heard).strip()


def _transcribe_sonic(pcm_bytes, hint=""):
    """Nova Sonic as the ears. Returns {"text", "provider"} or None.

    Runs the async SDK in its own loop inside the request thread. A permission or model-access error takes it out of
    rotation (it will not fix itself); a timeout or blip falls back for this
    clip only.
    """
    if len(pcm_bytes) < SAMPLE_RATE * 2 // 5:               # under 0.2 s (16-bit samples: 2 bytes each)
        return None
    try:
        loop = asyncio.new_event_loop()
        try:
            text = loop.run_until_complete(
                asyncio.wait_for(_sonic_hear(pcm_bytes, hint), timeout=20))
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for t in pending:
                    t.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:                                  # noqa: BLE001
                pass
            loop.close()
    except Exception as e:                                     # noqa: BLE001
        msg = "%s %s" % (type(e).__name__, e)
        # A ValidationException is about this request (this clip), not the provider: it is not counted.
        if any(w in msg for w in ("AccessDenied", "UnrecognizedClient",
                                  "ResourceNotFound", "SubscriptionRequired")):
            _disable("sonic", msg)
        else:
            LOG.warning("nova sonic transcription failed: %s", msg[:200])
        return None
    return {"text": text, "provider": "sonic"}


_voxtral = None


def _streaming_unsupported(e):
    """Does this error mean ConverseStream cannot be used at all (so Converse is worth one try)?"""
    if isinstance(e, (AttributeError, NotImplementedError)):
        return True
    msg = ("%s %s" % (type(e).__name__, e)).lower()
    return "unknownoperation" in msg or ("stream" in msg and "support" in msg)


def _transcribe_voxtral(pcm_bytes, hint="", model=None):   # `hint` is accepted and not sent: see below
    """Mistral's Voxtral on Bedrock as the ears: audio in, the words out, all inside the AWS account.

    Through Converse with an audio block. Two things learned the hard way: the audio goes BEFORE the
    instruction (the other way round it answers the question it hears, or invents one), and a
    system message is refused alongside audio. A model that talks about the audio instead of writing
    it down is caught by length: more words than the clip could hold is not a transcript.
    """
    global _voxtral
    if len(pcm_bytes) < SAMPLE_RATE * 2 // 5:               # under 0.2 s (16-bit samples: 2 bytes each)
        return None
    # No vocabulary goes in the prompt, on purpose. Given a list of team names, this chat model printed the list for
    # "The first one." and answered questions from it ("The score is Arsenal 1..."): measured on twelve clips, 0
    # failures without the names and up to 2 with them. Misheard names are repaired afterwards (resolve.py).
    instruction = ("Transcribe the speech in this audio word for word. Output only the words spoken. "
                   "Do not answer or comment on it.")
    try:
        if _voxtral is None:
            _voxtral = boto3.client("bedrock-runtime", region_name=REGION,
                                    config=BotoConfig(read_timeout=12, connect_timeout=3, retries={"total_max_attempts": 1}))
        used_stream = False
        text = ""
        usage = {}
        if hasattr(_voxtral, "converse_stream"):
            try:
                resp = _voxtral.converse_stream(
                    modelId=model or VOXTRAL_MODEL,
                    messages=[{"role": "user", "content": [{"audio": {"format": "wav", "source": {"bytes": _wav(pcm_bytes)}}},
                                                           {"text": instruction}]}],
                    inferenceConfig={"maxTokens": 80, "temperature": 0})
                chunks = []
                for event in resp.get("stream", []):
                    if "contentBlockDelta" in event:
                        delta = event["contentBlockDelta"].get("delta") or {}
                        if "text" in delta:
                            chunks.append(delta["text"])
                    elif "metadata" in event:
                        usage = event["metadata"].get("usage") or {}
                text = "".join(chunks).strip().strip('"').strip()
                used_stream = True
            except Exception as stream_err:                  # noqa: BLE001
                # Only a client or model without streaming is retried without it. A throttle, a timeout or a
                # refused clip would fail the same way again, at the cost of a second paid request.
                if not _streaming_unsupported(stream_err):
                    raise
                LOG.debug("voxtral converse_stream unsupported, using converse: %s", stream_err)

        if not used_stream:
            resp = _voxtral.converse(
                modelId=model or VOXTRAL_MODEL,
                messages=[{"role": "user", "content": [{"audio": {"format": "wav", "source": {"bytes": _wav(pcm_bytes)}}},
                                                       {"text": instruction}]}],
                inferenceConfig={"maxTokens": 80, "temperature": 0})
            text = " ".join(b.get("text", "") for b in resp["output"]["message"]["content"]).strip().strip('"').strip()
            usage = resp.get("usage") or {}

        from sideline import audit
        audit.record("tokens", source="speech", model=model or VOXTRAL_MODEL,
                     input=int(usage.get("inputTokens") or 0), output=int(usage.get("outputTokens") or 0))
    except Exception as e:                                     # noqa: BLE001
        msg = "%s %s" % (type(e).__name__, e)
        if any(w in msg for w in ("AccessDenied", "UnrecognizedClient", "ResourceNotFound", "not authorized",
                                  "Authentication failed")):
            _disable("voxtral", msg)
            _voxtral = None                  # a fresh client next time picks up rotated credentials
        else:
            LOG.warning("voxtral transcription failed: %s", msg[:200])
        return None
    lower = text.lower()
    refusals = (
        "not able to transcribe", "unable to transcribe", "cannot transcribe",
        "not provided", "no audio", "no speech", "please provide",
        "there is no audio", "there is no speech", "no intelligible speech"
    )
    if any(r in lower for r in refusals):
        LOG.info("voxtral returned non-transcript comment/refusal: %r; dropped", text)
        return {"text": "", "provider": "voxtral"}
    seconds = len(pcm_bytes) / float(SAMPLE_RATE * 2)
    if len(text.split()) > 4 * seconds + 4:                  # talking about the clip, not writing it down
        LOG.warning("voxtral returned more words than the clip holds; dropped")
        return None
    return {"text": text, "provider": "voxtral"}
