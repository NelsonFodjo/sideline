"""Speech in and speech out, for the simulator.

WHY THIS EXISTS

Sideline's product surface is MCP: Alexa+ does the listening and the
talking, and this server never touches audio. But the simulator has to
BE the voice, because Alexa+ owns the turn model and some behaviour can
only be shown in a client we control.

The browser can do both halves on its own - webkitSpeechRecognition and
speechSynthesis. We do not use them, for three reasons:

  1. speechSynthesis is noticeably robotic, and a voice product demoed
     with a robot voice is judged as a robot.
  2. webkitSpeechRecognition is Chrome-only, which makes the prototype
     unreproducible for anyone on Safari or Firefox.
  3. The browser gives no reliable word timings. Polly does, and word
     timings are what make the reading animation track the voice
     exactly rather than approximately.

So the browser captures audio, posts it here, and this module calls a
provider. Keys never reach the browser.

THE SPEECH MARKS POINT

Amazon Polly can return, alongside the audio, a JSON stream of speech
marks: every word with its offset in milliseconds. That is the whole
reason to prefer it. The simulator highlights each word at exactly the
moment the voice reaches it, from real data rather than a timer guessing
at a speech rate.

Two calls per utterance - one for audio, one for marks. Both are fast
and they could be issued in parallel; they are sequential here because
the clarity is worth more than the fifty milliseconds.

EVERYTHING DEGRADES

No credentials, no boto3, no key - the simulator falls back to the
browser's own speech and still works. A reviewer with nothing installed
still gets a talking prototype. That is deliberate: during the judging
window, a demo that needs an API key to run at all is a demo nobody
runs.

ENDPOINT NOTE

/stt and /tts are simulator support, not part of the MCP surface. They
are served by the same process for convenience. Alexa+ never calls
them, and nothing in sideline/tools/ knows they exist.
"""

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

try:
    from amazon_transcribe.client import TranscribeStreamingClient
    from amazon_transcribe.handlers import TranscriptResultStreamHandler
    HAVE_TRANSCRIBE = True
except ImportError:                                            # pragma: no cover
    TranscribeStreamingClient = None
    TranscriptResultStreamHandler = object
    HAVE_TRANSCRIBE = False

REGION = os.environ.get("AWS_REGION", "us-east-1")

# --- speech out -------------------------------------------------------
# Neural, and British by default: the listener is following English
# football and a matching accent is less jarring than a US voice reading
# "Ødegaard". Override with SIDELINE_POLLY_VOICE.
POLLY_VOICE = os.environ.get("SIDELINE_POLLY_VOICE", "Amy")
POLLY_ENGINE = os.environ.get("SIDELINE_POLLY_ENGINE", "neural")

# --- speech in --------------------------------------------------------
# Amazon Transcribe streaming is the default: it keeps the whole voice
# path inside AWS, alongside Bedrock and Polly, and it is fast enough
# for the two-to-four second clips a turn actually produces.
#
# Groq's Whisper stays as an alternative because it is a useful
# comparison and because it needs no AWS account - a reviewer with a
# Groq key and nothing else still gets a speech-first prototype.
#
# Not Nova Sonic, though it is the obvious thing to reach for. It is a
# unified speech-to-speech model, which means it would replace this
# pipeline rather than slot into it: we would lose Polly's speech marks,
# and with them the word-exact reading animation. It also needs an
# experimental SDK and Python 3.12+. Worth revisiting; wrong thing to
# stake a demo on. Noted as future work in docs/FEATURE_REQUESTS.md.
STT_PROVIDER = os.environ.get("SIDELINE_STT", "auto")    # auto|transcribe|groq|off
TRANSCRIBE_LANG = os.environ.get("SIDELINE_TRANSCRIBE_LANG", "en-GB")
SAMPLE_RATE = 16000
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("SIDELINE_GROQ_MODEL", "whisper-large-v3-turbo")
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

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


