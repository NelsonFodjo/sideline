# Sideline

**A friend for the match, in your ear. Built first for people who cannot see the screen. Football first.**

A self-hosted [MCP](https://modelcontextprotocol.io) server that answers a listener's questions about a match
happening right now, built for the Alexa+ track of the *Build, Ship, Shape: Amazon Developer Hackathon*.
Football is the first sport it speaks, and other sports plug in through one interface. It reads a live feed, keeps what each listener has already heard, and speaks through Amazon
Bedrock and Polly.

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

Blind and low-vision fans are the people we designed for first, and the ones with the most to gain. The same
problem is much wider, though. Anyone who has ever missed the moment, or wanted the answer the commentary did not
give, is in the same seat.

- **People who cannot see the screen.** The line-ups, the score, the referee and the cards, all spoken.
- **People whose attention is elsewhere.** Cooking, commuting, working, minding children, following a second
  game. Look away for ten minutes, ask "what did I miss?" and get exactly that gap, nothing you already heard.
- **People who always ask questions.** "Who is he?" "Who's refereeing?" "Have we beaten them before?" The things a
  commentator skips or says vaguely, answered when you want them and not before.
- **New and curious fans.** The friend who knows the game, without the embarrassment of asking the same thing again.
- **Anyone watching ahead or behind.** It holds back what your own broadcast has not shown yet.

This section is the vision behind the design, not a measured finding: the one person we have watched use it was
blind, and it worked. The rest is what the same tools make possible.

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
        \                                          a web page + the voice agent
         \                                         /
          MCP over Streamable HTTP, spec 2025-11-25
                          |
                   Sideline MCP server          27 tools · event log · last_told_at · sport profile
              /          |            \                   \
        Bedrock      DynamoDB      poller         live football feed
   (Nova Micro:      (listener     (a thread,     (Sportmonks)
    the wording,      state)        followed
    the agent)                      matches only)
   Polly (voice)   Voxtral / Nova Sonic (speech in)
```

In the intended deployment the client is Alexa+: it would do the listening, tool routing and speaking.
**That path is not reachable by hackathon participants** (the Alexa+ add-on tooling is partner-only), so
Sideline is demonstrated through a **simulated Alexa+**: a web page, plus a voice agent whose every tool call is
made over the MCP endpoint, exactly as an external client's would be. When it greets you it says so.

| AWS service | What it does here |
|---|---|
| **Bedrock, Nova Micro** | writes the spoken catch-up; in the simulator, the agent that chooses which tool to call |
| **Bedrock, Mistral Voxtral** | speech in: hears the listener. Level with or ahead of the third-party recogniser we started with (1.4% word error in noise, every name right, 0.8 s), which was then removed |
| **Bedrock, Nova 2 Sonic** | speech in, the fallback when Voxtral fails |
| **Polly** (generative voice, neural fallback) | speech out in Polly's most natural voice, an answer in one flowing piece, with word timings so the screen highlights each word as it is spoken |
| **DynamoDB** | listener state and the event log, so what a listener has heard survives a restart |

Where Bedrock is used, and where it deliberately is not: [docs/BEDROCK.md](docs/BEDROCK.md). More on the design:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Run it

**What you need, honestly.** Sideline has no recorded or demo data: it reads a live feed, so it needs a key,
and its voice runs on AWS.

| To get | You need |
|---|---|
| The server to start | a free [Sportmonks](https://www.sportmonks.com) token (`SPORTMONKS_TOKEN`): a few leagues, 180 calls an hour |
| Written and spoken answers, and the voice agent | AWS credentials with Bedrock access (Nova Micro) |
| The voice | Polly access too. A Bedrock API key alone is not enough |
| Durable state | DynamoDB access and the table (`make create-table`) |
| Speech in | the same AWS credentials: Voxtral and Nova Sonic run on Bedrock, so the listener's audio never leaves your account (see [docs/SPEECH.md](docs/SPEECH.md)) |

Python 3.8 or newer. The first launch creates an isolated `.venv` and installs
the dependencies from `requirements.txt`; later launches reuse it and reinstall
if the requirements change or `boto3` is missing. Packages are not installed
system-wide.

```bash
git clone https://github.com/NelsonFodjo/sideline && cd sideline
cp .env.example .env        # then fill in SPORTMONKS_TOKEN and your AWS credentials
make env                    # what is set; never prints a secret
make verify-data            # does the feed key work, and what is on today?
make run                    # bootstraps dependencies and starts the server
# then open http://127.0.0.1:8765/ (or: make sim)
```

You can also start it with `./run.sh`. To choose the interpreter when `.venv` is
first created, run `make run PY=/path/to/python3`.

Run it from the repository root. Allow the microphone once (browsers require a gesture), then talk. It
answers out loud and goes straight back to listening; cut in whenever you like.

**No AWS account?** The server still starts and every tool answers in templated wording through any MCP
client. The simulator's voice agent needs Bedrock; without it the page says it has no answer.

```bash
curl -s localhost:8765/mcp -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
make verify-data ARGS=--tools                      # every tool against a real match, printed
```

Settings are environment variables, documented in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) (23, and a test
keeps that page, `.env.example` and the code in step). **The free feed plan allows 180 calls an hour**, and one
match in play at the default 30 s poll uses two thirds of them; a match not yet started or already finished costs almost nothing (see `SIDELINE_POLL_SECONDS`).

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
and a tool whose need is missing is not offered, so a model is never shown one that would fail; Sportmonks' free plan
supplies all twenty-seven. Football is the sport the demo and the tests run on; the tools are sport-neutral and the
sport's words live in its `SportProfile`. Because a small model routes worse the more tools it sees,
`SIDELINE_AGENT_TOOLS=core` holds the voice agent to the core eleven.

Contracts, and the reasoning behind each description: [docs/TOOLS.md](docs/TOOLS.md).

## Football first, any sport next

The product does not depend on the sport. What does is a small set of facts in one `SportProfile`: what
scores, what counts as a headline, how time and scores are said aloud. Football is the sport with a live
feed. **Basketball runs through the same code, from an *invented* game in the tests**, to prove the seam is
real; there is no live basketball feed. See [docs/SPORTS.md](docs/SPORTS.md).

## What has been verified

Dated 2026-10-13, on one AWS account and one free Sportmonks plan. "Verified" means the command was run and
the result observed; every row says how to repeat it.

| | Status |
|---|---|
| MCP server, twenty-seven tools, spoiler guard, sport seam | **Verified**: `make test` (offline, no keys) |
| Live football feed (Sportmonks free plan) | **Verified** against a real, finished match (AGF against Sønderjyske, 2026-10-12): fixture, goals with assists, substitutions (on and off), cards, VAR notes, line-ups with formations, referee, statistics, head to head, standings, top scorers, injuries, recent form and a player's season all read correctly, and an unbroken read-through of the core tools. **Not yet seen during a live match**: the plan's four leagues had no match in play when it was checked. `make verify-data ARGS="--tools <fixture id>"` |
| Bedrock (Nova Micro): wording and tool use | **Verified**: a call takes about 1.5 to 2.1 s. `make aws-check` |
| The voice agent's tool calls go over MCP | **Verified**: with real Nova, through the MCP endpoint. `tests/test_mcp_client.py` |
| Polly speech out with word timings | **Verified**: `make aws-check` |
| DynamoDB state | **Verified** on a real table: the listener's marker survives a restart and re-polls add no duplicates (two bugs found and fixed) |
| Speech in: AWS models against a third-party benchmark | **Measured**, on synthetic speech (48 clips, clean and noisy): Voxtral Small 1.4% word error in noise, 47 of 48 clips exact, every name right, 0.8 s; the benchmark (Groq Whisper, since removed) 3.7%, 43 of 48 and 44 of 48 names; Nova 2 Sonic 8.5% at 4.2 s; Voxtral Mini unusable. `make compare-stt`; the story is in docs/SPEECH.md |
| Resolving mispronounced answers; ignoring keyboard noise | **Unit-tested**, and the former run against real Nova, on typed approximations and synthetic frames |
| A real microphone session | **Verified**: spoken questions, hands-free, with a real microphone |
| Use by a blind person | **Verified**: a blind person used it and it worked. The design is built on how a broadcast presents information, and this first session confirms it holds with a real listener |
| Alexa+ device or account linking | **Impossible for participants** (partner-only tooling) |
| Hosting | **Not built**: the hackathon FAQ says a locally runnable repo is enough |

## Scope and next steps

- **Sideline answers; it does not announce.** Alexa+'s docs describe a turn-based model and do not say whether a
  server may speak first, so it cannot say "GOAL!" unprompted. The agent is told never to promise updates.
- **One listener.** There is no account linking, so identity is a header or one shared id. Do not expose it to
  several people.
- **Alexa+ targets a 500 ms round trip.** A Bedrock catch-up takes about two seconds. The fast tools (score,
  line-ups, officials) call no model.
- **A free feed plan is thin.** Sportmonks' free plan covers four leagues (the Danish Superliga and the Scottish
  Premiership, with their play-offs) and 180 calls an hour per kind of data, so a match must be in one of them. Its
  statistics have possession, corners and cards but no shots, and it offers no win estimate. When the feed refuses,
  the listener hears its own error, word for word, and "try again shortly"; some matches have no line-ups or referee
  yet, and the tools say so rather than guess.
- **Live captions are the one place audio leaves AWS.** Speech in runs on Bedrock, but the live captions use the browser's own
  recognition, which sends audio to the browser vendor. Switchable: [docs/SPEECH.md](docs/SPEECH.md).

## Hackathon submission

**Track:** Alexa+, a self-hosted MCP server (Streamable HTTP, spec 2025-11-25), demonstrated through its own
MCP client as the hackathon FAQ describes. **Mini challenge:** AWS Builder (Bedrock, Nova Sonic, Polly,
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

Football data from [Sportmonks](https://www.sportmonks.com), under your own token and its terms. Weather for the match preview comes from [Open-Meteo](https://open-meteo.com/) (CC BY 4.0, no key; `SIDELINE_WEATHER=off` disables it). MIT licensed:
see [LICENSE](LICENSE).
