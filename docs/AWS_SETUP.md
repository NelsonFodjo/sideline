# Setting up the AWS side

Start to finish, in order, with a way to check each step worked before
moving to the next.

**You do not need any of this to run Sideline.** The default is
in-memory state and deterministic templates, and `python3 -m sideline`
works on a clean machine with nothing installed. This page is for
turning on the two AWS integrations: Bedrock for language, DynamoDB for
state.

Budget about 40 minutes the first time. Most of it is waiting for model
access.

---

## Step 0 — What you are turning on, and why

| | What it does | Needed for |
|---|---|---|
| **Bedrock** | Compresses a window of match events into one spoken paragraph | AWS Builder mini challenge; the catch-up reads better |
| **Polly** | Speech out for the simulator, with word-level speech marks | The reading animation being exact rather than approximate |
| **Transcribe** | Speech in for the simulator | A speech-first demo at all |
| **DynamoDB** | Listener state and the match event log | Nothing, for a demo. Memory works. Turn it on to show durable state |

If you are short on time: **Bedrock, then Polly and Transcribe, and skip
DynamoDB.** Bedrock qualifies the AWS Builder entry and is the piece a
judge can see working. Polly and Transcribe are what make the simulator
a speech-first demo instead of a typed one, and they need no setup
beyond the credentials you already configured in step 2.

All four sit in the same account under the same credential chain, which
is the point: there is no second vendor and no second key anywhere in
the voice path.

---

## Step 1 — An AWS account and a Builder ID

Two different things, and the submission form asks for the second.

1. An **AWS account** at aws.amazon.com, if you do not have one. Needs a
   card; everything here sits inside or just above the free tier.
2. An **AWS Builder ID** — a separate free profile, created at the AWS
   Builder ID sign-up page. The Devpost form has a field for it.

> Create the Builder ID early. It is free and takes two minutes, and it
> is an annoying thing to discover you need at 11pm on submission day.

---

## Step 2 — Credentials on your machine

```bash
pip3 install boto3 awscli amazon-transcribe
aws configure
```

It asks for four things. Region matters: **use `us-east-1`** unless you
have a reason not to. Model availability is widest there, and a model
that exists in one region simply is not there in another.

**Check it worked:**

```bash
aws sts get-caller-identity
```

You should see your account id and an ARN. If you see
`Unable to locate credentials`, `aws configure` did not save — on macOS
and Linux it writes to `~/.aws/credentials`.

---

## Step 3 — Enable Bedrock model access

**This is the step everyone misses.** Bedrock models are off by default.
Your credentials will be perfectly valid and the call will still fail,
with an error that reads like a permissions problem rather than a "you
have not asked for this model yet" problem.

1. AWS console → **Amazon Bedrock** → make sure you are in **us-east-1**
2. Left sidebar → **Model access**
3. **Modify model access** / **Enable specific models**
4. Tick **Claude 3.5 Haiku**
5. Submit

Anthropic models usually enable in under a minute. Some accounts get a
short review. The status has to read **Access granted** before anything
below will work.

**Check it worked:**

```bash
aws bedrock list-foundation-models --region us-east-1 \
  --query "modelSummaries[?contains(modelId,'haiku')].modelId" --output text
```

You want `anthropic.claude-3-5-haiku-20241022-v1:0` in the output. If
the list is empty, access has not come through yet.

---

## Step 4 — Permissions

If you are using your own root or admin credentials, skip this; you
already have them.

For a scoped IAM user or role, this is the whole policy:

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

One action, one model family. Not `bedrock:*`, not `"Resource": "*"` —
a judge reading the repo should see least privilege, and it costs
nothing to get right.

---

## Step 5 — Turn Bedrock on in Sideline

```bash
export SIDELINE_BEDROCK=on
export AWS_REGION=us-east-1
python3 scripts/verify_aws.py
```

`verify_aws.py` checks each layer in turn and tells you exactly which
one failed. Run it before the server, not after.

Then:

```bash
python3 -m sideline
python3 scripts/smoke_test.py       # in another terminal
```

**How to tell it is actually running through Bedrock:** the catch-up
response reports which path produced the words.

```
(window 12' -> 64', 5 events, via bedrock)
```

`via bedrock` means the model ran. `via template` means it fell back and
something above did not work. `via template-after-guard` means the model
ran but produced a scoreline that disagreed with ours and we discarded
it.

That field is in `structuredContent.generated_by` on every tool, so it
is visible in the raw response as well as the smoke test — which makes
it easy to put on screen in the demo video.

---

## Step 5b — Speech, for the simulator

Nothing to enable. Polly and Transcribe need no model-access step, and
the credentials from step 2 are enough.

```bash
pip3 install amazon-transcribe        # if you have not already
python3 -m sideline
```

The startup log tells you what is in use:

```
voice: in=transcribe out=polly (Amy, neural)
```

