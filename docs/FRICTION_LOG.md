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
| FL-15 | Replace a third-party speech recogniser with a model on Bedrock, and keep the accuracy | Voxtral rejected a system message next to audio, answered the question instead of transcribing when the instruction came first, and the small model worked while the mini one did not; it took a controlled comparison to find all that | important | Put audio before instruction in user turn, drop vocabulary list, select Voxtral Small with length-guard fallback to Nova Sonic | Document prompt ordering and restrictions for Converse audio models; add a dedicated transcription-only mode |
| FL-16 | Run Nova Sonic from the Python SDK on a new Python | The SDK's CRT component failed to import with `awscrt` 0.26.1 on Python 3.14 and reported "awscrt is not installed" while it was; upgrading to 0.37 fixed it, after one whole comparison run was wasted | important | Upgrade `awscrt` to >=0.37 and verify `crt.HAS_CRT` | Report underlying ImportError instead of generic missing dependency; state explicit compatible `awscrt` versions |
| FL-17 | Test a voice agent against a real DynamoDB table | Our own routing and verify runs wrote 108 items into the app's real table (85 invented listeners, three fixtures that the live feed has never heard of, stale follower markers), and the browser's listener was left following a match from the feed we had dropped, so every match question answered "can't find that match any more" | important | Cleaned stale items; enforce in-memory state for test providers regardless of `SIDELINE_STATE`; auto-drop stale followings | Make safe test isolation the default so "auto" state does not write test data to production tables |
| FL-18 | Run Bedrock Converse tool calls under multi-query loads | Nova Micro periodically failed immediately with `ServiceUnavailableException: Service capacity limit has been reached`, failing voice responses when retries were disabled for latency | important | Fast retry once after 0.6 s (`BUSY_RETRY_SECONDS`) exclusively for capacity and throttling errors; fail fast on timeouts | Document expected on-demand capacity limits for Nova models; guide builders to retry fast rejections but not timeouts in voice loops |
| FL-19 | Cache static MCP tool catalog definitions across conversational turns | Bedrock Converse rejected a `cachePoint` placed inside `toolConfig.tools` with `ValidationException: extraneous key [cachePoint] is not permitted`, preventing caching of 7,800 tokens of tool definitions | nice-to-have | Return short tool outputs directly without LLM rephrasing; pre-warm connections at startup | Support prompt caching in `toolConfig.tools` on Nova Micro, or clarify allowed cachePoint placements in Converse docs |
| FL-20 | Set up and run the service on Windows via quickstart scripts | `make run` failed with `make: command not found`; `./run.sh` hardcoded Unix `.venv/bin/python` causing it to fail on Windows (`Scripts/python.exe`), and CRLF line endings broke bash execution with `$'\r': command not found` | important | Updated `run.sh` to support Windows `Scripts/python.exe` and Unix `bin/python`; normalized line endings to LF; documented `python -m sideline` | Add `.gitattributes` to enforce `eol=lf` on shell scripts; make venv bootstrap scripts cross-platform aware; document Windows PowerShell run steps |

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

**Severity** nice-to-have **Workaround** Nova 2 Sonic, at the time. **Suggestion** A transcription mode for audio models
on Converse, or a note that they are chat-only.

**Update, same day.** The rejection was premature: it was how the model was asked. See FL-15, where Voxtral Small, asked
correctly, matched the third-party benchmark.

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

### FL-15 — A speech model on Bedrock can match a third-party recogniser, if you ask it the right way

**Evidence** Sideline build, 2026-10-13; the same 48 clips and scoring in [SPEECH.md](SPEECH.md), `make compare-stt`.

**Task** Take the listener's audio off a third-party service (Groq's hosted Whisper, which had won a first
comparison) and run speech in on Amazon Bedrock only, without losing accuracy; for a product whose listeners may be
blind, where their voice goes matters. **Steps** Listed the account's Bedrock models (124, none of them Groq or Whisper;
Amazon Transcribe returned `SubscriptionRequiredException`), found Mistral Voxtral (audio in, text out, through Converse)
and a newer Nova Sonic, built Voxtral as a provider, and ran every contender on the same clips, clean and with noise.
**Expected** A speech model to transcribe. **Actual**, in order:

1. Our earlier try had been rejected (FL-13): it answered "What's the score?" with an invented score.
2. A `system` message next to audio is refused: `Found system messages at indexes [0] and audio chunks in messages at
   indexes [1]. This is not allowed prior to the tokenizer version 13.` The instruction has to go in the user turn.
3. With the instruction *before* the audio the model answers what it hears; the mini model once wrote "Alright, so I'm
   going to ask you a question" repeatedly over a clip of "Follow Arsenal." With the **audio first**, the small model
   transcribed all three test phrases.
4. The vocabulary list we sent (as every other recogniser takes) made it worse: with team names in the prompt it printed the
   names for "The first one." and, in one wording, answered "What's the score?" with "The score is Arsenal 1...". Twelve
   clips: 0 failures without the names, up to 2 with them. So we send none.
