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

The listener is waiting with a match on.

| Path | Budget |
|---|---|
| Fast tools, no model | < 300 ms |
| Catch-up, one model call | < 2.5 s |
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

## Model choice

Claude on Bedrock. Alexa+ is itself built on Claude models, so the
phrasing layer sits in the same family as the voice the listener hears,
which keeps the register consistent for nothing. One region, one IAM
role, no second vendor, no second key in the repository.

`temperature=0.2`. This is reporting, not writing.

## Turning it on

Step by step in [AWS_SETUP.md](AWS_SETUP.md), including the one everyone
misses: **Bedrock model access is off by default**, and the resulting
error reads like a credentials problem when it is not.

```bash
pip3 install boto3
export SIDELINE_BEDROCK=on
python3 scripts/verify_aws.py
```

## Why it is off by default here

So the repository clones, runs and passes its tests with no AWS account
and no credentials. boto3 is imported and the client is initialised —
this is a live integration, not a reference — but the switch defaults to
off so a reviewer with nothing installed still gets a working server.

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

One catch-up is a few hundred input tokens and under a hundred output.
Catch-ups are rare — a listener asks a handful of times a match. This is
not a workload that needs a cost model; it needs a budget alarm, which is
in [DEPLOYMENT.md](DEPLOYMENT.md).
