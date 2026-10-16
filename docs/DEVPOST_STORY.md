# Devpost, "Project details" page: what to paste

Written for: the Devpost judges, who may read only this page, the images and the video. Paste the block under **About the
project** into the Markdown box. Every figure is in the repository (the file named after it); nothing here is estimated.
Cut or add before you paste if anything has changed since 16 October 2026.

---

## About the project (paste this)

## Inspiration

You want the score. So you stop what you are doing, unlock your phone, open an app, search for the match, scroll. Or you
just ask. For someone who cannot see a screen, asking is not a shortcut: it is the only way in. A televised match is a
picture with an audio track attached. The score sits in a corner, the line-ups flash on a graphic nobody reads out, and
the commentary talks to the picture ("what a chance!"). A blind fan watching with a friend turns and asks. Alone, there
is nobody to ask. Sideline is that friend, and the same friend helps anyone whose hands or eyes are busy, or who would
simply rather not search and type to find out what is happening.

## What it does

You ask out loud, it answers in a sentence or two, and you can interrupt at any time.

- **It remembers you.** The server keeps what each listener has already been told, so "what did I miss?" needs no time
  range and never repeats itself.
- **It never spoils.** Tell it your stream is behind and it holds back every goal your picture has not reached.
- **It says what it knows and what it does not.** Every fact comes from a tool, never from a model's memory. It will tell
  you the feed has no referee, no honours, no half-time score, no play-by-play for an NFL game, and it will not guess.
- **Five sports, one set of tools:** football, basketball, American football, hockey and baseball. The clock changes its
  own words (90', Q3, P2, an inning), a player's night comes from the box score, and league leaders, standings,
  schedules, line-ups and injuries work the same way.
- **A screen for the people who can use one.** A bare score strip with a full-width timeline, a pitch of the line-ups drawn
  home-left and away-right, large type and high contrast, a typing mode that still reads the answer aloud, and live
  commentary that never talks over you.

## How we built it

An MCP server (spec 2025-11-25, Streamable HTTP) written in standard-library Python, 30 tools, in one folder. A web page
plays the part of Alexa+, so it can be tried by voice. Four AWS services do real work:

- **Amazon Bedrock:** Amazon Nova Pro chooses the tool in the simulator, from a shortlist of the server's tools picked
  for each question (it picked the intended tool on 77 of 79 phrasings in our routing check); Mistral Voxtral and Amazon
  Nova 2 Sonic turn speech into text.
- **Amazon Polly:** the voice, with word timings so the screen follows along.
- **Amazon DynamoDB:** one table with each listener's memory and the match event log, behind a write-through cache after we
  measured the round trip from Mauritius.
- Live data from ESPN's public endpoints. Live data is cached for seconds; a finished match is kept for hours.

The official MCP Python SDK client connects to it, lists the tools and calls them. It also runs on its own: a test copies
the `sideline/` folder alone to an empty directory and starts it there.

## Challenges

We kept a friction log of **28 entries** (task, steps, expected, actual, severity, workaround, suggestion) and **9 feature
requests**. The add-on tooling is partner-only, so we built a faithful simulated client. A "one attempt" setting in the
Bedrock SDK was two. A first question took 11 seconds because 26 DynamoDB calls ran in a row at about 340 ms each. We told a
listener the wrong team had scored, because we believed a goal list over the feed's own score. Our simulated assistant was
slower than we had documented. For a while a smaller 3B speech model shipped by mistake and answered questions instead of
writing them down; we found it in the logs and switched back.

The most useful thing we did was ask it the questions fans actually ask, **174 of them on real matches** (50 about one
football match, 24 across the other four sports, and 100 more across all five), read every answer, and fix the tools. The first pass was poor: 23 of the first 50 were weak, and in the second batch a false "Did you mean...?" blocked
about 15 of 100 questions. We fixed the tool descriptions and the lookups, added league leaders, a player's night, who
pitched and the playoff series, and re-asked. The final run of the 100 was 83 good, 13 honestly "not in the feed", 3
partly right and 1 wrong. Across all 174: 129 good, 21 honest, 9 partly right and 15 wrong. Every question and answer is
in `docs/CURIOSITY_QA.md`, including the ones that were wrong.

## What we are proud of

- A server that holds what no client can: per-listener memory and a clock-exact spoiler guard, both under test.
- Truth over fluency: it declines rather than guesses, and says so.
- **68 offline test suites** that need no network or credentials, 174 real questions with their answers published, a routing
  check across four Bedrock models, and the official SDK run against the server.
- Candour: the README lists what is not done. It is not on real Alexa+, there is no OAuth, it serves one listener per
  deployment, and the data source is unofficial.

## What we learned

A tool's description is product surface: most of our routing failures were fixed by saying what a tool is *not* for. The
model picks the always-offered tool for anything out of scope, so out-of-scope questions need a plain answer, not a tool.
Live means live: caching a score for a minute makes an assistant wrong in front of the person who trusts it.

## What's next

1. Host it and connect a real client: it speaks standard MCP, so any MCP host can use it, and the README has the steps.
   The Alexa+ add-on with account linking is the step Amazon controls.
2. More leagues and sports as new profiles, not rewrites.
3. A licensed feed as a new provider behind the same interface, and answers in the listener's own language (already a
   stored preference).
