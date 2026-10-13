# Friction log

> Specific task attempted, steps taken, expected vs actual, severity,
> workaround, suggestion. The rules award up to a 10% bonus, assessed by
> Amazon's team, so each entry here is something **verified against a
> cited source on a stated date**. Entries that are not yet backed by a
> hands-on run are in "Candidates" at the bottom and are **not** part of
> the log until you have hit them. Check every entry against your own
> experience before submitting.

Severity: **critical** blocks shipping · **important** costs real time ·
**nice-to-have** rough edge.

## Summary

| # | Task | Expected vs actual | Severity | Workaround | Suggestion |
|---|---|---|---|---|---|
| FL-01 | Follow the Alexa+ QuickStart to set up an add-on | Setup pages give `alexa-ai` commands with no note that the tooling is partner-only; the FAQ says so | critical | Self-hosted server demoed through our own web MCP client, as the FAQ describes | State "preview, select partners only" on every page that shows a CLI command |
| FL-02 | Pass the QuickStart authentication checklist | Checklist requires a 401 *without* `WWW-Authenticate`; the MCP authorization spec expects the header | important | Followed the QuickStart; test pins it | State the deviation, the reason, and when the header will be supported |
| FL-03 | Keep an LLM-composed answer inside the QuickStart's 500 ms target | Target stated once, no pattern for model-backed tools | important | Configurable model timeout; templates as the fast path | Document a pattern: cached summaries, streaming, or a longer budget for declared slow tools |
| FL-04 | Decide whether the server can tell a listener something unprompted | The conversation-surface page does not say whether servers may speak first | important | Designed for on-demand questions only | State it, for or against |
| FL-05 | Plan AWS usage for the AWS Builder challenge | Rules say credit codes ran out 7 Oct; FAQ still explains how to request them | important | Mock Bedrock in tests; spin services up only to test | Update the FAQ, or restore credits for the remaining window |
| FL-06 | Find guidance on live-content sync for voice agents | The two Design Guide pages read had nothing on a voice agent being ahead of a delayed broadcast | nice-to-have | `sync_broadcast_delay`, anchored on what the listener hears | Mention live-content latency in the conversation-surface guidance |
| FL-07 | Share a private repo with reviewers | FAQ documents the 7-day invitation expiry; the instinct is to invite early | nice-to-have | Public repo needs no invites; otherwise invite on submission day | Surface the expiry next to the repo URL field |
| FL-08 | Enable Amazon Transcribe streaming for the simulator | IAM full-access policy and `transcribe:*` permission were added, but streaming still returned `SubscriptionRequiredException` (also seen on App Runner, 2026-10-13) | important | Use browser speech recognition while investigating the AWS account/service response | Explain what account or service action resolves this exception, and distinguish it clearly from missing IAM permission |
| FL-09 | Add Nova 2 Sonic speech in to a Python service | Not in boto3: needs a separate package (`aws-sdk-bedrock-runtime`, Python 3.12+) and `awscrt`; the config cannot be built directly and the transport keyword is not the one the type names suggest | important | Read the SDK's errors until it ran; pinned in `voice.py` | Put the Python install, the `resolve()` config call and a minimal streaming example in the Nova Sonic docs |
| FL-10 | Use Nova 2 Sonic only to transcribe | Closing the input right after the audio returns nothing: it waits for silence, so a trailing 2 s of silence is required, which is most of the 4.2 s latency of a short question. It also always tries to answer | important | Append silence, instruct it to say one word, read only the transcript events | Offer a transcription-only mode, and document the silence requirement |
| FL-11 | Pick credentials for a first Bedrock call, then the rest of the build | A Bedrock API key (backed by an IAM user) called Bedrock and Polly but was denied DynamoDB, Secrets Manager, CloudFormation, ECR, Lambda and CloudWatch; nothing at the point of creation says so | important | Switched to IAM credentials with an explicit policy | State, where the key is created, that it is scoped to Bedrock and what to use for everything else |
| FL-12 | Store listener state in DynamoDB with boto3 | `put_item` rejects Python floats (`Float types are not supported`), and reads return `Decimal`, which JSON cannot encode; a local fake accepts both, so nothing failed until a real table was used (every event was silently not logged) | important | Convert on write and read; `tests/test_dynamo.py` pins it | Show the Decimal rule next to the first `put_item` example, and make the error name the attribute |
| FL-13 | Transcribe a spoken question with a speech-capable model on Bedrock (Mistral Voxtral via Converse) | It accepts audio but is a chat model: it answered a spoken question with an invented score instead of transcribing it (2 of 4 phrases correct on Small) | nice-to-have | Used Nova 2 Sonic and Groq instead | Add a transcription mode to Converse for audio models, or say clearly that they are chat-only |
| FL-14 | Build and test against a free football feed for a day | The first feed's free plan allowed 100 requests a day and 10 a minute, with only yesterday to tomorrow visible; the day's quota was spent before the build was done, so every question returned the feed's error | important | Replaced it with Sportmonks, whose free plan is limited per hour, not per day | State the per-minute and date-window limits beside the daily number, return remaining quota on every response, and offer a hackathon-sized free tier |

