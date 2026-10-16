# Sideline

**A friend for the match, in your ear. Built first for people who cannot see the screen.**

A self-hosted [MCP](https://modelcontextprotocol.io) server that answers a listener's questions about live and recent
sport, built for the Alexa+ track of the *Build, Ship, Shape: Amazon Developer Hackathon*. It reads ESPN's public data
(football, basketball, American football, baseball and hockey), remembers what each listener has already heard, holds
back anything their delayed stream has not shown yet, and speaks through Amazon Bedrock and Polly.

> **The web page in this repository is a simulated Alexa+.** Alexa+ is the voice assistant that would talk to this
> server, and its add-on tooling is partner-only, so participants cannot connect the real one. The simulator plays that
> part honestly: it listens, chooses tools, calls them over MCP exactly as an external client would, and speaks the answer.
> It is a stand-in for Alexa+, not Alexa+, and it is how you run and judge everything below.

---

## At a glance

| | |
|---|---|
| **What it is** | A standard MCP server (spec 2025-11-25, Streamable HTTP): 30 tools, five sports, about 220 football competitions, live ESPN data with no key |
| **What no client can do alone** | Remember what *this* listener has heard (one marker, `last_told_at`) and hold back anything their delayed stream has not shown yet |
| **How it answers** | In a sentence or two, leading with the fact; says what its feed does not have; never answers a fact from a model's memory |
| **Speed** | A question after the first takes 0 to 3 s; the first takes about 6 s with the model (measured from Mauritius against a table in us-east-1; the follow tool alone is 4.5 s) |
| **Memory you control** | The conversation lives in the session only; "forget that" ends it; "forget everything about me" erases what the server keeps |
| **Built on** | Amazon Bedrock (Nova Pro as the host, Voxtral and Nova Sonic for speech in), Polly, DynamoDB |
| **Evidence** | 61 offline test suites; 70 live questions on real matches; routing **77 of 79** on a 79-phrasing check; the official MCP Python SDK client run against it |
| **Honesty** | 28-entry [friction log](docs/FRICTION_LOG.md), 9 [feature requests](docs/FEATURE_REQUESTS.md), and a [known-limitations list](#known-limitations) that includes what is not done |

---

## The problem

A football broadcast is a visual medium with an audio track attached. Strip away the picture and a surprising amount of
the match goes with it. The line-ups are a graphic shown once and never read aloud. The score and the clock sit in a
corner of the screen. Substitutions appear on a board. The booking, the referee's name, the VAR decision: all on screen,
rarely spoken. A blind fan watching with a sighted friend simply turns and asks. Watching alone, there is nobody to ask.

**Sideline is that friend.** It works from match data, not video, and is meant to be heard privately, through an earbud.
The [WHO](https://www.who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment) estimates that at least 2.2 billion people live with a near or distance vision impairment; blind and low-vision fans
are who we designed for first. The same features suit anyone with their eyes busy, in a noisy room, or tired of spoilers.

## What it sounds like

These are real answers from the live ESPN feed on 2026-10-15, about a match played the night before. They are the words
the tools return; with a model in front, they are spoken by it.

> **"What happened in the PSG game last night?"**
> Manchester City against Paris Saint-Germain, yesterday: Full time. Paris Saint-Germain 4, Manchester City 2. Désiré Doué
> scored on 13, set up by Fabián Ruiz. Ousmane Dembélé scored on 15, set up by Désiré Doué. Vitinha scored on 32 … Erling
> Haaland scored on 75, set up by Ayyoub Bouaddi. Paris Saint-Germain were awarded a penalty on 87, after Nuno Mendes was
> fouled by Matheus Nunes. Ferran Torres's penalty was saved by Gianluigi Donnarumma on 90.

> **"Tell me about the goalkeeper who saved the penalty."**
> Gianluigi Donnarumma, Manchester City goalkeeper, number 1, started. In this match: 6 saves and 4 conceded. Ferran
> Torres's penalty was saved by Gianluigi Donnarumma on 90.

> **"Tell me more about Nuno Mendes."**
> Nuno Mendes is a 24-year-old Portuguese defender at Paris Saint-Germain, shirt number 25. I can't give his major titles:
> my feed doesn't carry honours. Want his numbers this season, or how he did in the latest match?

> **"Who stood out?"**
> The standouts in Manchester City against Paris Saint-Germain, by goals, assists and shots: Erling Haaland, Manchester
> City: 2 goals and 8 shots with 3 on target. … The feed gives no player ratings, so that is what they did, not a verdict.

It says what it does not have (a referee the feed does not name, expected goals, a player's honours) instead of leaving it
out or guessing, and when something goes wrong it says an error occurred and to rephrase or try again later, never "no
matches".

## What makes it a server and not a lookup

**Reach.** A match is happening right now. A language model alone cannot know the score, the line-up or how many cards the
referee has shown.

**State.** The server keeps an event log of the match and, the part that matters, one marker per listener:

```
last_told_at: 12'
```

That is when we last told *this* listener anything about *this* match. When they come back after half an hour and say "what
did I miss", the request carries no time range, because Alexa+ has no idea when they last heard anything:

```json
{ "name": "what_did_i_miss", "arguments": {} }
```

No `since`. The listener gets to be terse because the server holds the state ([`sideline/state/store.py`](sideline/state/store.py)).

**The spoiler guard.** Streams run behind real time. The listener tells us what they just *heard* ("that's half time", "I
just heard a goal") and the server holds back every event their picture has not reached, by the clock: an event is spoken
once the delay after we first saw it has passed. Every tool that reads events goes through the same filter, so the match
report, the player and the officials never say what the score hides (`tests/test_critical_fixes.py`).

## How it works

```
   Alexa+  (the real client: partner-only)        the simulated Alexa+ (what runs today)
        \                                          a web page + a Bedrock model as MCP host
         \                                         /
          MCP over Streamable HTTP, spec 2025-11-25
                          |
                   Sideline MCP server          30 tools · event log · last_told_at · sport profiles
              /          |            \                   \
        Bedrock      DynamoDB      poller         ESPN public API
   (a model: the       (listener   (a thread,     (unofficial; cached,
    host, and the       state)      followed       see docs/ESPN_NOTES.md)
    wording)                        matches only)
   Polly (voice)   Voxtral / Nova Sonic (speech in)
```

| AWS service | What it does here |
|---|---|
| **Bedrock** (a model of your choice, `SIDELINE_BEDROCK_MODEL`) | in the simulator, chooses tools from the full MCP catalog and words the answer; writes the spoken catch-up. Measured comparison of four models: [docs/BEDROCK.md](docs/BEDROCK.md) |
| **Bedrock, Mistral Voxtral** and **Nova 2 Sonic** | speech in: hears the listener, inside the AWS account |
| **Polly** (generative voice, neural fallback) | speech out, with word timings so the screen highlights each word as it is spoken |
| **DynamoDB** | listener state and the event log, so what a listener has heard survives a restart |

More on the design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/BEDROCK.md](docs/BEDROCK.md), [docs/MCP.md](docs/MCP.md).

## What is the MCP, and what is around it

The MCP is the [`sideline/`](sideline/) folder, and only that folder: standard-library Python, no install step. Everything
else in the repository supports it and can be left behind: [`simulator/`](simulator/) is a web page that plays the part of
Alexa+ so the server can be tried by voice, `scripts/` holds developer benchmarks and checks, `tests/` the offline suite,
and `docs/` the write-ups. A test (`tests/test_standalone.py`) copies `sideline/` alone to an empty directory and checks
that it starts and serves its 30 tools there.

## Run it

| To get | You need |
|---|---|
| **The server and the live data** | Nothing: no key, no account. ESPN's public endpoints need none |
| **Answers in a model's voice, and the voice agent** | AWS credentials with Bedrock access |
| **The voice** | Polly access too. A Bedrock API key alone is not enough |
| **Durable state** | DynamoDB access and a table (`make create-table`); without it the state is kept in memory |

Python 3.8 or newer. The first launch creates an isolated `.venv` and installs `requirements.txt`; nothing is installed
system-wide.

```bash
git clone https://github.com/NelsonFodjo/sideline && cd sideline
cp .env.example .env        # then fill in your AWS credentials (the data needs none)
make env                    # what is set; never prints a secret
make run                    # starts the server on http://127.0.0.1:8765/  (or: make sim)
make test                   # the offline suite: no network, no credentials
```

Open the page, allow the microphone once, and talk. The page plays Alexa+: a conversation you can scroll back through (the
**Conversation** button, or H), a match card, and a light bar along the bottom that shows whether it is listening, thinking
or speaking.

**A followed match stays on screen.** Follow a match and its card (score, minute, a "following, live" label) stays until you
follow another match, which replaces it, or say "stop following" (or press the × on the card). While the match is in play the
card refreshes every 30 seconds, the same beat the server polls it on, and after every answer; it stops refreshing at full
time and says so. The refresh is held to your stream delay, so it never shows a goal ahead of your picture. The server
remembers what you follow, so a page refresh brings the card back.

**Watching what happens behind it.** The **Dev log** (Alt+D) shows, for every question: what was heard and what was acted on;
how the turn was handled (how many of the 30 tools the model was offered, how many earlier turns it remembered, whether a first
answer with no tool was sent back); each model call with its time and tokens; and, for every MCP tool call, the arguments it was
given, the words it returned, the feed requests it made and how many were answered from what was kept, the time inside the
server, what it changed about the listener (the match followed, the marker, the delay), the full structured result, and a
"copy as MCP call" button; then a timeline of speech in, agent and speech out. It is kept in local storage and cleared when you
refresh. The server's console prints the same, one readable block per tool call and per agent turn (`SIDELINE_LOG=DEBUG` adds
the full result), and `logs/` keeps them as JSON lines.

Without AWS the server still starts and every tool answers in templated wording through any MCP client; the simulator's
agent needs Bedrock. How to connect another client, and how to host it, is in the next section.

## Connect it to anything, and host it later

Sideline is a standard MCP server (spec 2025-11-25, Streamable HTTP, one endpoint: `/mcp`). Nothing in it is specific to
the simulator, so any MCP client can use it. This is the whole path from this repository to a client on another machine.
What has been run is marked **tested**; the rest is the standard procedure, written out, and **not yet run by us** on a real
server.

### Step 1. Check it on your machine (tested)

```bash
make run                                                        # leave it running; endpoint http://127.0.0.1:8765/mcp
curl -s localhost:8765/health                                   # {"ok": true, "tools": 30, ...}

H='-H Content-Type:application/json -H Accept:application/json,text/event-stream'
SID=$(curl -si localhost:8765/mcp $H -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' \
      | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}' | tr -d '\r')
curl -s localhost:8765/mcp $H -H "Mcp-Session-Id: $SID" -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
curl -s localhost:8765/mcp $H -H "Mcp-Session-Id: $SID" -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'     # the 30 tools
```

A client must `initialize`, then send back the `Mcp-Session-Id` it was given on every later request. The official MCP Python
SDK has also been run against it (tested): `pip install mcp` in a throwaway virtualenv, then
`python3 scripts/check_with_sdk.py`.

### Step 2. Put it on a server

Any machine with Python 3.8+ and a public address works. The example is a small Linux VM (for instance an EC2 instance
with Ubuntu) and a domain name you control, `sideline.example.com` below.

1. **Open the ports.** Allow inbound 80 and 443 (the security group or firewall). Do **not** open 8765: only the web server
   in front of it should reach it.
2. **Install and fetch.**
   ```bash
   sudo apt-get update && sudo apt-get install -y python3 python3-pip git
   sudo git clone https://github.com/NelsonFodjo/sideline /opt/sideline && cd /opt/sideline
   pip3 install boto3            # optional: Bedrock wording and DynamoDB state. Without it the server still works
   ```
3. **Configure it.** Make a token and put the settings in `/opt/sideline/.env`:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"      # copy the output
   cp .env.example .env && nano .env
   ```
   ```
   SIDELINE_HOST=127.0.0.1                     # stays on this machine; the web server in front of it is what the world reaches
   SIDELINE_AUTH_TOKEN=<the token you made>
   SIDELINE_STATE=dynamo                       # optional, see "State" below; omit to keep state in memory
   ```
   The server refuses a token shorter than 16 characters, and warns at start-up if it is reachable from outside with no token.
4. **Run it as a service** so it restarts. Create `/etc/systemd/system/sideline.service`:
   ```ini
   [Unit]
   Description=Sideline MCP server
   After=network-online.target

   [Service]
   WorkingDirectory=/opt/sideline
   ExecStart=/usr/bin/python3 -m sideline
   Restart=on-failure
   User=ubuntu

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   sudo systemctl daemon-reload && sudo systemctl enable --now sideline
   curl -s localhost:8765/health                # {"ok": true ...}
   ```
5. **Add HTTPS.** The server speaks plain HTTP, so put a web server in front. Caddy fetches and renews the certificate itself.
   Point a DNS `A` record for `sideline.example.com` at the machine, install Caddy, and set `/etc/caddy/Caddyfile`:
   ```
   sideline.example.com {
       reverse_proxy 127.0.0.1:8765 {
           flush_interval -1          # send the event stream (GET /mcp) as it is written, not in batches
       }
   }
   ```
   then `sudo systemctl reload caddy`. (nginx or an AWS load balancer do the same job: the one thing to get right is not
   buffering responses.)
6. **Check it from your laptop**, not from the server:
   ```bash
   curl -s https://sideline.example.com/health                                           # 200, open on purpose
   curl -s -o /dev/null -w "%{http_code}\n" -X POST https://sideline.example.com/mcp      # 401: the token is required
   ```
   and repeat the Step 1 handshake against `https://sideline.example.com/mcp` with `-H "Authorization: Bearer <token>"` added.

**State (optional, recommended for a real deployment).** With `SIDELINE_STATE=dynamo` what each listener has heard survives
a restart. Run `make create-table` once with AWS credentials that may create a table. At run time the machine needs only
`dynamodb:GetItem`, `dynamodb:PutItem` and `dynamodb:Query` on that table; give an EC2 instance an IAM role with those,
not access keys in a file. For model-written wording it also needs `bedrock:InvokeModel`.

### Step 3. Point a client at it

Every client needs the same two things: the URL `https://sideline.example.com/mcp` and the header
`Authorization: Bearer <token>`.

| Client | How |
|---|---|
| **Claude Code** (not yet run by us) | `claude mcp add --transport http sideline https://sideline.example.com/mcp --header "Authorization: Bearer <token>"` |
| **MCP Inspector** (not yet run by us) | `npx @modelcontextprotocol/inspector`; choose transport *Streamable HTTP*, enter the URL, add the `Authorization` header, connect, then *List tools* |
| **A client that takes a JSON config** | `{ "mcpServers": { "sideline": { "url": "https://sideline.example.com/mcp", "headers": { "Authorization": "Bearer <token>" } } } }` (the field names vary by client; the URL and header do not) |
| **Your own code** | Use any MCP SDK's Streamable HTTP client with that URL and header. The official Python SDK against the local server is **tested** (`scripts/check_with_sdk.py`) |
| **A client that cannot send a header** | Put an API gateway in front that adds it; or, only on a network you control, leave `SIDELINE_AUTH_TOKEN` unset |

Alexa+ itself is a separate step. It needs a public HTTPS endpoint with account linking and OAuth 2.1, which are **not built**,
and the add-on tooling is partner-only (see [docs/MCP.md](docs/MCP.md)). The bearer token is a stopgap that keeps a
deployment from being open; it is not a replacement.

### Step 4. Look after it

| | |
|---|---|
| Logs | `journalctl -u sideline -f`, and daily files in `/opt/sideline/logs` |
| Update | `cd /opt/sideline && git pull && sudo systemctl restart sideline` |
| Health check for a load balancer | `GET /health` (open, cheap) |
| Run one copy | Sessions and the live-match poller live in the process: one instance, or sticky sessions, until they are moved out |
| One listener | State is kept per listener, taken from the `X-Sideline-Listener` header, else one shared id. Today that is **one listener per deployment**; do not give one server to several real people |
| The simulator | Not for a hosted server: the page does not send the token. Use it against a local server with no token |

### If it does not work

| You see | Because |
|---|---|
| `401` on `/mcp` | The token is missing or wrong: send `Authorization: Bearer <token>` exactly |
| `400 Mcp-Session-Id is required` | The client skipped `initialize`, or did not send back the session id |
| `403 origin not allowed` | A browser client on another origin: add it to `SIDELINE_ALLOWED_ORIGINS` (full origin, e.g. `https://app.example.com`) |
| The client connects but hangs or never gets events | Something in front is buffering: turn buffering off for `/mcp` (`flush_interval -1` in Caddy, `proxy_buffering off` in nginx) |
| `/agent/chat` or `/voice/*` answer `404` | Normal: those belong to the simulator, which a hosted server does not need |
| The server will not start, naming `SIDELINE_AUTH_TOKEN` | It is shorter than 16 characters |

Try it without a model, against the live feed:

```bash
python3 scripts/ask.py                                  # ask any tool a question, with the ESPN requests and time shown
python3 scripts/convo.py tests/conversations/batch-03-broad.json    # 50 questions, live, as one conversation
make bench                                              # what each tool costs, and the size of the tool list
python3 scripts/route_check.py                          # does a real Bedrock model pick the right tool? (costs Bedrock calls)
```

Settings are environment variables, documented in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md); a test keeps that page,
`.env.example` and the code in step.

## The tools

Thirty, each one intent, each naming its neighbour in its description so a model does not have to guess. A tool is offered
only if the feed behind the server can answer it.

| Group | Tools |
|---|---|
| **A match you follow** | `follow_match`, `get_match_state`, `what_did_i_miss`, `get_event_detail`, `sync_broadcast_delay` |
| **A match, followed or not** | `get_match_report`, `get_match_stats`, `get_match_preview`, `get_lineups`, `get_officials`, `get_injuries`, `get_head_to_head`, `get_standouts` |
| **People** | `get_player_profile`, `get_player_stats`, `get_player_context` |
| **Teams and competitions** | `get_schedule`, `get_squad`, `get_team_stats`, `get_team_form`, `get_standings`, `get_top_scorers`, `get_fixtures`, `get_competitions`, `search` |
| **News** | `get_news` |
| **You** | `set_favourites`, `get_my_matches`, `set_preferences`, `get_capabilities` |

Contracts, and the reasoning behind each description: [docs/TOOLS.md](docs/TOOLS.md). The tool list is about 8,000 tokens,
paid on every model turn (`make bench`).

## Where this goes

Sideline is a working answer to a narrow problem, and the parts that make it work are not narrow.

**For the listener, well beyond the screen.** Blind and low-vision fans are who it was designed for first, and the same
help is wanted by anyone whose eyes are busy (driving, cooking, a second screen), anyone in a noisy bar or a quiet house at
night, and anyone watching a delayed or recorded stream who cannot bear a group chat that has already shown the goal. The spoiler
guard, which holds back events by the clock until the listener's picture reaches them, is as useful to them as to anyone.

**For broadcasters and rights holders.** An audio layer built from match data, not from video, costs almost nothing
per match and covers every match the data covers: about 220 football competitions and four more sports today, from a public
feed. The data source sits behind one interface ([docs/DATA_PROVIDERS.md](docs/DATA_PROVIDERS.md)), so a licensed official feed
is a new provider, not a new product, and a new sport is a new profile ([docs/SPORTS.md](docs/SPORTS.md)), not a rewrite.

**For Alexa+ add-on authors.** Most first add-ons answer one question at a time. Sideline shows the shape of one that does
not: the server holds a marker per listener, so the request can be as short as "what did I miss"; tools say what they do not
know instead of guessing; a failure is a sentence a person can act on; and tool descriptions are treated as the product's
interface, with a measured check on whether a model picks the right one. The 9 [feature requests](docs/FEATURE_REQUESTS.md)
and 28 [friction entries](docs/FRICTION_LOG.md) are what we would want Amazon's teams to know from building it.

**For the pattern.** "What has changed since I last asked" is the question behind a delivery, a flight, a market, a
match. A per-listener marker plus a held-back view of events is a reusable answer to it, and sport, where the listener
cannot see the screen, is where it matters most.

**What stands between this and a product, said plainly:** certified Alexa+ account linking with OAuth (partner-only today),
a licensed data source in place of the public feed, one server per table until sessions move out of the process, and a
way for a server to speak first ("goal", the moment it happens), which the platform does not offer yet
([FR-01](docs/FEATURE_REQUESTS.md)). The hosting steps above get the server itself to any client today.

## What has been verified

Dated 2026-10-15. "Verified" means it was run and the result observed; each row says how to repeat it.

| | Status |
|---|---|
| The server, tools, spoiler guard, state | **Verified**: `make test`, 61 offline suites, no network or credentials |
| Live ESPN data across five sports | **Verified**: three live conversation batches, 70 questions on real matches (finished, upcoming and one in play), in `tests/conversations/`. 50 questions took about 35 s; they found 12 problems, all fixed and tested |
| One question's cost | **Measured**: the first question about a match is 3 ESPN requests and about 3 s (it was 116 and 18 s); a repeat is free |
| A model choosing among the tools | **Measured**: `scripts/route_check.py`, 79 phrasings, four Bedrock models: Amazon Nova Pro called the intended tool on **77 of 79** (97%); Claude Sonnet 4.5 and Haiku 4.5 were last measured, earlier and with fewer fixes, at 56 and 53 (Nova Pro was 59 at that stage). Table and caveats in [docs/BEDROCK.md](docs/BEDROCK.md) |
| Bedrock, Polly, DynamoDB | **Verified** by `make aws-check`; see [docs/BEDROCK.md](docs/BEDROCK.md) and [docs/AWS_SETUP.md](docs/AWS_SETUP.md) |
| Memory on a real DynamoDB table | **Verified** 2026-10-15 with a test listener, cleaned up afterwards: follow-ups ("who scored", "tell me more about him") understood; after a restart the listener still followed the match and kept their team; "forget that" kept the match; "forget everything about me" removed the profile and marker from the table |
| Speed with DynamoDB as the state | **Measured**: a cold first follow made 26 table calls in a row (11 s); now 4.5 s for the tool and 6.3 s with the model; later questions 0 to 3 s ([FL-26](docs/FRICTION_LOG.md)) |
| A real microphone session; use by a blind person | **Reported by the team**: spoken questions, hands-free, with a real microphone, and a first session with a blind listener |
| An independent MCP client | **Verified once** (2026-10-15): the official MCP Python SDK 2.3.0 connected, listed the 30 tools, called two tools against the live feed, and received a bad argument as a tool error (`scripts/check_with_sdk.py`). The MCP Inspector and other clients were not run |
| Alexa+ itself | **Not possible**: the add-on tooling is partner-only |

## Known limitations

We would rather you read these here than find them.

- **Not deployed, and no OAuth.** It runs on one machine. An optional bearer token (`SIDELINE_AUTH_TOKEN`) protects a
  deployment, but Alexa+ needs a public HTTPS endpoint with account linking and OAuth 2.1; that is not built (see
  [docs/MCP.md](docs/MCP.md), "Not implemented, and why").
- **The data source is unofficial.** ESPN publishes no documentation or stability promise for these endpoints. We cache,
  and we say when the feed cannot be reached, but a change on their side would break things.
- **Football is the best tested.** Basketball, hockey and the NFL work for scores, tables and reports, but their match
  events are thinner (ESPN gives hockey and NFL plays differently; see `docs/ESPN_NOTES.md`).
- **What the feed does not have, we do not say:** expected goals, player ratings, a player's honours or titles, and often the
  referee's name.
- **Routing depends on the model.** The same 30 tools were chosen correctly far more often by some Bedrock models than by
  others, and the tool list costs about 8,000 tokens a turn. See the measured comparison in [docs/BEDROCK.md](docs/BEDROCK.md).
- **One listener per server** by default; the state layer is keyed by listener, so the step is account linking.

## For the hackathon

**Track:** Alexa+, a self-hosted MCP server (Streamable HTTP, spec 2025-11-25), demonstrated through its own simulated
Alexa+. **Mini challenge:** AWS Builder (Bedrock, Polly, DynamoDB, Voxtral, Nova Sonic).

| | |
|---|---|
| The submission text | [docs/HACKATHON.md](docs/HACKATHON.md) |
| The demo video script and shot list | [docs/VIDEO_SCRIPT.md](docs/VIDEO_SCRIPT.md) |
| **Friction log** (28 entries: task, steps, expected vs actual, severity, workaround, suggestion) | [docs/FRICTION_LOG.md](docs/FRICTION_LOG.md) |
| Product feedback, per tool, API and SDK | [docs/PRODUCT_FEEDBACK.md](docs/PRODUCT_FEEDBACK.md) |
| Feature requests, with priority | [docs/FEATURE_REQUESTS.md](docs/FEATURE_REQUESTS.md) |

## Documentation

[ARCHITECTURE](docs/ARCHITECTURE.md) · [MCP](docs/MCP.md) · [TOOLS](docs/TOOLS.md) · [BEDROCK](docs/BEDROCK.md) ·
[SPEECH](docs/SPEECH.md) · [ACCESSIBILITY](docs/ACCESSIBILITY.md) · [FINDER](docs/FINDER.md) · [SPORTS](docs/SPORTS.md) ·
[DATA_PROVIDERS](docs/DATA_PROVIDERS.md) · [ESPN_NOTES](docs/ESPN_NOTES.md) · [ENVIRONMENT](docs/ENVIRONMENT.md) ·
[AWS_SETUP](docs/AWS_SETUP.md) · [VIDEO_SCRIPT](docs/VIDEO_SCRIPT.md) · [CREDITS](docs/CREDITS.md) · [CONTRIBUTING](CONTRIBUTING.md)

## Credits and licence

Ideas from BetTrack (cache design, whole-word name matching) and community ESPN documentation are credited, with their
licences, in [docs/CREDITS.md](docs/CREDITS.md). MIT licence: [LICENSE](LICENSE).