4. A way for a server to speak first, so "goal" can arrive the moment it happens, still held back to the listener's picture.
5. The same design, a marker per listener and a list of what changed since they last asked, suits a delivery, a flight or
   a market.

---

## Built with (up to 25 tags)

`Python`, `Model Context Protocol`, `Amazon Bedrock`, `Amazon Nova Pro`, `Amazon Nova Sonic`, `Mistral Voxtral`,
`Amazon Polly`, `Amazon DynamoDB`, `AWS`, `Alexa+`, `ESPN public API`, `JavaScript`, `Web Audio API`, `HTML5 Canvas`,
`boto3`, `Node.js (tests)`, `Streamable HTTP`, `JSON-RPC`

## "Try it out" links

1. `https://github.com/NelsonFodjo/sideline` (the repository; the README's "Run it" is the judge's path: `make run`, then open
   `http://127.0.0.1:8765/`; the live data needs no key)
2. The README's friction log: `https://github.com/NelsonFodjo/sideline/blob/main/docs/FRICTION_LOG.md`
3. The 174 questions: `https://github.com/NelsonFodjo/sideline/blob/main/docs/CURIOSITY_QA.md`

(Make the repository public first, and check the links in a private window after pushing.)

## Image gallery (up to 15, 3:2 is best, 5 MB each)

Take these from [docs/video/screenshots/](video/screenshots/), in this order. They were built from real results of 15
October 2026 in a preview copy of the page, not on a real microphone:

1. `02-following-a-match.png`: the strip, the sport, the date, the eye clear
2. `10-lineups.png`: the line-ups, one spoken sentence
3. `03-timeline-open.png`: the timeline, the ground and the date
4. `11-basketball-following.png`: Knicks 122-120 Raptors, in quarters
5. `13-american-football-following.png`: Broncos 17-14 Seahawks
6. `12-basketball-lineups.png`: starters and bench in a sport with no formation
7. `09-dev-log.png`: every answer traceable: tool, arguments, timings
8. `06-high-contrast.png` and `07-typing-mode.png`: made for people who cannot rely on sight
9. `15-lineup-highlight.png`: the line-ups, with each player lit as she says the name
10. A terminal showing `make test` ending "all suites passed" (take it yourself)

If the gallery wants 3:2, crop the screenshots (they are 1440 x 860, about 5:3).

## Video demo link

The public YouTube or Vimeo URL once recorded. See [VIDEO_GUIDE.pdf](VIDEO_GUIDE.pdf).

---

# Devpost, "Additional info" page: what to put

Judges and organisers see this page; only the fields marked *(public)* show in the gallery. **you** marks the answers only
you can give. Everything else is ready to paste and comes from the file named next to it.

## Upload a file

Optional. If you upload anything, zip [FRICTION_LOG.md](FRICTION_LOG.md), [FEATURE_REQUESTS.md](FEATURE_REQUESTS.md) and
[PRODUCT_FEEDBACK.md](PRODUCT_FEEDBACK.md) (well under 35 MB). The repository link already covers it.

## Submitter type, organisation, country, Canada

- **Submitter type:** **you** (individual or team, whichever is true).
- **Organization name:** `N/A`, unless you are entering on behalf of an organisation. **you** decide.
- **Country of residence** *(public)*: **you**. The docs say the latency was measured from Mauritius; pick your own country.
- **Canadian province:** `N/A` (unless a team member lives in Canada).

## Primary track *(public)*

