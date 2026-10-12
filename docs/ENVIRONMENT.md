# Environment variables

**Environment variables take priority over everything.** Precedence, highest
first:

1. a real environment variable (a shell `export`, a container's env, an App
   Runner setting)
2. an optional `.env` file in the repo root (`cp .env.example .env`), which
   only fills in what you have not exported. It is git-ignored.
3. the built-in default

Every setting in `.env.example` is live, none is commented out, and a
blank value is skipped, so leaving a line empty is safe.

**Integrations switch on by themselves.** Their defaults are `auto`:

| Setting | `auto` means |
|---|---|
| `SIDELINE_BEDROCK` | on when AWS credentials are present |
| `SIDELINE_STATE` | DynamoDB when AWS credentials are present *and* the table answers (`make create-table`), otherwise memory with a warning |
| `SIDELINE_PROVIDER` | live API-Football when a football key or secret is present, otherwise the recorded real match |

An explicit value always wins: `SIDELINE_BEDROCK=off` turns Bedrock off
even with keys exported. With nothing set at all, `python3 -m sideline`
serves a real recorded match with no AWS and no key.

```bash
make env          # what is set, and what each "auto" resolves to; never prints a value
```

## Setting them

**macOS / Linux (bash or zsh)**, for the current terminal only (or put the same values in `.env`):

```bash
export SIDELINE_BEDROCK=on
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=AKIA...                 # not a secret on its own
read -s -p "AWS secret key: " AWS_SECRET_ACCESS_KEY; echo; export AWS_SECRET_ACCESS_KEY
```

`read -s` keeps the secret out of your terminal history. Close the
terminal and it is gone. To keep variables between terminals without a
file in this repo, put the `export` lines in your own shell profile
(`~/.zshrc`), or use your password manager's CLI.

**Windows PowerShell:**

```powershell
$env:SIDELINE_BEDROCK = "on"
$env:AWS_ACCESS_KEY_ID = "AKIA..."
$env:AWS_SECRET_ACCESS_KEY = (Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText)
```

**Docker:** `docker run -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY ...`
(with no value, `-e NAME` passes the variable from your shell without
writing it anywhere).

**On AWS (App Runner):** no keys at all. The service's instance role
supplies AWS credentials, and the football key is injected from Secrets
Manager as the `SIDELINE_FOOTBALL_KEY` variable
([deploy/sideline.yaml](../deploy/sideline.yaml)).

## The variables

Secrets are marked **secret**.

### AWS credentials

boto3 reads these from the environment automatically. You do not need the
`aws` command-line tool for Sideline to work; `make aws-check` uses boto3
only.

| Variable | |
|---|---|
| `AWS_ACCESS_KEY_ID` | **secret.** From an IAM user's access key. |
| `AWS_SECRET_ACCESS_KEY` | **secret.** Shown once when the key is created. |
| `AWS_SESSION_TOKEN` | **secret.** Only for temporary credentials. |
| `AWS_REGION` | Default `us-east-1`. |

### AWS features

| Variable | Default | |
|---|---|---|
| `SIDELINE_BEDROCK` | `auto` | `auto` = on when AWS credentials are present; `on` / `off` force it. |
| `SIDELINE_BEDROCK_MODEL` | `amazon.nova-micro-v1:0` | Any model or inference-profile id your account can call; `make aws-check` checks it. |
| `SIDELINE_BEDROCK_TIMEOUT` | `3.0` | Seconds. Alexa+ targets 0.5 s round trip; see [BEDROCK.md](BEDROCK.md). |
| `SIDELINE_WORD_TARGET` | `45` | Spoken-word budget for a catch-up. |
| `SIDELINE_CATCHUP_MODE` | `cached` | `cached` = the model writes summaries in the background and asking is a lookup; `live` = the model is called when the listener asks. |
| `SIDELINE_STATE` | `auto` | `auto` = DynamoDB if credentials and table, else memory; `memory` / `dynamo` force it. |
| `SIDELINE_TABLE` | `sideline` | DynamoDB table name. |
| `SIDELINE_DYNAMO_ENDPOINT` | real AWS | e.g. `http://localhost:8000` for DynamoDB Local. |
| `SIDELINE_EMF` | `off` | `on` writes CloudWatch metric lines to stdout. |

### Live football data

| Variable | Default | |
|---|---|---|
| `SIDELINE_PROVIDER` | `auto` | `auto` = live when a key is present; `replay` / `apifootball` force it. `apifootball` with no key falls back to the replay. |
| `SIDELINE_FOOTBALL_KEY` | none | **secret.** API-Football key. `make verify-data` checks it. |
| `SIDELINE_FOOTBALL_SECRET` | none | Secrets Manager name or ARN; fetched at startup if the key variable is unset. |
| `SIDELINE_FOOTBALL_BASE` | API-Football v3 | Override only for a proxy. |
| `SIDELINE_POLL_SECONDS` | `15` | Raise to 60 on a free plan. |
| `SIDELINE_REPLAY` | bundled real match | Path to a replay file. Leave unset. |
| `SIDELINE_REPLAY_SPEED` / `_START` | `1.0` / `0` | Replay speed and start minute. |

### Authentication (account linking)

Off by default. See [ALEXA_SETUP.md](ALEXA_SETUP.md).

| Variable | |
|---|---|
| `SIDELINE_AUTH` | `off` or `required`. |
| `SIDELINE_AUTH_ISSUER` | Authorization server issuer URL. |
| `SIDELINE_PUBLIC_URL` | Canonical `https://.../mcp`, as in the add-on manifest. |
| `SIDELINE_AUTH_JWKS_URL` | RS256 signing keys (needs `pip install cryptography`). |
| `SIDELINE_AUTH_HS256_SECRET` | **secret.** Shared-secret alternative, for tests. |
| `SIDELINE_AUTH_SCOPES` | Space separated, published as `scopes_supported`. |
| `SIDELINE_AUTH_AUDIENCE` | Optional: enforce this `aud`. |

### Server and simulator voice

| Variable | Default | |
|---|---|---|
| `SIDELINE_HOST` / `SIDELINE_PORT` | `127.0.0.1` / `8765` | `0.0.0.0` in a container (the Dockerfile sets it). |
| `SIDELINE_LOG` | `INFO` | |
| `SIDELINE_ALLOWED_ORIGINS` | `localhost,127.0.0.1` | Browser origins only; Alexa+ sends none. |
| `SIDELINE_POLLY_VOICE` / `_ENGINE` | `Amy` / `neural` | |
| `SIDELINE_STT` | `auto` | `auto`, `transcribe`, `groq`, `off`. |
| `SIDELINE_TRANSCRIBE_LANG` | `en-GB` | |
| `GROQ_API_KEY` | none | **secret.** Alternative speech-to-text. |

## Safe habits

- Use an IAM **user** with the narrow policy in
  [AWS_SETUP.md](AWS_SETUP.md), never root keys.
- Never paste a secret into a chat, an issue or a commit. `make env` is
  safe to paste because it prints no values.
- Rotate the key if you ever do: IAM → user → Security credentials.
