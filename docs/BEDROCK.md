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
| `catchup()` | Composition and prioritisation. The one that genuinely earns it. |
| `milestones()` | A long absence, compressed to headlines plus an offer of detail. Called by `what_did_i_miss`. |
| `open_question()` | "Are we under pressure?" maps to no single tool. Reasons over retrieved events only. **Implemented, not yet exposed through a tool.** |
| `translate()` | Same facts, another language. Free accessibility win. |

**Not used — these return templates**

| Tool | Why not |
|---|---|
| `get_match_state` | A scoreline is a fact. Generating it adds latency and risk and improves nothing. |
| `get_officials` | Likewise. |
| `get_event_detail` | One event, one sentence, already deterministic. |
| `get_lineups` | A list of names. Nothing to compose. |

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
discards the whole output if it disagrees with ours. The template takes
over and `generated_by` reports `template-after-guard`, so the fallback
is visible in the response rather than silent.

Deliberately conservative: it only rejects when the text states a
parseable scoreline **and** it disagrees. Vague text passes.

## Latency budget

> **Alexa+'s QuickStart sets a round-trip target of 500 ms** (read
> 2026-10-12). Measured: the template tools take about 0.2 ms of server
> time (docs/EVIDENCE.md). **Not measured: a Bedrock call.** No request has
> ever been made, so whether a model-written catch-up can meet 500 ms is
> unknown; the table below is design intent, not a result. Choose
> deliberately with `SIDELINE_BEDROCK_TIMEOUT`:
>
> | Setting | Effect |
> |---|---|
> | `3.0` (default) | Best-written catch-up; can take 1–3 s; misses the 500 ms target. |
> | `0.4` | Keeps every reply inside the target; in practice the model rarely finishes, so answers are the deterministic templates. |
>
> **A way to have both is built: precomputed summaries** (below). They move
> the model off the listener's clock; they do not make it faster, and they
> have only been tested with a simulated model.

Design targets. The listener is waiting with a match on.

| Path | Budget |
|---|---|
| Fast tools, no model | target < 300 ms; **measured ~0.2 ms server time** |
| Catch-up, one model call | target < 2.5 s; **not measured** |
| Hard ceiling | 3 s, then the template |

Three rules keep us inside it:

1. Fast tools never touch Bedrock.
2. Catch-up prompts are capped at 12 events.
3. The provider cache means no tool ever waits on the football API.

`max_attempts=1` on the boto3 client is intentional. A retry costs
another three seconds and the listener does not have six. One try, then
the template.

The timeout is not a safety net, it is a product decision: a correct
template answer at 2.9 s beats a beautiful generated one at 5 s, because
by then they have missed whatever just happened.

## Precomputed summaries (`sideline/summaries.py`)

The model should not be on the listener's clock, so it is not.

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
- It moves the model off the clock; it does not speed it up. The first ask
  after a new event can still get the template if generation has not
  finished.
- Non-English listeners take the live path (a Creole speaker should not be
  answered in English), so they still pay the model's latency.
- The cache is per process. It needs the long-running server; a Lambda
  poller that exits between runs would leave nothing to read.
- With DynamoDB state, "who follows this fixture" uses marker items
  (`FOLLOWERS#<fixture>`); that path is tested with a fake table only.
- **Tested with a simulated 300 ms model, never with Bedrock.** Real
  Bedrock latency is still unmeasured, and so is how often a real ask lands
  on a hit.

`SIDELINE_CATCHUP_MODE=live` restores the old behaviour (the model is called
when the listener asks).

## Model choice

Claude on Bedrock, because it is one AWS account, one region and one IAM
role, with no second vendor or key in the repository. Haiku is chosen on
the expectation that it is quick enough for a voice turn; **that has not
been measured here** and the model id may not be available on your account
(`make aws-check` lists what is). We make no claim about what model Alexa+
uses.

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

So the repository clones, runs and passes its tests with no AWS account and
no credentials. The client code is written and imported, but it has **never
been called against a real account**, so treat the integration as
unverified until `make aws-check` passes and its output is kept.

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
    "Action": "bedrock:InvokeModel",
    "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
  }]
}
```

No `bedrock:*`. No wildcard resource. The server invokes one model
family and nothing else.

## Cost

Not measured. A catch-up sends a few hundred tokens of event JSON and asks
for at most `MAX_TOKENS` (160) back, and a listener is expected to ask a
handful of times per match; those are expectations, not observations. Set a
budget alarm before turning it on (see DEPLOYMENT.md) and read your actual
usage after the first run.
