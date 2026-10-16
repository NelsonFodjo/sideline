# The simulated Alexa+

This page **simulates Alexa+**, the voice assistant that talks to the Sideline MCP server. While the real Alexa+ add-on tooling is partner-only, this simulator provides a production-grade demonstration: a hands-free voice client that continuously listens, lets a model on Amazon Bedrock (Amazon Nova Pro by default) select among the server's 30 MCP tools (`initialize`, `tools/list`, `tools/call`), and speaks natural answers out loud.

When you press **Go live**, the assistant introduces itself:
> *"Hi, I'm a simulated Alexa+, connected to Sideline: an MCP server for live sports. I read real matches as they happen. I remember what you last heard, so just ask what did I miss. I stay behind your TV, so I won't spoil a goal. Say stop and I will stop. Which game are we following?"*

### The look

The page plays Alexa+ talking to the Sideline server: a deep blue stage, cyan as the voice colour, a match card, a light bar
along the bottom edge that shows listening, thinking and speaking, and a scroll-back conversation (the Conversation button, or
H) where each answer carries a "Sideline" chip, the tools that ran and the time they took. It is inspired by Alexa+, not a
copy: no logo and no proprietary typeface.

A followed match keeps its strip on screen (sport, score, clock, date) while the talk is about it, and goes by itself when the
talk moves on. After two questions about something else, the match is let go (it is no longer followed, and the commentary stops);
ask about it again and it returns. "Stop following" works too. It refreshes every 30 s while the match is in play and stops at full time.
A new session starts clean: a match followed in an earlier session is not shown until you ask for it.

### Listening

A turn is fluid when you do not have to repeat yourself and nothing you did not say gets in.
- **She answers whatever she hears.** The wake word is **off** by default. Turn it on in Settings and, outside the 12 seconds after
  she finishes, a question must be addressed to her ("Alexa, what's the score"), so a TV or a room full of people cannot ask her things.
  If she hears words and lets them go for that reason, they appear on screen with how to fix it, never silently.
- **Only your voice stops her.** A key, a click or a tap never interrupts an answer; "stop", "wait" or "Alexa, ..." does, and only if
  there is a loud voice behind the words (a TV, a far room or her own echo cannot). Commentary never starts while you are speaking,
  typing or waiting for an answer, and for 10 seconds after.
- **Real speech only.** A clip needs enough voiced time (about 300 ms) to be sent; a cough or a click is dropped, and so are
  the stock phrases a recogniser invents from near silence ("thanks for watching"). Her own words coming back through the speakers
  are recognised and dropped. The agent runs only after the words have passed all of this.
- **The old sentence makes way.** The moment you start speaking her last answer fades out, and after 40 seconds of quiet the
  words go and only the eye remains. The conversation (the Conversation button, or H) keeps everything.
- **Everything ignored is in the Dev log**, with the reason, so a missed question can be explained.
- **Not yet verified on a real microphone.** The gate's logic is tested in Node (`tests/test_listening_gate.py`); how it feels with a real room is for a person to judge.

### What sets Sideline apart
1. **Live, verified data only:** Connects to open CDN feeds across 5 major sports (football, basketball, American football, baseball, hockey). No synthetic mock data, no hallucinations.
2. **Durable listener memory:** Remembers what each fan was last told, enabling conversational catch-ups (*"what did I miss"*).
3. **Zero-spoiler broadcast synchronization:** Holds back commentary behind your specific TV or stream latency so big moments are never spoiled before your picture shows them.
4. **Hard to fool:** her own voice, a commentator on the TV or a room full of people cannot interrupt her or ask her things (see "Listening", below). Say "stop" or "wait", or address her ("Alexa, ..."), and she stops and listens.

A single button click opens the microphone (as required by browser security policies). After that, the experience is 100% hands-free: nothing is clicked and nothing is typed.

```bash
make run          # terminal 1: start the Sideline server & MCP endpoints (see docs/ENVIRONMENT.md)
make sim          # opens http://127.0.0.1:8765/ (the hands-free simulator)
```

Press **Go live**, then talk naturally. The assistant answers out loud and returns directly to listening. Say "stop", "wait" or "Alexa, ..." and she stops speaking and listens. Because the page is served by the server itself, it is same-origin and respects strict Origin validation.

**What stays on screen:** Teams, scores, and match timelines display only while an answer carries live match data. 30 seconds after the last interaction, the text and scores gracefully fade, leaving only the calm ambient core ready for your next question.

**Pause:** there is no key that pauses her. To turn the microphone off, use the typing mode (Alt+T or the footer button). Space only
retries the microphone when it was refused.

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
- **Barge-in.** Only a stop word at the start ("stop", "wait", "hold on") or her name ("Alexa, ...") interrupts her, on top of
  about 300 ms of sustained, non-click speech. Any other words are ignored until she has finished: her own voice coming back through
  the speakers, a match commentator and the room all produce words, and none of them is an instruction. Echo cancellation is on in
  `getUserMedia` as well.
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

## The strip, the line-ups and large type

- **Followed match:** a bare strip across the top (teams, score, minute) with the match timeline running the full
  width under it. Goals and cards are ticks; the dot is where your picture is; a dotted line marks the live edge when you
  told it your TV is behind. Click the strip for the legend, the event chips and the competition, ground and kick-off time;
  the × stops following. While a match is on the resting eye turns warm: the words "live" are not written anywhere.
- **Line-ups:** ask "show me the line-ups" and a pitch takes the eye's place: the home side on the left defending the left
  goal, the away side on the right, each goalkeeper at their own end and the shape between (from the formation and positions the
  feed gives, not tracked positions), with the substitutes under each side and the competition, ground and kick-off time above.
  It goes when you ask something else, when the words clear, or on the ×.
- **What she did behind an answer** (the tool, the feed requests, the timings) is in the Dev log, not on the screen.
- **Large type:** Settings has a button that cycles off, large (a big score and small print), and high contrast (white and
  yellow on black). The choice is remembered in the browser. Not yet tested with real low-vision users.

## Live commentary, and typing instead of talking

- **Live commentary:** while a match is followed she reads the play out as it happens. Every 12 seconds the page asks
  the MCP for `get_match_report` with `part: "commentary"` and `since_line` (the `cursor` the last answer gave), so only
  new lines come back, at most three, never ahead of the listener's picture. No model is involved and she never talks over
  you: if anyone is speaking, the lines wait and none are lost. Say "stop commentary" or "start commentary" (or use the footer
  button). If the feed has no running commentary for a match she reads out what happens (`what_did_i_miss`) instead.
  It ends at full time or when you stop following.
- **Live is the eye's colour:** the words "following live" are gone. While a match is on, the resting eye turns warm.
- **Typing:** the footer's Mode button (or Alt+T) turns the microphone off and shows a field. She still **reads her answers aloud**
  (commentary too). Switch back to voice the same way. Typed "stop commentary" works as well.
- **Seeing what she hears:** with `SIDELINE_LIVE_CAPTION=browser` (set in the local `.env`) your words appear as you speak. Chrome and Edge
  send that audio to their vendor too; remove the line to keep audio inside AWS only.
- Not tested with a real microphone; the logic is covered in `tests/test_live_commentary.py`.
