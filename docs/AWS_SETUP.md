# Setting up the AWS side

In order, each step with a way to check it worked. Console menu names and model availability change; where a
step fails, trust the error and `make aws-check` over this page.

> **Status, 2026-10-13, one account.** Bedrock (Nova Micro), Nova 2 Sonic, Polly and DynamoDB were each run
> against a real account and work. Nothing here has been run on a different account, so treat the permission lists
> as what *this* code calls, not as a promise about yours.

You do not need all of it. What each piece unlocks:

| | What it does | Without it |
|---|---|---|
| **Bedrock (Nova Micro)** | writes the spoken catch-up; the voice agent chooses tools | the fast tools still answer in templated wording; the simulator's voice agent has no answer |
| **Polly** | the voice, with word timings | the page uses the browser's own voice |
| **Nova 2 Sonic** | speech in, when there is no Groq key | the browser's own recognition (the least accurate) |
| **DynamoDB** | what a listener has heard survives a restart | state lives in memory |

If you are short on time: Bedrock first, then Polly, and skip DynamoDB.

## Step 1: an AWS account

An AWS account at aws.amazon.com (it needs a card; everything here costs cents). The hackathon form also asks
for an **AWS Builder ID**, a separate free profile; create it early. Per the rules the AWS credit codes ran out
on 7 October, so assume you pay for what you use.

## Step 2: credentials on your machine

```bash
pip3 install boto3
cp .env.example .env     # then fill in the AWS lines, or export them in your shell
```

Any one of: `AWS_ACCESS_KEY_ID` with `AWS_SECRET_ACCESS_KEY`, or `AWS_PROFILE`, or (Bedrock only)
`AWS_BEARER_TOKEN_BEDROCK`. Region: **`us-east-1`** unless you have a reason not to, because model availability is
widest there.

A **Bedrock API key** (a bearer token) works for Bedrock but not for Polly or DynamoDB: it is backed by an IAM
user that, on the account this was built on, could call Bedrock and Polly but was denied DynamoDB. Use IAM keys
for the full set.

**Check it:** `make env` (shows which are set, never the values), then `make aws-check`; its first lines read
"credentials resolve".

## Step 3: Bedrock model access

Check that Amazon Nova Micro is available to your account in the region: console, Amazon Bedrock, Model catalog
or Model access, and complete any first-use step shown. The default id is `amazon.nova-micro-v1:0`.

**Check it:** `make aws-check` runs a real call ("bedrock responds") and lists models you can use if the id is
wrong. Set `SIDELINE_BEDROCK_MODEL` to change it.

## If Bedrock says "Authentication failed"

A Bedrock **API key** (`AWS_BEARER_TOKEN_BEDROCK`) is tried before your access keys, and the short-term ones expire. With
both set, an expired API key breaks every Bedrock call even though the access keys are fine. Blank
`AWS_BEARER_TOKEN_BEDROCK` (your access keys also cover Polly and DynamoDB, which an API key never does).
Likewise `AWS_PROFILE` is a *name* from `~/.aws/config`, not an account number: leave it blank unless you use a profile.

## Step 4: permissions

