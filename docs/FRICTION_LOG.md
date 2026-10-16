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
| FL-14 | Build and test against a free football feed for a day | The first feed's free plan allowed 100 requests a day and 10 a minute, with only yesterday to tomorrow visible; the day's quota was spent before the build was done, so every question returned the feed's error | important | Replaced it with Sportmonks, whose free plan is limited per hour, not per day (later replaced by ESPN's public feed) | State the per-minute and date-window limits beside the daily number, return remaining quota on every response, and offer a hackathon-sized free tier |
| FL-15 | Replace a third-party speech recogniser with a model on Bedrock, and keep the accuracy | Voxtral rejected a system message next to audio, answered the question instead of transcribing when the instruction came first, and the small model worked while the mini one did not; it took a controlled comparison to find all that | important | Put audio before instruction in user turn, drop vocabulary list, select Voxtral Small with length-guard fallback to Nova Sonic | Document prompt ordering and restrictions for Converse audio models; add a dedicated transcription-only mode |
| FL-16 | Run Nova Sonic from the Python SDK on a new Python | The SDK's CRT component failed to import with `awscrt` 0.26.1 on Python 3.14 and reported "awscrt is not installed" while it was; upgrading to 0.37 fixed it, after one whole comparison run was wasted | important | Upgrade `awscrt` to >=0.37 and verify `crt.HAS_CRT` | Report underlying ImportError instead of generic missing dependency; state explicit compatible `awscrt` versions |
| FL-17 | Test a voice agent against a real DynamoDB table | Our own routing and verify runs wrote 108 items into the app's real table (85 invented listeners, three fixtures that the live feed has never heard of, stale follower markers), and the browser's listener was left following a match from the feed we had dropped, so every match question answered "can't find that match any more" | important | Cleaned stale items; enforce in-memory state for test providers regardless of `SIDELINE_STATE`; auto-drop stale followings | Make safe test isolation the default so "auto" state does not write test data to production tables |
| FL-18 | Run Bedrock Converse tool calls under multi-query loads | Nova Micro periodically failed immediately with `ServiceUnavailableException: Service capacity limit has been reached`, failing voice responses when retries were disabled for latency | important | Fast retry once after 0.6 s (`BUSY_RETRY_SECONDS`) for capacity and throttling errors; since then, one retry on a read timeout too (see the entry) | Document expected on-demand capacity limits for Nova models; guide builders to retry fast rejections but not timeouts in voice loops |
| FL-19 | Cache static MCP tool catalog definitions across conversational turns | Bedrock Converse rejected a `cachePoint` placed inside `toolConfig.tools` with `ValidationException: extraneous key [cachePoint] is not permitted`, preventing caching of 7,800 tokens of tool definitions | nice-to-have | Return short tool outputs directly without LLM rephrasing; pre-warm connections at startup | Support prompt caching in `toolConfig.tools` on Nova Micro, or clarify allowed cachePoint placements in Converse docs |
| FL-20 | Set up and run the service on Windows via quickstart scripts | `make run` failed with `make: command not found`; `./run.sh` hardcoded Unix `.venv/bin/python` causing it to fail on Windows (`Scripts/python.exe`), and CRLF line endings broke bash execution with `$'\r': command not found` | important | Updated `run.sh` to support Windows `Scripts/python.exe` and Unix `bin/python`; normalized line endings to LF; documented `python -m sideline` | Add `.gitattributes` to enforce `eol=lf` on shell scripts; make venv bootstrap scripts cross-platform aware; document Windows PowerShell run steps |
| FL-21 | Allow exactly one attempt on a Bedrock or DynamoDB call, to keep a voice turn short | `retries={"max_attempts": 1}` was meant as "no retry"; botocore counts retries, so it makes **two** attempts | important | `retries={"total_max_attempts": 1}` | Name the setting for what it counts, or warn in the `Config` docs |
| FL-22 | Run many Bedrock Converse calls back to back for an evaluation | A `ConnectTimeoutError` to `bedrock-runtime` mid-run, while a second evaluation shared the connection; the run then reported every case as "agent unavailable" | nice-to-have | Run evaluations one at a time; the agent reports the failure | Document connection and concurrency limits for Converse from one client |
| FL-23 | List every football match on a day, across all competitions, from ESPN's public API | No documentation: the one request that does it, its silent 100-match cut-off, and the way to get upcoming fixtures were all found by probing | important | Probed and recorded in `docs/ESPN_NOTES.md` | Publish the endpoints, or at least the `limit` and `fixture=true` behaviour |
| FL-24 | Write an MCP 2025-11-25 server by hand and check it against the spec | Review against the spec found eight deviations in our own server (session not required, version header unchecked, batches accepted, and more) | important | All eight fixed with a test each (`tests/test_fix_server.py`); a bad argument is now an `isError` result with `reason: "invalid_arguments"` | A runnable conformance check for a hand-written Streamable HTTP server |
| FL-25 | Choose a Bedrock model to act as the host over a 30-tool MCP server | With the whole tool list offered, models answered with no tool, or the wrong one, on up to two thirds of 79 phrasings; the same runs were also throttled | important | Measured routing per model, a prompt that treats statements as requests, a shortlist, waiting and retrying on throttling | Guidance on tool-list size for a model host (FR-07), and published on-demand rate limits for Converse (FR-08) |
| FL-26 | Keep a listener's state in DynamoDB and ask a first question from a region far from the table | One cold first question took 11 s, almost all of it 26 sequential table calls at about 340 ms each | important | Do independent calls at once, keep the server's own records while it is the only writer, ask for only what is needed | Document per-call latency from distant regions and a batch-get pattern for single-table designs |
| FL-27 | Judge how fast a voice assistant feels, using our own simulated Alexa+ page | The page's end-of-speech wait depended on a browser feature that was off by default, so it ran at its slowest setting and was longer than the 0.70 s our docs stated; the simulator did not represent what we thought we were measuring | important | Start transcription during the quiet, send early on a finished sentence, make the default and the docs agree | A reference latency budget for a voice add-on, and a way to measure one end to end |
| FL-28 | Tell a listener the score of a match in play, behind their stream's delay | A listener was told a team had scored that had not: the delayed score was rebuilt by counting the feed's goal events, which are incomplete and name teams inconsistently | critical | Use the feed's own score and take off only the goals still held back; refresh on doubt; keep live pages for seconds | A field on the feed that says whether its event list is complete, and goal events keyed to the same team ids as the score |

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

