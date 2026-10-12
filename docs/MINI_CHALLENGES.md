# Mini challenges

A project may win one track prize and one mini challenge prize. We enter
both; neither requires work we were not already doing.

---

## AWS Builder

**Qualifies by** using AWS services in the project with documented
integrations.

| Service | Used for | Where |
|---|---|---|
| **Amazon Bedrock** | Compressing an event window into one spoken paragraph; open questions; translation | `language/bedrock.py` |
| **DynamoDB** | Listener state and the match event log | `state/dynamo.py` |
| **EventBridge Scheduler** | Waking the poller every 15 s | `poller.py`, `docs/DEPLOYMENT.md` |
| **App Runner** | Hosting the Streamable HTTP endpoint | `docs/DEPLOYMENT.md` |
| **Secrets Manager** | The football API key | `docs/DEPLOYMENT.md` |
| **CloudWatch** | Per-tool latency, alarms | `mcp/server.py`, `docs/DEPLOYMENT.md` |

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

2. **A separate sports-feed-to-MCP adapter.** The genuinely reusable
   part: `providers/base.Provider` plus the normalising rules, extracted
   as its own package.

### Why the adapter is the real contribution

Everyone who puts a sports feed behind MCP hits the same three problems,
and gets them wrong in the same three ways:

- Stoppage time, which is not an integer minute and must not be read out
  as "forty five plus two".
- VAR, where the naive implementation deletes an overturned goal and
  leaves a listener who heard the crowd with no explanation.
- Event taxonomy, where penalties and own goals get their own kinds and
  every downstream consumer then has to know three things mean "the score
  changed".

Solving those once, in public, is worth more than the prize. It also
answers the judging criterion about understanding the developer
ecosystem with an artefact rather than a claim, and it means the project
is still useful after the deadline — which is the "audience beyond the
hackathon" test.

**Submission fields required:** contribution URL, repo URL, GitHub
username, and a short description of what it does, how it works and why
it matters.

---

## The friction log

Not a mini challenge, but the cheapest marks available: submissions with
friction logs earn up to a **10% judging bonus**, and detailed product
feedback is mandatory regardless.

Each entry needs: task attempted, steps taken, expected versus actual,
severity, workaround, actionable suggestion.

Ours are in [FRICTION_LOG.md](FRICTION_LOG.md), written as we hit them.
Most entrants will submit two lines of feedback on the last night. This
is where a well-run team quietly gains a grade.