If you use your own admin credentials, skip this. For a scoped IAM user, this is what the code calls, no more:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Sid": "Language",
     "Effect": "Allow",
     "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                "bedrock:InvokeModelWithBidirectionalStream"],
     "Resource": ["arn:aws:bedrock:*::foundation-model/amazon.nova-*",
                  "arn:aws:bedrock:*:<account-id>:inference-profile/*"]},
    {"Sid": "ListModels",
     "Effect": "Allow",
     "Action": ["bedrock:ListFoundationModels", "bedrock:ListInferenceProfiles"],
     "Resource": "*"},
    {"Sid": "Voice",
     "Effect": "Allow",
     "Action": "polly:SynthesizeSpeech",
     "Resource": "*"},
    {"Sid": "State",
     "Effect": "Allow",
     "Action": ["dynamodb:CreateTable", "dynamodb:DescribeTable", "dynamodb:UpdateTimeToLive",
                "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"],
     "Resource": "arn:aws:dynamodb:us-east-1:<account-id>:table/sideline"}
  ]
}
```

Replace `<account-id>`. Attach it as an inline policy (IAM, Users, your user, Add permissions, Create inline
policy, JSON). The two `List` actions are used only by `make aws-check` to enumerate models; Polly's action
supports no resource-level scoping; the DynamoDB list is exactly the operations in `sideline/state/dynamo.py` and
`scripts/create_table.py`. Keep it scoped: not `bedrock:*`, not `"Resource": "*"` for DynamoDB.

## Step 5: check Bedrock and the voice

```bash
make aws-check
```

It checks each layer in turn and names the one that failed: boto3, credentials, region, model access, a real
Bedrock answer, **Nova calling a Sideline tool**, **a catch-up written by Bedrock**, speech in, speech out, and
DynamoDB. It uses small synthetic inputs, so it needs no football key. Run it before the server, not after.

Polly needs no model-access step. The startup log then reads `voice: in=... out=polly (Amy)`; `out=browser` means it
fell back to the browser's voice (no credentials). `SIDELINE_POLLY_VOICE` changes the voice: `Amy` and `Brian` are
British, `Joanna` and `Matthew` American. A British voice reads European football names with less friction.

## Step 6: Nova Sonic, for speech in

```bash
pip3 install aws-sdk-bedrock-runtime awscrt       # Python 3.12 or newer
```

It is not in boto3: the bidirectional streaming API needs its own SDK. With it installed, and no Groq key, speech
in goes to Nova Sonic. It uses IAM credentials resolved through boto3. The comparison with Groq, and when each is
used, is in [SPEECH.md](SPEECH.md). **Check it:** `make aws-check` reports "speech in (sonic, live call)".

## Step 7: DynamoDB, so state survives a restart

Optional. Memory is fine for trying it out.

```bash
make create-table       # one table, pay-per-request, TTL on `expires_at`
make aws-check          # the last line: "dynamodb table ... ACTIVE"
make run                # SIDELINE_STATE=auto now uses it
```

Follow a match and ask a question; in the console (DynamoDB, Tables, sideline, Explore items) you should see
`LISTENER#` and `FIXTURE#` items. Restart the server and ask "what did I miss": it still knows where you were.
Pay-per-request means a trial costs cents; delete the table afterwards with
`aws dynamodb delete-table --table-name sideline`.

`SIDELINE_STATE=auto` (the default) uses DynamoDB when credentials are present and the table answers, and falls
back to memory with a warning otherwise. Set `dynamo` to insist (a failure is then loud), or `memory` to opt out.

## What it costs

Not measured. Set a billing alarm before turning anything on (console, Billing, Budgets). The main risk is a
runaway loop calling a paid service. Nothing here runs when the server is stopped, and the hackathon FAQ says you
do not need AWS running during judging, so tear things down when you are not testing.

## When it does not work

| Symptom | Cause | Fix |
|---|---|---|
| `Unable to locate credentials` | the key variables are not set in this terminal | step 2, then `make env` |
| `AccessDeniedException` on Bedrock | model access or IAM permission missing | steps 3 and 4 |
| `ValidationException: model not found` | wrong region or model id | `AWS_REGION=us-east-1`; `make aws-check` lists what you can use |
| `AccessDeniedException` on DynamoDB, Polly | the IAM user lacks the permission (often a Bedrock API key's user) | step 4 |
| `ResourceNotFoundException` on DynamoDB | the table does not exist | `make create-table` |
| `ThrottlingException` | an account quota or burst limit | with Bedrock on, the failure is reported to the listener; request a quota increase if it persists |
| a slow first answer, quick ones after | a cold connection | the server warms Polly and Bedrock at startup; the first question after a long idle is still slower |
| `CERTIFICATE_VERIFY_FAILED` on any HTTPS call | python.org Python on macOS has no CA bundle | handled in `sideline/tls.py`, which never disables verification; or run "Install Certificates.command" |
| `ImportError: boto3` | not installed | `pip3 install boto3` |
| `out=browser` in the startup log | no AWS credentials for Polly | step 2 |
| `in=browser` in the startup log | no Groq key and no Nova Sonic SDK | step 6, or [SPEECH.md](SPEECH.md) |
| `SubscriptionRequiredException` | the account is not subscribed to that service. **Not** an IAM problem | see below |

**Amazon Transcribe is not used.** On the account this was built on, Transcribe streaming returned
`SubscriptionRequiredException` ("The AWS Access Key Id needs a subscription for the service") even with full IAM
permissions, and nothing on the console offers an "activate" button; the reports of this error on AWS re:Post
point at an account-level state fixed through an Account and billing support case. Rather than wait on that,
speech in uses Nova Sonic and Groq. The friction is recorded in [FRICTION_LOG.md](FRICTION_LOG.md) (FL-08).