**Since fixed.** The server now follows the MCP spec: with `SIDELINE_AUTH_TOKEN` set, a 401 carries
`WWW-Authenticate: Bearer realm="sideline"` (`sideline/mcp/server.py`; probed in `tests/test_fix_server.py`).

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

**Evidence** Sideline build, 2026-10-13, `simulator/voice.py`; numbers in [SPEECH.md](SPEECH.md).

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

**What we did.** Added targeted retry logic in [`simulator/agent.py`](../simulator/agent.py): we wait 0.6 s (`BUSY_RETRY_SECONDS`) and retry once **only** for `ServiceUnavailableException` (capacity limit reached) and throttling exceptions (`ThrottlingException`). Any other error (including model timeouts) fails immediately to avoid keeping the voice listener waiting. Pinned in `tests/test_agent.py`.

**Update.** Failing fast on a timeout turned out to cost more than it saved: a single read timeout was failing the first
question of a session ("Sorry, an error occurred"), three times in two days of logs. The agent's `_ask` in
`simulator/agent.py` now tries once more on a timeout or a throttle; any other error still fails at once.

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

### FL-21 — `max_attempts: 1` is two attempts

**Evidence** Checked 2026-10-15 with botocore 1.43.111: `Config(retries={"max_attempts": 1})` reports `total_max_attempts: 2`; `{"total_max_attempts": 1}` reports 1.

**Task** Allow a single attempt on a Bedrock Converse call and on the DynamoDB start-up probe, so a failure costs one timeout and the listener is not left waiting.

**Steps** Set `retries={"max_attempts": 1}` on both clients, as the surrounding comments describe ("no retry"). A code review later asked what the settings do; we read the resulting client configuration.

**Expected** One attempt, as the word suggests.

**Actual** Two. `max_attempts` counts retries after the first attempt, so a Bedrock timeout of 8 s cost about 16 s and the start-up probe about 6 s plus connect time.

**Severity** important: it doubles the worst-case wait on exactly the path (a voice turn) where waiting is least tolerable, and nothing fails visibly.

