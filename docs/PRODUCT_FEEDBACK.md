# Product feedback

The hackathon requires, for **each tool, API or SDK used**: what you used
it for, what worked well, what needs work, how onboarding felt (zero to
hello world), and whether you would build with it again, and why.

**How to read this page.** Every statement here is something a test or a measurement in this repository backs
(the README's verification table, [SPEECH.md](SPEECH.md), `make aws-check`), something read in the cited
documentation on the stated date, or something we ran into while building. Each section ends with whether we
would build with it again.

AWS services used must also be described in this answer on the Devpost
form (rules, AWS Builder mini challenge).

---

## 1. Alexa+ MCP add-on documentation (read; the toolkit itself was not usable)

**Used for** Designing the server to the Alexa+ requirements: the
[QuickStart](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html),
[Account Linking](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html)
and the Design Guide pages on
[tools and schema](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-tools-schema-data-design.html)
and the [conversation surface](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-conversation-surface.html),
read 2026-10-12. **The CLI, MCP Toolkit and Web Simulator were never used**:
the hackathon FAQ says they are partner-only.

**What worked well**
- The Design Guide's tool rules are concrete and usable: one customer
  intent per tool, a description that says when to call it, no overlapping
  tools, declare only parameters you honour, always return something.
- The QuickStart states the protocol version (2025-11-25), the transport
  (Streamable HTTP) and a response-time target (500 ms) plainly.

**What needs work** (each is a friction-log entry with its evidence)
- Access: the setup pages show CLI commands without saying the tooling is
  partner-only (FL-01).
- The 401 rule contradicts the MCP authorization spec and says so only by
  omission (FL-02).
- A 500 ms target with no pattern for tools whose responses a model composes (FL-03).
- Whether a server can speak first is not stated on the conversation-surface page (FL-04).

**Onboarding** Reading the docs to a clear picture of the requirements was
quick. Discovering that none of the tooling is reachable took the FAQ.

**Would we build with it again?** Yes. The tool rules are the best part of the docs and shaped how we split
Sideline into single-purpose tools (twenty-seven now). We would build on it as soon as the toolkit is open to everyone, and we
would be glad to test it. Until then we can only build to the documented requirements.

## 2. Model Context Protocol, spec 2025-11-25, Streamable HTTP

**Used for** The server itself ([sideline/mcp/server.py](../sideline/mcp/server.py)),
written with the standard library, no SDK.

**Evidence** `tests/test_mcp_protocol.py` passes nine checks: initialize
and session id, notification gets 202 with no body, `tools/list`, a tool
call, invalid-params rejection, method-not-found, unknown session gets 404,
batch requests, and DELETE ends the session. `tests/test_mcp_client.py` adds
that the voice agent's tool calls really cross the endpoint. These are *our own* conformance
tests, written from our reading of the spec; no official suite was run
(none was found).

**What worked well** The spec is short and precise about the parts that matter: the session id header, a 202 with
no body for notifications, and a clean split between protocol errors and tool errors. That last one let us return
"the feed is unavailable" as a result the agent can speak, not as a crash.
**What needs work** There is no official conformance suite, so we wrote our own and could not tell whether we had
read the spec the way its authors meant. A reference test runner would remove that doubt. Optional parts, such as
what a server does with `GET /mcp`, were the places where we had to decide for ourselves.
**Onboarding** Quick. The spec was enough on its own to write the server on the standard library with no SDK.
**Would we build with it again?** Yes. It is small enough to implement by hand, and that is why Sideline has no
dependencies to install.

## 3. Amazon Bedrock, Converse API, Nova Micro

**Used for** Composing the catch-up paragraph, long-absence milestones and
translation ([sideline/language/bedrock.py](../sideline/language/bedrock.py)), and
as the voice agent that chooses tools through Converse tool use
([sideline/language/agent.py](../sideline/language/agent.py)). Guarded: a generated
scoreline that disagrees with the real one is refused (tested in
`tests/test_language.py`).

**Status: verified on one account, not exhaustively.** `make aws-check` on
2026-10-13 confirmed a Nova Micro response, agent tool use and a live
catch-up. Two runs took about 2.1 s and about 1.5 s for the "ready" call;
this is not a latency guarantee or a user-quality evaluation.

**Observed, hands-on:** the credentials in use were a Bedrock **API key**,
which AWS backs with an IAM user (`BedrockAPIKey-...`). That user could
call Bedrock and Polly but was denied DynamoDB, Secrets Manager,
CloudFormation, ECR, Lambda and CloudWatch, and the account returned
`SubscriptionRequiredException` for Transcribe and App Runner. So a
Bedrock API key gets you to a first answer quickly, but it is not a
credential for the rest of an AWS build. We did not find that stated where the key is created, and we only
learned it when DynamoDB refused us. A one-line note there would have saved us time.

**What worked well** Nova Micro is fast and cheap enough to sit inside a voice loop (about 1.5 to 2.1 s a call),
and Converse tool use worked on the first attempt: the model read our MCP tool schemas and picked the right tool.
That made the voice agent small. It also writes a clear spoken paragraph when it is told the facts and told not to
add any.
**What needs work** A small model will sometimes write a wrong scoreline or refuse, so we check every answer
against the real score and retry once. A built-in way to constrain output to given facts would make that guard
unnecessary. The access flow could say more plainly which models are ready to use on a new account.
**Speech models on Bedrock.** Mistral Voxtral accepts audio through Converse and is now our speech-in model: see 5a.

**Onboarding** Short. Most of the time went on working out the credential difference above; after that it was one call.
**Would we build with it again?** Yes. It is the part Alexa+ cannot do for us: turning a stretch of match events
into one spoken paragraph.

## 4. Amazon DynamoDB

**Used for** Listener state and the match event log, single table
([sideline/state/dynamo.py](../sideline/state/dynamo.py), table definition in
`scripts/create_table.py`).

**Status: verified on a real table, 2026-10-13** (`us-east-1`, on-demand,
TTL on). After following a match and being told things at minute 12, a
brand-new process read the same marker back; the next catch-up covered
exactly 12' to 64', and re-polling twice added no duplicates. The first
real run also failed in two ways the in-memory store and our tests had
hidden, now fixed and pinned by `tests/test_dynamo.py`:
1. boto3 rejects Python floats (`Float types are not supported. Use Decimal
   types instead.`), and every event carries a float timestamp, so the poller
   logged **zero** events. Reads come back as `Decimal`, which JSON cannot
   encode.
2. The conditional write that dedupes events keyed on an id that live
   providers mint fresh on every read, so it would never have fired.

Setup note: before this, the IAM user was denied `ListTables`; a policy
([AWS_SETUP.md](AWS_SETUP.md), Step 4) fixed that.

**What worked well** One table, on-demand billing and a TTL covered everything: the listener's marker, the event
log and expiry. A restart no longer loses what someone has been told, which is the whole point of the product.
**What needs work** The float error is the sort of thing that only appears against a real table, because local
fakes accept floats. Documenting it next to the first `put_item` example would save the next person an hour.
**Onboarding** Short once the IAM policy was right. The `ListTables` denial was the only stumble.
**Would we build with it again?** Yes. It is the right size for per-listener state.

## 5. Amazon Polly (speech out), and Amazon Transcribe (tried, not used)

**Used for** Polly: speech out with word-level speech marks
([sideline/voice.py](../sideline/voice.py)). Transcribe was tried for speech in and
removed.

**Status: Polly verified, Transcribe blocked.** On 2026-10-13 a real Polly
call (Amy, neural) returned 14 KB of audio and word-level speech marks.
Transcribe streaming returned `SubscriptionRequiredException`: "The AWS
Access Key Id needs a subscription for the service", even though Polly
worked from the same credentials, so it is an account state and not an IAM
gap (see FL-08). App Runner returned the same error on the same account.
Rather than wait on a support case, speech in runs on Bedrock models instead
(5a and 5b below). Our own `make aws-check` had been reporting "speech in: ok" from a
capability check alone; it now makes a real round trip through the provider in use.

**Polly: what worked well** The neural voice is clear at speed, which matters to a listener who relies on it, and
the word-level speech marks let the page highlight each word as it is spoken. Both came back in a single call.
**Polly: what needs work** Nothing blocking. Marks and audio are separate requests, so we make them in parallel.
**Polly: onboarding** Immediate. It worked on the first call with the same credentials as Bedrock.
**Would we build with Polly again?** Yes.

**Transcribe: would we build with it again?** We would like to, but not on the evidence we have: we could not get
past `SubscriptionRequiredException` (FL-08) and had to move on. We would try again if the error said what the
account needed.

### 5a. Amazon Bedrock, Mistral Voxtral Small (speech in, first choice)

**Used for** Hearing the listener: the clip is sent through Converse as an audio block and the words come back
([sideline/voice.py](../sideline/voice.py)). It is the first speech-in model, so the listener's audio never leaves the AWS
account. Full numbers and method: [SPEECH.md](SPEECH.md); the story is FL-15 in [FRICTION_LOG.md](FRICTION_LOG.md).

**What worked well** On 48 Polly-spoken clips, clean and noisy, it measured 0.0% word error clean and 1.4% in noise, 47 of 48
exact, every name right (48 of 48) and 0.8 s a clip: level with or ahead of the third-party recogniser we had started with
(0.4%, 3.7%, 43 of 48, 44 of 48 names, 1.4 s), which was then removed. It needs only boto3. **What needs work** It is a chat model, so it has to be asked
the right way: the audio must come **before** the instruction (the other way round it answers what it hears), a system
message is refused next to audio, and the small model is reliable where the mini one is not (24.6% and 39.1% error; it
answered questions). We guard against a model that talks instead of transcribing by dropping a reply with more words than
the clip could hold. It also does worse when given a vocabulary: a list of team names made it print the list or answer from it,
so we send none. The remaining risk is a short, wrong reply, which the length guard cannot see: none appeared in 48 clips.

**Onboarding** Our first try (2026-10-13, morning) failed and we rejected it: it answered "What's the score?" with an
invented score. Working out why took a controlled comparison, and the documentation we found did not say how to ask.
**Would we build with it again?** Yes, with the guard, and with a dedicated transcription mode we would not need it. Being
level with a specialised recogniser inside the account is the reason we dropped the third party entirely.

### 5c. Amazon Bedrock, Titan Text Embeddings v2 (tried, not used)

**Tried for** choosing which of 27 tools to show the model: embed the question and each tool's documented phrasings, offer the
nearest few. It runs on the account with no extra setup (`amazon.titan-embed-text-v2:0`, 256 dimensions, normalised). On 47
questions written to avoid the words in the tool descriptions it put the right tool in the top 8 for 42 of 47, about 0.5 s a
question warm; combined with word matching, 44 of 47. Too many misses to use as a filter and too slow to add to every turn, so
it is **not in the product** ([FINDER.md](FINDER.md), "Tried and rejected"). The result is worth stating because it is
tempting: embeddings found "who has the armband" for the squad tool but missed "anyone hurt for Celtic" for injuries. **Would
we use it again?** For a much larger tool list, or as a suggestion to the model, not as a hard filter.

### 5b. Amazon Bedrock, Nova 2 Sonic (speech in, fallback)

**Used for** Hearing the listener when Voxtral cannot ([sideline/voice.py](../sideline/voice.py)): audio streamed in,
transcript read back. Full numbers and method: [SPEECH.md](SPEECH.md).

**Status: verified with real calls, 2026-10-13.** From the Polly-spoken test
set, 17 of 24 clips exact on a first run; in the later head-to-head 8.5% word
error in noise and 4.2 s per clip, behind Voxtral's 2.6% and 1.2 s on the same
clips. The newer Nova 2.5 Sonic gave 3.4 s and 8% on a six-clip sample: a little quicker, no more accurate. Names it got right included Ødegaard and Bellerín; it misheard
Alderweireld and, in noise, Saka.

**What worked well** It transcribes: the user's words come back as text events
before it answers, which is what made it usable as an ear. Access needed no
model-enable step on this account, and it uses the same IAM credentials as the
rest of Bedrock.

**What needs work** Found only by building it:
1. It is **not in boto3**. It needs a separate package
   (`aws-sdk-bedrock-runtime`, Python 3.12+) and `awscrt`; the default
   transport fails with a clear `UnsupportedTransportError`, which helped.
2. The Python config cannot be built directly (`ConfigError: ... Use await
   AsyncBedrockRuntimeConfig.resolve(...)`), and the transport option is
   `transport=`, not `http_client=`; neither is obvious from the type names.
3. Closing the prompt right after the audio silently returns nothing. It waits
   to hear silence, so a trailing 2 s of silence is needed, which is also most
   of its latency for a short question.
4. It always tries to answer; for transcription only, you must tell it to say
   one word and stop reading. A plain transcription mode would be simpler.
5. A Bedrock **API key** alone was not used here: IAM credentials were. We did not test whether a bearer token
   works for streaming.

**Onboarding** A first transcript took a few attempts, mostly the points above, and then it was dependable.

**Would we build with it again?** Yes, as the in-account fallback: it is accurate on names and needs no extra vendor. It
is about three times slower than Voxtral (we stream 2 s of silence so it knows the clip has ended), so it is second. A plain
transcription mode, with no silence to wait for, would make it the obvious default. The SDK also said "awscrt is not
installed" when it was, on a new Python (FL-16).

## 6. Sportmonks (live football data): hands-on findings

**Used for** Today's fixtures, live events, line-ups, the referee, head to head, tables, statistics and a player's
season ([sideline/providers/sportmonks.py](../sideline/providers/sportmonks.py)). Run against the live service on
2026-10-13 on the **Free plan** (four leagues, 180 calls an hour), on a real finished match.

**Added after a conversation with a real listener's questions (2026-10-14).** Three more reads, all on the free plan, all
checked live on a real team: a team's fixtures over any window (`fixtures/between/{from}/{to}/{teamId}`: 8 results in the last
120 days and 5 matches in the next 30 for Celtic), a team's season statistics (126 statistic rows, the latest season has games,
wins, goals, clean sheets, possession) and a squad with shirt numbers, positions, captain and, through `coaches.coach`, the
manager. Two details that cost time: `sidelined.sideline` is an include on a fixture but not on a team (HTTP 404, "The
requested include 'sideline' does not exist on Sidelined"), and the squad endpoint gives player ids until you ask for
`player.position`. The rate limit is per kind of entity, so a squad lookup does not use the fixture budget.

**What worked well** One request returns a fixture with its events, line-ups, formations, state and score through
`include`, so a followed match costs one call per poll. The per-hour limit comes back in every response
(`rate_limit.remaining`, `resets_in_seconds`), which is how a free plan should behave. Substitutions say who came on
and who went off, goals name the assist and the running score, and VAR decisions come with a plain note.

**What needs work** Found only by running against real data:
1. The pricing page does not say what the free plan includes; we learned it (four leagues, 180 a hour) from the
   dashboard and then from the `leagues` endpoint.
2. An empty day is an HTTP 200 with a `message` saying "you may not have access", which reads the same as "nothing
   on": the caller cannot tell a quiet day from a plan limit.
3. The free plan's statistics have possession, corners and cards but no shots or fouls, with no way to know before asking.
4. The `starting_at` time is a string with no zone (UTC); a timestamp field exists and is safer.
5. Win estimates are an add-on, so a match preview cannot say who is favoured.

**Onboarding** Quick once the token existed; the docs are open without an account, which helped.
**Would we use it again?** Yes for a hackathon-sized project: the hourly limit cannot be spent in a day the way a daily
one can (FL-14).

## 7. Devpost and the hackathon materials

**What worked well** The rules page is specific about submission
requirements, judging stages and criteria, and the FAQ answers the
partner-only question directly.

**What needs work** The FAQ still explains how to request AWS credits while
the rules page says the codes ran out on 7 October (FL-05).

**Would we do it again?** Yes. The judging criteria were clear from the start, and the FAQ saved us from building
the wrong thing for the Alexa+ track.
