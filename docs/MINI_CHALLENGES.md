# Mini challenges

A project may win one track prize and one mini challenge prize (rules,
2026-10-12). Whether to enter either is for you to decide against the
evidence: AWS Builder needs documented integrations that have actually run;
Open Source needs a project or contribution that exists.

---

## AWS Builder

> The official rules say to **describe the AWS services and how in the
> Product Feedback answer on the Devpost form**. Paste the tables below
> there; do not rely on the repo alone. The rules also describe a single
> Bedrock call as the "obvious" entry and a multi-service pipeline as the
> "creative" one, so lead with how many services do real work together.

**Qualifies by** using AWS services in the project with documented
integrations.

**In code, called from this repository**

| Service | Used for | Where |
|---|---|---|
| **Amazon Bedrock** | Compressing an event window into one spoken paragraph; long-absence milestones; translation | `language/bedrock.py` |
| **Amazon Polly** | Speech out for the simulator, with word-level speech marks | `voice.py` |
| **Amazon Transcribe** | Speech in for the simulator | `voice.py` |
| **Secrets Manager** | The football API key, fetched at startup when `SIDELINE_FOOTBALL_SECRET` is set | `secretsmanager.py` |
| **DynamoDB** | Listener state and the match event log (also runs against DynamoDB Local) | `state/dynamo.py`, `scripts/create_table.py` |
| **CloudWatch** | Per-tool latency and decline metrics (Embedded Metric Format) | `metrics.py`, `mcp/server.py` |

**Deployment, as infrastructure-as-code that has not been deployed by us**

| Service | Used for | Where |
|---|---|---|
| **App Runner** | Hosting the Streamable HTTP endpoint | `deploy/sideline.yaml`, `Dockerfile`, `scripts/deploy_aws.sh` |
| **Secrets Manager** | The football key, injected into the container as `SIDELINE_FOOTBALL_KEY` | `deploy/sideline.yaml` |
| **ECR, IAM** | Image registry and a least-privilege instance role | `deploy/sideline.yaml` |
| **CloudWatch alarm** | Catch-up p95 above 2.5 s | `deploy/sideline.yaml` |

The template passes `cfn-lint`; see [DEPLOYMENT.md](DEPLOYMENT.md) for the
status note.

**Documented alternative, not deployed**

| Service | Intended use | Where |
|---|---|---|
| **EventBridge Scheduler + Lambda** | Polling from outside the server (the poller otherwise runs in-process) | `scripts/lambda_handler.py`, `docs/DEPLOYMENT.md` |

Bedrock is not decoration here. It does the one piece of work that
cannot be delegated upward to Alexa+, because Alexa+ only sees what we
return. [BEDROCK.md](BEDROCK.md) sets out where it is used and — just as
deliberately — where it is not.

The documentation this challenge asks for is the architecture section we
needed anyway.

---

## Open Source

**Qualifies by** shipping a new open-source project, or a contribution to
a public repository, during the hackathon window.

**What we ship**

1. **This server**, MIT licensed, documented for reuse.

2. **A separate sports-feed-to-MCP adapter** *(planned; not yet
   published, and not part of this repo)*. The genuinely reusable
   part: `providers/base.Provider` plus the normalising rules, extracted
   as its own package.

### Why the adapter would be the contribution

The provider interface encodes three rules (see
`sideline/providers/base.py`) that any feed-to-MCP bridge has to decide:

- Stoppage time, which is not an integer minute and must not be read out
  as "forty five plus two".
- VAR, where the naive implementation deletes an overturned goal and
  leaves a listener who heard the crowd with no explanation.
- Event taxonomy, where penalties and own goals get their own kinds and
  every downstream consumer then has to know three things mean "the score
  changed".

Publishing them as a standalone package would be an artefact others could
reuse. **It does not exist yet.** The rules count a new open-source project
or a contribution (branch, fork or PR) made during the window; until one
exists, do not claim this mini challenge.

**Submission fields required:** contribution URL, repo URL, GitHub
username, and a short description of what it does, how it works and why
it matters.

---

## The friction log

Not a mini challenge: submissions with friction logs can earn up to a
**10% bonus**, assessed by Amazon's team (rules, 2026-10-12). Detailed
product feedback is mandatory regardless.

Each entry needs: task attempted, steps taken, expected versus actual,
severity, workaround, actionable suggestion.

Ours are in [FRICTION_LOG.md](FRICTION_LOG.md): seven entries, each tied to a
cited source and date. Check each against your own experience before
submitting.
