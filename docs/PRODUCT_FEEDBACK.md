# Product feedback

The hackathon requires, for **each tool, API or SDK used**: what you used
it for, what worked well, what needs work, how onboarding felt (zero to
hello world), and whether you would build with it again, and why.

**How to read this page.** Every statement here is either
(a) something a test or a measurement in this repository backs (the README's
verification table, [SPEECH.md](SPEECH.md), `make aws-check`), (b) something read in the cited documentation on the stated date,
or (c) marked **`TODO(you)`**, which only a hands-on run can answer.
Nothing here claims experience that has not happened. **Do not submit
while any `TODO(you)` remains**: answer it from a real run, or delete the
section if you did not use the thing. "Would you build with it again?" is
yours to answer honestly in each section.

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

**Would you build with it again?** `TODO(you)`: yes or no, and why.

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

**What worked well** `TODO(you)`: what in the spec was clear.
**What needs work** `TODO(you)`: what you had to guess.
**Onboarding** `TODO(you)`.
**Would you build with it again?** `TODO(you)`.

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
credential for the rest of an AWS build. `TODO(you)`: whether that was
documented clearly where you created the key.

**What worked well** `TODO(you)`: after `make aws-check`.
**What needs work** `TODO(you)`: cold-start latency, model access flow,
error clarity. Record the real `latencyMs` figures the server logs.
**Also tried (2026-10-13), speech models on Bedrock.** Mistral Voxtral accepts
audio through Converse, but as a chat model it answered a spoken question with
an invented score instead of transcribing it (2 of 4 phrases correct on Small).
A dedicated transcription mode for these models would make them usable.

**Onboarding** `TODO(you)`: account to first successful call.
**Would you build with it again?** `TODO(you)`.

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

`TODO(you)`: what worked well, what needs work, onboarding, and build-again yes or no.

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
Rather than wait on a support case, speech in now uses Nova Sonic and Groq
(5b below). Our own `make aws-check` had been reporting "speech in: ok" from a
capability check alone; it now makes a real round trip through the provider in use.

`TODO(you)`: Polly: what worked well, what needs work, onboarding, and build-again.
Transcribe: whether you would build with it again, and why.

### 5b. Amazon Bedrock, Nova 2 Sonic (speech in)

**Used for** Hearing the listener: audio streamed in, transcript read back
([sideline/voice.py](../sideline/voice.py)). It is the in-account fallback when
no Groq key is set. Full numbers and method: [SPEECH.md](SPEECH.md).

**Status: verified with real calls, 2026-10-13.** From the Polly-spoken test
set, 17 of 24 clips exact on a first run; in the later head-to-head 8.5% word
error in noise and 4.2 s per clip, behind Groq's 3.7% and 1.1 s on the same
clips. Names it got right included Ødegaard and Bellerín; it misheard
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
5. A Bedrock **API key** alone was not used here: IAM credentials were.
   `TODO(you)`: whether bearer-token auth works for streaming.

**Onboarding** A first transcript took a few attempts, mostly the points above.
`TODO(you)`: account to first success, in your own words.

**Would you build with it again?** `TODO(you)`.

**Also tried:** Mistral Voxtral through Converse. It accepts audio but is a chat
model: it answered a spoken question with an invented score instead of
transcribing it. A transcription mode for these models would make them usable.

## 6. API-Football (live data): hands-on findings

**Used for** Today's fixtures, live events, line-ups, the referee and
head-to-head ([sideline/providers/apifootball.py](../sideline/providers/apifootball.py)).
Run against the live service on 2026-10-13 on a **Free plan** (100
requests a day).

**What worked well** One `fixtures?id=` response embeds events and line-ups,
so a followed match costs about one request per poll. Scores, cards,
substitutions and own goals came through for a finished match and a live
one (minute 89).

**What needs work** Found only by running against real data, and pinned by
tests:
1. The vendor labels an ordinary goal "Normal Goal"; read aloud it sounds
   like a fault.
2. Own goals are credited to the benefiting team, so "X scored" is wrong.
3. Head-to-head with `last=` is refused on the Free plan, and the response
   includes the match being watched.
4. A bad key is HTTP 200 with an `errors` field, which reads as "no such
   match" unless handled.
5. Line-ups and referee can be absent on a live fixture.

**Onboarding** Slower than it should have been: the first key was rejected
(`Error/Missing application key`) and a replacement worked; the error does
not say whether the key is wrong, revoked or for another host.

**Terms** The hackathon requires authorisation to use any third-party data;
the vendor's terms were not retrievable here, so confirm yours.

**Would you use it again?** `TODO(you)`.

## 7. Devpost and the hackathon materials

**What worked well** The rules page is specific about submission
requirements, judging stages and criteria, and the FAQ answers the
partner-only question directly.

**What needs work** The FAQ still explains how to request AWS credits while
the rules page says the codes ran out on 7 October (FL-05).

**Would you do it again?** `TODO(you)`.