5. Full run, 48 clips, no vocabulary: Voxtral Small 0.0% word error clean, 1.4% noisy, 47 of 48 exact, every name right
   (48 of 48), 0.8 s a clip; the third-party benchmark 0.4% and 3.7%, 43 of 48, 44 of 48 names, 1.4 s. With names in the
   prompt (the first run) Voxtral was 1.3% and 2.6% at 1.2 s. **Voxtral Mini** was unusable: 24.6% and 39.1% error with the
   names and 21 failed clips without, because it answered questions and printed the names. Nova Sonic took 3.4 to 4.2 s a clip
   (8% to 8.5% word error), on Nova 2 and the newer 2.5 alike.

**Severity** important: a rejected approach looked final, and nothing in the Converse documentation we found says an
audio block should come before the instruction or that a system message is refused with audio.

**What we did.** Made Voxtral Small the first choice and Nova Sonic the fallback, put a guard on its reply (more words
than the clip could hold is not a transcript, so the clip falls back), and **removed the third-party service from the
product**: its key, its request code, its tests. Eliminations followed the rule "one error, or being slow, is enough": Voxtral
Mini on errors, Nova 2 and 2.5 Sonic on speed. The numbers are from synthetic speech and are a comparison, not an
accuracy a listener will see (SPEECH.md lists the limits). The Nova 2.5 figures are a six-clip sample: the full runs for
Sonic did not complete (see FL-16).

**Suggestion** Document, on the Voxtral Bedrock page, how to transcribe with it through Converse (audio block first, no
system message, an instruction that forbids answering), or add a transcription-only mode; and publish a speech-to-text
accuracy figure next to the model list, so that a builder choosing an AWS-only path can see that one exists.

### FL-16 — The Nova Sonic SDK said "awscrt is not installed" when it was

**Evidence** Sideline build, 2026-10-13, Python 3.14.8, `aws-sdk-bedrock-runtime` with `smithy-http` 0.6.0.

**Task** Run Nova Sonic speech in from a script. **Steps** `pip3 install awscrt`, then called Sonic. **Expected** A
transcript. **Actual** `MissingDependencyError: Attempted to use awscrt component, but awscrt is not installed.` on every
clip, although `import awscrt` worked and `pip list` showed `awscrt 0.26.1`. The SDK guards its CRT import in a
`try/except ImportError` and sets `HAS_CRT = False`, so any import failure inside it becomes that message. Upgrading to
`awscrt` 0.37.0 made `HAS_CRT` true. The comparison script had run its whole length (96 failed calls) before the
cause was clear, because each clip's failure was only a log line.

**Severity** important: the message names the wrong problem, and the failure hides in a log. **Workaround** Upgrade
`awscrt`; check `from smithy_http.aio import crt; crt.HAS_CRT`. **Suggestion** Report the underlying import error, and
state the compatible `awscrt` range for each SDK release (our `requirements.txt` said `>=0.26`, which was not enough on
Python 3.14).

### FL-17 — Tests that touch a real table leave the product answering about matches that do not exist

**Evidence** Sideline build, 2026-10-14, a read of the table before any change: 109 items, of which 108 were ours.

**Task** Ask a real question in the simulator ("Who are the members of the team squad?"). **Expected** A squad, or a plain
"which team?". **Actual** "I can't find that match any more." **Why** The first routing run (2026-10-13) used the invented
test provider with `SIDELINE_STATE=auto`, and `auto` means DynamoDB when it answers. So 85 test listeners
(`route-*`, `verify-agent*`), their follower markers and three fixture rows (one invented, two left from the feed we had
dropped) were written to the table the app uses, and the browser's own listener was following an id the live feed does not
know. Every match tool then failed the same way, and the poller kept asking the feed about those ids at 30 s, which spends
the hourly limit for nothing. **Severity** important: it looked like the product could not answer, and it spent quota.

**What we did.** Deleted the 108 items (only ours, after listing them, and kept the real listener's own data, clearing only
the stale followed match); made a followed match the feed does not know get forgotten, with a plain sentence, the first time
it is seen; made the poller give up on a fixture the feed does not know after three misses; and made a server built with a
test provider use memory state only, whatever `SIDELINE_STATE` says, with a test. **Suggestion** for anyone building the same:
"auto" backends are convenient and dangerous in tests; make the safe choice the one that needs no configuration.

### FL-18 — Bedrock Converse intermittently fails with "Service capacity limit has been reached"

**Evidence** Sideline routing and verification runs, 2026-10-13; commit `3495516` ([`tests/test_agent.py`](../tests/test_agent.py), [`docs/PRODUCT_FEEDBACK.md`](PRODUCT_FEEDBACK.md) section 3a).

**Task** Run batch test suites and multi-turn voice queries through Bedrock Converse with Nova Micro (`amazon.nova-micro-v1:0`).

**Steps** Sent sequential and rapid tool-use requests to the Bedrock Converse API with retry defaults disabled to keep voice turnaround under 2 seconds.

**Expected** Requests to succeed, queue briefly, or throttle with standard retry headers.

**Actual** `converse` intermittently failed with immediate `ServiceUnavailableException: Service capacity limit has been reached. Please try again later.`, occurring seconds apart from calls that succeeded. Because a voice agent cannot afford standard multi-second exponential backoff without doubling listener latency, standard zero-retry client configs treated this as a hard conversational drop.

