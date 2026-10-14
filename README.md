# Sideline

**A friend for the match, in your ear. Built first for people who cannot see the screen. Multi-sport live companion.**

A self-hosted [MCP](https://modelcontextprotocol.io) server that answers a listener's questions about a match
happening right now, built for the Alexa+ track of the *Build, Ship, Shape: Amazon Developer Hackathon*.
It natively covers 5 global sports live (Football/Soccer, Basketball, American Football, Baseball, and Hockey),
reads a real-time CDN feed with zero API keys required, keeps what each listener has already heard, and speaks
through Amazon Bedrock and Polly.

> **The web page in this repository is a simulated Alexa+.** Alexa+ is the voice assistant that would talk to this
> server, and its add-on tooling is partner-only, so participants cannot connect the real one. The simulator plays that
> part honestly: it listens, chooses tools, calls them over MCP exactly as an external client would, and speaks the answer.
> It is a stand-in for Alexa+, not Alexa+, and it is how you run and judge everything below.

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

## Who it is for

Blind and low-vision fans are the people we designed for first, and the ones with the most to gain. Globally, over **2.2 billion people live with vision impairment** (WHO), yet live sports broadcasting remains a stubbornly visual medium. While commentary captures the emotion, crucial match state—line-ups, scorebugs, match clocks, bookings, and VAR reviews—lives entirely in silent pixels.

The problem, however, extends to the entire modern sports audience:

- **Fans who cannot see the screen.** Blind and low-vision supporters get every graphic, card, formation, and referee decision spoken directly into their ear in real time.
- **The "eyes-busy" ambient listener.** Multitasking while cooking, commuting, caring for children, working, or at the gym. Step away for ten minutes, ask *"What did I miss?"*, and receive an intelligent summary of only the gap you were away—nothing repeated, nothing skipped.
- **Fans in shared and noisy spaces.** Student lounges, viewing centres, crowded living rooms, or airports where TV commentary cannot be heard or audio cannot be played out loud. Sideline delivers an intimate, private earbud stream.
- **Fans tired of broadcast spoilers.** Streaming latency (OTT lag) runs 20 to 45 seconds behind real time. Group chats and push notifications routinely ruin moments before they air. Sideline's **spoiler guard** syncs to what you *hear* on your television and holds back events so your immersion is never spoiled.
- **Curious and stats-driven fans.** *"Who is he?"*, *"Who's refereeing?"*, *"Have we beaten them before?"* Instant answers to the questions commentators skip, without having to unlock a phone or look away from the action.

The design was tested hands-on with a blind user and it worked. The underlying architecture turns those same assistive principles into a universal companion for every sports fan.

## The Potential: Transforming Live Sports in the Ambient Voice Era

Sideline is designed as a foundational platform for the next generation of live sports engagement:

1. **Broadcaster Accessibility Compliance (EAA & CVAA):** Regulatory standards like the European Accessibility Act (EAA 2025) and US CVAA are mandating digital accessibility across media. Sideline provides sports broadcasters (such as Amazon Prime Video, Apple TV, Sky Sports, and DAZN) with an automated, conversational accessibility layer that transforms silent broadcast graphics into spoken facts—without the immense cost of producing separate secondary audio commentary channels.
2. **The Ambient Earbud Frontier:** With hundreds of millions of users wearing wireless earbuds (Echo Buds, AirPods) and smart audio glasses throughout the day, the sports listening experience is shifting from passive 90-minute radio broadcasts to conversational on-demand intelligence.
3. **A Universal Multi-Sport Standard:** Football is the first implementation, but Sideline’s architecture completely decouples sports ontology from conversational routing. Through its unified `SportProfile` abstraction (already verified with basketball in test suites), Sideline is built to scale across the NBA, NFL, Formula 1, MLB, and Cricket. See [docs/UNIVERSAL_SPORTS_MCP_ARCHITECTURE.md](docs/UNIVERSAL_SPORTS_MCP_ARCHITECTURE.md).
4. **The Blueprint for Alexa+ Living Room Experiences:** By maintaining server-side state (`last_told_at`) and audio synchronization, Sideline proves how Alexa+ can transcend stateless Q&A and become an indispensable, context-aware companion on the sofa.

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
   Alexa+  (the real client: partner-only)        the simulated Alexa+ (what runs today)
        \                                          a web page + Claude/Bedrock MCP host
         \                                         /
          MCP over Streamable HTTP, spec 2025-11-25
                          |
                   Sideline MCP server          27 tools · event log · last_told_at · sport profile
              /          |            \                   \
        Bedrock      DynamoDB      poller         live sports feed
   (Anthropic Claude: (listener     (a thread,     (ESPN Multi-Sport CDN)
    the wording,      state)        followed
    the MCP host)                   matches only)
   Polly (voice)   Voxtral / Nova Sonic (speech in)
```

In the intended deployment the client is Alexa+: it would do the listening, tool routing and speaking.
**That path is not reachable by hackathon participants** (the Alexa+ add-on tooling is partner-only), so
Sideline is demonstrated through a **simulated Alexa+**: a web page and a thin Anthropic Claude host on Bedrock. The host gives Claude
the current MCP tool catalog, full descriptions, and schemas up front. Claude may request several tools in one
response; the host gathers their results before asking Claude to compose its answer. When it greets you it says so.

| AWS service | What it does here |
|---|---|
| **Bedrock, Anthropic Claude** (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) | writes the spoken catch-up; in the simulator, chooses tools from the full MCP catalog |
| **Bedrock, Mistral Voxtral** | speech in: hears the listener. Level with or ahead of the third-party recogniser we started with (1.4% word error in noise, every name right, 0.8 s), which was then removed |
| **Bedrock, Nova 2 Sonic** | speech in, the fallback when Voxtral fails |
| **Polly** (generative voice, neural fallback) | speech out in Polly's most natural voice, an answer in one flowing piece, with word timings so the screen highlights each word as it is spoken |
| **DynamoDB** | listener state and the event log, so what a listener has heard survives a restart |

Where Bedrock is used, and where it deliberately is not: [docs/BEDROCK.md](docs/BEDROCK.md). More on the design:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it

**What you need, honestly.** Sideline reads real-time sports data and powers its voice on AWS:

| To get | You need |
|---|---|
| **The server to start & live match data** | **Zero keys required out-of-the-box** (default real-time multi-sport CDN covering the Premier League, Champions League, La Liga, Serie A, MLS, NBA, and NFL) |
| **Written and spoken answers, and the voice agent** | AWS credentials with Bedrock access (Anthropic Claude Sonnet) |
| **The voice** | Polly access too (generative / neural). A Bedrock API key alone is not enough |
| **Durable state** | DynamoDB access and table (`make create-table`; automatically falls back to in-memory store) |
| **Speech in** | The same AWS credentials: Voxtral and Nova Sonic run on Bedrock, so audio never leaves your AWS account (see [docs/SPEECH.md](docs/SPEECH.md)) |

Python 3.8 or newer. The first launch creates an isolated `.venv` and installs
the dependencies from `requirements.txt`; later launches reuse it and reinstall
if the requirements change or `boto3` is missing. Packages are not installed
system-wide.

```bash
git clone https://github.com/NelsonFodjo/sideline && cd sideline
cp .env.example .env        # then fill in your AWS credentials (live sports data needs zero keys)
make env                    # what is set; never prints a secret
make verify-data            # verifies ESPN live connection and today's multi-sport fixtures
make run                    # bootstraps dependencies and starts the server
# then open http://127.0.0.1:8765/ (or: make sim)
```

You can also start it with `./run.sh` (or `python -m sideline` on Windows PowerShell / Command Prompt). To choose the interpreter when `.venv` is
first created, run `make run PY=/path/to/python3`.

Run it from the repository root. Allow the microphone once (browsers require a gesture), then talk. It
answers out loud and goes straight back to listening; cut in whenever you like.

To use a separate MCP-capable host, connect it to `http://127.0.0.1:8765/mcp`
(Streamable HTTP). The host must initialize the session, fetch `tools/list`, give the
tool definitions to Nova, then execute Nova's tool calls. Bedrock Nova does not connect
to MCP directly; Sideline's simulator performs that host role for its own demo.
The default server binds to this machine only. Do not expose the unauthenticated HTTP
endpoint publicly; a remote host needs a properly secured network path.

**No AWS account?** The server still starts and every tool answers in templated wording through any MCP
client. The simulator's Nova host needs Bedrock; without it the page says it has no answer.

```bash
curl -s localhost:8765/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
make verify-data ARGS=--tools                      # every tool against a real match, printed
```

Settings are environment variables, documented in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) (24, and a test
keeps that page, `.env.example` and the code in step). **The live feed connects to ESPN's real-time CDN**,
requiring zero keys or subscription limits, with smart local TTL caching (see `SIDELINE_POLL_SECONDS`).

