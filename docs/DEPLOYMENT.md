# Deployment

Local runs with no AWS at all. This page is the **production reference**:
table definitions, schedules, IAM, monitoring.

**Setting AWS up for the first time?** Start with
[AWS_SETUP.md](AWS_SETUP.md) instead — it walks through account, model
access, credentials and verification in order, with a check after each
step.

## Local

```bash
python3 -m sideline
curl -s localhost:8765/health
```

To expose it to Alexa+ during development:

```bash
cloudflared tunnel --url http://localhost:8765
```

Alexa+ requires a remote HTTPS URL. A tunnel is the documented approach
for local development.

## App Runner

Chosen over Lambda behind API Gateway for one reason: Streamable HTTP
wants a long-lived HTTPS endpoint, and App Runner gives you one with no
load balancer, no gateway configuration and no cold-start behaviour on
the listener's critical path.

```bash
aws apprunner create-service \
  --service-name sideline \
  --source-configuration file://apprunner.json
```

> **Not shipped in this repository:** `apprunner.json` and a Dockerfile.
> They hold account-specific values (image or repo connection, role
> ARNs), so you write them for your own account. Nothing in the demo
> depends on them.

Health check `/health`, port 8765.

## DynamoDB

```bash
aws dynamodb create-table \
  --table-name sideline \
  --attribute-definitions AttributeName=PK,AttributeType=S \
                          AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH \
                AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

aws dynamodb update-time-to-live \
  --table-name sideline \
  --time-to-live-specification Enabled=true,AttributeName=expires_at
```

**Single table**, because the access patterns are two and known:

```
PK                 SK                     holds
LISTENER#<id>      PROFILE                following, last_told_at, told ids
FIXTURE#<id>       EVENT#<min>#<id>       one match event
FIXTURE#<id>       META                   teams, kickoff, status
```

Both hot reads are a single query. Nothing needs a scan, nothing needs a
GSI.

**On-demand capacity.** Match-day traffic is bursty and small.
Provisioning for it would cost a day and save nothing.

**TTL at 48 hours after kickoff.** Match events have no value afterwards.
Keeping them costs money and creates a privacy surface for no reason.

## EventBridge Scheduler

```bash
aws scheduler create-schedule \
  --name sideline-poller \
  --schedule-expression "rate(15 seconds)" \
  --flexible-time-window Mode=OFF \
  --target '{"Arn":"<lambda-arn>","RoleArn":"<role-arn>"}'
```

> **Status:** the handler exists ([scripts/lambda_handler.py](../scripts/lambda_handler.py));
> the schedule below is documented, not deployed from this repo.

The Lambda handler is three lines around `poller.poll_once(ctx)`. The
poller does not know whether a thread or a scheduler is calling it, which
is why the same code runs in both places.

Watch the interaction between a 15-second schedule and a third-party rate
limit. Overrunning it is easy and the failure shows up on the provider's
side, not yours. See FL-07.

## Secrets

```bash
aws secretsmanager create-secret \
  --name sideline/football-key \
  --secret-string '{"SIDELINE_FOOTBALL_KEY":"..."}'
```

> **Status:** documented design. No code in this repo calls Secrets
> Manager; today the key is read from the `SIDELINE_FOOTBALL_KEY`
> environment variable, which you would populate from the secret.

The key never enters the repository. This repo is public for the Open
Source mini challenge; a committed key would be both a security incident
and an avoidable embarrassment.

## IAM

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "arn:aws:bedrock:*::foundation-model/anthropic.claude-*" },
    { "Effect": "Allow",
      "Action": ["dynamodb:GetItem","dynamodb:PutItem","dynamodb:Query"],
      "Resource": "arn:aws:dynamodb:*:*:table/sideline" },
    { "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:*:*:secret:sideline/*" }
  ]
}
```

No wildcards on action. No `*` resource. The server invokes one model
family, touches one table and reads one secret prefix.

## Monitoring

> **Status:** latency is logged by the server; the CloudWatch alarms
> below are not created by this repo.

Per-tool latency is logged on every call (`took_ms` in `_meta`). The two
alarms worth having:

- **catch-up p95 above 2.5 s** — we are about to start falling back to
  templates, and the listener is noticing.
- **Bedrock spend above a daily threshold** — small workload, but a
  runaway poll loop could change that quickly.

## Configuration

Everything is environment variables. See `.env.example`. Defaults are
chosen so that no environment at all gives a working server against the
recorded match.
