# The simulator

A hands-free voice client. One button, once, because browsers will not
open a microphone without a gesture. After that nothing is clicked and
nothing is typed.

```bash
python3 -m sideline              # terminal 1
open http://127.0.0.1:8765/        # served by the running server; `make sim` does this
```

Press **Start listening**, then talk. It answers out loud and goes
straight back to listening. Cut in whenever you like — it stops and
listens.

## Watch it without a microphone (preview mode)

To see the screen working with no microphone and no sound, add `?preview=`
to the address, with questions separated by `|`:

```
http://127.0.0.1:8765/?preview=follow the Arsenal game|what did I miss|who's refereeing
```

Optional `&pace=1200` sets the pause between questions in milliseconds. It
makes the same MCP calls to the server and plays the same animation, but
**does not speak**: the words are timed from an estimated speaking rate, not
from a voice. It is a way to look at the interface, not a test of speech,
and it is not part of the product (a listener never types).

## What the screen does

Three zones, top to bottom:

- **Top: the score and the major updates.** Team names flank a large
  scoreboard that bumps (and the eye sends out a shockwave) when a goal goes
  in; below it the clock, a match timeline and up to four event chips, goals,
  red cards and VAR decisions first. None of it is required: every fact is
  also spoken and is in a screen-reader live region.
- **Centre: the eye.** A core inside rings that react to your microphone while
  you speak and to the returning voice while it answers. Aurora light drifts
  and swells with the energy, the waveform is a smooth curve, and rings ripple
  on each change of state. **Colour is the status** (there is no status label):
  blue idle, pale blue listening, deep blue thinking (with a comet around the
  ring), gold speaking.
- **Below the eye: the words.** The text hangs 10px below the eye's resting
  outer edge (`EYE_GAP` in `index.html`), on any screen size. Your question
  appears live as you speak, and the answer is set at a modest size, fitted
  to the room beneath it. Every word
  is laid out at once, faintly, so nothing reflows; as the voice reaches a word
  it sharpens, a gold light wipes through it left to right (timed by Polly's
  marks when available, otherwise estimated) and a thin glowing underline
  glides to it. Scores, minutes and numbers turn amber. When the voice finishes
  the line rests at full strength and stays until you speak again.

`prefers-reduced-motion` turns the animation off and shows the text plainly.
No blur filters are used on the canvas, to keep it smooth.

Verified by rendering in headless Chrome (wide and phone-sized) and looking at
the frames. **Not verified:** a real microphone session, Polly's marks, other
browsers, or the motion's smoothness on slower machines. Because colour alone
carries the status, it is not conveyed to a colour-blind viewer on screen; the
spoken answer and the screen-reader announcement are unaffected.

## Why there are no buttons

The listener cannot see push-to-talk buttons, suggestion chips or a text
box, so the simulator has none. The rule, in `docs/ACCESSIBILITY.md`:
before adding any input, ask what it requires of the listener; if the
answer involves looking at something, it is the wrong input.

## Nova agent and MCP

The page sends each transcript to `/agent/chat`. With Bedrock enabled,
Nova receives the MCP tool descriptions and schemas, chooses and invokes
the server's existing registered tools, then phrases a concise reply from
their results. The simulator still initializes its MCP connection to
display and verify the server's tools. Other MCP clients can call `/mcp`
directly.

If Bedrock is unavailable in demo mode, it falls back to the browser's
local keyword router and direct MCP calls so the demo remains usable. The
fallback is labelled "local routing"; a Nova answer is labelled "Nova".
In live mode it reports the failure instead and does not substitute a
prebuilt answer.
**It is not Alexa.** Nova's agent loop is a Bedrock tool-use bridge, not an
Alexa+ integration.

## Speech in

Three paths, chosen automatically in this order:

1. **Amazon Transcribe streaming** if the server has AWS credentials.
   The words appear once the clip has been transcribed. **Not yet run
   against a real account.**
2. **Groq Whisper** if there is a `GROQ_API_KEY` and no AWS. Same behaviour.
3. **The browser's own speech recognition** if the server has neither, and
   the browser has it (Chrome, Edge, some Safari). **Your words are written
   on screen live as you speak.** Chrome and Edge send the audio to their
   vendor's recognition service to do this (not Amazon), and it needs a
   network connection. Firefox has no speech recognition: the page says so
   in plain words rather than listening to nothing.

Without one of these the simulator cannot hear you, and (before this was
fixed) it failed silently: it recorded you, found no transcriber and went
back to listening with nothing on screen.

The rest of this section describes paths 1 and 2.

The browser captures, this server transcribes. Credentials never reach
the page.

**Amazon Transcribe streaming** by default, so the voice path sits in one
account under one credential chain. Streaming rather than batch, because
batch needs an S3 upload and a job poll. **Not yet run against a real
account.**

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

### Nova Sonic was not used

It is a speech-to-speech model, and the simulator assembles listen,
look-up and speak by hand instead. The reason recorded here is that the
reading animation needs word-level timings and Polly provides them as
speech marks. We did not verify whether Nova Sonic offers timing data, so
treat that reason as unchecked.

Turn-taking is energy-gated: speech lifts the level above a floor,
and a pause below it for 850 ms ends your turn. No wake word, no hold —
the listener is not looking at anything.

## Speech out, and the reading animation

**Amazon Polly**, neural, `Amy` by default.

The reason to use it is **speech marks**: alongside the audio, Polly can
return every word with its offset in milliseconds. The simulator sets one
timer per word from those offsets. **Not yet run against a real account**;
the code path is written but unobserved.

Without AWS credentials it speaks with the browser's own voice, which
fires word boundary events in Chrome and is approximated elsewhere.

```bash
pip3 install boto3 amazon-transcribe   # then export AWS_ACCESS_KEY_ID etc. (docs/ENVIRONMENT.md)
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

Only the page's logic has been exercised (by `tests/test_simulator.py`,
with no browser). **No browser has been tested**: audio capture, speech
timing and the animations are unverified in Chrome, Safari and Firefox.
Chrome is the likeliest to work for microphone capture, but that is an
expectation, not an observation.

## Honesty

This is not Alexa. Alexa+ does the listening and chooses the wording;
here the routing is keyword-matched in the browser and you hear the
server's raw answer. Say so in the video.