`in=browser out=browser` means it fell back. The simulator shows the
same thing along the bottom of the screen.

**Why these two specifically.** Transcribe keeps the whole voice path in
one account under one credential chain. Polly is there for speech marks
— it returns every word with its millisecond offset, which is what makes
the reading animation land on the word rather than near it. No other
option in the pipeline gives that.

**Permissions**, if you are on a scoped role:

```json
{
  "Effect": "Allow",
  "Action": ["polly:SynthesizeSpeech", "transcribe:StartStreamTranscription"],
  "Resource": "*"
}
```

Neither action supports resource-level permissions, which is why these
are the one place in the project with a `*`.

**Voices.** `Amy` and `Brian` are British, `Joanna` and `Matthew`
American. Set `SIDELINE_POLLY_VOICE`. A British voice reads European
football names with less friction.

## Step 6 — DynamoDB, locally, for nothing

Optional. Use DynamoDB Local rather than a real table: same API calls,
same code path, no cloud spend, no IAM.

```bash
docker run -d -p 8000:8000 amazon/dynamodb-local

aws dynamodb create-table \
  --table-name sideline \
  --attribute-definitions AttributeName=PK,AttributeType=S \
                          AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH \
                AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --endpoint-url http://localhost:8000

export SIDELINE_STATE=dynamo
export SIDELINE_DYNAMO_ENDPOINT=http://localhost:8000
python3 -m sideline
```

**Check it worked:**

```bash
aws dynamodb scan --table-name sideline \
  --endpoint-url http://localhost:8000 --max-items 5
```

Follow a match and ask a question first — you should see `LISTENER#` and
`FIXTURE#` items come back.

For a real table, drop `--endpoint-url` and unset
`SIDELINE_DYNAMO_ENDPOINT`. The table design and TTL are in
[DEPLOYMENT.md](DEPLOYMENT.md).

---

## Step 7 — Hosting, only if you are connecting a real device

Not needed for the demo video or for a judge running the repo. Needed
only to deploy the Alexa+ add-on against a real Echo.

For development, a tunnel is enough and is the documented approach:

```bash
cloudflared tunnel --url http://localhost:8765
```

That gives you an HTTPS URL to hand to `alexa-ai`. For something
longer-lived, App Runner is in [DEPLOYMENT.md](DEPLOYMENT.md) — chosen
over Lambda behind API Gateway because Streamable HTTP wants a
long-lived endpoint and App Runner gives you one with no load balancer
to configure.

---

## What it costs

Small enough that the honest answer is "set a billing alarm and stop
thinking about it."

A catch-up is a few hundred input tokens and under a hundred out, and a
listener asks a handful of times a match. Haiku is the cheapest model in
the family. DynamoDB Local is free; a real on-demand table at this
volume is pennies.

The one thing that could change that is a runaway poll loop, so:

```bash
aws budgets create-budget --account-id <your-id> \
  --budget '{"BudgetName":"sideline","BudgetLimit":{"Amount":"10","Unit":"USD"},
             "TimeUnit":"MONTHLY","BudgetType":"COST"}'
```

---

## When it does not work

| Symptom | Cause | Fix |
|---|---|---|
| `via template` with `SIDELINE_BEDROCK=on` | Something upstream failed and we degraded silently, by design | `python3 scripts/verify_aws.py` |
| `AccessDeniedException` on invoke | Model access not granted — **not** a credentials problem | Step 3 |
| `ValidationException: model not found` | Wrong region, or wrong model id | `AWS_REGION=us-east-1` |
| `Unable to locate credentials` | `aws configure` never saved | Step 2 |
| `ThrottlingException` | New accounts have low initial quotas | It falls back to templates; request a quota increase if it persists |
| First call slow, later ones fine | Cold start after idle — known, logged as FL-05 | Nothing to fix; the 3 s ceiling catches it |
| `ResourceNotFoundException` on DynamoDB | Table not created, or wrong endpoint | Step 6 |
| `ImportError: boto3` | Not installed | `pip3 install boto3` |
| `in=browser` in the startup log | Transcribe SDK missing or no credentials | `pip3 install amazon-transcribe`, then `aws sts get-caller-identity` |
| `out=browser` in the startup log | No credentials for Polly | Step 2 |
| Robotic voice in the simulator | It fell back to the browser | Check the strip along the bottom of the page |

Everything above degrades rather than crashes. If Bedrock is
unreachable, the language layer uses templates and the product still
works — which is deliberate, so a reviewer with no AWS account still
sees a working server.

---

## The short version

```bash
pip3 install boto3 amazon-transcribe
aws configure                      # region: us-east-1
# console -> Bedrock -> Model access -> enable Claude 3.5 Haiku
export SIDELINE_BEDROCK=on
python3 scripts/verify_aws.py       # must pass before the next line
python3 -m sideline                # expect: voice: in=transcribe out=polly
```