Tick **Alexa+** only. Sideline is a self-hosted MCP server built for the Alexa+ add-on requirements, demoed through a
simulated Alexa+ because the add-on tooling is partner-only. Do not tick Fire TV, Bee or Ring.

## Code repository URL

```
https://github.com/NelsonFodjo/sideline
```

Make it public first and check that GitHub's About box shows the **MIT** licence.

## New or existing before 31 August 2026?

**New.** The "what did you update" box can stay empty, or paste:

```
New project. Nothing predates the submission period: the first commit is dated 2026-10-12.
```

## AWS Builder Mini Challenge

**Yes.** Paste this into "Which AWS services did you incorporate and how?":

```
Four AWS services do real work in Sideline. Each was run against a real account on 2026-10-13.

1. Amazon Bedrock, Amazon Nova Pro (amazon.nova-pro-v1:0), through the Converse API.
   - It is the voice agent in our simulated Alexa+. It reads the MCP server's tools/list (30 tools) and calls the
     tools through Converse tool use. For each question it is offered a shortlist: four core tools plus up to four
     more picked by keyword. A few plain questions ("what's the score?") are answered by a fixed pattern with one
     tool and no model call.
   - In a 79-phrasing routing check, through the same shortlist, it called the intended tool on 77.
   - It also writes the spoken "what did I miss" catch-up. A generated scoreline that disagrees with the real score
     is refused, and that check is under test.
   - Code: sideline/language/bedrock.py and simulator/agent.py.
   - We also compared Claude Sonnet 4.5, Claude Haiku 4.5, Nova Micro and Nova Lite: docs/BEDROCK.md.

2. Amazon Bedrock, Mistral Voxtral Small (speech in, first choice) and Amazon Nova 2 Sonic (speech in, fallback).
   - The listener's audio never leaves the AWS account.
   - Voxtral gets the clip as an audio block through Converse. On 48 Polly-spoken clips, clean and noisy, it got
     0.0% word error on clean clips and 1.4% in noise, every name right, at 0.8 s a clip.
   - Nova 2 Sonic streams the audio through aws-sdk-bedrock-runtime. It is the fallback.
   - Code: simulator/voice.py. Method: docs/SPEECH.md.

3. Amazon Polly (generative voice, neural fallback).
   - It is the speech out.
   - It also returns word-level speech marks, so the screen highlights each word as it is spoken.
   - Code: simulator/voice.py.

4. Amazon DynamoDB.
   - One on-demand table with TTL. It holds each listener's marker (what they have already been told), the match
     event log (deduplicated, expiring after 48 hours) and match snapshots. What a listener has heard survives a
     restart.
   - A cold first question took 11 s: 26 sequential calls at about 340 ms each from Mauritius to us-east-1. We
     rebuilt it around parallel calls and a write-through cache, which brought the tool to 4.5 s.
   - Code: sideline/state/dynamo.py. Two real-table bugs (floats versus Decimal, a dedupe key that never matched)
     are pinned in tests/test_dynamo.py.

Not used: AgentCore, Strands, Kiro and SageMaker. Transcribe was tried, but the account returned
SubscriptionRequiredException (friction log FL-08).
Details: docs/HACKATHON.md ("AWS services") and docs/PRODUCT_FEEDBACK.md.
```

## Open Source Mini Challenge

**No.** Leave the four Open Source fields empty. No separate open-source project or outside contribution exists
([HACKATHON.md](HACKATHON.md), "Open Source mini challenge: not entered"). Switch to Yes only if you make a real
contribution before the deadline.

## [Optional] Feature requests

```
Full list with evidence: https://github.com/NelsonFodjo/sideline/blob/main/docs/FEATURE_REQUESTS.md

FR-01 (Critical): State whether an Alexa+ MCP add-on may speak first, and let users opt in.
  A live-sport companion for blind listeners wants to say "goal" when it happens. Without that, the listener has to
  suspect something happened before they can ask. Accessibility and safety alerts hit the same limit.
FR-02 (Important): Put "preview, select partners only" on every setup page that shows alexa-ai commands.
FR-03 (Important): Document why the QuickStart's 401 leaves out WWW-Authenticate, unlike the MCP authorization spec,
  and when that will change.
FR-04 (Important): A pattern for tools whose answers a model composes, which cannot meet the 500 ms target.
FR-07 (Important): Guidance on how many MCP tools a voice assistant can reliably choose among. With 30 tools, routing
  needed real work.
FR-05 (Nice-to-have): A "this UI is supplementary" signal for MCP Apps.
FR-06 (Nice-to-have): A published MCP conformance suite for hand-written Streamable HTTP servers.
FR-08 (Nice-to-have): State the retry behaviour and error types of Bedrock Converse calls.
FR-09 (Nice-to-have): Make truncation visible in ESPN's public scoreboard. This is a third-party API, not an AWS one.
```

