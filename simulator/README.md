# The simulated Alexa+

This page **simulates Alexa+**, the voice assistant that talks to the Sideline MCP server. While the real Alexa+ add-on tooling is partner-only, this simulator provides a production-grade demonstration: a hands-free voice client that continuously listens, lets an LLM (Anthropic Claude on Amazon Bedrock) select among the server's 27 MCP tools (`initialize`, `tools/list`, `tools/call`), and speaks natural answers out loud.

When you press **Go live**, the assistant introduces itself:
> *"Hi, I'm a simulated Alexa+, connected to Sideline: an MCP server for live sports. I read real matches as they happen. I remember what you last heard, so just ask what did I miss. I stay behind your TV, so I won't spoil a goal. And you can talk over me. Which game are we following?"*

### What sets Sideline apart
1. **Live, verified data only:** Connects to open CDN feeds across 5 major sports (football, basketball, American football, baseball, hockey). No synthetic mock data, no hallucinations.
2. **Durable listener memory:** Remembers what each fan was last told, enabling conversational catch-ups (*"what did I miss"*).
3. **Zero-spoiler broadcast synchronization:** Holds back commentary behind your specific TV or stream latency so big moments are never spoiled before your picture shows them.
4. **Natural conversational barge-in:** Speak over the assistant at any time—the voice ducks instantly and begins listening.

A single button click opens the microphone (as required by browser security policies). After that, the experience is 100% hands-free: nothing is clicked and nothing is typed.

```bash
make run          # terminal 1: start the Sideline server & MCP endpoints (see docs/ENVIRONMENT.md)
make sim          # opens http://127.0.0.1:8765/ (the hands-free simulator)
```

Press **Go live**, then talk naturally. The assistant answers out loud and returns directly to listening. Cut in whenever you like: it stops speaking within 360 ms and listens. Because the page is served by the server itself, it is same-origin and respects strict Origin validation.

**What stays on screen:** Teams, scores, and match timelines display only while an answer carries live match data. 30 seconds after the last interaction, the text and scores gracefully fade, leaving only the calm ambient core ready for your next question.

**Pause:** Press the space bar to mute the voice and microphone; press it again to resume (Pause and Escape keys work identically).

## What the screen does

Three zones, top to bottom:

- **Top: the score and the major updates.** Team names flank a large scoreboard that bumps when a goal goes in;
  below it the clock, a match timeline and up to four event chips, goals, red cards and VAR decisions first. None
  of it is required: every fact is also spoken and is in a screen-reader live region.
- **Centre: the eye.** A core inside rings that react to your microphone while you speak and to the returning
  voice while it answers. **Colour is the status** (there is no status label): blue idle, pale blue listening, deep
  blue thinking, gold speaking.
- **Below the eye: the words.** Your question appears as you speak, and the answer streams generatively word-by-word with **zero lookahead preview**—just like an AI token stream synchronized with voice playback. Each word pops in dynamically as it is spoken, accompanied by a gold light wipe and the gliding beam, before settling cleanly into place.

`prefers-reduced-motion` turns the animation off. Because colour alone carries the status, it is not conveyed to a
colour-blind viewer on screen; the spoken answer and the screen-reader announcement are unaffected.

## Why there are no buttons

The listener cannot see push-to-talk buttons, suggestion chips or a text box, so the simulator has none. The rule,
in [docs/ACCESSIBILITY.md](../docs/ACCESSIBILITY.md): before adding any input, ask what it requires of the listener;
if the answer involves looking at something, it is the wrong input.

## It is an MCP client

On each turn the server resolves the transcript ([docs/SPEECH.md](../docs/SPEECH.md)) and its MCP host fetches
the live tool catalog and server instructions over `/mcp`. Claude receives complete descriptions and schemas
up front, compares their use cases, and can call multiple tools in one response. The host refuses names absent
from the discovered catalog. Results are returned together so Claude can compose its answer. Every selected tool is called through
[`simulator/mcp_client.py`](./mcp_client.py) to `/mcp`. Tool choice is not forced and the model prompt
does not contain phrase-to-tool rules. Any other MCP client can call `/mcp` directly. **It is not Alexa:** the
simulator is a Bedrock host using MCP, not an Alexa+ integration.

## Speech in

The browser captures raw 16 kHz mono PCM (not a recording, which sidesteps MediaRecorder's container differences)
and posts it to the server, which tries Voxtral, then Nova Sonic (both on Bedrock), and tells the page what it
heard. With neither, the browser's own recognition does it. Providers, measurements and the privacy trade-offs:
[docs/SPEECH.md](../docs/SPEECH.md).

- **Typing as you speak.** Server recognition returns text only after the clip ends, so the page also runs the
  browser's recognition on the side, purely to show interim words, then replaces them with the server's more
  accurate transcript. That audio also reaches the browser vendor; `SIDELINE_LIVE_CAPTION=off` avoids it. Firefox
  has no browser recognition, and then nothing types until the clip ends.
- **Turn-taking is not a loudness gate.** A fixed level cannot tell a voice from a key press. A frame counts as
  speech only if it is louder than this room's learned noise, is not click-like (a click has much of its energy above
  5 kHz, speech little), and holds for several frames in a row. Typing, fast typing and a desk thump never start a
  turn; speech with keys in it does. The logic runs under Node in `tests/test_simulator.py`. A pause of 700 ms ends
  your turn. No wake word, no hold.
- **Barge-in.** Talk over the answer and it stops: about 300 ms of sustained, non-click speech, so typing while it
  talks does not cut it off. Echo cancellation is on in `getUserMedia`, or the voice would interrupt itself.
- **The server also checks.** A clip needs at least 160 ms of sustained sound before it reaches any provider; a clip
  of clicks is dropped for free.

## Speech out

**Instant Browser Speech (`<15ms`)** is the default voice engine (`SIDELINE_TTS=browser`), producing natural local speech with zero network latency and real-time word boundary synchronization. Where cloud speech is preferred, **Amazon Polly** (`Amy` / `Brian`), **Cartesia** (~60ms), and **ElevenLabs** Flash v2.5 (~75ms) provide cloud speech marks with words streaming one-by-one as audio plays. The wire strip along the bottom reports which speech in and out are in use, the tool that ran and its millisecond latency, and who wrote the words (Claude or a template).

## The look

Blue on near-black, with a reactive core: concentric rings, a radial waveform and a spectrum ring, all driven by
real audio (your microphone while it listens, the returning voice while it speaks), never a decorative loop on a
timer. **Public Sans** carries the interface and **IBM Plex Mono** the machine layer, loaded from Google Fonts. No
third-party mark or character design is used; the hackathon rules forbid third-party trademarks.

## What has been verified

- **Verified:** the page's logic (`tests/test_simulator.py`, including the speech detector under Node, with no
  browser); the server endpoints it uses; Polly's speech marks (`make aws-check`).
- **Tested by hand:** a real microphone session, by the author and by a blind person; it worked.
- **Next:** the speech detector with a real keyboard, the live captions, other browsers, and slower machines.
