# Amazon Bedrock

## The fair challenge

Alexa+ already contains a language model. Why call another one?

**Because Alexa+ only ever sees what we return.** Any reasoning that has
to happen *before* the response leaves our server has to happen on our
server.

The catch-up is exactly that case. Eleven minutes of a match can hold
nine raw events. Returning nine lines hands Alexa+ a list, and a list
read aloud sounds like a spreadsheet. Compressing nine events into one
paragraph that *leads with the goal* is a judgement about what mattered,
and it has to be made here, because once we return, it is too late.

## Where it is used — and deliberately not

**Used**

| Call | Why a model is needed |
|---|---|
| Simulator `/agent/chat` | Nova receives the MCP tool schemas, selects tools, and answers from their results. |
| `catchup()` | Composition and prioritisation. The one that genuinely earns it. |
| `milestones()` | A long absence, compressed to headlines plus an offer of detail. Called by `what_did_i_miss`. |
| `open_question()` | "Are we under pressure?" maps to no single tool. Reasons over retrieved events only. **Implemented, not yet exposed through a tool.** |
| `translate()` | Same facts, another language. Free accessibility win. |

**Direct MCP tools return deterministic data**

| Tool data | Why it is deterministic |
|---|---|
| `get_match_state`, `get_officials` | Structured match facts; the simulator agent passes these to Nova to phrase the final answer. |
| `get_event_detail`, `get_lineups` | Event and lineup data are supplied to Nova; direct MCP clients can consume the deterministic text/structured result. |

That split is a latency decision as much as a quality one.

## The grounding rule

This is the most important paragraph in the repository.

```
Use ONLY the events given to you. Never add a detail that is not in
them - no scorers, minutes, reasons or context from your own knowledge
of football. If something is not in the data, it did not happen.
```

A product whose entire claim is *"it knows what is happening right now"*
is destroyed by one confidently invented goal. A judge will test exactly
this, and should.

Full prompts: [`language/prompts.py`](../sideline/language/prompts.py).

### The guard

Prompting is necessary but not sufficient, so there is a check as well.
`_score_consistent()` parses any scoreline in the generated text and
discards the whole output if it disagrees with ours. In demo mode the
template takes over and `generated_by` reports `template-after-guard`.
In live mode the mismatch is surfaced as a failure; no canned answer is
substituted.

Deliberately conservative: it only rejects when the text states a
parseable scoreline **and** it disagrees. Vague text passes.

## Latency budget

> **Alexa+'s QuickStart sets a round-trip target of 500 ms** (read
> 2026-10-12). Measured: the template tools take about 0.2 ms of server
> time (docs/EVIDENCE.md). One real Nova verification invocation took
> about 2.1 s on 2026-10-13; this is one sample, not a catch-up latency
> guarantee. The table below is a design target. Choose
> deliberately with `SIDELINE_BEDROCK_TIMEOUT`:
>
> | Setting | Effect |
> |---|---|
> | `3.0` (demo default) | Best-written catch-up; can take 1–3 s; misses the 500 ms target. |
> | `0.4` | Usually too short for a model call. Demo mode may use templates; live mode reports timeout/failure instead. |
>
> **A way to have both is built: precomputed summaries** (below). They move
> the model off the listener's clock; they do not make it faster, and they
> have only been tested with a simulated model.

Design targets. The listener is waiting with a match on.

| Path | Budget |
|---|---|
| Fast tools, no model | target < 300 ms; **measured ~0.2 ms server time** |
| Catch-up, one model call | target < 2.5 s; exercised once with a real model, latency not recorded |
| Request ceiling | configurable; demo may fall back, live mode surfaces failure |

Three rules keep us inside it:

1. Fast tools never touch Bedrock.
2. Catch-up prompts are capped at 12 events.
3. The provider cache means no tool ever waits on the football API.

`max_attempts=1` on the boto3 client is intentional. A retry costs
another request timeout. Live mode reports a failed attempt; demo mode
may use its deterministic fallback.

The timeout bounds how long a live request waits. It does not turn a
failed call into an answer in live mode.

## Precomputed summaries (`sideline/summaries.py`)

In non-strict mode, the model can run off the listener's clock.

1. When the poller logs new events, it works out, for each listener
   following that fixture, the exact window they would be told about, and
   has the model write it **in a background thread**. The text goes in an
   in-process cache.
2. When the listener asks, the window is looked up. **A hit returns the
   cached paragraph with no model call.**
3. **A miss does not wait either**: it answers at once with the template and
   queues the generation, so the next ask in that state is a hit.