**Workaround** `retries={"total_max_attempts": 1}`, in `sideline/language/bedrock.py`, `sideline/state/__init__.py` and `simulator/voice.py`.

**Suggestion** Say in the `Config` documentation that `max_attempts` counts retries, or rename it; `total_max_attempts` is the clearer name.

### FL-22 — A connection timeout makes every case in a long evaluation look like a product failure

**Evidence** Observed 2026-10-15 while running `scripts/route_check.py` for two models at once: `botocore.exceptions.ConnectTimeoutError: Connect timeout on endpoint URL: "https://bedrock-runtime.us-east-1.amazonaws.com/model/.../converse"`.

**Task** Compare how several Bedrock models choose among our 30 tools, 79 phrasings per model.

**Steps** Ran one evaluation in the background and, while it was running, a second from the same machine to diagnose a result.

**Expected** Both to run; or a clear statement of what concurrency a single client and account support.

**Actual** The second run's first call failed to connect within the default connect timeout, and the product (correctly) reported "agent unavailable". Separately, a first version of the evaluation reported 0 of 71 correct for the same reason: Bedrock had been switched off by a test helper (our bug), which looked identical from outside.

**Severity** nice-to-have: it cost time in diagnosis, not a failed answer.

**Workaround** Run evaluations one at a time; log the underlying exception type next to "agent unavailable" (the developer log in the simulator now shows it).

**Suggestion** Document the connection and concurrency expectations for Converse from one client, and make the default error text distinguish "could not connect" from "the model refused".

### FL-23 — ESPN's public football API works well, but only if you already know how

**Evidence** Probed live on 2026-10-15; the findings are recorded, with what we could and could not confirm, in [ESPN_NOTES.md](ESPN_NOTES.md). ESPN publishes no documentation for these endpoints; community lists exist and are cited there.

**Task** Answer "what happened yesterday?" for any football competition ESPN covers, quickly.

**Steps** Started from the per-league scoreboard URL (25 hard-coded leagues, one request each). A live AFC Champions League Two match was invisible because it was not on the list. Looked for a better endpoint.

**Expected** A documented way to list a day's matches across competitions, and to find a team's next match.

**Actual** `soccer/all/scoreboard?dates=...&limit=500` returns every competition in one request, but without `limit` it silently stops at 100 matches (135 on the day we measured). A team's schedule lists only played matches unless `?fixture=true` is added, and then lists only upcoming ones. A match event carries a league number, not a name: the names come from a separate `leagues/dropdown` request. Standings return an empty body under `/apis/site/v2/` and work under `/apis/v2/`. One question that took **116 requests and 18 s** now takes 3 requests and about 3 s.

**Severity** important: every one of these cost real time, and a silent cut-off could have dropped matches from an answer without any error.

**Workaround** The provider uses those endpoints, with tests built from saved real responses (`tests/test_fast_lookup.py`, `tests/fixtures/espn-*.json`).

**Suggestion** Publish the endpoint list with its parameters. At minimum, document the default `limit`, make it a visible truncation (a `truncated` flag) instead of a silent one, and return the league's name on the event.

### FL-24 — Writing a spec-conformant MCP server by hand: eight deviations that only a spec-versus-code review found

**Evidence** `tests/test_fix_server.py` (raw-socket probes against an in-process server), commit history of 2026-10-15; the spec revision is 2025-11-25.

**Task** Implement MCP over Streamable HTTP, revision 2025-11-25, with no SDK, so the server is self-hosted with no dependencies.

**Steps** Built the server from the spec text; ran our own protocol tests, which passed; then reviewed every request path against the spec and probed it with hand-made requests.

**Expected** Passing our own tests to mean the server conforms.

**Actual** It did not: a session id was issued but not required afterwards; `MCP-Protocol-Version` was never validated; JSON-RPC batches (removed from the protocol) were still accepted; a bad argument came back as a protocol error where a tool-execution error lets the model correct itself; the Origin check ignored the port; a rejected request left its connection open, so a request hidden in the body ran without the check; `Content-Length: -1` blocked a thread; and the server advertised an MCP Apps capability it did not implement.

**Severity** important: each is invisible to a happy-path test and is exactly what an independent client or reviewer would meet first.

