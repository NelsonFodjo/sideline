# Amazon Bedrock

## The fair challenge

Alexa+ already contains a language model. Why call another one?

**Because Alexa+ only ever sees what we return.** Any reasoning that has to happen *before* the response leaves
our server has to happen on our server.

The catch-up is exactly that case. Eleven minutes of a match can hold nine raw events. Returning nine lines
hands Alexa+ a list, and a list read aloud sounds like a spreadsheet. Compressing nine events into one paragraph
that *leads with the goal* is a judgement about what mattered, and it has to be made here, because once we
return, it is too late.

## Where it is used, and deliberately not

**Used**

| Call | Why a model is needed |
|---|---|
| `catchup()` | Composition and prioritisation. The one that genuinely earns it. |
| `milestones()` | A long absence, compressed to headlines plus an offer of detail. Called by `what_did_i_miss`. |
| `translate()` | The same facts in another language or register (a listener can ask for one). |
| The MCP host, `/agent/chat` (Amazon Nova Pro by default) | Fetches `initialize` instructions and `tools/list` over MCP, gives the model a shortlist from the live tool catalog, then executes its `tools/call` selections over MCP. |
| Mistral Voxtral, then Nova 2 Sonic as the fallback | speech in: a separate use of Bedrock, described in [SPEECH.md](SPEECH.md). |

**Deterministic, never a model**

| Tool | Why |
|---|---|
| `get_match_state`, `get_officials`, `get_lineups`, `get_event_detail` | These are facts. Generating a scoreline adds latency and risk and improves nothing. |

That split is a latency decision as much as a quality one.

## One rule for failure

If Bedrock is **on** (`SIDELINE_BEDROCK=on`, or `auto` with AWS credentials), a failure is **reported** and never
papered over with canned wording:

- a call that errors or times out raises `BedrockUnavailable` (not retried: a retry costs another timeout);
- text that comes back empty or with a wrong score is refused, **retried once** (it is quick and often not
  repeated), and then raises `BedrockUnavailable`;