## [Optional] Friction log

```
https://github.com/NelsonFodjo/sideline/blob/main/docs/FRICTION_LOG.md
```

It has 28 entries. Each gives the task, the steps, expected versus actual, the severity, the workaround and a
suggestion, and the summary table comes first.

## [Optional] Project testing link

No hosted demo exists, so leave it empty or use the repository URL. The README's "Run it" is the testing path:
`git clone`, `make run`, open `http://127.0.0.1:8765/`.

## Feedback question 1: which developer tools, APIs and SDKs did you use, and for what?

```
- Alexa+ MCP add-on documentation (QuickStart, Account Linking, Design Guide). We designed the server to its rules.
  The CLI, MCP Toolkit and Web Simulator are partner-only, so we could not use them.
- Model Context Protocol, spec 2025-11-25, Streamable HTTP. The server itself: 30 tools, written by hand on the
  Python standard library. We checked it with the official MCP Python SDK client.
- Amazon Bedrock Converse API with Amazon Nova Pro. The voice agent that chooses tools, and the spoken catch-up.
- Amazon Bedrock, Mistral Voxtral Small and Amazon Nova 2 Sonic (aws-sdk-bedrock-runtime and awscrt). Speech in.
- Amazon Polly. Speech out, with word-level speech marks.
- Amazon DynamoDB. Listener state and the match event log.
- boto3 and botocore. Every AWS call.
- ESPN's public API (unofficial, no key). All live data across five sports. It replaced Sportmonks, which we used
  first.
- Open-Meteo. The weather at the ground for a match preview.
- Browser Web Audio and Canvas. The simulated Alexa+ page.
- Tried and dropped: Amazon Transcribe (account not subscribed), Titan Text Embeddings v2 (tool shortlisting missed
  too often) and Bedrock prompt caching on Nova Micro (refused on tools).
```

## Feedback question 2: what worked well?

```
- Alexa+ docs: the Design Guide's tool rules are concrete. One intent per tool, a description that says when to call
  it, no overlapping tools, always return something. They shaped how we split Sideline into 30 tools. The QuickStart
  states the protocol version, the transport and the 500 ms target plainly.
- MCP spec: short and precise. It was enough on its own to write the server with no SDK. The split between protocol
  errors and tool errors lets us return "the feed is unavailable" as something the agent can say, instead of a crash.
- Bedrock Converse (Nova Pro): tool use worked cleanly from our MCP schemas. It called the intended tool on 77 of 79
  phrasings, offered a shortlist of the 30 tools for each. Calls take about 1.5 to 2.1 s.
- Voxtral on Bedrock: 0.0% word error on clean clips and 1.4% in noise, 48 of 48 names right, 0.8 s a clip. That
  matched the third-party recogniser we started with, so we removed it and speech stays inside AWS. It needs only
  boto3.
- Nova 2 Sonic: accurate on names, no model-enable step, the same IAM credentials as the rest of Bedrock.
- Polly: worked on the first call. The neural voice is clear at speed, which matters to a listener who relies on it,
  and the word timings let the screen follow along.
- DynamoDB: one on-demand table with TTL covered the marker, the event log and expiry. A restart no longer loses what
  a listener has been told.
- ESPN: one request lists every football match on a day, with no key and no quota we hit. Answers came back in 0.4 to
  1.5 s.
```

## Feedback question 3: what needs work?