**Workaround** All eight are fixed, one test each. The last to go was the bad argument: it now comes back as a tool-execution error (`isError: true`, `structuredContent.reason: "invalid_arguments"`, the schema problem in the text) so a model can correct itself; an unknown tool or malformed params stay protocol errors. The official MCP Python SDK client was then run against the server and worked first time (`scripts/check_with_sdk.py`); no other independent client has been tried.

**Suggestion** Publish a conformance check a server author can run (the transport, session, header and error rules), so "my tests pass" and "I follow the spec" are not the same unverified claim.

### FL-25 — Choosing a model to route among 30 MCP tools: most of the early failures were not the model's

**Evidence** Observed 2026-10-15 with `scripts/route_check.py` (79 phrasings, each with the tool it should reach), real Bedrock, invented match data; per-model figures in [BEDROCK.md](BEDROCK.md), "Model choice".

**Task** Pick the Bedrock model that, given the whole tool list from `tools/list` (about 8,000 tokens), calls the right tool for what a listener says.

**Steps** Ran the check on Nova Micro, Nova Pro, Claude Haiku 4.5 and Claude Sonnet 4.5; read each miss; changed the prompt and the tool descriptions; re-ran.

**Expected** A strong model to route correctly most of the time with no help, and a miss to mean a model's mistake.

**Actual** First run: Nova Pro 56 of 79, Sonnet 43, Haiku 34 (Micro 39 of an earlier 71), mostly because the model answered with no tool call. After a prompt change telling it to use a tool for any current fact: Pro 59, Sonnet 56, Haiku 53. Reading the misses showed three causes that were ours, not the models': a replay clock that ran the match to full time during the check, a timezone argument that moved the invented match out of "today", and a "did you mean" repair that turned the word "support" into "Porto" before the model saw it (a real bug that would also have hit a live listener). Bedrock also returned `ThrottlingException` on an on-demand account during back-to-back 79-call runs, which first counted as a miss. After the fixes and with throttled calls waited out and retried, Nova Pro reached 76 of 79, then 77 of 79 after one more agent change (a fact question the model first answers from memory is sent back to the tools; [BEDROCK.md](BEDROCK.md)).

**Severity** important: it decides which model the product is shown with, and it nearly produced a wrong conclusion twice.

**Workaround** Treat a miss as a prompt, description or harness problem first. The check now waits and retries on throttling, reports calls that never got an answer as not scored, and freezes the replay clock. The repair that mistook ordinary words for teams now ignores any word our own tool descriptions use (`tests/test_resolve.py`).

**Suggestion** Say what tool-list size a model host is expected to handle and how a platform narrows it (FR-07); document the on-demand request limits for Converse and what a client should do on throttling (FR-08).

### FL-26 — DynamoDB is fast, and 26 of it in a row is not

**Evidence** Measured 2026-10-15 from Mauritius against a table in us-east-1 (on-demand, TTL on): `get_item` 340 ms, `put_item` 335 ms, `delete_item` 370 ms, each at the median. A profile of a cold first follow (every ESPN request and table call timed) is in the commit that fixed it.

**Task** Follow a match as a new listener, and answer the first question quickly.

**Steps** Ran the same conversation with state in memory (3.2 s for the follow tool) and in DynamoDB (11 s). Timed every call.

**Expected** The table to add a few hundred milliseconds in all.

**Actual** The follow made 26 table calls, one after another: a profile read, two writes for the profile and its follower marker, two for the fixture and its index, a query and a profile read per follower marker (stale markers left by earlier listeners each cost one read), and the event log read back repeatedly. At 340 ms each that was about 9 of the 11 seconds. A second, unrelated cost: the poller that the follow triggered also read every other match anyone followed, including one that needed a three-day sweep of every sport's scoreboard (24 requests).

**Severity** important: the first question is the one a listener is waiting for.

**Workaround** Independent writes and reads now run at the same time; the server's own records (not the live feed) are kept while this process is the only writer, and every write updates them; a new follow reads only the match it followed; a soccer match is found with one summary request instead of a scan; start-up opens the connections. The cold follow tool went from about 11 s to 4.5 s, and the first question with a model from 12.3 s to 6.3 s. The cost is that one server per table is the supported shape.

**Suggestion** Say in the DynamoDB guidance what a call costs from a distant region and show the single-table patterns that avoid chains of dependent reads (batch get, parallel queries, a profile item that carries what a follow needs).

### FL-27 — Our simulated assistant was slower than we said, because of a setting we did not know it depended on

