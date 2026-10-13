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
| The server to start | `SPORTMONKS_TOKEN` (a free Sportmonks token) |
| Spoken, written catch-ups, and the voice agent in the simulator | AWS credentials with Bedrock access (the access key pair) |
| Nova's voice (Polly) | AWS credentials with Polly access. A Bedrock API key alone is not enough |
| Durable listener state | AWS credentials with DynamoDB access, and the table (`make create-table`) |
| Speech in (the listener's voice) | the same AWS credentials: Voxtral and Nova Sonic run on Bedrock, so audio never leaves the account (see [SPEECH.md](SPEECH.md)) |

With no football key the server refuses to start and says why: Sideline has no recorded
or demo data. With no AWS credentials it still starts, but the agent in the simulator
has nothing to answer with and listener state is kept in memory.

## The variables

| Variable | Default | What it does |
|---|---|---|
| `SPORTMONKS_TOKEN` | *(none)* | Sportmonks token (free plan: a few leagues, 180 calls an hour). Required: there is no recorded or demo data. **Secret.** |
| `SIDELINE_POLL_SECONDS` | `30` | Seconds between polls of a followed match while it is in play (free plan: 180 calls an hour). A match not yet started is checked every 5 minutes, a finished one once. |
| `SIDELINE_HOST` | `127.0.0.1` | Interface to bind. |
| `SIDELINE_PORT` | `8765` | Port. |
| `SIDELINE_LOG` | `INFO` | Log level. |
| `SIDELINE_LOG_DIR` | `logs` | Folder for daily log files (a text log and a JSON line per call); off disables. Git-ignored. |
| `SIDELINE_LOG_KEEP_DAYS` | `14` | Days of log files to keep; older ones are deleted. |
| `SIDELINE_ALLOWED_ORIGINS` | `localhost,127.0.0.1` | Browser origins allowed (DNS-rebinding guard). |
| `AWS_REGION` | `us-east-1` | Region for Bedrock, DynamoDB and Polly. |
| `AWS_ACCESS_KEY_ID` | *(none)* | AWS credentials (with the secret below). **Secret.** |
| `AWS_SECRET_ACCESS_KEY` | *(none)* | AWS credentials (with the key id above). **Secret.** |
| `SIDELINE_BEDROCK` | `auto` | auto (on when AWS credentials are present), on, or off. |
| `SIDELINE_BEDROCK_MODEL` | `amazon.nova-micro-v1:0` | Bedrock model or inference-profile id. |
| `SIDELINE_STATE` | `auto` | auto (DynamoDB if it answers, else memory), memory, or dynamo. |
| `SIDELINE_TABLE` | `sideline` | DynamoDB table name. |
| `SIDELINE_POLLY_VOICE` | `Amy` | Polly voice (speech out). |
| `SIDELINE_POLLY_ENGINE` | `generative` | Polly engine: generative (most natural, falls back to neural) or neural. |
| `SIDELINE_STT` | `auto` | Speech in: auto (Voxtral, then Nova Sonic, both on Bedrock), voxtral, sonic, or off. |
| `SIDELINE_WEATHER` | `on` | on adds the weather at the ground to a match preview (city and country go to Open-Meteo); off does not. |
| `SIDELINE_AGENT_TOOLS` | `all` | Tools offered to the voice agent: all, or core (the core eleven, which route more reliably on a small model). |
| `SIDELINE_LIVE_CAPTION` | `browser` | browser types interim words while you speak (audio also reaches the browser vendor); off does not. |

## Notes

- **`SIDELINE_POLLY_ENGINE`.** Polly's generative voices sound the most natural (they vary pace and stress where the
  neural ones read every sentence alike) and are the default. They cannot return word timings, so the highlight's timings come
  from the neural voice for the same sentence, fitted to the generative audio's exact length; sentences are made in parallel
  so a long answer is ready after its slowest sentence. A voice or region without the generative engine falls back to
  neural, per sentence, with its own exact timings. `neural` skips all of that.
- **`SIDELINE_LOG_DIR`.** Every run writes `logs/sideline-<date>.log` (everything the server logs) and
  `logs/calls-<date>.jsonl` (one JSON line per tool call, agent turn and speech clip: the tool, its arguments, how long
  it took, what was declined and why; what a listener asked, what was answered, which speech provider heard a clip and
  what it heard). A new file starts each day and files older than `SIDELINE_LOG_KEEP_DAYS` are deleted. No audio is
  ever recorded, and any secret from the environment is replaced with `***` wherever it would appear. The folder is
  local and git-ignored; `off` turns it all off. `make log-report` summarises it.
- **`SIDELINE_POLL_SECONDS`.** One followed match costs about one request per poll
  (the fixture response carries its events and line-ups). The free plan allows 180 calls an
  hour per kind of data, and every question that looks up a match shares that same bucket. The
  interval applies only while a match is in play: 30 s (the default) uses two thirds of the hour and leaves 60 for
  questions, 60 s a third. A match that has not started is checked every 5 minutes until ten minutes before kick-off,
  and a finished one is read once, so setting up, past matches and static data cost almost nothing. The server warns at
  startup when the interval takes more than half. Following two live matches doubles the cost.
- **AWS credentials.** Any one of: the key pair, a profile, or (Bedrock only) a Bedrock API
  key. Temporary credentials also need `AWS_SESSION_TOKEN`, which boto3 reads itself. An
  instance role is not detected automatically: set `SIDELINE_BEDROCK=on` and
  `SIDELINE_STATE=dynamo` yourself.
- **`SIDELINE_BEDROCK`.** When Bedrock is on, a failure is reported to the listener and never
  replaced with canned wording. When it is off, the deterministic templates are used and the
  response says `generated_by: template`.
- **`SIDELINE_AGENT_TOOLS`.** The server lists every tool its feed can answer; the voice agent (Nova Micro) is offered
  all of them by default. A small model routes worse the more tools it sees, so `core` limits it to the core eleven
  that the product is built around. If a spoken question lands on the wrong tool, try `core` first.
- **`SIDELINE_WEATHER`.** A match preview can say what the weather will be at the ground. The football feed has no
  weather, so the city and country are sent to [Open-Meteo](https://open-meteo.com/) (free, no key, CC BY 4.0). If the
  city cannot be placed with confidence, or the service is down, the preview leaves the weather out. It never guesses.
- **`SIDELINE_LIVE_CAPTION`.** The page can type your words while you speak, using the browser's
  own recognition on the side, because server recognition only returns text once the clip ends.
  That audio also reaches the browser vendor. `off` avoids it.
- **TLS on macOS.** python.org's Python ships without a CA bundle until you run "Install
  Certificates.command"; `sideline/tls.py` finds a real bundle and always verifies. It never
  disables verification.
