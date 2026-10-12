# Deployment

Local runs with no AWS at all. This page is the **production path**: one
command to build and deploy, plus the reference for what it creates.

**Setting AWS up for the first time?** Do [AWS_SETUP.md](AWS_SETUP.md)
first. It gets credentials and Bedrock access working and verified.

> **Status, stated plainly.** `deploy/sideline.yaml` passes `cfn-lint`
> and the deploy script passes `bash -n`, and the code paths they run
> are covered by the test suite. The stack has **not been deployed to a
> live AWS account by the authors**. Expect to read one CloudFormation
> error the first time; `aws cloudformation describe-stack-events` says
> what it was.

## Local

```bash
python3 -m sideline
curl -s localhost:8765/health
```

To expose it to Alexa+ during development, without deploying anything:

```bash
cloudflared tunnel --url http://localhost:8765
```

Alexa+ requires a remote HTTPS URL; a tunnel is the documented approach
for local development.

## One command to production

```bash
aws sts get-caller-identity          # credentials work
docker info >/dev/null                # docker is running
make deploy                           # = scripts/deploy_aws.sh
```

It creates an ECR repository, builds the [Dockerfile](../Dockerfile) for
`linux/amd64` (App Runner runs amd64, which matters on Apple Silicon),
pushes it, and deploys [deploy/sideline.yaml](../deploy/sideline.yaml).
The output table gives you `ServiceUrl`; the MCP endpoint is
`<ServiceUrl>/mcp`.

To change parameters, pass them through `EXTRA`:

```bash
EXTRA="BedrockModelId=us.anthropic.claude-haiku-4-5-20251001-v1:0" make deploy
EXTRA="AuthMode=required AuthIssuer=https://cognito-idp.us-east-1.amazonaws.com/<pool> \
       AuthResource=https://<ServiceUrl>/mcp AuthScopes=sideline.read \
       AuthJwksUrl=https://cognito-idp.us-east-1.amazonaws.com/<pool>/.well-known/jwks.json" make deploy
```

(The model id above is an example of the *shape* of an inference-profile
id; use whatever `scripts/verify_aws.py` lists for your account.)

Tear it all down, and stop the bill:

```bash
aws cloudformation delete-stack --stack-name sideline
```

## What the stack creates

| Resource | Why |
|---|---|
| **App Runner service** | Hosts the Streamable HTTP endpoint. Chosen over Lambda behind API Gateway because Streamable HTTP wants a long-lived HTTPS endpoint, with no gateway to configure and no cold start on the listener's critical path. Health check `/health`, port 8765. |
| **DynamoDB table** | Listener state and the match event log, on-demand, TTL on `expires_at`. |
| **Instance role** | `bedrock:InvokeModel` on `anthropic.claude-*` (and inference profiles in this account), `GetItem/PutItem/Query` on the one table, and `GetSecretValue` on the one secret if you supply one. No wildcard actions. |
| **ECR access role** | The AWS-managed policy App Runner needs to pull the image. |
| **CloudWatch alarm** | `what_did_i_miss` p95 above 2.5 s: model calls are about to hit the 3 s ceiling and fall back to templates. |

### DynamoDB design

Single table, because the access patterns are two and known:

```
PK                 SK                     holds
LISTENER#<id>      PROFILE                following, last_told_at, told ids
FIXTURE#<id>       EVENT#<min>#<id>       one match event
FIXTURE#<id>       META                   teams, kickoff, status
```

Both hot reads are a single query. Nothing needs a scan or a GSI.
On-demand capacity because match-day traffic is bursty and small. TTL at
48 hours after kickoff because match events have no value afterwards and
keeping them only creates a privacy surface.

Outside the stack (for local or hand-built setups) `make create-table`
does the same thing, against DynamoDB Local if `SIDELINE_DYNAMO_ENDPOINT`
is set.

### The poller

It runs **inside the server process** (`poller.py`, started by
`app.main`). The stack therefore needs no Lambda and no schedule.

If you would rather poll from outside, [scripts/lambda_handler.py](../scripts/lambda_handler.py)
is three lines around `poller.poll_once(ctx)`, and an EventBridge
Scheduler rule `rate(15 seconds)` can call it. That variant is
**documented, not deployed from this repo**. Mind the interaction
between a 15-second schedule and a third-party rate limit; overrunning
it shows up on the provider's side, not yours. See FL-07.

### Secrets

For a paid football feed, store the key in Secrets Manager (the secret's
**string value is the key itself**) and give the stack its ARN. App
Runner injects it into the container as the ordinary environment variable
`SIDELINE_FOOTBALL_KEY`, which wins over everything. (Outside App Runner,
`SIDELINE_FOOTBALL_SECRET` makes the app fetch it from Secrets Manager at
startup when the key variable is unset: `sideline/secretsmanager.py`.) The instance role gets read access to that one secret only.

```bash
aws secretsmanager create-secret --name sideline/football-key --secret-string '<key>'
EXTRA="FootballSecretArn=<arn from the command above>" make deploy
```

The key is never in the template, the image, or App Runner's plain-text
variables. This repo is public for the Open Source mini challenge; a
committed key would be both a security incident and an avoidable
embarrassment.

### Monitoring

The stack sets `SIDELINE_EMF=on`. Each tool call then writes one
CloudWatch Embedded Metric Format line to stdout
([metrics.py](../sideline/metrics.py)), which CloudWatch turns into
`Sideline/ToolLatency` and `Sideline/ToolDeclined` metrics, per tool, with
no extra API calls or permissions. `took_ms` is also in every response's
`_meta`.

Not created by the stack, worth adding: a daily Bedrock spend alarm.
A runaway poll loop could change a tiny workload quickly. A plain
account budget does the job:

```bash
aws budgets create-budget --account-id <your-id> \
  --budget '{"BudgetName":"sideline","BudgetLimit":{"Amount":"10","Unit":"USD"},
             "TimeUnit":"MONTHLY","BudgetType":"COST"}'
```

## Configuration

Everything is environment variables, which take priority over an optional
`.env` file for local runs. See [ENVIRONMENT.md](ENVIRONMENT.md).
Defaults are chosen so that no environment at all gives a working server
against the recorded match.