**Severity** important: turns failed randomly for the listener during active use.

**What we did.** Added targeted retry logic in [`sideline/language/agent.py`](../sideline/language/agent.py): we wait 0.6 s (`BUSY_RETRY_SECONDS`) and retry once **only** for `ServiceUnavailableException` (capacity limit reached) and throttling exceptions (`ThrottlingException`). Any other error (including model timeouts) fails immediately to avoid keeping the voice listener waiting. Pinned in `tests/test_agent.py`.

**Suggestion** Document whether capacity limits are expected on on-demand Nova models under modest burst traffic, and publish guidance on voice-optimized retry policies (retry instant capacity refusals, but fail fast on latency timeouts).

### FL-19 — Bedrock Converse rejects prompt caching on `toolConfig.tools`

**Evidence** Sideline build, 2026-10-13; [`docs/BEDROCK.md`](BEDROCK.md) and [`docs/PRODUCT_FEEDBACK.md`](PRODUCT_FEEDBACK.md) section 3b.

**Task** Reduce latency and token consumption across turns by caching the static MCP tool catalog (~7,800 input tokens across 27 tools) with Bedrock Converse prompt caching.

**Steps** Injected `cachePoint: {"type": "default"}` into the `toolConfig.tools` schema sent to `amazon.nova-micro-v1:0`.

**Expected** Converse to accept the cache point and cache the repetitive tool definitions across questions.

**Actual** Bedrock rejected the request with `ValidationException: Malformed input request: #/toolConfig/tools/26: extraneous key [cachePoint] is not permitted`. While Converse accepts a `cachePoint` inside the `system` prompt block, the system text is only a small fraction of the request, whereas the tool catalog represents over 90% of the token payload.

**Severity** nice-to-have: warm calls take ~0.75 s without caching, but repeated tool definitions consume unnecessary tokens and latency every turn.

**What we did.** We skipped prompt caching for tool definitions; instead, we return tool outputs of 240 characters or fewer directly without asking the model to rephrase them (`generated_by: tool`), pre-warm the Bedrock connection on server startup to absorb TLS handshake overhead, and keep tool schemas concise.

**Suggestion** Allow `cachePoint` declarations on `toolConfig` or after tools on Nova models in Converse, or state clearly in the Converse documentation that `cachePoint` cannot be placed inside `toolConfig.tools`.

### FL-20 — Setup scripts fail on Windows due to POSIX venv paths and CRLF line endings

**Evidence** Hands-on developer onboarding on Windows, 2026-10-13; `run.sh` terminal logs.

**Task** Clone the repository and start the server using the documented quickstart command (`make run` or `./run.sh`).

**Steps** Attempted `make run` in Git Bash, then ran `./run.sh` on a Windows machine with Python 3.14.

**Expected** The bootstrap script to create `.venv`, install `requirements.txt`, and start the MCP server.

**Actual**
1. `make run` failed with `bash: make: command not found` because `make` is not available out-of-the-box on Windows.
2. `./run.sh` hardcoded Unix paths (`VENV_PYTHON="$VENV/bin/python"`). On Windows, `python -m venv` places binaries under `.venv/Scripts/python.exe`, causing the check `[ ! -x "$VENV/bin/python" ]` to report `/c/.../.venv/bin/python: No such file or directory` followed by the misleading error: `The Python in .venv is too old. Remove .venv and rerun with Python 3.8 or newer.`
3. When saved or checked out with Windows default CRLF line endings (`\r\n`), bash failed to execute `run.sh` with `./run.sh: line 2: set: -: invalid option`, `./run.sh: line 3: $'\r': command not found`, and `syntax error near unexpected token 'elif'`.

**Severity** important: completely blocked first-time developer onboarding and execution on Windows.

**What we did.**
1. Converted `run.sh` line endings to LF (`\n`).
2. Updated `run.sh` to check for Windows `.venv/Scripts/python.exe` and `.venv/Scripts/python` as well as POSIX `.venv/bin/python`.
3. Created [`.gitattributes`](../.gitattributes) enforcing `eol=lf` for shell scripts and code.
4. Added native Windows PowerShell instructions (`python -m sideline`) to avoid depending on bash or make.

**Suggestion** Add a `.gitattributes` file configuring `*.sh text eol=lf` so Git preserves Unix line endings on Windows checkouts; update setup scripts to accommodate Windows virtual environment directories (`Scripts/` vs `bin/`); and document native Windows PowerShell commands in the README quickstart alongside `make` and bash.

---

## Candidates: add an entry only if you actually hit it

These were in an earlier draft as if they had happened. They have not been
observed, so they are **not** in the log. Promote one only with a real
observation and its numbers.

- Bedrock first-call latency after idle: tested with connection pre-warming
  on startup; retry and capacity behaviors were measured and promoted to FL-18.
- Free football-data tiers being delayed or capped. Unverified: the vendor
  pages blocked automated reading; check them by hand.
- `_meta` conventions for UI payloads. No observation.