- the `what_did_i_miss` tool turns that into a spoken decline ("The language model said: <the real error>. Try again shortly", or earlier wording: "I can't put that into words right now, ask me
  again in a moment") **without moving the listener's marker**, so asking again still gets the whole gap;
- the voice agent surfaces it as "no answer".

If Bedrock is **off**, the deterministic templates in [`templates.py`](../sideline/language/templates.py) are used,
and the response says `generated_by: template`. That is a configuration choice, not a fallback.

Every response reports who wrote the words in `structuredContent.generated_by`: `bedrock`, `template`,
`tool-data` (the host asked for facts) or `bedrock+bedrock` (translated). It is the easiest way to show the model
working on camera.

## The grounding rule

This is the most important paragraph in the repository.

```
Use ONLY the data given to you. Never add a detail that is not in it - no scorers, minutes, reasons
or context from your own knowledge of the sport. If something is not in the data, it did not happen.
```

A product whose entire claim is *"it knows what is happening right now"* is destroyed by one confidently invented
goal. Full prompts: [`language/prompts.py`](../sideline/language/prompts.py).

### The guard

Prompting is necessary but not sufficient, so there is a check as well. `_score_consistent()` parses any
scoreline in the generated text and refuses the whole output if it disagrees with ours (`BedrockUnavailable`, so
the listener is told, not given a wrong score). It is deliberately conservative: it only refuses when the text
states a parseable scoreline **and** it disagrees. Vague text passes.

## Latency

> **Alexa+'s QuickStart sets a round-trip target of 500 ms** (rules read 2026-10-12). **A Bedrock catch-up misses
> it:** a real Bedrock Converse call took about 1.5 to 2.1 s on 2026-10-13 (a few samples on one account, not a guarantee). The
> fast tools call no model, so they are not held to account by this.

Three rules keep the rest inside a listener's patience:

1. Fast tools never touch Bedrock.
2. Catch-up prompts are capped at 12 events.
3. The provider caches what changes for seconds only (the scoreboard and a live match summary 5 s, most other reads
   10 s by default), so the tools one question calls share one read of the feed.

`total_max_attempts=1` on the boto3 client is intentional: a retry costs another request timeout (botocore's
`max_attempts=1` would mean two tries). The exception is the Bedrock MCP host. It retries **once**, after 0.6 s, when AWS
answers at once with "capacity limit reached" or "slow down" (`ServiceUnavailableException`, `ThrottlingException`). And
`_ask` in `simulator/agent.py` tries once more after a read timeout, a throttle or `ServiceUnavailable`, because the first
question of a session failed that way in the logs. Any other error is not retried. The request ceiling is
8 seconds, so the worst case is two timeouts. A first-ever precompute-and-cache design was built and then removed: it moved the model off the
listener's clock but was only ever tested against a simulated model, and the honest statement is that a catch-up
takes about two seconds.

## The MCP host

The simulator posts the listener's transcript to `/agent/chat`. The server resolves what they meant
([SPEECH.md](SPEECH.md)), then discovers the MCP `initialize` instructions and `tools/list` catalog over
[`simulator/mcp_client.py`](../simulator/mcp_client.py). It passes a shortlist of the discovered tools, with their full
descriptions and input schemas, to Bedrock Converse: four core tools plus up to four that match the question's words
(`_select_candidate_tools`). The model (Amazon Nova Pro by default) decides whether and what to call; selected tools are
executed through the same server's `/mcp` endpoint, with protocol sessions and server-side schema validation. Tool
results return to the model for its answer. The prompt contains general grounding and spoken-response guidance, not
phrase-to-tool rules. If the model answers a fact question with no tool, the next call must use one (`toolChoice: any`).
Some plain questions ("what's the score") skip the model: a fast path (`_try_fast_path`) matches the whole question to a
fixed pattern and runs one read-only tool; if it fails, the model answers instead.

Bedrock is a model API, not an MCP client: a host must do this discovery and dispatch. Any other
MCP-capable host can connect directly to `/mcp` and give its model the same tool catalog.

Conversation context is four layers, each small and bounded, and none is persisted across restarts:

1. **Recent turns**: the last 12 messages per listener, 30-minute idle expiry, 256 listeners at most.
2. **The topic** (`Focus` in `agent.py`): after each turn the real tool results, not the model's wording, are reduced to
   the match, team and player just discussed, and the next turn's system prompt says so ("The listener was last talking
   about the match Arsenal against Lille, the player Saka..."). That is what makes "and their form?", "what about him?"
   and "that match" mean something on a model, including for a match the listener is not following. It expires
   after ten minutes, a new match drops the old player, a bare pronoun is never a topic, and the prompt says it is
   context, not a fact to state.
3. **Offers** (`resolve.py`): what was just offered ("Arsenal or Arsenal W?") is remembered for two minutes, so a
   mispronounced or one-word answer snaps to an option.
4. **The interruption**: if the listener talked over the last answer, the words that were cut off are passed along so
   what they say next is read as a follow-up to them.

The durable context, which team is followed, what has been told (`last_told_at`), the broadcast delay, favourites and
time zone, lives in the state store and survives restarts. The model never receives AWS credentials. The agent is told to answer in 1 to 3 short,
complete sentences unless asked for more, never to narrate, and never to promise to keep the listener updated (the
server cannot speak first). The answer is then capped by the listener's detail level: one sentence for brief, three by
default, five for full.

For the host, `what_did_i_miss` returns its structured event facts, not a prewritten paragraph (a header asks for
this): the host model is itself an LLM and would only paraphrase a paragraph, at the cost of a second model call.

## Model choice

**Default: `amazon.nova-pro-v1:0` (Amazon Nova Pro)**, set by `SIDELINE_BEDROCK_MODEL`. It uses Bedrock's Converse API for
both MCP tool use and catch-up generation. Availability varies by account and region; `make aws-check` checks the
selected model. We make no claim about what model Alexa+ uses. This only decides which model plays the host in our
simulator; the MCP server does not depend on it.

**Why Nova Pro.** `scripts/route_check.py` gives a model the full tool list from `tools/list` and 79 things a
listener might say, each with the tool it should land on, and counts how often the model calls that tool. Invented match
data, real Bedrock, one account, one run per cell (2026-10-15):

| Model | First run | After the prompt fix | After the final fixes |
|---|---|---|---|
| **Amazon Nova Pro** | 56 / 79 | 59 / 79 | **77 / 79** (re-run after the last agent changes) |
| Anthropic Claude Sonnet 4.5 | 43 / 79 | 56 / 79 | not re-run |
| Anthropic Claude Haiku 4.5 | 34 / 79 | 53 / 79 | not re-run |
| Amazon Nova Micro | 39 / 71 (an earlier, shorter set) | not re-run | not re-run |

Read it for what it is. Nova Pro was ahead at every stage where the models were run under the same conditions (3 to 6
phrasings over Sonnet, more over the others), and it is the only one we measured after the last fixes, because we stopped
comparing and chose it. The last column also includes changes to the harness (a frozen match clock, waiting and retrying
when Bedrock throttles) that the earlier columns did not have, so do not read 59 to 77 as the model getting better alone. (The last column was run twice, 76 then 77, with an agent change between: a fact question the model first answers from memory is now sent back to the tools.)
The two remaining misses are "say that again" (no tool call: the harness reports a miss, and a person might answer it from
the conversation) and "how did the Arsenal Lille game finish" (the model asked for the fixtures, not the match report). This is a routing check on 79 lines, not a quality ranking of the
models.

Earlier history. On 2026-10-13 a broad batch of live questions showed Nova Micro dropping arguments the question plainly
gave ("where is Celtic in the league?" arrived with no team) where Nova Lite kept them. That is why Micro is not the
default. Switching is one line: `SIDELINE_BEDROCK_MODEL=<model id>`. Prompt caching (`cachePoint`) is refused by Nova Micro
(FL-19) and was not tried on Pro.

## Turning it on

Step by step in [AWS_SETUP.md](AWS_SETUP.md). Model access is granted per account and model, and an access failure
can look like a credentials error; `make aws-check` separates the two.

```bash
./run.sh
# On first launch this installs boto3 in .venv from requirements.txt.
# Set AWS credentials in .env and Bedrock switches on by itself (SIDELINE_BEDROCK=auto).
```

## IAM

What the Bedrock code calls (the full policy, with Polly and DynamoDB, is in [AWS_SETUP.md](AWS_SETUP.md)):

```json
{"Effect": "Allow",
 "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
            "bedrock:InvokeModelWithBidirectionalStream"],
 "Resource": ["arn:aws:bedrock:*::foundation-model/amazon.nova-*",
              "arn:aws:bedrock:*::foundation-model/mistral.*"]}
```

`mistral.*` is for Voxtral (speech in). A Claude model set through `SIDELINE_BEDROCK_MODEL` needs its own resource;
[AWS_SETUP.md](AWS_SETUP.md) uses `foundation-model/*` plus inference profiles, which covers all of them.

The agent uses `InvokeModel` or the streaming call; the catch-up uses `InvokeModelWithResponseStream`; Nova Sonic uses
the bidirectional stream. No `bedrock:*`.

## Cost

Not measured. A catch-up sends a few hundred tokens of event JSON and asks for at most 160 back, and a listener is
expected to ask a handful of times per match; those are expectations, not observations. Set a budget alarm before
turning it on and read your actual usage after the first run.

## Token usage

Every model call writes a `tokens` line to the day's call log (`logs/calls-<date>.jsonl`) with the input and output
counts exactly as Bedrock reports them (the Converse response's `usage`), and `make log-report` totals them by source
(`agent` for the voice agent, `text` for catch-ups). The full 30-tool list is about 8,000 tokens by the estimate in
`scripts/bench.py` (characters / 4, for comparing versions, not for billing). The simulator's agent sends a shortlist
of the tools a question could need, and one real Bedrock trace of a single turn showed about 2,200 input tokens.
`make route-check` runs the routing comparison above against the live model and invented match data.
