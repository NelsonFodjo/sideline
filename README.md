# Sideline

**Live football for people who cannot see the screen.**

A self-hosted MCP server for the Alexa+ track of the *Build, Ship, Shape:
Amazon Developer Hackathon*.

---

## The problem

A football broadcast is a visual medium with an audio track attached.
Strip away the picture and a surprising amount of the match goes with it.

The line-ups are a graphic shown once before kick-off and never read
aloud. The score and the clock sit permanently in a corner of the screen.
Substitutions appear on a board. The booking, the referee's name, the VAR
decision — all on screen, rarely spoken. Commentators talk *to* the
picture: they say "ohhh, what a chance", not "Saka, eighteen yards, left
foot, off the post."

A blind fan watching with a sighted friend simply turns and asks. Watching
alone, there is nobody to ask.

**Sideline is that friend.**

### Where we had this in mind

Not a quiet suburban front room. In Nairobi, Lagos, Accra, Port Louis,
football is watched in viewing centres and student lounges — dozens of
people around one wall-mounted screen. For a fan with low vision, or
anyone sitting at the back, the screen may as well not be there. Ambient
noise rules out an open smart speaker.

Sideline works through an earbud. The fan keeps the atmosphere of the
room and gets the facts privately, without having to lean on the person
next to them every two minutes.

That setting also drove a technical choice. Streaming a match burns
gigabytes of mobile data. Sideline runs on telemetry — a whole match as
15-second JSON state is under a megabyte. The question "what's the
score" costs a few hundred bytes and no video at all.

```
"Who's playing?"            -> the eleven, the formation, the bench
"What did I miss?"          -> exactly the gap since you last asked
"Who's refereeing?"         -> the ref, and how many cards he's shown
"Tell me about that goal."  -> go back to a moment, an hour later
"Who is he?"                -> resolved from what just happened
"Kick-off just went."       -> never spoils what your screen hasn't shown
```

---

## Run it in sixty seconds

No AWS account. No API key. No dependencies.

```bash
git clone <this repo> && cd sideline
python3 run.py                     # http://127.0.0.1:8765/mcp
```

Then, in another terminal:

```bash
python3 scripts/smoke_test.py      # every tool, end to end
```

No install step, no virtualenv, no `PYTHONPATH`, no AWS account.
`python3 -m sideline` does the same thing; `run.py` exists because it
also gives a useful error if you are in the wrong directory.

> On most Linux and macOS systems the command is `python3`. If `python3`
> is not found, try `python` — and if neither is, install Python 3.8 or
> newer.

It runs against a **real match** from StatsBomb Open Data, replayed at
real speed through the identical code path a live provider uses. Not a
mock — real events, real names, deterministic playback. See
[docs/DATA_PROVIDERS.md](docs/DATA_PROVIDERS.md).

Want the AWS integrations live? Follow
[docs/AWS_SETUP.md](docs/AWS_SETUP.md) — about 40 minutes, mostly
waiting for Bedrock model access. Then
`python3 scripts/verify_aws.py` tells you which layer failed if any did.
Without it, everything falls back to deterministic templates and still
works.

Point any MCP client at `http://127.0.0.1:8765/mcp` (Streamable HTTP).

### Or just talk to it

```bash
open simulator/index.html          # with the server running
```

Hands-free. One button once, because browsers need a gesture to open a
microphone; after that you talk, it answers out loud, and it listens
again. Cut in whenever you like and it stops.

Speech in is Amazon Transcribe, speech out is Amazon Polly — and Polly's
speech marks give the exact millisecond of every word, so the reading
animation tracks the voice rather than approximating it. Both fall back
to the browser if you have not set them up.

The core on screen is drawn from the live audio: the waveform is the
sample buffer as a circle, the outer ring is the spectrum, and the glow
follows amplitude.

See [simulator/README.md](simulator/README.md).

---

## What makes this a server and not a lookup

Two things, and only two, are genuinely ours.

**Reach.** A football match is happening right now. No model holds the
score, the line-up or the referee's card count, and none ever can.

**State.** We keep an event log of the match, and — the part that matters
— one timestamp per listener:

```
last_told_at: 12'
```

That is when we last told *this* listener anything about *this* match.
When they come back after half an hour and say "what did I miss", there
is no time range in the request. Alexa+ has no idea when they last heard
anything. We resolve the window from our own state.

Look at the arguments on that call:

```json
{ "name": "what_did_i_miss", "arguments": { "fixture_id": 1208341 } }
```

No `since`. No history. The listener gets to be terse because the server
holds the state. That single field is the product.

Read [`sideline/state/store.py`](sideline/state/store.py) first if
you only read one file.

---

## Architecture

```
          Echo / Echo Show / Alexa app
                      |
              ALEXA+ SERVICE                      Amazon's
    speech to text | tool routing | wording
    | text to speech | UI rendering
    ( acts as the MCP client )
                      |
         MCP / Streamable HTTP / 2025-11-25
                      |
            ALEXA+ MCP ADD-ON                     we deploy
    tool discovery | OAuth linking | protocol
                      |
             OUR MCP SERVER                       this repo
    9 tools | event log | last_told_at
         |          |           |            |
     Bedrock    DynamoDB   EventBridge   football feed
    (language) (state)     (poller)      (reach)
```