def capabilities():
    """What the simulator should use. Asked once, at page load.

    Honest about what will actually work. The browser decides from this
    whether to post audio here or fall back to its own engine, so a
    hopeful answer here becomes a broken prototype there.
    """
    aws = _have_aws_credentials()

    stt = None
    if STT_PROVIDER != "off":
        if STT_PROVIDER == "groq" and GROQ_KEY:
            stt = "groq"
        elif STT_PROVIDER == "transcribe" and aws and HAVE_TRANSCRIBE:
            stt = "transcribe"
        elif STT_PROVIDER == "auto":
            # AWS first: it keeps the whole voice path in one account
            # and one credential chain.
            if aws and HAVE_TRANSCRIBE:
                stt = "transcribe"
            elif GROQ_KEY:
                stt = "groq"

    tts = "polly" if aws else None
    out = {
        "stt": stt,                       # None -> browser recognition
        "tts": tts,                       # None -> browser speech synthesis
        "voice": POLLY_VOICE if tts else None,
        "engine": POLLY_ENGINE if tts else None,
    }
    # Say why, so the simulator can tell the user what to set rather
    # than silently being worse than it could be.
    if not stt:
        if not aws and not GROQ_KEY:
            out["stt_hint"] = "run `aws configure` for Transcribe, or set GROQ_API_KEY"
        elif aws and not HAVE_TRANSCRIBE:
            out["stt_hint"] = "pip3 install amazon-transcribe"
        else:
            out["stt_hint"] = "speech-to-text disabled"
    if not tts:
        out["tts_hint"] = ("install boto3" if not HAVE_BOTO3
                           else "no AWS credentials - run `aws configure`")
    return out


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
        audio = c.synthesize_speech(Text=text, OutputFormat="mp3",
                                    VoiceId=POLLY_VOICE, Engine=POLLY_ENGINE)
        mp3 = audio["AudioStream"].read()

        marks_resp = c.synthesize_speech(Text=text, OutputFormat="json",
                                         SpeechMarkTypes=["word"],
                                         VoiceId=POLLY_VOICE, Engine=POLLY_ENGINE)
        # Polly returns speech marks as newline-delimited JSON, one
        # object per mark - not a JSON array.
        marks = []
        for line in marks_resp["AudioStream"].read().decode("utf-8").splitlines():
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
def transcribe(audio_bytes, mime="audio/pcm"):
    """Audio in, text out. Returns {"text": ..., "provider": ...} or None.

    The browser sends raw 16 kHz mono PCM. That is what Transcribe
    streaming wants, and it sidesteps MediaRecorder's container
    differences between browsers entirely - WebM in Chrome, MP4 in
    Safari, neither of which Transcribe accepts.

    Groq wants a file, so PCM is wrapped in a WAV header on that path.
    Forty-four bytes, no transcoding.
    """
    which = capabilities()["stt"]
    if which == "transcribe":
        return _transcribe(audio_bytes)
    if which == "groq":
        return _groq(_wav(audio_bytes) if "pcm" in mime else audio_bytes,
                     "audio/wav" if "pcm" in mime else mime)
    return None


def _wav(pcm, rate=None):
    """Wrap raw PCM in a WAV header. No transcoding, 44 bytes."""
    import struct
    rate = rate or SAMPLE_RATE
    n = len(pcm)
    return (b"RIFF" + struct.pack("<I", 36 + n) + b"WAVEfmt "
            + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", n) + pcm)


def _groq(audio_bytes, mime):
    """Whisper on Groq. Multipart by hand - no third-party HTTP client."""
    boundary = "----sideline%s" % os.urandom(8).hex()
    ext = "webm" if "webm" in mime else ("ogg" if "ogg" in mime else "wav")

    def part(name, value):
        return ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                % (boundary, name, value)).encode()

    body = b"".join([
        ('--%s\r\nContent-Disposition: form-data; name="file"; '
         'filename="clip.%s"\r\nContent-Type: %s\r\n\r\n'
         % (boundary, ext, mime)).encode(),
        audio_bytes, b"\r\n",
        part("model", GROQ_MODEL),
        part("response_format", "json"),
        # Priming the model with the vocabulary of the domain measurably
        # improves proper nouns, which is most of what a listener says.
        part("prompt", "Football match commentary. Team and player names, "
                       "minutes, goals, cards, substitutions, kick-off, "
                       "half time, the referee."),
        ("--%s--\r\n" % boundary).encode(),
    ])

    req = urllib.request.Request(
        GROQ_URL, data=body,
        headers={"Authorization": "Bearer " + GROQ_KEY,
                 "Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            doc = json.loads(r.read().decode("utf-8"))
        return {"text": (doc.get("text") or "").strip(), "provider": "groq"}
    except Exception as e:                                     # noqa: BLE001
        LOG.warning("groq whisper failed: %s", e)
        return None


def _transcribe(pcm_bytes):
    """Amazon Transcribe streaming.

    Streaming rather than batch, even though we have the whole clip
    already: the batch API needs an S3 upload and a job poll, which
    costs tens of seconds. Streaming returns while the audio is still
    being pushed, so a three-second clip comes back in about a second.

    The SDK is asyncio-based and this server is threaded, so the loop
    runs inside the request thread. That is fine - the thread is going
    to block on this call either way.

    Chunked at 8 kB because Transcribe rejects oversized frames; the
    size is not tuned for throughput, it is the documented ceiling.
    """
    if not HAVE_TRANSCRIBE:
        LOG.warning("amazon-transcribe not installed")
        return None

    import asyncio

    async def go():
        client = TranscribeStreamingClient(region=REGION)
        stream = await client.start_stream_transcription(
            language_code=TRANSCRIBE_LANG,
            media_sample_rate_hz=SAMPLE_RATE,
            media_encoding="pcm")

        said = {"text": ""}

        class Collect(TranscriptResultStreamHandler):
            async def handle_transcript_event(self, event):
                for r in event.transcript.results:
                    # Partials arrive continuously and are revised; only
                    # a settled result is worth keeping.
                    if not r.is_partial and r.alternatives:
                        said["text"] += r.alternatives[0].transcript + " "

        async def push():
            CHUNK = 8 * 1024
            for i in range(0, len(pcm_bytes), CHUNK):
                await stream.input_stream.send_audio_event(
                    audio_chunk=pcm_bytes[i:i + CHUNK])
            await stream.input_stream.end_stream()

        await asyncio.gather(push(), Collect(stream.output_stream).handle_events())
        return said["text"].strip()

    try:
        loop = asyncio.new_event_loop()
        try:
            text = loop.run_until_complete(asyncio.wait_for(go(), timeout=15))
        finally:
            loop.close()
        return {"text": text, "provider": "transcribe"} if text else None
    except Exception as e:                                     # noqa: BLE001
        LOG.warning("transcribe failed: %s", e)
        return None
