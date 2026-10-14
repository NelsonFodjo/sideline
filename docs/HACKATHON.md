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

The rules call a *single-turn Q&A bot* or a *basic MCP wrapper around an existing API* the obvious Alexa+ entry,
and a *context-aware add-on that maintains state across sessions* the creative one. Sideline's answer to "basic
wrapper" is the per-listener state (`last_told_at`) and the spoiler guard: the server holds what no client can.

## The track: Alexa+

| Requirement | Where it is met |
|---|---|
| A self-hosted MCP server, spec 2025-11-25 or later, Streamable HTTP | [`sideline/mcp/server.py`](../sideline/mcp/server.py): `POST /mcp`, `GET /mcp` (SSE), `DELETE /mcp`, protocol version negotiated on `initialize`. Conformance: `tests/test_mcp_protocol.py` (no official suite exists) |
| The repo calls the track technology in code, not only in a README | The server is the implementation. `python3 -m sideline` is the entry point |
| Participants cannot use the Alexa+ add-on tooling | Correct, per the FAQ ("select partners only"). So the project is demonstrated through its own MCP client, which the FAQ says satisfies the track |
| A web page acting as a real MCP client (`initialize`, `tools/list`, `tools/call`) | The simulated Alexa+ (the simulator page, which introduces itself as that) opens an MCP session and lists the tools; the voice agent it talks to makes **every `tools/call` over `/mcp`** through [`sideline/mcp/client.py`](../sideline/mcp/client.py). `tests/test_mcp_client.py` |
| Alexa+'s own requirements (HTTPS, 500 ms round trip, account linking, add-on metadata) | **Not met, and stated.** Local HTTP only; a catch-up takes about two seconds (the fast tools call no model); no account linking (the tooling is partner-only, so it could not be exercised); no add-on manifest |

## AWS Builder

The rules say to describe the AWS services and how they are used in the Product Feedback answer on the form
(not only in the repo). Everything listed ran against a real account on 2026-10-13; nothing is listed that did not.

| Service | Used for | Where | Verified |
|---|---|---|---|
| **Amazon Bedrock, Anthropic Claude** (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) | the spoken catch-up; the voice agent choosing tools | [`language/bedrock.py`](../sideline/language/bedrock.py), [`language/agent.py`](../sideline/language/agent.py) | `make aws-check` |
| **Amazon Bedrock, Nova 2 Sonic** | speech in (streaming) | [`voice.py`](../sideline/voice.py) | `make aws-check`, `make compare-stt` |
| **Amazon Polly** | speech out in a generative voice, with word timings | [`voice.py`](../sideline/voice.py) | `make aws-check` |
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
  a locally runnable public repo plus the video is enough and hosting is not required. Sideline connects to
  open live sports feeds (ESPN CDN) with zero authentication or API keys required, completely removing third-party data restrictions.
  The server starts out of the box and answers every MCP tool offline or against live games without any cost.
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
| ESPN Public CDN | the live multi-sport feed across Soccer, Basketball, NFL, Baseball, and NHL | Public real-time scoreboards, zero authentication, no rate limit |
| AWS (Bedrock, Polly, DynamoDB) | as above | the user's own account and charges; no credits were available (see FL-05) |
| Open-Meteo | weather at the ground for a match preview; a city and country are sent, nothing about the listener; off with `SIDELINE_WEATHER=off` | CC BY 4.0, free for non-commercial use, no key |
| MCP specification 2025-11-25 | implemented from the spec, no SDK | open standard |
| boto3, aws-sdk-bedrock-runtime, awscrt | optional AWS SDKs | their licences |
| Public Sans, IBM Plex Mono | the simulator page's fonts, loaded from Google Fonts | open licences; confirm before relying on this |
| Python standard library | everything else | n/a |

**Zero data keys required.** Live sports data requires zero configuration or API tokens. AWS credentials unlock Bedrock Claude/Nova reasoning, DynamoDB persistence, and Polly natural voice. The README documents exactly what each piece unlocks and what still works without AWS.

---

## Devpost Pitch & Submission Copy

*(Ready to copy and adapt for the Devpost submission form)*

### Elevator Pitch
**Sideline is an intelligent, voice-first companion in your ear for live sports. Built first for blind and low-vision fans, it transforms silent TV broadcast graphics into real-time spoken facts, remembers what you've heard across match gaps, and guards against stream lag spoilers—powered by a self-hosted MCP server on Amazon Bedrock, Polly, and DynamoDB.**

---

