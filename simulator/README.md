# The simulated Alexa+

This page **simulates Alexa+**, the voice assistant that would talk to the Sideline MCP server. The real Alexa+ add-on
tooling is partner-only, so this stands in for it: a hands-free voice client that listens, lets a model choose among the
server's tools, calls them over MCP (`initialize`, `tools/list`, `tools/call`) as an external client would, and speaks
the answer. It says what it is when you press Go live: *"Hi, I'm a simulated Alexa+, connected to Sideline: an MCP server
for live sports, football for now..."*, followed by what sets the server apart (real matches only, it remembers what you last heard, it
stays behind your TV so it won't spoil a goal, you can talk over it). It is not Alexa+, and does not claim to be.

A hands-free voice client for the Sideline MCP server. One button, once, because browsers will not open a
microphone without a gesture. After that nothing is clicked and nothing is typed.

```bash
make run          # terminal 1: the server (needs SPORTMONKS_TOKEN; see the README)
make sim          # opens http://127.0.0.1:8765/, served by the running server
```

Press **Go live**, then talk. It answers out loud and goes straight back to listening. Cut in whenever you
like: it stops and listens. The page is served by the server it talks to, so it is same-origin and the Origin
allow-list stays strict; opened from disk (`file://`) it could not initialize.

**What stays on screen:** the teams and score show only while the answer carries match data; an answer with none (no
tool, nothing found, the feed refused) takes them away. A minute after the last word the answer text and the
teams and score all leave, and the page waits for a new question. The footer, after the model name, says "space to pause".

**Cutting in:** talk over it and it stops, but only for a word: about 360 ms of speech-like sound. A cough or a
door only turns the voice down for a moment, and it comes back. **After a minute of quiet only the eye remains**: the
text, the teams and score and the status line all fade, and anything you say or ask brings them back.

**Pause:** press the space bar to stop the voice and the microphone, and press it again to carry on (Pause and
Escape do the same). An answer already on its way is kept and spoken when you resume.

It shows live data only. There is no recorded match, no preview mode and no offline fallback: if the feed or Nova
cannot answer, it says so.

## What the screen does

Three zones, top to bottom:

- **Top: the score and the major updates.** Team names flank a large scoreboard that bumps when a goal goes in;
  below it the clock, a match timeline and up to four event chips, goals, red cards and VAR decisions first. None
  of it is required: every fact is also spoken and is in a screen-reader live region.
- **Centre: the eye.** A core inside rings that react to your microphone while you speak and to the returning
  voice while it answers. **Colour is the status** (there is no status label): blue idle, pale blue listening, deep
  blue thinking, gold speaking.
- **Below the eye: the words.** Your question appears as you speak, and the answer is set large, fitted to the
  room. Every word is laid out at once, faintly, so nothing reflows; as the voice reaches a word it sharpens and a
  gold light wipes through it, timed by Polly's speech marks (browser voice: estimated).

`prefers-reduced-motion` turns the animation off. Because colour alone carries the status, it is not conveyed to a
colour-blind viewer on screen; the spoken answer and the screen-reader announcement are unaffected.

## Why there are no buttons

The listener cannot see push-to-talk buttons, suggestion chips or a text box, so the simulator has none. The rule,
in [docs/ACCESSIBILITY.md](../docs/ACCESSIBILITY.md): before adding any input, ask what it requires of the listener;
if the answer involves looking at something, it is the wrong input.

## It is an MCP client

On each turn the server resolves the transcript ([docs/SPEECH.md](../docs/SPEECH.md)) and its MCP host fetches
the live tool catalog and server instructions over `/mcp`. Nova receives complete descriptions and schemas
up front, compares their use cases, and can call multiple tools in one response. The host refuses names absent
from the discovered catalog. Results are returned together so Nova can compose its answer. Every selected tool is called through
[`sideline/mcp/client.py`](../sideline/mcp/client.py) to `/mcp`. Tool choice is not forced and the model prompt
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

**Amazon Polly**, neural, `Amy` by default (`SIDELINE_POLLY_VOICE`). The reason to use it is **speech marks**:
alongside the audio Polly returns every word with its offset in milliseconds, and the page sets one timer per word
from those. Without AWS credentials it speaks with the browser's own voice (word boundaries in Chrome, estimated
elsewhere). The strip along the bottom reports which speech in and out are in use, the tool that ran and how long it
took, and who wrote the words (Nova or a template).

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
