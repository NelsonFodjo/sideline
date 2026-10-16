# Hackathon: how Sideline meets the requirements

For the *Build, Ship, Shape: Amazon Developer Hackathon* ([Devpost](https://amazonappdev2026.devpost.com/)).
The rules, FAQ, schedule, resources and announcements were fetched again on 2026-10-13 directly from Devpost
and are paraphrased here. The rules are "subject to change at any time" (§11) and **prevail over every other
page** if they disagree, so re-read before relying on this one:
[rules](https://amazonappdev2026.devpost.com/rules) ·
[FAQ](https://amazonappdev2026.devpost.com/details/faqs) ·
[dates](https://amazonappdev2026.devpost.com/details/dates) ·
[resources](https://amazonappdev2026.devpost.com/resources) ·
[updates](https://amazonappdev2026.devpost.com/updates).

**Track:** Alexa+, a self-hosted MCP server. **Mini challenge:** AWS Builder. **Not entered:** Open Source (see below).

## Dates (Pacific Time)

| | |
|---|---|
| Submission closes | **Friday 23 October 2026, 12:00 pm** (23:00 in Mauritius). No changes after, except to remove infringing or personal material |
| Judging | **Mon 9 Nov to Fri 20 Nov 2026** per the rules §1 and the FAQ. The Devpost schedule tab says Oct 26 to Nov 20: the rules prevail |
| Winners | on or around Thu 3 Dec 2026, 12:00 pm Pacific |
| Office hours | **Mon 19 Oct, 9:00 am Pacific (20:00 in Mauritius).** The first session (6 Oct) has passed |

## How it is judged

Stage one is pass/fail: the project reasonably fits the theme and applies the required technology. Stage two
scores four equally weighted criteria (25 each): **Tech Implementation**, **Design**, **Potential Impact**,
**Quality of the Idea**. **The friction log is assessed by Amazon's internal review team during Stage 1**, which
passes a recommended bonus of up to 10% to the Stage 2 panel; the panel applies it to the final score. Ties are
broken by the highest score on the first criterion, then the next. Judges are not required to test the project and
may judge from the text, images and video alone, and judging may use "automated AI-driven analysis".

Where each criterion is answered, for a judge reading only the text:

| Criterion | Where to look |
|---|---|
| **Tech Implementation** | [README, "What makes it a server"](../README.md#what-makes-it-a-server-and-not-a-lookup) and "What has been verified"; [ARCHITECTURE.md](ARCHITECTURE.md); the 61 offline suites, the official-SDK check, the routing check ([BEDROCK.md](BEDROCK.md)) |
| **Design** | [ACCESSIBILITY.md](ACCESSIBILITY.md) (rules for a listener who cannot see a screen); [TOOLS.md](TOOLS.md) (what each answer sounds like); the simulator's screen and Dev log |
| **Potential Impact** | [README, "Where this goes"](../README.md#where-this-goes); section 6 of the submission text below |
| **Quality of the Idea** | per-listener state and the clock-exact spoiler guard ([README](../README.md#what-makes-it-a-server-and-not-a-lookup)); truth over fluency ([README, "What it sounds like"](../README.md#what-it-sounds-like)) |
| **Friction log** | [FRICTION_LOG.md](FRICTION_LOG.md): 28 entries, each with a workaround and a suggestion |

The rules call a *single-turn Q&A bot* or a *basic MCP wrapper around an existing API* the obvious Alexa+ entry,
and a *context-aware add-on that maintains state across sessions* the creative one. Sideline's answer to "basic
wrapper" is the per-listener state (`last_told_at`) and the spoiler guard: the server holds what no client can.

## The track: Alexa+

| Requirement | Where it is met |
|---|---|
| A self-hosted MCP server, spec 2025-11-25 or later, Streamable HTTP | [`sideline/mcp/server.py`](../sideline/mcp/server.py): `POST /mcp`, `GET /mcp` (SSE), `DELETE /mcp`, protocol version negotiated on `initialize`. Conformance: `tests/test_mcp_protocol.py` (no official suite exists) |
| The repo calls the track technology in code, not only in a README | The server is the implementation. `python3 -m sideline` is the entry point |
| Participants cannot use the Alexa+ add-on tooling | Correct, per the FAQ ("select partners only"). So the project is demonstrated through its own MCP client, which the FAQ says satisfies the track |
| A web page acting as a real MCP client (`initialize`, `tools/list`, `tools/call`) | The simulated Alexa+ (the simulator page, which introduces itself as that) opens an MCP session and lists the tools; the voice agent it talks to makes **every `tools/call` over `/mcp`** through [`simulator/mcp_client.py`](../simulator/mcp_client.py). `tests/test_mcp_client.py` |
| Alexa+'s own requirements (HTTPS, 500 ms round trip, account linking, add-on metadata) | **Not met, and stated.** Local HTTP only; a catch-up takes about two seconds (the fast tools call no model); no account linking (the tooling is partner-only, so it could not be exercised); no add-on manifest |

## AWS Builder

The rules say to describe the AWS services and how they are used in the Product Feedback answer on the form
(not only in the repo). Everything listed ran against a real account on 2026-10-13; nothing is listed that did not.

| Service | Used for | Where | Verified |
|---|---|---|---|
| **Amazon Bedrock, Amazon Nova Pro** (`amazon.nova-pro-v1:0`) | the spoken catch-up; the voice agent choosing tools | [`language/bedrock.py`](../sideline/language/bedrock.py), [`simulator/agent.py`](../simulator/agent.py) | `make aws-check` |
| **Amazon Bedrock, Mistral Voxtral Small** | speech in, first choice | [`voice.py`](../simulator/voice.py) | `make aws-check`, `make compare-stt` |
| **Amazon Bedrock, Nova 2 Sonic** | speech in (streaming), the fallback | [`voice.py`](../simulator/voice.py) | `make aws-check`, `make compare-stt` |
| **Amazon Polly** | speech out in a generative voice, with word timings | [`voice.py`](../simulator/voice.py) | `make aws-check` |
| **Amazon DynamoDB** | listener state and the event log | [`state/dynamo.py`](../sideline/state/dynamo.py) | `make create-table`, then a restart test; `tests/test_dynamo.py` pins the bugs it exposed |

Bedrock is not decoration here: it does the one piece of work that cannot be delegated upward to Alexa+, because
Alexa+ only sees what the server returns. Where it is used and where it is deliberately not:
[BEDROCK.md](BEDROCK.md). The rules rate "single Bedrock call for text generation, S3 for storage" as the obvious AWS entry and
"multi-service pipeline (Bedrock + AgentCore + Strands), agentic architecture, agent orchestration patterns" as the
creative one. Sideline is four services doing real work together, with an agent loop of its own (Bedrock Converse
tool use over MCP); it does **not** use AgentCore, Strands or Kiro, and does not claim to.
Not used, because they could not be run: Transcribe (this account is not subscribed, see
[FRICTION_LOG.md](FRICTION_LOG.md) FL-08), and any hosting service.

## Open Source mini challenge: not entered

The challenge needs a *new, additional* open-source project, or a contribution made during the window to an
existing public repository, alongside the main submission. A contribution can be **a branch, a fork or a pull
request, and a PR does not need to be merged**; a forked, unmerged version is fine. It needs the contribution URL,
the project repository URL, your GitHub username, and what you did, how it works and why it matters. The rules
call a README fix or a typo "obvious", and a meaningful feature with tests, a bug fix that unblocks other
developers, or a new integration pattern "creative".

Nothing is claimed that does not exist: Sideline's reusable part (the provider interface,
[`providers/base.py`](../sideline/providers/base.py)) is not published separately, and no outside contribution has
been made. The bar is lower than this page used to say (an unmerged PR counts), so it is still open to enter
before the deadline. A project can win one track prize and one mini-challenge prize, so this would not displace
AWS Builder.

## Rules that can bite

- **"Free of charge and without any restriction."** The rules (§4, Testing) say the project must be available
  free of charge and without restriction to the Sponsor, Administrator and judges until judging ends. The FAQ says
  a locally runnable public repo plus the video is enough and hosting is not required. Sideline reads
  ESPN's public, undocumented endpoints, which need no key or account. ESPN grants no licence or stability promise for them
  (see [ESPN_NOTES.md](ESPN_NOTES.md)), so that data is used as found, not as a right. The server starts with no setup and
  no cost; its tools need the live feed to answer (the offline test suite uses invented data).
- **No edits after the deadline**, other than removing infringing or personal material. Drafts can be saved before.
- **English** for the video, description and documentation.
- **One Devpost representative** submits for a team. Multiple submissions must each be substantially different.
- **IP.** The submission must be original work, with no financial or preferential support from the Sponsor or
  Administrator; open-source components are fine if their licences are followed.
- **Publicity.** Entering licenses Amazon and Devpost to use your name, likeness, voice and the submission to
  promote the hackathon, for three years after.
- **Private repo only:** add `knmeiss`, `giolaq`, `anishamalde`, `mosesroth`, `emersonsklar`, `chris-trag` and
  `testing@devpost.com`; each must accept and invitations expire after 7 days. Not needed while the repo is public.

## The prizes at stake

| Prize | Cash | AWS credits | Also |
|---|---|---|---|
| Alexa+ track, 1st | $25,000 | $15,000 | meeting with the Amazon Developer team; featured |
| Alexa+ track, 2nd | $15,000 | $5,000 | featured |
| Alexa+ track, 3rd | $4,000 | $1,000 | featured |
| AWS Builder mini challenge | $5,000 | $5,000 | meeting; featured |
| Open Source mini challenge | $5,000 | $5,000 | meeting; featured |

## What the submission form asks for

| Item | Where |
|---|---|
| Text description | [README](../README.md) |
| Public GitHub repo with an open-source licence | MIT, [LICENSE](../LICENSE). It must be detectable in the repo's About box |
| Demo video, under three minutes, public, no third-party trademarks or music | to be recorded; show the simulator running on a live match |
| Product feedback on every tool, API and SDK, with a yes/no on building again | [PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md) |
| Friction log (optional, up to +10%) | [FRICTION_LOG.md](FRICTION_LOG.md) |
| Feature requests (optional) | [FEATURE_REQUESTS.md](FEATURE_REQUESTS.md) |
| If the project predates 31 August, what changed in the window | Nothing predates it: the first commit is dated 2026-10-12 |

## Third-party material and terms

The rules require authorisation to use any SDK, API or data, and that judges can test the project free of charge
until judging ends (20 November).

| What | How it is used | Terms |
|---|---|---|
| ESPN Public CDN | the live multi-sport feed across Soccer, Basketball, NFL, Baseball, and NHL | Public, undocumented endpoints; no key. ESPN publishes no rate limit, licence or stability promise (the provider caches and says when the feed is down) |
| AWS (Bedrock, Polly, DynamoDB) | as above | the user's own account and charges; no credits were available (see FL-05) |
| Open-Meteo | weather at the ground for a match preview; a city and country are sent, nothing about the listener; off with `SIDELINE_WEATHER=off` | CC BY 4.0, free for non-commercial use, no key |
| MCP specification 2025-11-25 | implemented from the spec, no SDK | open standard |
| boto3, aws-sdk-bedrock-runtime, awscrt | optional AWS SDKs | their licences |
| Public Sans, IBM Plex Mono | the simulator page's fonts, loaded from Google Fonts | open licences; confirm before relying on this |
| Python standard library | everything else | n/a |

**Zero data keys required.** Live sports data requires zero configuration or API tokens. AWS credentials unlock Bedrock Claude/Nova reasoning, DynamoDB persistence, and Polly natural voice. The README documents exactly what each piece unlocks and what still works without AWS.

---

## Devpost Pitch & Submission Copy

*(Ready to copy and adapt for the Devpost submission form. Every number below is measured and has its source in the
repository; where something is not done, it says so.)*

### Elevator Pitch
**Sideline is a friend for the match, in your ear. It is a self-hosted MCP server for live sport that tells a listener what
is happening, remembers what they have already heard, and never spoils a goal their stream has not shown yet. Built first
for blind and low-vision fans, on Amazon Bedrock, Polly and DynamoDB.**

---

### 1. Inspiration
A televised match is a picture with an audio track attached. Strip away the picture and much of the match goes with it.
The score and the clock sit silently in a corner. Line-ups, bookings, substitutions and VAR decisions appear on graphics
that commentators rarely read out. When they do speak, they speak *to* the screen: *"Ohhh, what a chance!"*, not
*"Saka, eighteen yards, left foot, off the post."*

At least 2.2 billion people live with a near or distance vision impairment (per the
[WHO](https://www.who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment)). A blind fan watching with a
sighted friend simply turns and asks. Watching alone, or in a noisy room, there is nobody to ask. Sideline is that friend.
The same thing helps anyone whose eyes are busy, or who is tired of a group chat ruining a goal.

---

### 2. What It Does
You ask out loud; it answers in a sentence or two, leading with what matters.

* **It remembers you, so you can be brief.** The server keeps one marker per listener, `last_told_at`. After ten minutes away,
  *"what did I miss?"* carries no time range at all, and returns only what happened since this listener last heard
  anything, with no repeats. A client with no memory of its own could not do this.
* **It never spoils.** Streams run 20 to 45 seconds behind real time. Tell it what you just heard (*"that's half-time"*) and
  it holds back every event your picture has not reached, by the clock, in every tool: the report, the player, the
  officials. Totals that cannot be rewound, such as live match stats, are held back too.
* **It says what it knows, and what it does not.** It answers *"tell me more about Nuno Mendes"* with his name, age,
  nationality, position and club, and says plainly that its feed has no honours. A fact comes from a tool, never from a
  model's memory: if a model tries to answer without one, it is sent back to the tools. When something fails, it says an
  error occurred and to rephrase or try again later.
* **It is live, always.** Anything that changes during a match is read from the feed on every question (a few seconds'
  sharing at most, so one question's tools make one read), and an old score is never served when the feed is down.
* **It forgets on request.** The conversation is session memory, kept in the process and never written to the table.
  *"Forget that"* ends it; *"forget everything about me"* erases what the server keeps, through a tool any client can call.
* **Thirty tools across five sports** (football, basketball, American football, baseball, hockey): scores, line-ups,
  penalties, match stats, standouts, standings, head-to-head, news, a player's profile and season, and the question people
  actually ask: *"was there a penalty, and what happened?"*

---

### 3. How We Built It (AWS Builder Architecture)
The MCP server is standard-library Python in one folder (`sideline/`); a web page plays the part of Alexa+ so it can be
tried by voice. Four AWS services do real work together:
* **Amazon Bedrock, Amazon Nova Pro.** In the simulator it is the host: it reads the server's `tools/list`, chooses the tool
  and words the answer. On a 79-phrasing routing check with all 30 tools offered it called the intended tool on
  77 of the 79 (97%) (the other models we ran, and the caveats, are in [BEDROCK.md](BEDROCK.md)).
* **Amazon Bedrock, Mistral Voxtral and Nova 2 Sonic.** Speech in, entirely inside the listener's AWS account.
* **Amazon Polly (generative voice).** Speech out, with word timings so the screen highlights each word as it is spoken.
* **Amazon DynamoDB.** One table: the listener's marker, the match event log (deduplicated, expiring after 48 hours) and
  the match snapshots, so what a listener has heard survives a restart. We measured what each call costs from a distant
  region and rebuilt the first question around it ([FRICTION_LOG.md](FRICTION_LOG.md), FL-26).
* **A hand-written MCP server (spec 2025-11-25, Streamable HTTP).** Sessions, protocol-version checks, origin checks,
  optional bearer-token auth, argument errors as tool errors a model can correct. The official MCP Python SDK client
  connects to it, lists the 30 tools and calls them. It runs on its own: a test copies the `sideline/` folder alone to an
  empty directory and starts it there.

---

### 4. Challenges We Ran Into & The Friction Log
We kept a [friction log of 28 entries](FRICTION_LOG.md), each with the task, steps, what we expected, what happened, how
bad it was, our workaround and a suggestion. The ones we would most want Amazon's teams to read:
* **The add-on tooling is partner-only** while the hackathon invites everyone (FL-01): we built a faithful simulated client.
* **`max_attempts: 1` is two attempts** in the Bedrock SDK, which doubled every timeout we had budgeted (FL-21).
* **A first question took 11 seconds** because 26 DynamoDB calls ran in a row at about 340 ms each from Mauritius; at the
  table's own speed it was fine (FL-26).
* **A hand-written MCP server had eight spec deviations** that only a spec-versus-code review found, all fixed (FL-24).
* **Choosing a model to route among 30 tools** looked like a model problem and was mostly ours: a clock, a time zone and
  a repair that heard "support" as "Porto" (FL-25).
* **A wrong score** because we trusted a goal list over the feed's own score: fixed, and the answer now says when it cannot
  be sure (FL-28).
* **Our simulated assistant was slower than we had said,** because its wait to be sure the listener had stopped depended
  on a browser setting that was off by default, so it ran at its slowest and not the documented speed (FL-27).

---

### 5. Accomplishments That We're Proud Of
* **The server holds what no client can.** Per-listener state and a clock-exact spoiler guard turn a lookup into something
  worth a server, and both are covered by tests.
* **Truth over fluency.** It declines to guess (a referee the feed does not name, expected goals, a player's honours), and
  every fact traces to a tool result.
* **Evidence.** 61 offline test suites that need no network or credentials; three live conversation batches (70 questions)
  against real matches; a routing check across four Bedrock models; the official SDK client run against the server.
* **Candour.** The README lists what is not done: no real Alexa+, no OAuth, one listener per server, an unofficial data source.
* **Tried with a blind listener (reported by the team):** one blind person used it informally in a first session, with a
  real microphone. That is one person and no measurements, not a study, and we would like many more sessions.

---

### 6. What's Next
1. **Connect it to something real.** The README has the step-by-step to host it (a server, HTTPS, a bearer token, DynamoDB
   state) and point any MCP client at it. The step Amazon controls is the certified Alexa+ add-on with OAuth account linking,
   which is partner-only today; it would turn "one listener per deployment" into one per Amazon account.
2. **More sport, same shape.** Five sports work now through a per-sport profile ([SPORTS.md](SPORTS.md)); leagues and sports
   such as Formula 1 are new profiles, not a rewrite, and ESPN's coverage is wide.
3. **Speak first.** Alexa+ cannot be spoken first by a server today (FR-01). With an opt-in way to push a short message,
   *"goal"* could arrive the moment it happens, still held back to the listener's picture.
4. **A pattern others can copy.** The marker-per-listener design suits any add-on that answers "what changed since I last
   asked": a delivery, a flight, a market. Sport is where it matters most when you cannot see the screen.