**Evidence** Found 2026-10-15 while reading the page's voice loop (`simulator/index.html`) to make it faster. [SPEECH.md](SPEECH.md) said the wait to be sure the listener had stopped was 0.70 s (`SILENCE_MS`).

**Task** Trust the simulated Alexa+ as a stand-in for the real one when judging how quickly an answer arrives.

**Steps** Followed what happens between the listener's last word and the first audio, and read the numbers in the docs against the code.

**Expected** The wait to match the documented 0.70 s, and the page to behave the same whichever browser features were on.

**Actual** The wait was 750 to 950 ms, chosen by how many words the *browser's* live caption had heard (fewer words, longer wait). With captions off, which is what the server's own default said (`SIDELINE_LIVE_CAPTION=off`; the settings table said `browser`, so the two disagreed), the page heard no words and always waited 950 ms. So the simulator was less accurate than we had said in two ways: it was slower than documented, and its speed depended on a browser feature that has nothing to do with Sideline or with Alexa+. The documented total therefore left out about a quarter of a second at best and more than that at worst. We have not measured by how much on a real microphone.

**Severity** important: the product's whole promise is a conversation that feels natural and fast, and the stand-in used to judge it was misleading us about it.

**Workaround** The page now starts transcribing after 320 ms of quiet while it keeps listening, drops the result if the listener carries on, and asks at once when the transcript is a finished sentence and the quiet has held. The agent is never started on a guess, because its tools change what the listener has been told. The captions setting now defaults to off in both the code and the settings table, and the adaptive wait no longer depends on it. A test (`tests/test_speculative_stt.py`) pins the shape of the logic; the effect on a real microphone has not been timed.

**Suggestion** Publish a latency budget for a voice add-on (end of speech, recognition, tool calls, first audio) and a way to measure a turn end to end, so a team can tell whether a stand-in is faithful. Without one, "fast enough" is whatever our own page happens to do.

### FL-28 — The score was wrong because we believed the event list over the score

**Evidence** Reported by a team member after watching a live match on 2026-10-15: one team had 1 and the other 0, and Sideline kept saying the other team had 1. We could not retrieve that match afterwards, so the cause below is the one the code and a check across the day's matches support, not a replay of that match. The check: 135 football matches from yesterday and today, the feed's score against the score counted from its goal events: they disagreed in 70, mostly lower-league and college matches that list few or no goal events (for example a feed score of 2 to 1 with a goal list that gives 2 to 0).

**Task** Tell a listener, whose stream runs behind real time, the score their screen has reached.

**Steps** Read the code from the question to the spoken score, and compared what the feed says in its two places: the match's score, and its list of events.

**Expected** The event list to add up to the score, so either could be used.

**Actual** They do not always. For a listener with a delay, the score was rebuilt by counting goal events up to the point their screen had reached, with every event not credited to the home team counted for the away team. A feed that lists a goal under a team name that differs from the match's, or omits a goal, therefore gave one team a goal it had not scored or took one away. Separately, a match in play was kept in a 60-second cache by its id, so a recheck could repeat a minute-old score.

**Severity** critical: a wrong score said confidently is the one failure this product cannot afford, and a blind listener cannot see that it is wrong.

**Workaround** The feed's own score is the authority. For a delayed listener only the goals still held back are taken off it, each placed on a side by a tolerant team-name match; if one cannot be placed, or the result would be below nothing, the feed's score stands and the answer says it cannot be sure it matches their screen. A match in play is kept for 3 seconds, not 60; saying "are you sure" makes the model call the score tool with `refresh`, which forgets what is kept and asks the feed again. Tests pin each case (`tests/test_score_truth.py`).

**Suggestion** Say in the feed's documentation which of the two places is authoritative, and add a marker on a match when its event list is known to be incomplete, so a client can tell a quiet match from a poorly covered one.

## Candidates: add an entry only if you actually hit it

These were in an earlier draft as if they had happened. They have not been
observed, so they are **not** in the log. Promote one only with a real
observation and its numbers.

- Bedrock first-call latency after idle: tested with connection pre-warming
  on startup; retry and capacity behaviors were measured and promoted to FL-18.
- Free football-data tiers being delayed or capped. Unverified: the vendor
  pages blocked automated reading; check them by hand.
- `_meta` conventions for UI payloads. No observation.