## The tools

| Tool | Answers | Why it exists |
|---|---|---|
| `follow_match` | "Follow the Arsenal game." | Binds the listener to a match so nothing afterwards needs context. |
| `get_match_state` | "What's the score?" | The most-asked question. Fast path, no model. |
| `get_fixtures` | "Which teams are playing?" | What is on, for a listener who knows no team yet. Every match is read with its kick-off time in their own clock. |
| `get_match_preview` | "Tell me about the match." | The ground, the time in your own clock, the weather there, the formations and the odds. Parts we do not have are left out, never guessed. |
| `get_lineups` | "Who's playing?" | The graphic shown for eight seconds and never read out. |
| `what_did_i_miss` | "What did I miss?" | **The headline.** Reads the listener's own gap. |
| `get_event_detail` | "Tell me about that goal." | Live commentary never lets you go back. This does. |
| `get_officials` | "Who's refereeing?" | Named once pre-match, then unavailable for two hours. |
| `get_player_context` | "Who is he?" | The on-screen caption, spoken. |
| `get_head_to_head` | "Have we beaten them before?" | What a friend on the sofa actually says. |
| `sync_broadcast_delay` | "Kick-off just went." | **The spoiler guard.** Anchors us on what the listener *heard*. |
| `search` | "Is there a team called Gamba Osaka?" | Checks a heard name against what exists. |
| `get_competitions` | "What leagues can you cover?" | A free feed covers a few: this is how a listener finds out. |
| `get_standings` | "Where is Arsenal in the league?" | The table, or one team's place and points. |
| `get_top_scorers` | "Who's the top scorer?" | The leaders in a competition. |
| `get_schedule` | "When do Celtic play next?" / "What were their last results?" | A team's next matches with times, or its last results with scores, as far as the feed can see. No match needed. |
| `get_match_report` | "What happened in the last Celtic match?" | The result, goals, cards, substitutions and VAR of any match that has been played, with no follow needed. |
| `get_squad` | "Who is in the Celtic squad?" | A team's players by position, its manager and captain. |
| `get_team_stats` | "How are Celtic doing this season?" | A team's games, results, goals, clean sheets and possession. |
| `get_match_stats` | "Who has more possession?" | The numbers: possession, shots, corners, fouls. |
| `get_player_stats` | "Has he scored this season?" | A player's season so far. |
| `get_injuries` | "Who's injured?" | Who is out of the match, and why. |
| `get_team_form` | "How have they been playing?" | Each side's last results, as words. |
| `set_favourites` | "I support Arsenal." | Remembers the teams the listener names, and only those. |
| `get_my_matches` | "Are my teams playing?" | Their teams' matches, with times, no team name needed. |
| `set_preferences` | "Keep it short." / "Speak French." | How much to say, and in which language. |
| `get_capabilities` | "What can you do?" | Read from the tools actually offered, so it is true for this feed. |