```
Every item is a friction-log entry with evidence:
https://github.com/NelsonFodjo/sideline/blob/main/docs/FRICTION_LOG.md

- Alexa+: the setup pages show alexa-ai commands without saying the tooling is partner-only (FL-01). The 401 rule
  differs from the MCP authorization spec without saying so (FL-02). There is no pattern for model-composed tools
  under 500 ms (FL-03). The docs do not say whether a server may speak first (FL-04).
- MCP: there is no official conformance suite. Reviewing our server against the spec found eight deviations in our
  own code (FL-24).
- Bedrock: a Bedrock API key cannot be used for DynamoDB, Lambda and other services, and nothing says so where the
  key is created (FL-11). Nova Micro returns "Service capacity limit has been reached" with no documented retry
  policy (FL-18). A cachePoint in toolConfig.tools is refused on Nova Micro (FL-19). Tool-list size guidance for a
  model host is missing (FL-25).
- botocore: retries={"max_attempts": 1} makes two attempts. You need total_max_attempts (FL-21).
- Voxtral: it is a chat model. The audio must come before the instruction, a system message next to audio is
  refused, and it answers the question instead of transcribing it unless asked the right way. None of this is
  documented (FL-13, FL-15).
- Nova 2 Sonic: it is not in boto3 (a separate package, Python 3.12+). The config needs an async resolve() call. It
  needs 2 s of trailing silence, which is most of its 4.2 s latency. It has no transcription-only mode (FL-09,
  FL-10). The SDK said "awscrt is not installed" when it was (FL-16).
- DynamoDB: put_item rejects Python floats, but local fakes accept them, so every event went silently unlogged
  until we used a real table (FL-12). There is no guidance on per-call latency from a distant region. 26 sequential
  calls made a first question take 11 s (FL-26).
- Transcribe: SubscriptionRequiredException even with full IAM permissions, and the error does not say what the
  account needs (FL-08).
- ESPN (third party): no documentation, a silent 100-match cut-off, and an event list that is incomplete for the
  score (FL-23, FL-28).
```

## Feedback question 4: how was onboarding (zero to hello world)?

```
- Alexa+ docs: reading them to a clear picture of the requirements was quick. Finding out that none of the tooling
  is reachable took the FAQ.
- MCP: quick. The spec alone was enough to write the server by hand.
- Bedrock (Nova Pro): short. Most of the time went on finding out that the Bedrock API key covers Bedrock and Polly
  only. After that it was one call.
- Polly: immediate. It worked on the first call with the same credentials.
- DynamoDB: short once the IAM policy was right. The ListTables denial was the only stumble.
- Voxtral: the first try failed. It answered "What's the score?" with an invented score. Working out how to ask
  took a controlled comparison.
- Nova 2 Sonic: a first transcript took a few attempts (the package, the config and the silence). Then it was
  dependable.
- ESPN: about an hour to the first answer, and two days to learn its traps.
```

## Feedback question 5: would you build with these again?

```
Yes, for every AWS service we shipped:
- Bedrock: it does the one job Alexa+ cannot do for us, turning a stretch of match events into one spoken
  paragraph, and Nova Pro routes tools reliably.
- Voxtral: it keeps speech inside the account at specialised-recogniser accuracy.
- Nova 2 Sonic: it is a good in-account fallback. A transcription mode would make it the default.
- Polly: clear and fast, with word timings.
- DynamoDB: the right size for per-listener state, as long as the calls are made together.
- The MCP spec: small enough to implement by hand, which is why the server has no dependencies to install.
- Alexa+ add-ons: yes, as soon as the toolkit is open to everyone. We would be glad to test it. Until then we can
  only build to the documented requirements.
- ESPN: yes for a hackathon, no for a product. We would license a feed with a contract, and our provider interface
  makes that swap small.
- Transcribe: not yet. We could not get past SubscriptionRequiredException.
```

## Eligibility checkboxes

**you** Tick the three only if they are true for you and every teammate: age of majority, eligible jurisdiction, and not
an employee or agent of Amazon, Devpost or their affiliates.

## Which AI tools have you leveraged?

**you** List everything you used. This conversation shows **Claude Code**; add any others. Do not count the Bedrock
models above: they are part of the product. A starting line:

```
Claude Code (Anthropic) for writing code, tests and documentation. Inside the product: Amazon Nova Pro, Mistral Voxtral
and Amazon Nova 2 Sonic on Amazon Bedrock. We also compared Claude Sonnet 4.5 and Haiku 4.5 on Bedrock for tool routing.
```

## Level of learning, and AI value for your career

**you** Both are personal selections. The friction log and [CURIOSITY_QA.md](CURIOSITY_QA.md) are the evidence, if the
form asks you to back them up.

---

**Left out on purpose:** the earlier draft's line about a blind listener trying it in a first session. Put it back only if
the team will state it first-hand, in one sentence, with "one person, no measurements".
