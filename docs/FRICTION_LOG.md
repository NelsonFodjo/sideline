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
| FL-08 | Enable Amazon Transcribe streaming for the simulator | IAM full-access policy and `transcribe:*` permission were added, but streaming still returned `SubscriptionRequiredException` | important | Use browser speech recognition while investigating the AWS account/service response | Explain what account or service action resolves this exception, and distinguish it clearly from missing IAM permission |

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
yet been measured by us; see EVIDENCE.md.)

**Severity** important **Workaround** `SIDELINE_BEDROCK_TIMEOUT` and
deterministic templates as the fast path. **Suggestion** Document a
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

**Severity** important: the simulator cannot use its configured AWS
speech-to-text path, despite the permissions troubleshooting.
**Workaround** Use browser speech recognition where available, or set
`SIDELINE_STT=off` to avoid repeated failing Transcribe calls. Browser
recognition may send audio to the browser vendor's service.
**Suggestion** Explain how to resolve this exception for the account, and
make the error distinguish service/account access problems from missing
IAM permissions.

---

## Candidates: add an entry only if you actually hit it

These were in an earlier draft as if they had happened. They have not been
observed, so they are **not** in the log. Promote one only with a real
observation and its numbers.

- Bedrock first-call latency after idle, or retry/timeout defaults too slow
  for voice. Measure with `make aws-check` and real calls.
- Bedrock model-access flow or error messages being unclear.
- Free football-data tiers being delayed or capped. Unverified: the vendor
  pages blocked automated reading; check them by hand.
- `_meta` conventions for UI payloads. No observation.