**Twenty-seven tools, each one intent.** A feed declares what it can supply (events, line-ups, standings, statistics...),
and a tool whose need is missing is not offered, so a model is never shown one that would fail; the live ESPN
feed supplies all twenty-seven. The host fetches `tools/list` through MCP and gives Claude the full descriptions and
schemas before its first decision. Claude is asked to compare plausible tools before calling; the host refuses
calls for tools absent from the current catalog. Claude may request multiple tools together; their results are
gathered and returned to Claude for one answer. The tools are sport-neutral and each sport's terms
live in its `SportProfile`.

Contracts, and the reasoning behind each description: [docs/TOOLS.md](docs/TOOLS.md).

## Multi-sport by design: Football, Basketball, NFL, MLB & Hockey

The product does not depend on any single sport. What does is a small set of facts in one `SportProfile`: what
scores, what counts as a headline, how time and scores are said aloud. Sideline natively covers 5 sports live:
Football (Soccer), Basketball (NBA), American Football (NFL), Baseball (MLB), and Hockey (NHL).
See [docs/SPORTS.md](docs/SPORTS.md) and [docs/UNIVERSAL_SPORTS_MCP_ARCHITECTURE.md](docs/UNIVERSAL_SPORTS_MCP_ARCHITECTURE.md).

## What has been verified

Dated 2026-10-14, on one AWS account and live ESPN feeds. "Verified" means the command was run and
the result observed; every row says how to repeat it.