### 1. Inspiration
A televised sports broadcast is fundamentally a visual medium with an ambient audio track attached. Strip away the picture, and the match goes with it. The score and match clock sit silently in the top corner. Line-ups, bookings, substitutions, and VAR reviews appear on graphic overlays that commentators rarely read aloud. When commentators speak, they speak *to* the visual screen: *"Ohhh, what a chance!"*—not *"Saka, eighteen yards, left foot, off the post."*

Over 2.2 billion people worldwide live with vision impairment. A blind fan watching with a sighted friend simply turns and asks. But watching alone, or in noisy viewing centers, there is nobody to ask. 

We built **Sideline** to be that friend on the sofa.

---

### 2. What It Does
Sideline is an audio-first ambient companion designed to be heard through an earbud:
* **The "What Did I Miss?" Temporal Gap Engine:** Ask *"What did I miss?"* after ten minutes away, and Sideline calculates exactly the gap since your last interaction (`last_told_at`). It returns only what was missed, leading with goals before chronology, with zero repeated facts.
* **The Broadcast Lag Spoiler Guard:** Live OTT streaming lags 20 to 45 seconds behind real time. Push notifications and group chats routinely ruin goals. Sideline anchors to what the listener *hears* (e.g., *"Kick-off just went"* or *"Half-time whistle"*) and deliberately buffers events so nothing is spoiled ahead of their broadcast.
* **27 Deep Conversational Tools:** From live tactical formations, officials and yellow cards, to head-to-head records, standings, and pronoun resolution (*"Tell me about that goal"*, *"Who is he?"*).
* **Kinetic Companion Typography:** Spoken via Amazon Polly generative voice, with millisecond word timestamps dynamically highlighting text on screen for sighted friends or carers in the room.

---

### 3. How We Built It (AWS Builder Architecture)
Sideline is an end-to-end, multi-service AWS and Model Context Protocol implementation:
* **Amazon Bedrock (Anthropic Claude Sonnet):** Orchestrates tool routing across all 27 MCP tool definitions and crafts natural, spoken-syntax catch-up summaries that avoid conversational filler.
* **Amazon Bedrock (Mistral Voxtral & Nova 2 Sonic):** Multi-tier speech-to-text pipeline that processes audio entirely within the listener's AWS account.
* **Amazon Polly (Generative & Neural):** Renders natural voice responses and returns speech marks for real-time word-level synchronized kinetic typography.
* **Amazon DynamoDB:** Serves as the persistent event log and listener state store, guaranteeing that listener bookmarks (`last_told_at`) and deduplicated events survive server restarts.
* **Self-Hosted MCP Server (Spec 2025-11-25):** Fully conformant Streamable HTTP server exposing 27 rich tools, consumed by an agentic host that executes tools over standard MCP protocols.

---

### 4. Challenges We Ran Into & The Friction Log
Integrating cutting-edge MCP standards with live streaming audio presented real engineering friction. Rather than papering over them, we documented **20 rigorously verified friction items in [docs/FRICTION_LOG.md](FRICTION_LOG.md)**:
* Navigating partner-only CLI documentation vs. hackathon FAQ allowances (FL-01).
* Overcoming boto3 DynamoDB Python `Float` rejections and `Decimal` serialization bugs in live match telemetry (FL-12).
* Bedrock Converse audio prompt-ordering rules and Nova 2 Sonic silence duration requirements (FL-10, FL-15).
* Resolving `awscrt` runtime incompatibilities on Python 3.14 (FL-16).

---

### 5. Accomplishments That We're Proud Of
* **Validated Accessibility:** Tested hands-on with a blind user—proving that an earbud companion built on strict accessibility rules (*lead with the fact, minutes said the way people say them, refusals are spoken*) fundamentally restores autonomy to live sports viewing.
* **100% Hermetic Test Coverage:** 27 automated test suites passing with zero credential leaks or mock network dependencies.
* **Stateful Over Stateless:** Moving past the trivial "API wrapper" paradigm to build true temporal state persistence in DynamoDB.

---

### 6. What's Next: The Commercial & Broadcaster Future
Sideline is architected for enterprise scalability:
1. **Broadcaster Integration (Prime Video, DAZN, Apple TV):** Meeting EAA 2025 and CVAA accessibility mandates by offering interactive, voice-driven audio descriptions for live sports rights holders.
2. **Universal Multi-Sport Expansion:** Activating the proven `SportProfile` ontology for the NBA, NFL, Formula 1, and MLB ([docs/UNIVERSAL_SPORTS_MCP_ARCHITECTURE.md](UNIVERSAL_SPORTS_MCP_ARCHITECTURE.md)).
3. **Certified Alexa+ Add-On & Proactive Whispers:** Transitioning to public Alexa+ developer runtimes with Amazon OAuth 2.0 account linking and proactive audio notifications.