Full detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## The nine tools

| Tool | Answers | Why it exists |
|---|---|---|
| `follow_match` | "Follow the Arsenal game." | Binds the listener to a fixture so nothing afterwards needs context. |
| `get_match_state` | "What's the score?" | Most-asked question. Fast path, no model, under 300 ms. |
| `get_lineups` | "Who's playing?" | The graphic shown for eight seconds and never read out. |
| `what_did_i_miss` | "What did I miss?" | **The headline.** Reads the listener's own gap. |
| `get_event_detail` | "Tell me about that goal." | Live commentary never lets you go back. This does. |
| `get_officials` | "Who's refereeing?" | Named once pre-match, then unavailable for two hours. |
| `get_player_context` | "Who is he?" | The on-screen caption, spoken. |
| `get_head_to_head` | "Have we beaten them before?" | What a friend on the sofa actually says. |
| `sync_broadcast_delay` | "Kick-off just went." | **The spoiler guard.** Streams run 20–45 s behind. The listener anchors us on what they *heard* — no screen, nobody's help. |

Contracts and the reasoning behind each description:
[docs/TOOLS.md](docs/TOOLS.md).

---

## Hackathon submission

**Track:** Alexa+ — self-hosted MCP server, Streamable HTTP, spec 2025-11-25.

**Mini challenges:** AWS Builder and Open Source. See
[docs/MINI_CHALLENGES.md](docs/MINI_CHALLENGES.md).

**Required reading for judges:** start with
[docs/START_HERE.md](docs/START_HERE.md).

| | |
|---|---|
| [docs/START_HERE.md](docs/START_HERE.md) | One page: run it, and where everything is |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it fits together and why |
| [docs/AWS_SETUP.md](docs/AWS_SETUP.md) | Step by step: account, model access, credentials, verification |
| [docs/BEDROCK.md](docs/BEDROCK.md) | Where Bedrock is used, and where it is deliberately not |
| [docs/PRODUCT_FEEDBACK.md](docs/PRODUCT_FEEDBACK.md) | Feedback on every tool, API and SDK |
| [docs/FRICTION_LOG.md](docs/FRICTION_LOG.md) | Friction entries with severity and suggestions |
| [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md) | The rules this product holds itself to |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | The three minutes, shot by shot |
| [docs/COMPLIANCE.md](docs/COMPLIANCE.md) | Every official requirement, mapped to where we satisfy it |
| [docs/FEATURE_REQUESTS.md](docs/FEATURE_REQUESTS.md) | What we'd want built, and how urgent |

---

## Honest limits

We would rather state these than have a judge find them.

**Alexa+ owns the turn model.** Our server cannot make a device speak
first, so Sideline cannot shout "GOAL!" unprompted. The product is built
around on-demand questions because that is both what the platform
supports and what the use case actually wants — a listener does not want
to be narrated at, they want to be able to ask. The SSE channel in
`mcp/server.py` is implemented and held open so that if the platform ever
allows server-initiated messages, the notification has somewhere to go.

**There is no authentication yet.** Listener identity comes from a
header, falling back to a single shared id, so this is a single-listener
demo server. OAuth account linking is specified in
[docs/ALEXA_SETUP.md](docs/ALEXA_SETUP.md) and not implemented.

**No blind user has tested it yet.** The design follows published
accounts of how blind fans watch football and the structure of broadcast
information, not our own user research. We say so in
[docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md) rather than implying
otherwise.

**Bedrock is off by default, not absent.** boto3 is imported and the
Converse client is initialised in
[`language/bedrock.py`](sideline/language/bedrock.py); set
`SIDELINE_BEDROCK=on` to turn it on. It stays off by default so the
repository clones, runs and passes its tests with nothing installed —
which matters during judging, when a reviewer who cannot run the project
scores nothing.

**The data is historical.** StatsBomb Open Data is real but not live. The
rules permit a deterministic offline replay harness, and we would rather
demo real events than a live feed that might produce a goalless ninety
minutes. The demo says "a real match, replayed" and never implies
otherwise.

---

## Tests

```bash
make test
```

```
routing phrases   tool descriptions still contain the phrasings listeners use
language          phrasing, ordering, and the invented-scoreline guard
tools             all nine, plus every failure that reaches the listener
what_did_i_miss   the gap logic the product rests on
mcp protocol      conformance against spec 2025-11-25
```

No network. No credentials. No test fixtures that flatter us.

---

## Beyond the hackathon

The hard question for any sports product is where the data comes from at
scale, and buying league rights is not an answer a small team has.

It does not have to be. Broadcasters already hold official feeds, and
Amazon already holds broadcast rights for live sport on Prime Video and
Fire TV. Sideline is the layer that turns a feed somebody already owns
into a conversational accessibility feature. Nothing below the provider
interface is football-specific, and nothing in it assumes a particular
vendor.

That is also the honest answer to "could this serve an audience beyond
the hackathon": not as a consumer app buying data it cannot afford, but
as the bridge between feeds that already exist and listeners who
currently get nothing.

## Attribution

Match data from StatsBomb Open Data, used under its licence.

## Licence

MIT. See [LICENSE](LICENSE).
