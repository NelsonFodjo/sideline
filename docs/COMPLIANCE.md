# Compliance

Every official requirement, mapped to where it is addressed. Checked
against the Devpost rules and FAQ directly. **"Addressed" is not "done":**
the right-hand column says what exists; whether each piece has been
verified is in [EVIDENCE.md](EVIDENCE.md), which wins any disagreement.

> Re-verified against the live rules on 2026-10-12; sources, dates and
> the things that could *not* be confirmed are in
> [OFFICIAL_RULES.md](OFFICIAL_RULES.md). That page supersedes anything
> below that disagrees with it.

## Track eligibility — Alexa+

> Build a self-hosted MCP server (spec 2025-11-25 or later, Streamable
> HTTP) or an Agent Skill.

> For Alexa+, Bee and Ring: your repo needs to actually call your
> track's required technology in code — an import, an entry point, a
> loaded agent/flow/MCP config — not just a mention in the README.

| Requirement | Where |
|---|---|
| Self-hosted MCP server | `sideline/mcp/server.py` |
| Spec 2025-11-25 | `PROTOCOL_VERSION`, negotiated on `initialize` |
| Streamable HTTP | `POST /mcp`, `GET /mcp` (SSE), `DELETE /mcp` |
| Called in code, not described | The server **is** the implementation. `python3 -m sideline` is the entry point; `tests/test_mcp_protocol.py` is our own nine-check suite (no official conformance suite was found) |

**On dependencies.** The rule names the *track's* required technology.
For Alexa+ that is an MCP server over Streamable HTTP, which this is —
there is no requirement to import any particular SDK. Our transport is
standard-library Python so the repository clones and runs with no
install step, which matters during judging: a reviewer who cannot run
the project scores nothing.

## AWS Builder mini challenge

> Use AWS services (Bedrock, AgentCore, Strands SDK, Kiro Crew,
> SageMaker, etc.) in your project with documented integrations.

| Service | Where | What it does |
|---|---|---|
| **Bedrock** (Converse, Nova Micro) | `language/bedrock.py`, `language/agent.py` | Nova selects MCP tools, answers from their results, and composes catch-ups; demo mode retains offline templates |
| **DynamoDB** | `state/dynamo.py` | Listener state and the match event log, single-table |
| **CloudWatch** (EMF) | `metrics.py`, `mcp/server.py` | Per-tool latency and decline metrics |
| **Secrets Manager** | `secretsmanager.py`, `deploy/sideline.yaml` | Football key injected as an environment variable. Not deployed by the authors |
| **App Runner, ECR, IAM** | `deploy/sideline.yaml`, `Dockerfile` | Hosting and least-privilege role. Passes `cfn-lint`; not deployed by the authors |
| **Polly** (neural + speech marks) | `sideline/voice.py` | Speech out for the simulator; word-level timings drive the reading animation |
| **Transcribe** (streaming) | `sideline/voice.py` | Speech in for the simulator, over raw 16 kHz PCM |
| EventBridge Scheduler + Lambda | `scripts/lambda_handler.py` | Documented alternative to the in-process poller; not deployed |

Setup is documented step by step in [AWS_SETUP.md](AWS_SETUP.md), and
`scripts/verify_aws.py` checks each layer so a reviewer can confirm the
integration rather than take it on trust.

boto3 is imported behind an optional dependency guard and initialized
lazily. In demo mode Bedrock falls back to deterministic templates and
state falls back to memory, so the repo still runs for a reviewer with
nothing installed. In live mode, Bedrock failures are surfaced instead
of returning canned language. Documented in `BEDROCK.md` and
`DEPLOYMENT.md`.

## Open Source mini challenge

> Ship a new, additional open-source project (include an open-source
> license) or a contribution to a public repository during the hackathon
> window. Include the contribution URL, your repo URL, your GitHub
> username, and a short description of what you did, how it works and
> why it matters.

MIT licence in the root. The additional project is the sports-feed
adapter. **It is planned and not yet published** — see `MINI_CHALLENGES.md`
for what it is and why the three problems it solves are worth solving
once in public. Do not claim this challenge until the repository exists.

> Each project can only win one track prize and one mini challenge prize.

Understood. We enter both mini challenges; only one can be won.

## What to submit

| Requirement | Where |
|---|---|
| Text description of what it does and how it works | `README.md` |
| GitHub repo with all source, assets and run instructions | this repository |
| Public with an open-source licence, **or** private and shared with the reviewers | `LICENSE` (MIT) — if kept private, see the handles in `SUBMISSION_CHECKLIST.md` |
| Demo video under 3 minutes, YouTube or Vimeo, public, English | **Not recorded.** A plan is in `DEMO_SCRIPT.md` |
| No third-party trademarks or copyrighted music/footage | `DEMO_SCRIPT.md`, hard rules |
| Product feedback on every tool, API or SDK | `PRODUCT_FEEDBACK.md`: **a draft with `TODO(you)` slots** that only hands-on runs can fill |
| Which track and mini challenges | Alexa+ · AWS Builder · Open Source |
| **If the project existed before the hackathon**, what changed in the window | `PRIOR_WORK.md` |
| *Optional:* feature requests with urgency | `FEATURE_REQUESTS.md` |
| *Optional:* friction log entries — **up to a 10% judging bonus** | `FRICTION_LOG.md` |

## Judging window

Reviewers must be able to reach and run the project through the judging
period. Three things protect that:

- No install step, no credentials, no paid API. `python3 -m sideline`
  works from a clean clone.
- No live data dependency. The replay harness is deterministic, so the
  demo path works on any day, at any hour.
- GitHub reviewer invitations expire after 7 days — sent **on
  submission day**, not before. If one lapses, re-send from the same
  Collaborators page.

## Data and attribution

Match data from StatsBomb Open Data, used under its licence, attributed
in the README, in the demo video description, and in the replay file
itself.

The demo describes replayed data as **"a real match, replayed"** and
never implies live. The data is genuine; the clock is ours.