---

### FL-01 — Nothing on the setup pages says the toolkit is partner-only

**Evidence** [QuickStart](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html)
and [Account Linking](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html),
read 2026-10-12, versus the [Devpost FAQ](https://amazonappdev2026.devpost.com/details/faqs).

**Task** Set up an Alexa+ add-on for a self-hosted MCP server.

**Steps** Read both pages; wrote a setup guide around `alexa-ai configure`,
`alexa-ai new mcp`, `alexa-ai deploy`; designed OAuth account linking to the
stated requirements; later read the FAQ.

**Expected** The pages to say whether a hackathon participant can use the tools.

**Actual** The pages present the commands as available. The FAQ says the
Category SDK, MCP Toolkit, CLI and Web Simulator are "in preview and
available to select partners only", and that this "is called out on
Amazon's add-on docs home page, though it's sometimes missing from
individual setup-guide pages, which has caused some confusion".

**Severity** critical: part of the work was aimed at a path no participant can take.

**Workaround** A self-hosted MCP server and our own web page acting as an MCP client.

**Suggestion** Put the access note at the top of every page showing a CLI
command, and next to the Alexa+ link on the hackathon Resources page.

### FL-02 — The 401 rule contradicts the MCP authorization spec

**Evidence** QuickStart, read 2026-10-12: unauthenticated requests return
"401 Unauthorized without a `WWW-Authenticate` header", and "`WWW-Authenticate`
in 401 responses" is listed under not supported yet.

**Task** Implement the authentication checklist. **Steps** Compared the
checklist with the MCP authorization specification. **Expected** They agree.

**Actual** The spec expects a `WWW-Authenticate` challenge pointing at the
protected-resource metadata; the QuickStart requires its absence. Following
either breaks the other.

**Severity** important **Workaround** Followed the QuickStart; the behaviour
is pinned in `tests/test_auth.py` with a comment explaining why.

**Suggestion** Say explicitly that this deviates from the spec, why, and when
the header will be supported.

### FL-03 — A 500 ms target, no pattern for LLM-composed answers

**Evidence** QuickStart, read 2026-10-12: "round-trip query response under 500 ms".

**Task** Keep a Bedrock-composed catch-up inside the voice round trip.
**Steps** Read the target; looked for guidance on tools whose responses a
model composes. **Expected** A recommended pattern. **Actual** The target
is stated once, with no guidance. (The latency of a Bedrock call has *not*
yet been measured by us at the time; a real call later took about 1.5 to 2.1 s.)

**Severity** important **Workaround** Deterministic templates as the fast path,
and stating that a Bedrock catch-up takes about two seconds. **Suggestion** Document a
pattern for LLM-backed tools: precomputed summaries, streaming partial
results, or a longer budget for tools declared as slower.

### FL-04 — Whether a server can speak first is not stated

**Evidence** [Conversation Surface](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-conversation-surface.html),
read 2026-10-12: describes a turn-based model; does not address
server-initiated speech or notifications.

**Task** Decide whether the product can announce a goal unprompted.
**Steps** Read the page. **Expected** An explicit yes or no. **Actual**
Silence; the answer is inferred from the turn-based description.

**Severity** important: it decides the whole interaction model.
**Workaround** On-demand questions only. **Suggestion** State it.

### FL-05 — AWS credits: the rules and the FAQ disagree

**Evidence** [Rules](https://amazonappdev2026.devpost.com/rules), read 2026-10-12:
"October 7th Update: We are out of credit codes and will no longer be
accepting credit requests." [FAQs](https://amazonappdev2026.devpost.com/details/faqs),
same date: explains how to request $150 credits and says they can be applied
to Bedrock usage.

**Task** Plan AWS spend for the AWS Builder challenge. **Expected** A
consistent statement. **Actual** Two. **Severity** important
**Workaround** Test with mocks, spin services up briefly. **Suggestion**
Update the FAQ, or restore credits.

### FL-06 — No guidance on a voice agent running ahead of a delayed broadcast

**Evidence** Scope is limited: the Conversation Surface and Tools/Schema
design pages, read 2026-10-12, say nothing about it. Other pages were not read.

**Task** Answer "what's the score" without spoiling a goal the listener's
television has not shown. **Expected** Some mention of live-content latency.
**Actual** None found in those two pages. **Severity** nice-to-have
**Workaround** `sync_broadcast_delay`. **Suggestion** Name the problem in the
conversation-surface guidance.

### FL-07 — GitHub invitations expire in seven days

**Evidence** FAQ, read 2026-10-12: "invitations expire after 7 days, so add
reviewers around when you submit rather than weeks in advance".

**Task** Share a private repo. **Expected** An expiry that does not bite.
**Actual** Documented, easy to trip. **Severity** nice-to-have
**Workaround** A public repo with an open-source licence needs no invites.
**Suggestion** Surface the expiry next to the repo URL field.

### FL-08 — Transcribe subscription error persists after granting IAM access

**Evidence** Sideline server log, 2026-10-13: Amazon Transcribe streaming
returned HTTP 403 `SubscriptionRequiredException` with the message "The AWS
Access Key Id needs a subscription for the service." The AWS console
documentation for
[streaming setup](https://docs.aws.amazon.com/transcribe/latest/dg/streaming-setting-up.html),
checked 2026-10-13, identifies `transcribe:StartStreamTranscription` as the
required IAM action. During troubleshooting, the user added
`AmazonTranscribeFullAccess` and shared a policy allowing `transcribe:*`;
the same exception continued. No credentials or key material are recorded
here.

**Task** Enable speech input through Amazon Transcribe streaming in the
simulator. **Steps** Configured AWS credentials, used the `us-east-1`
region, added the Transcribe managed policy and a policy allowing
`transcribe:*`, restarted Sideline, and retried the microphone.
**Expected** Transcribe accepts the streaming request once the required
permission is granted. **Actual** AWS continued returning
`SubscriptionRequiredException`; the error does not identify what account
or service change is required.

**Re-observed 2026-10-13** with a real streaming call from `make aws-check`:
the same exception, while Polly worked from the same credentials, which
points at an account-level state rather than IAM. App Runner's
`ListServices` returned `SubscriptionRequiredException` on the same account.
Neither error says what to do about it.

**Severity** important: the simulator cannot use its configured AWS
speech-to-text path, despite the permissions troubleshooting.
**Workaround** Use browser speech recognition where available, or set
`SIDELINE_STT=off` to avoid repeated failing Transcribe calls. Browser
recognition may send audio to the browser vendor's service.
**Suggestion** Explain how to resolve this exception for the account, and
make the error distinguish service/account access problems from missing
IAM permissions.

### FL-09 — Nova 2 Sonic is not in boto3, and its config cannot be built directly

**Evidence** Sideline build, 2026-10-13, `sideline/voice.py`; numbers in [SPEECH.md](SPEECH.md).

**Task** Stream a listener's audio to Nova 2 Sonic from a Python service and read the transcript back.
**Steps** Tried the default boto3 Bedrock Runtime client; then the separate SDK; built its config.
**Expected** The same client we use for Converse. **Actual** boto3 does not offer it. It needs
`aws-sdk-bedrock-runtime` (Python 3.12+) and `awscrt`. The default transport fails with `UnsupportedTransportError`
(clear, which helped). The config cannot be built directly (`ConfigError: ... Use await
AsyncBedrockRuntimeConfig.resolve(...)`), and the transport option is `transport=`, not `http_client=`; neither
is obvious from the type names.

**Severity** important: the first transcript took several attempts. **Workaround** Followed the errors; the working
setup is in `voice.py`. **Suggestion** Add the Python install, the `resolve()` call and a minimal streaming example
to the Nova Sonic documentation.

### FL-10 — Nova 2 Sonic waits for silence, and always tries to answer

**Evidence** Sideline build, 2026-10-13; head-to-head against Groq in [SPEECH.md](SPEECH.md) (48 clips).

**Task** Use Sonic as an ear only: speech in, text out. **Steps** Sent audio and closed the prompt right after.
**Expected** A transcript. **Actual** Nothing: it waits to hear silence, so a trailing 2 s of silence is needed.
It also answers, so it has to be told to say one word and stop; the transcript arrives as text events before
that. In noise it measured 8.5% word error at 4.2 s per clip, against 3.7% at 1.1 s for Groq on the same clips.

**Severity** important for a voice product: the silence is most of the latency of a short question.
**Workaround** Append silence, constrain the reply, read only the transcript events.
**Suggestion** A transcription-only mode, and the silence requirement stated in the docs.

### FL-11 — A Bedrock API key is not a credential for the rest of an AWS build

**Evidence** Sideline build, 2026-10-13. The key is backed by an IAM user (`BedrockAPIKey-...`).

**Task** Get a first Bedrock answer, then add the rest of the stack. **Steps** Created the key, called Bedrock
and Polly, then DynamoDB, Secrets Manager, CloudFormation, ECR, Lambda and CloudWatch. **Expected** One
credential good for the build. **Actual** Bedrock and Polly worked; the others were denied. Nothing at the point
of creation says the key is scoped.

**Severity** important: it surfaced only when DynamoDB refused us, after the code was written.
**Workaround** IAM credentials with an explicit policy ([AWS_SETUP.md](AWS_SETUP.md)).
**Suggestion** One line where the key is created: what it covers, and what to use for everything else.

### FL-12 — DynamoDB rejects floats, and a local fake hides it

**Evidence** Sideline build, 2026-10-13, first run against a real table; pinned by `tests/test_dynamo.py`.

**Task** Log match events and the listener's marker. **Steps** Wrote events with a float timestamp.
**Expected** The write to work as it did against our in-memory store. **Actual** boto3 raised `Float types are
not supported. Use Decimal types instead.`; every event was dropped, so the poller logged zero. Reads return
`Decimal`, which JSON cannot encode. A second bug appeared in the same run: the conditional write meant to dedupe
events keyed on an id the live feed mints fresh on every read, so it would never have fired.

**Severity** important: silent data loss that no test against a fake could show. **Workaround** Convert on write
and on read, and key events by a digest. **Suggestion** Show the Decimal rule beside the first `put_item` example,
and have the error name the offending attribute.

### FL-13 — Speech models on Converse are chat models, not transcribers

**Evidence** Sideline build, 2026-10-13: Mistral Voxtral through Converse.

**Task** Transcribe a spoken question. **Steps** Sent audio and asked for a transcript. **Expected** The words.
**Actual** It accepts audio but answered the question: it invented a score instead of transcribing (2 of 4 phrases
correct on Small). For a blind listener an invented score is worse than silence.

**Severity** nice-to-have **Workaround** Nova 2 Sonic and Groq. **Suggestion** A transcription mode for audio models
on Converse, or a note that they are chat-only.

### FL-14 — The first free football feed ran out in a day, so we replaced it

**Evidence** Sideline's own logs and the first feed's (API-Football's) responses, 2026-10-13 (a third-party feed,
not an Amazon service: this entry explains a decision in this repository). It is named only here.

**Task** Build and test a live-only product against a free football feed. **Steps** Followed matches, searched
fixtures by team, and ran the voice agent against the live feed over a day of development; the poller ran at the
same time. **Expected** A free plan to last a day of building. **Actual**, in the vendor's own words:
`rateLimit: Too many requests. Your rate limit is 10 requests per minute.`, then `requests: You have reached the
request limit for the day`. Looking further than a day ahead was refused too: `Free plans do not have access to this
date, try from 2026-10-12 to 2026-10-14`, with the same kind of refusal for the `next` parameter and for the
current season on a team query. So "when does Arsenal play next week" could not be answered on that plan at all.

**Severity** important: once the quota was gone, every question returned the feed's error until the next day.
Our own testing was a large part of the use, and the poller added one request a minute.

**What we did.** First, in code: cached the day's list for five minutes, asked for less per question, waited once
and retried on a rate limit, and made every refusal reach the listener in the vendor's own words ("The match data
feed said: ... Try again shortly.") instead of being reworded. Then we **replaced the feed with Sportmonks**, whose
free plan is limited **per hour** (180 calls, per kind of data) and not per day, so it cannot be spent in a day the
same way. The trade is coverage: four leagues on that plan, so a demo needs a match in one of them. We removed the
old provider, its tests and its settings rather than keep two paths to maintain; Sportmonks was checked against a
real finished match first (README, docs/DATA_PROVIDERS.md).

**Suggestion** Put the per-minute limit and the date window on the plan page next to the daily number; return the
remaining quota in every response (Sportmonks does, in `rate_limit`); and offer a small hackathon-sized free tier,
because a daily cap that a day of development spends is a cap on building.

---

## Candidates: add an entry only if you actually hit it

These were in an earlier draft as if they had happened. They have not been
observed, so they are **not** in the log. Promote one only with a real
observation and its numbers.

- Bedrock first-call latency after idle, or retry/timeout defaults too slow
  for voice. Measure with `make aws-check` and real calls.
- Free football-data tiers being delayed or capped. Unverified: the vendor
  pages blocked automated reading; check them by hand.
- `_meta` conventions for UI payloads. No observation.
