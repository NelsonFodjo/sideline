# Sideline

**Live football for people who cannot see the screen.**

A self-hosted [MCP](https://modelcontextprotocol.io) server that answers a listener's questions about a match
happening right now, built for the Alexa+ track of the *Build, Ship, Shape: Amazon Developer Hackathon*.
It reads a live football feed, keeps what each listener has already heard, and speaks through Amazon
Bedrock and Polly.

---

## The problem

A football broadcast is a visual medium with an audio track attached. Strip away the picture and a
surprising amount of the match goes with it.

The line-ups are a graphic shown once before kick-off and never read aloud. The score and the clock sit
permanently in a corner of the screen. Substitutions appear on a board. The booking, the referee's name,
the VAR decision: all on screen, rarely spoken. Commentators talk *to* the picture: they say "ohhh, what a
chance", not "Saka, eighteen yards, left foot, off the post."

A blind fan watching with a sighted friend simply turns and asks. Watching alone, there is nobody to ask.

**Sideline is that friend.**

*The setting we designed for is motivation, not a measured finding:* football is often watched in shared
spaces (viewing centres, student lounges, around one screen) where a person with low vision, or anyone at
the back, cannot see the graphics and an open speaker is impractical. So Sideline works from match data, not
video, and is meant to be heard privately, through an earbud.

## What you can ask

```
"Who's playing?"            -> the eleven, the formation, the bench
"What did I miss?"          -> exactly the gap since you last asked
"Who's refereeing?"         -> the ref, and how many cards he's shown
"Tell me about that goal."  -> go back to a moment, an hour later
"Who is he?"                -> resolved from what just happened
"Kick-off just went."       -> never spoils what your screen hasn't shown
```

And it understands you when you are not clear. If it offers a choice ("Tottenham Hotspur against Arsenal,
or Arsenal against Tottenham?") and you answer "tottenham hot spur", it works out which you meant. If it
cannot tell two options apart, it asks again rather than guess.

## What makes it a server and not a lookup

**Reach.** A match is happening right now. A language model alone cannot know the score, the line-up or how
many cards the referee has shown.

**State.** The server keeps an event log of the match and, the part that matters, one timestamp per listener:

```
last_told_at: 12'
```

That is when we last told *this* listener anything about *this* match. When they come back after half an
hour and say "what did I miss", the request carries no time range, because Alexa+ has no idea when they last
heard anything:

```json
{ "name": "what_did_i_miss", "arguments": { "fixture_id": 1208341 } }
```

No `since`. The listener gets to be terse because the server holds the state. That single field is the
product, and [`sideline/state/store.py`](sideline/state/store.py) is the file to read first. The second
safeguard is the spoiler guard: streams run 20 to 45 seconds behind real time, so the listener tells us what
they just *heard* ("that's half time") and we hold everything back to match their picture.

## How it works

```
   Alexa+  (the intended client)                 the simulator (what runs today)
        \                                          a web page + the voice agent
         \                                         /
          MCP over Streamable HTTP, spec 2025-11-25
                          |
                   Sideline MCP server           9 tools · event log · last_told_at · sport profile
              /          |            \                   \
        Bedrock      DynamoDB      poller         live football feed
   (Nova Micro:      (listener     (a thread,     (API-Football)
    the wording,      state)        followed
    the agent)                      matches only)
   Polly (voice)   Nova Sonic / Groq (speech in)
```

In the intended deployment the client is Alexa+: it would do the listening, tool routing and speaking.
**That path is not reachable by hackathon participants** (the Alexa+ add-on tooling is partner-only), so
Sideline is demonstrated through its own MCP client: a web page, plus a voice agent whose every tool call is
made over the MCP endpoint, exactly as an external client's would be.

| AWS service | What it does here |
|---|---|
| **Bedrock, Nova Micro** | writes the spoken catch-up; in the simulator, the agent that chooses which tool to call |
| **Bedrock, Nova 2 Sonic** | speech in: hears the listener (the fallback when no Groq key is set) |
| **Polly** (neural) | speech out, with word timings so the screen highlights each word as it is spoken |
| **DynamoDB** | listener state and the event log, so what a listener has heard survives a restart |

Where Bedrock is used, and where it deliberately is not: [docs/BEDROCK.md](docs/BEDROCK.md). More on the design:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it

**What you need, honestly.** Sideline has no recorded or demo data: it reads a live feed, so it needs a key,
and its voice runs on AWS.

| To get | You need |
|---|---|
| The server to start | a free [API-Football](https://dashboard.api-football.com) key |
| Written and spoken answers, and the voice agent | AWS credentials with Bedrock access (Nova Micro) |
| The voice | Polly access too. A Bedrock API key alone is not enough |
| Durable state | DynamoDB access and the table (`make create-table`) |
| The most accurate speech in | optional: a free Groq key (your audio then leaves AWS, see [docs/SPEECH.md](docs/SPEECH.md)) |

Python 3.8 or newer. The server itself uses only the standard library.

```bash
git clone https://github.com/NelsonFodjo/sideline && cd sideline
pip3 install boto3                                 # the AWS integrations (all optional)
pip3 install aws-sdk-bedrock-runtime awscrt        # Nova Sonic speech in (Python 3.12+; optional)

cp .env.example .env        # then fill in SIDELINE_FOOTBALL_KEY and your AWS credentials
make env                    # what is set; never prints a secret
make verify-data            # does the feed key work, and what is on today?
make aws-check              # does each AWS piece actually work?
make run                    # then open http://127.0.0.1:8765/  (or: make sim)
```

Run it from the repository root. Allow the microphone once (browsers require a gesture), then talk. It
answers out loud and goes straight back to listening; cut in whenever you like.

**No AWS account?** The server still starts and every tool answers in templated wording through any MCP
client. The simulator's voice agent needs Bedrock; without it the page says it has no answer.

```bash
curl -s localhost:8765/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
make verify-data ARGS=--tools                      # every tool against a real match, printed
```

Settings are environment variables, documented in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) (19, and a test
keeps that page, `.env.example` and the code in step). **A free feed plan allows 100 requests a day**, which
one followed match at the default 60 s poll spends in about an hour and a half.

## The nine tools

| Tool | Answers | Why it exists |
|---|---|---|
| `follow_match` | "Follow the Arsenal game." | Binds the listener to a match so nothing afterwards needs context. |
| `get_match_state` | "What's the score?" | The most-asked question. Fast path, no model. |
| `get_lineups` | "Who's playing?" | The graphic shown for eight seconds and never read out. |
| `what_did_i_miss` | "What did I miss?" | **The headline.** Reads the listener's own gap. |
| `get_event_detail` | "Tell me about that goal." | Live commentary never lets you go back. This does. |
| `get_officials` | "Who's refereeing?" | Named once pre-match, then unavailable for two hours. |
| `get_player_context` | "Who is he?" | The on-screen caption, spoken. |
| `get_head_to_head` | "Have we beaten them before?" | What a friend on the sofa actually says. |
| `sync_broadcast_delay` | "Kick-off just went." | **The spoiler guard.** Anchors us on what the listener *heard*. |

Contracts, and the reasoning behind each description: [docs/TOOLS.md](docs/TOOLS.md).

## Football first, any sport next

The product does not depend on the sport. What does is a small set of facts in one `SportProfile`: what
scores, what counts as a headline, how time and scores are said aloud. Football is the sport with a live
feed. **Basketball runs through the same code, from an *invented* game in the tests**, to prove the seam is
real; there is no live basketball feed. See [docs/SPORTS.md](docs/SPORTS.md).

## What has been verified, and what has not

Dated 2026-10-13, on one AWS account and one free API-Football plan. "Verified" means the command was run and
the result observed; every row says how to repeat it.

| | Status |
|---|---|
| MCP server, nine tools, spoiler guard, sport seam | **Verified**: `make test` (offline, no keys) |
| Live football feed (free plan) | **Verified**: real fixtures, a live match and a finished one read through every tool; five bugs the feed exposed are fixed and pinned by tests. `make verify-data ARGS=--tools` |
| Bedrock (Nova Micro): wording and tool use | **Verified**: a call takes about 1.5 to 2.1 s. `make aws-check` |
| The voice agent's tool calls go over MCP | **Verified**: with real Nova, through the MCP endpoint. `tests/test_mcp_client.py` |
| Polly speech out with word timings | **Verified**: `make aws-check` |
| DynamoDB state | **Verified** on a real table: the listener's marker survives a restart and re-polls add no duplicates (two bugs found and fixed) |
| Speech in: Groq against Nova Sonic | **Measured**, on synthetic speech (48 clips, clean and noisy): Groq 3.7% word error in noise at 1.1 s, Sonic 8.5% at 4.2 s. `make compare-stt` |
| Resolving mispronounced answers; ignoring keyboard noise | **Unit-tested**, and the former run against real Nova, on typed approximations and synthetic frames. **Not tried with real voices or a real keyboard** |
| Use by a blind or low-vision person | **Not tested.** The design rests on how a broadcast presents information, not on user research |
| Alexa+ device or account linking | **Impossible for participants** (partner-only tooling) |
| Hosting | **Not built**: the hackathon FAQ says a locally runnable repo is enough |

## Honest limits

- **Sideline answers; it does not announce.** Alexa+'s docs describe a turn-based model and do not say whether a
  server may speak first, so it cannot say "GOAL!" unprompted. The agent is told never to promise updates.
- **One listener.** There is no account linking, so identity is a header or one shared id. Do not expose it to
  several people.
- **Alexa+ targets a 500 ms round trip.** A Bedrock catch-up takes about two seconds. The fast tools (score,
  line-ups, officials) call no model.
- **A free feed plan is thin.** 100 requests a day; some matches have no line-ups or referee yet, and the tools
  say so rather than guess.
- **Speech in has a privacy cost.** Groq is a third party, and the live captions use the browser's own
  recognition, which sends audio to the browser vendor. Both are switchable: [docs/SPEECH.md](docs/SPEECH.md).

## Hackathon submission

**Track:** Alexa+, a self-hosted MCP server (Streamable HTTP, spec 2025-11-25), demonstrated through its own
MCP client as the hackathon FAQ describes. **Mini challenge:** AWS Builder (Bedrock, Nova Sonic, Polly,
DynamoDB). How each requirement is met, the third-party material, and the dates: [docs/HACKATHON.md](docs/HACKATHON.md).

## Where to read more

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it fits together, and why |
| [docs/TOOLS.md](docs/TOOLS.md) | The nine contracts, and why each description is worded as it is |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | Every environment variable |
| [docs/AWS_SETUP.md](docs/AWS_SETUP.md) | The AWS side, step by step, and what each service needs |
| [docs/BEDROCK.md](docs/BEDROCK.md) | Where Bedrock is used, and where it is not |
| [docs/SPEECH.md](docs/SPEECH.md) | Speech in: the providers, the measurements, understanding what was meant, keyboard noise |
| [docs/DATA_PROVIDERS.md](docs/DATA_PROVIDERS.md) | The live feed: what we observed, and how to write another provider |
| [docs/SPORTS.md](docs/SPORTS.md) | The sport profile seam, and what is proven |
| [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md) | The rules this product holds itself to |
| [docs/PRODUCT_FEEDBACK.md](docs/PRODUCT_FEEDBACK.md), [FRICTION_LOG.md](docs/FRICTION_LOG.md), [FEATURE_REQUESTS.md](docs/FEATURE_REQUESTS.md) | Feedback on the tools we used |
| [simulator/README.md](simulator/README.md) | The web client |
| [tests/README.md](tests/README.md), [CONTRIBUTING.md](CONTRIBUTING.md) | The suite, and the rules for changing things |

## Attribution and licence

Football data from [API-Football](https://www.api-football.com) under your own key and its terms. MIT licensed:
see [LICENSE](LICENSE).