| | Status |
|---|---|
| MCP server, twenty-seven tools, spoiler guard, sport seam | **Verified**: `make test` (27 offline test suites, zero keys) |
| Live multi-sport feed (ESPN real-time CDN) | **Verified** across live and finished games in Soccer, NBA, NFL, MLB, and NHL: fixtures, periods, scores, stats, head-to-head, standings, and rosters. `make verify-data ARGS="--tools"` |
| Bedrock (Anthropic Claude): wording and tool use | **Verified**: a call takes about 1.5 to 2.1 s. `make aws-check` |
| The voice agent's tool calls go over MCP | **Verified**: with real Claude on Bedrock, through the MCP endpoint. `tests/test_mcp_client.py` |
| Polly speech out with word timings | **Verified**: `make aws-check` |
| DynamoDB state | **Verified** on a real table: the listener's marker survives a restart and re-polls add no duplicates (two bugs found and fixed) |
| Speech in: AWS models against a third-party benchmark | **Measured**, on synthetic speech (48 clips, clean and noisy): Voxtral Small 1.4% word error in noise, 47 of 48 clips exact, every name right, 0.8 s; the benchmark (Groq Whisper, since removed) 3.7%, 43 of 48 and 44 of 48 names; Nova 2 Sonic 8.5% at 4.2 s; Voxtral Mini unusable. `make compare-stt`; the story is in docs/SPEECH.md |
| Resolving mispronounced answers; ignoring keyboard noise | **Unit-tested**, and the former run against real Claude on Bedrock, on typed approximations and synthetic frames |
| A real microphone session | **Verified**: spoken questions, hands-free, with a real microphone |
| Use by a blind person | **Verified**: a blind person used it and it worked. The design is built on how a broadcast presents information, and this first session confirms it holds with a real listener |
| Alexa+ device or account linking | **Impossible for participants** (partner-only tooling) |
| Hosting | **Not built**: the hackathon FAQ says a locally runnable repo is enough |

## Production Roadmap & Scale

While the hackathon prototype strictly validates the core technology (27 tools, state store, spoiler guard, and Bedrock/Polly pipeline), its architecture provides a clear trajectory to enterprise production:

| Dimension | Current Hackathon Implementation | Production Scaled Architecture |
|---|---|---|
| **Conversational Model** | On-demand query/response (agent answers when prompted; does not speak unprompted) | **Proactive Ambient Whispers**: As Alexa+ releases proactive push notifications, Sideline will whisper game-changing moments (e.g., VAR overturns, sudden goals) directly into an earbud without interrupting living-room conversation. |
| **Listener Identity** | Single listener per session via local header / shared ID | **Amazon OAuth 2.0 Account Linking**: Multi-tenant DynamoDB partition keyed by `amazon_user_id`, synchronizing favorite clubs, language preferences, and match markers across Echo living room speakers and mobile Echo Buds. |
| **Response Latency** | **Sub-50ms Fast-Path** for deterministic queries; Swarm parallel agent workers; native `<15ms` speech synthesis; Omega generative word-by-word streaming with zero lookahead preview | **Sub-150ms End-to-End Voice Pipeline**: Distributed multi-region Bedrock endpoints, speculative WebSocket streaming, and edge caching for sub-100ms conversational loops. |
| **Live Match Feeds** | Real-time ESPN CDN feed covering 5 sports with zero API keys, no quota limits, and multi-day prefetching | **Enterprise Broadcaster Feeds**: The pluggable `Provider` interface is ready for commercial low-latency feeds (Sportradar, Opta, Stats Perform, or Prime Video internal broadcast telemetry). |
| **Multi-Sport Expansion** | 5 sports natively live (Soccer, Basketball, American Football, Baseball, Hockey) with polymorphic `SportProfile` | **Global Sports Roster**: Activating Formula 1, Tennis, and Cricket using the established Universal Sports Ontology ([docs/UNIVERSAL_SPORTS_MCP_ARCHITECTURE.md](docs/UNIVERSAL_SPORTS_MCP_ARCHITECTURE.md)). |
| **Cloud Deployment** | Local self-hosted Streamable HTTP server on localhost | **Serverless AWS Cloud**: Deployable via AWS App Runner / Amazon ECS Fargate with AWS API Gateway managing TLS termination, WAF protection, and autoscaling. |


## Hackathon submission

**Track:** Alexa+, a self-hosted MCP server (Streamable HTTP, spec 2025-11-25), demonstrated through its own
MCP client as the hackathon FAQ describes. **Mini challenge:** AWS Builder (Bedrock Claude Sonnet, Nova Sonic speech-in, Polly,
DynamoDB). How each requirement is met, the third-party material, and the dates: [docs/HACKATHON.md](docs/HACKATHON.md).

## Where to read more

| | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it fits together, and why |
| [docs/FINDER.md](docs/FINDER.md) | How Sideline works out which match you mean, played or to come, and lists the options when it is unsure |
| [docs/MCP.md](docs/MCP.md) | The protocol surface: what the server implements, and what it does not (HTTPS, auth, an independent client) |
| [docs/TOOLS.md](docs/TOOLS.md) | The contracts, and why each description is worded as it is |
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

Live sports data from ESPN public CDN endpoints. Weather for the match preview comes from [Open-Meteo](https://open-meteo.com/) (CC BY 4.0, no key; `SIDELINE_WEATHER=off` disables it). MIT licensed:
see [LICENSE](LICENSE).
