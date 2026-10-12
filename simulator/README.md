# The simulator

A hands-free voice client. One button, once, because browsers will not
open a microphone without a gesture. After that nothing is clicked and
nothing is typed.

```bash
python3 -m sideline              # terminal 1
open simulator/index.html
```

Press **Start listening**, then talk. It answers out loud and goes
straight back to listening. Cut in whenever you like — it stops and
listens.

## Why there are no buttons

An earlier version of this had push-to-talk, suggestion chips and a text
box. The listener cannot see any of them.

That is the same class of mistake as the first `sync_broadcast_delay`,
which asked a blind listener to read the clock on their television. Both
were features that worked perfectly and were useless to the person they
were for.

The rule, which is now in `docs/ACCESSIBILITY.md`: before adding any
input, ask what it requires of the listener. If the answer involves
looking at something, it is the wrong input.

## Speech in

The browser captures, this server transcribes. Credentials never reach
the page.

**Amazon Transcribe streaming** by default, so the whole voice path —
listening, reasoning, speaking — sits in one account under one
credential chain. Streaming rather than batch: batch needs an S3 upload
and a job poll, which costs tens of seconds; streaming returns while the
audio is still being pushed.

**Groq Whisper** (`whisper-large-v3-turbo`) as an alternative, chosen
automatically if there is a `GROQ_API_KEY` and no AWS. Useful as a
comparison, and it means a reviewer with a Groq key and no AWS account
still gets a speech-first prototype.

The browser sends **raw 16 kHz mono PCM**, not a recording. That is what
Transcribe wants, and it sidesteps MediaRecorder's container
differences entirely — Chrome produces WebM, Safari MP4, and Transcribe
accepts neither. Groq wants a file, so PCM gets a 44-byte WAV header
server-side. No transcoding anywhere.

With neither configured the page says so rather than silently being
worse.

### Not Nova Sonic, and why

Nova Sonic is the obvious model for this: a unified speech-to-speech
path with built-in interruption handling, which is the interaction we
assembled by hand.

We did not use it because it streams audio chunks and gives no word
timings. The reading animation needs to know which word is being spoken
at each millisecond, and Polly's speech marks are the only thing in the
pipeline that provides it. The stronger model on one side, the better
instrumentation on the other — instrumentation won.

It also needs an experimental SDK and Python 3.12+, which is a lot to
stake a demo on. Filed as `FR-06` in `docs/FEATURE_REQUESTS.md`.

Turn-taking is energy-gated: speech lifts the level above a floor,
and a pause below it for 850 ms ends your turn. No wake word, no hold —
the listener is not looking at anything.

## Speech out, and the reading animation

**Amazon Polly**, neural, `Amy` by default.

The reason to use it is not voice quality, although that matters. It is
**speech marks**: alongside the audio, Polly returns every word with its
offset in milliseconds. The simulator sets one timer per word, so each
word lights at exactly the moment the voice reaches it. Real data, not
a timer approximating a speech rate.

Without AWS credentials it falls back to the browser's own speech, which
fires word boundary events in Chrome and is approximated elsewhere.

```bash
pip3 install boto3 amazon-transcribe && aws configure
export GROQ_API_KEY=...                 # optional alternative for speech in
```

The strip along the bottom reports which of each is in use.

## Barge-in

Talk over it and it stops. Four consecutive frames above the floor —
about 240 ms of real speech, enough to ignore a cough.

This is here because the product is about being interruptible. A
simulator that has to be waited out would be demonstrating the opposite
of what we built.

Echo cancellation is on in `getUserMedia`, or the voice would
continuously interrupt itself.

## What is on screen

Sighted people will watch this, so it is designed — but nothing on it is
required to use the thing.

**The core**, centred and full-bleed. The radial waveform is the actual
sample buffer drawn as a circle; the outer ring is the frequency
spectrum, mirrored so it is symmetrical; the arcs counter-rotate and
speed up while a tool is running. The glow tracks amplitude, so it
brightens when you speak and when it answers.

**The answer**, large, lighting word by word.

**The match line**, across the top: the clock, event ticks, the blue
`told` marker, and an amber band showing your current gap. Ask what you
missed and watch the band close. That is the hero feature, visible,
with nothing explaining it.

**The machine strip**, along the bottom: the tool that ran, how long it
took, and whether the words came from Bedrock or a template. Put that
last field on camera — the language layer falls back silently by design,
so it is the only way to see the model actually ran.

## The look

Blue on near-black, with a reactive core: concentric rings, rotating
arcs, a radial waveform and a spectrum ring. That vocabulary belongs to
audio interfaces generally and long predates any one product.

Everything in it is driven by real audio — your microphone while it
listens, the returning voice while it speaks. Nothing is a decorative
loop on a timer. Colour carries state, so a sighted person can read it
across a room: dim blue idle, pale blue listening, deep blue thinking,
amber speaking.

**Public Sans** carries the interface and **IBM Plex Mono** the machine
layer, so you can tell at a glance which you are looking at. Public Sans
rather than Amazon Ember, which is proprietary and not licensable for
this.

Two things deliberately absent: a recreation of any specific device's
light ring, and any third-party mark or character design. The rules
forbid third-party trademarks in the submission, and the genre is wide
enough that nothing is lost by staying inside it.

## Browsers

| | |
|---|---|
| Chrome, Edge | Everything |
| Safari | Works; MediaRecorder output differs, Whisper handles it |
| Firefox | Works with Groq; no browser speech-recognition fallback |

Chrome for filming.

## Honesty

This is not Alexa. Alexa+ does the listening and chooses the wording;
here the routing is keyword-matched in the browser and you hear the
server's raw answer. Say so in the video — it reads as confidence.