Guarantees, each pinned by `tests/test_summaries.py`:
- **Never stale.** The key is fixture, mode, language, score and the ids of
  the events in the window (flagged if VAR overturned them). Any change is
  a miss.
- **Never ungrounded.** Only text the existing guard accepted is cached; a
  contradicting scoreline is discarded.
- **Never silent.** Every response carries `summary_source`:
  `precomputed`, `template-fast`, `live` or `template`.
- **The poller is not blocked** by generation.

Limits, stated plainly:
- Precomputation and template-on-miss are disabled in strict live mode,
  which calls Nova for each request and surfaces failures.
- In non-strict mode, it moves the model off the clock; it does not speed
  it up. The first ask after a new event can still get the template if
  generation has not finished.
- Non-English listeners take the live path (a Creole speaker should not be
  answered in English), so they still pay the model's latency.
- The cache is per process. It needs the long-running server; a Lambda
  poller that exits between runs would leave nothing to read.
- With DynamoDB state, "who follows this fixture" uses marker items
  (`FOLLOWERS#<fixture>`); that path is tested with a fake table only.
- **Tested with a simulated 300 ms model.** Live catch-up passed
  `make aws-check` on 2026-10-13; real precompute/cache hit rates have not
  been measured.

`SIDELINE_CATCHUP_MODE=live` calls the model when the listener asks.
Strict `SIDELINE_MODE=live` forces this behavior and bypasses both
precomputed summaries and template-on-miss, regardless of the catch-up
mode setting.

## The simulator agent

The simulator posts the listener's transcript to `/agent/chat`. The server
passes the public MCP tool names, descriptions and input schemas to Nova
through Bedrock Converse tool use, validates each proposed argument using
the same schema as `tools/call`, then runs the existing registered tool
implementation. Tool results are returned to Nova for a final concise,
grounded answer. Recent user/assistant turns are retained in a bounded,
in-process per-listener history (30-minute idle expiry) so follow-up
questions have context; the history is not persisted across restarts. The
model never receives AWS credentials or calls an
external MCP endpoint; the server bridges Bedrock tool use to its own MCP
registry. The normal MCP transport remains available to other clients.

This differs from Alexa+: Nova does the routing and response phrasing in
the simulator, while Alexa+ is not involved. If Bedrock is unavailable, the
simulator falls back to its local keyword router and direct MCP calls.
That fallback is available only in demo mode. In `SIDELINE_MODE=live`, a
failed Nova request is surfaced as an error; the simulator does not answer
with keyword-routed tool output or a canned substitute.

In live mode, the `what_did_i_miss` tool supplies its structured event facts
to Nova directly, without an extra summary-model call or a prewritten
summary. Other tools likewise supply their verified match data as tool
results, and Nova composes the listener-facing answer.

## Model choice

`amazon.nova-micro-v1:0` is the default on Bedrock, configured in
`SIDELINE_BEDROCK_MODEL`. It supports the Converse API used for both tool
use and catch-up generation. The account must have valid AWS credentials
and permission to invoke the model in the configured region. Availability
varies by account and region; `make aws-check` checks the selected model.
We make no claim about what model Alexa+ uses.

`temperature=0.2`. This is reporting, not writing.

## Turning it on

Step by step in [AWS_SETUP.md](AWS_SETUP.md). Bedrock model access has to be
granted per account and model, and an access failure can look like a
credentials error; `make aws-check` separates the two.

```bash
pip3 install boto3
# export AWS credentials, then it switches on by itself (SIDELINE_BEDROCK=auto)
make aws-check
```

## Why it is only on when credentials are present

Demo mode runs without an AWS account. The Nova Micro invocation, agent
tool use, and live catch-up were verified with `make aws-check` on
2026-10-13. This confirms the configured account, region and model at that
time; it is not an end-to-end deployment test.

Every answer reports which path produced it, in
`structuredContent.generated_by`: `bedrock`, `template`, or
`template-after-guard` when the model contradicted the score and we
discarded it. That field is the easiest way to show the model working on
camera.

## IAM

Minimum viable policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
    "Resource": "arn:aws:bedrock:*::foundation-model/amazon.nova-*"
  }]
}
```

The non-streaming agent uses `InvokeModel`; the existing streamed
catch-up path uses `InvokeModelWithResponseStream`. No `bedrock:*`. Narrow
the resource to the selected model and region when your policy supports it.

## Cost

Not measured. A catch-up sends a few hundred tokens of event JSON and asks
for at most `MAX_TOKENS` (160) back, and a listener is expected to ask a
handful of times per match; those are expectations, not observations. Set a
budget alarm before turning it on (see DEPLOYMENT.md) and read your actual
usage after the first run.
