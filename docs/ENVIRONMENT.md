# Environment variables

Every variable the code reads, and nothing else. This page, `.env.example`,
`config.VARIABLES` (what `make env` prints) and the code itself name exactly the
same set; `tests/test_environment.py` fails if they ever differ.

**Precedence, highest first:** a real environment variable (a shell `export`), then
the `.env` file in the repo root (`cp .env.example .env`; git-ignored, blank values
skipped), then the default below.

`make env` shows what is set and what each `auto` resolves to. It never prints a
secret.

## What you need

| To get | You need |
|---|---|
| The server to start | `SIDELINE_FOOTBALL_KEY` (a free API-Football key) |
| Spoken, written catch-ups, and the voice agent in the simulator | AWS credentials with Bedrock access (the three `AWS_*` rows are alternatives) |
| Nova's voice (Polly) | AWS credentials with Polly access. A Bedrock API key alone is not enough |
| Durable listener state | AWS credentials with DynamoDB access, and the table (`make create-table`) |
| The most accurate speech in | `GROQ_API_KEY` (audio then leaves AWS: see [SPEECH.md](SPEECH.md)) |

With no football key the server refuses to start and says why: Sideline has no recorded
or demo data. With no AWS credentials it still starts, but the agent in the simulator
has nothing to answer with and listener state is kept in memory.

## The variables

| Variable | Default | What it does |
|---|---|---|
| `SIDELINE_FOOTBALL_KEY` | *(none)* | API-Football key. Required: there is no recorded or demo data. **Secret.** |
| `SIDELINE_POLL_SECONDS` | `60` | Seconds between polls of a followed match (free plan: 100 requests a day). |
| `SIDELINE_HOST` | `127.0.0.1` | Interface to bind. |
| `SIDELINE_PORT` | `8765` | Port. |
| `SIDELINE_LOG` | `INFO` | Log level. |
| `SIDELINE_ALLOWED_ORIGINS` | `localhost,127.0.0.1` | Browser origins allowed (DNS-rebinding guard). |
| `AWS_REGION` | `us-east-1` | Region for Bedrock, DynamoDB and Polly. |
| `AWS_ACCESS_KEY_ID` | *(none)* | AWS credentials (with the secret below). **Secret.** |
| `AWS_SECRET_ACCESS_KEY` | *(none)* | AWS credentials (with the key id above). **Secret.** |
| `AWS_PROFILE` | *(none)* | A named AWS profile, instead of keys. |
| `AWS_BEARER_TOKEN_BEDROCK` | *(none)* | A Bedrock API key (Bedrock only, not Polly or DynamoDB). **Secret.** |
| `SIDELINE_BEDROCK` | `auto` | auto (on when AWS credentials are present), on, or off. |
| `SIDELINE_BEDROCK_MODEL` | `amazon.nova-micro-v1:0` | Bedrock model or inference-profile id. |
| `SIDELINE_STATE` | `auto` | auto (DynamoDB if it answers, else memory), memory, or dynamo. |
| `SIDELINE_TABLE` | `sideline` | DynamoDB table name. |
| `SIDELINE_POLLY_VOICE` | `Amy` | Polly voice (speech out). |
| `SIDELINE_STT` | `auto` | Speech in: auto, groq, sonic, or off. |
| `GROQ_API_KEY` | *(none)* | Turns on Groq Whisper for speech in. Audio then leaves AWS. **Secret.** |
| `SIDELINE_LIVE_CAPTION` | `browser` | browser types interim words while you speak (audio also reaches the browser vendor); off does not. |

## Notes

- **`SIDELINE_POLL_SECONDS`.** One followed match costs about one request per poll
  (the fixture response carries its events and line-ups). A free plan allows 100 requests
  a day, so 60 s gives you roughly an hour and a half of one match. Use a paid plan for more.
- **AWS credentials.** Any one of: the key pair, a profile, or (Bedrock only) a Bedrock API
  key. Temporary credentials also need `AWS_SESSION_TOKEN`, which boto3 reads itself. An
  instance role is not detected automatically: set `SIDELINE_BEDROCK=on` and
  `SIDELINE_STATE=dynamo` yourself.
- **`SIDELINE_BEDROCK`.** When Bedrock is on, a failure is reported to the listener and never
  replaced with canned wording. When it is off, the deterministic templates are used and the
  response says `generated_by: template`.
- **`SIDELINE_LIVE_CAPTION`.** The page can type your words while you speak, using the browser's
  own recognition on the side, because server recognition only returns text once the clip ends.
  That audio also reaches the browser vendor. `off` avoids it.
- **TLS on macOS.** python.org's Python ships without a CA bundle until you run "Install
  Certificates.command"; `sideline/tls.py` finds a real bundle and always verifies. It never
  disables verification.
