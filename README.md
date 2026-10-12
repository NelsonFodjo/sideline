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

### The setting we designed for

*This is the motivation, not a measured finding.* Football is often
watched in shared spaces (viewing centres, student lounges, around one
screen) where a person with low vision, or anyone at the back, cannot see
the on-screen graphics, and an open speaker is impractical. Sideline is
meant to be used privately, for example through an earbud.

That setting drove a technical choice: run on match data, not video. We
measured it ([docs/EVIDENCE.md](docs/EVIDENCE.md)): polling the score every
15 seconds for a whole 90-minute match is about **190 KB** of response
bodies (about 530 bytes a call), roughly **400 KB** with HTTP headers
counted, and excludes the spoken audio. Streaming video is not measured here.

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

It runs against a **real match**, Tottenham 2-2 Arsenal (5 March 2016),
built from StatsBomb Open Data and replayed at real speed through the same
code path a live provider uses: real events and names, deterministic
playback. See [docs/DATA_PROVIDERS.md](docs/DATA_PROVIDERS.md).

Want the AWS integrations live? Follow
[docs/AWS_SETUP.md](docs/AWS_SETUP.md), then `make aws-check` names the
layer that failed, if any. Without credentials everything falls back to
deterministic templates and still works. **The AWS paths have not yet been
run against a real account**; see [docs/EVIDENCE.md](docs/EVIDENCE.md).

Point any MCP client at `http://127.0.0.1:8765/mcp` (Streamable HTTP).

### Or just talk to it

```bash
open http://127.0.0.1:8765/        # the simulator, served by the running server (make sim)
```

Hands-free. One button once, because browsers need a gesture to open a
microphone; after that you talk, it answers out loud, and it listens
again. Cut in whenever you like and it stops.

Speech in is Amazon Transcribe, speech out is Amazon Polly, whose speech
marks give each word's millisecond offset for the reading animation. Both
are written but **not yet run against a live AWS account**; without
credentials the simulator uses the browser's own speech for both directions: it
speaks with the browser's voice and transcribes you with the browser's
speech recognition (Chrome, Edge and some Safari versions; Chrome sends that
audio to its vendor's recognition service, not Amazon's), showing your words live.

The core on screen is drawn from the live audio: the waveform is the
sample buffer as a circle, the outer ring is the spectrum, and the glow
follows amplitude.

See [simulator/README.md](simulator/README.md).

---

## What makes this a server and not a lookup

Two things are ours.

**Reach.** A football match is happening right now. A language model on its own has
no way to know the score, the line-up or the referee's card count.

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
holds the state. That single field is the product. (A tool call carries
only its arguments; nothing in the MCP protocol itself says when this
listener last heard anything, so the server keeps it.)

Read [`sideline/state/store.py`](sideline/state/store.py) first if
you only read one file.

---

## Architecture

```
   MCP client                          what runs here today
   -----------                         ------------------------------------
   the simulator (a web page that      simulator/index.html, served by the
   speaks MCP), or any MCP client      server at http://127.0.0.1:8765/
            |
   MCP / Streamable HTTP / 2025-11-25
            |
     OUR MCP SERVER   (this repo)
     9 tools | event log | last_told_at
        |          |             |             |
     Bedrock    DynamoDB    poller (in the   match data: replay of a
     (language) (state)     server process)  real match, or a live feed
```

In the intended deployment the MCP client is Alexa+ (speech, tool routing,
wording and rendering would be Amazon's). **That path is not reachable by
hackathon participants**: the Alexa+ add-on tooling is partner-only (see
[docs/OFFICIAL_RULES.md](docs/OFFICIAL_RULES.md)), so this project is
demonstrated through its own MCP client. Bedrock and DynamoDB are wired but
not yet run against real services.

Full detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## The nine tools

| Tool | Answers | Why it exists |
|---|---|---|
| `follow_match` | "Follow the Arsenal game." | Binds the listener to a fixture so nothing afterwards needs context. |
| `get_match_state` | "What's the score?" | Most-asked question. Fast path, no model; about 0.2 ms of server time ([EVIDENCE.md](docs/EVIDENCE.md)). |
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

**Track:** Alexa+ — self-hosted MCP server, Streamable HTTP, spec 2025-11-25, demonstrated through its own web MCP client (the route the hackathon FAQ describes; no real Alexa+ device or add-on tooling was used or available).

**Mini challenges:** AWS Builder and Open Source. See
[docs/MINI_CHALLENGES.md](docs/MINI_CHALLENGES.md).

**Required reading for judges:** start with
[docs/START_HERE.md](docs/START_HERE.md).

| | |
|---|---|
| [docs/START_HERE.md](docs/START_HERE.md) | One page: run it, and where everything is |
| [docs/OFFICIAL_RULES.md](docs/OFFICIAL_RULES.md) | The hackathon rules and Alexa+ requirements as read on 2026-10-12, with sources |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it fits together and why |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | Every environment variable; no config files; `make env` shows what is set |
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

**Sideline answers; it does not announce.** Alexa+'s published docs describe
a turn-based model and do not say whether a server may speak first, so the
product is designed around on-demand questions and cannot say "GOAL!"
unprompted. The SSE channel in `mcp/server.py` is implemented and held open,
sending nothing, in case a client ever supports server-initiated messages.

**Authentication is built but off by default, and untested against a real
Alexa+ account link.** With it off, listener identity comes from a header
or one shared id, so the default is a single-listener demo server. With
`SIDELINE_AUTH=required` it verifies bearer tokens the way Alexa+'s docs
describe; the authorization server is yours to provide
([docs/ALEXA_SETUP.md](docs/ALEXA_SETUP.md)).

**Alexa+ targets a 500 ms round trip; the Bedrock catch-up can exceed it.**
Fast tools answer in milliseconds. The model-written catch-up has a 3 s
ceiling by default, configurable with `SIDELINE_BEDROCK_TIMEOUT`. To keep
the model off the listener's clock, the poller precomputes each follower's
catch-up in the background and asking is a cache lookup
(`SIDELINE_CATCHUP_MODE=cached`, the default); that is tested with a
simulated model only ([docs/BEDROCK.md](docs/BEDROCK.md)).

**No blind or low-vision person has used it.** The design rests on how a
football broadcast presents information and on our own reasoning, not on
user research or cited sources. See
[docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md).

**Bedrock is wired but has never been called.** boto3 is imported and the
Converse client is written in
[`language/bedrock.py`](sideline/language/bedrock.py); with
`SIDELINE_BEDROCK=auto` (the default) it switches on when AWS credentials
are present, and otherwise the server uses deterministic templates so it
runs with nothing installed. No request has been made to a real account, so
its latency and availability are unmeasured
([docs/EVIDENCE.md](docs/EVIDENCE.md)).

**The default data is historical.** StatsBomb Open Data is real but not live. The
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
(15 suites; the list below is a sample, see tests/README.md)
auth              bearer tokens: RS256/HS256, expiry, issuer, 401 behaviour Alexa+ requires
live provider     API-Football handling against canned responses; real-match regressions
routing phrases   tool descriptions still contain the phrasings listeners use
language          phrasing, ordering, and the invented-scoreline guard
tools             all nine, plus every failure that reaches the listener
what_did_i_miss   the gap logic the product rests on
mcp protocol      conformance against spec 2025-11-25
```

No network and no credentials. The only invented data is a small fixture
(`data/replay/arsenal-spurs.json`, labelled as such) that some tests use.

---

## Beyond the hackathon

A sports product needs a data source, and buying league rights is not
something a small team can do. Sideline keeps the source behind a provider
interface (`sideline/providers/base.py`): the bundled replay and an
API-Football provider are the two implementations, and the interface is not
football-vendor specific. Whether a broadcaster would supply an official
feed to a feature like this is a hypothesis; **nothing in this repository
tests it**, and no rights arrangement is claimed.

## Attribution

Match data from StatsBomb Open Data, used under its licence.

## Licence

MIT. See [LICENSE](LICENSE).
