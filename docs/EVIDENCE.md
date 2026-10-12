# Evidence

Every number below was **measured by `scripts/collect_evidence.py`**, not
typed in. This is a dated snapshot, not a current status dashboard:
subsequent live AWS verification is recorded in
[AWS_SETUP.md](AWS_SETUP.md). Re-run it (`make evidence`) and this file is
rewritten. Unverified items below describe the state at this snapshot.

| | |
|---|---|
| Measured | 2026-10-12 16:16 +04 |
| Git commit | `dd1d82c` (uncommitted changes: yes) |
| Python | 3.14.8 on macOS-27.0-arm64-arm-64bit-Mach-O |
| Replay used | `data/replay/spurs-arsenal-2016.json` (the default) |

## The bundled match

| | |
|---|---|
| Fixture | Tottenham Hotspur v Arsenal, White Hart Lane |
| Events | 17 (6 card, 4 goal, 6 substitution, 1 var) |
| Referee | Michael Oliver |
| Line-ups | Tottenham Hotspur: 11 starters; Arsenal: 11 starters |
| Attribution in file | yes |

## Protocol

| | |
|---|---|
| Protocol version negotiated | 2025-11-25 |
| Tools exposed | 9: follow_match, get_match_state, get_lineups, what_did_i_miss, sync_broadcast_delay, get_event_detail, get_officials, get_player_context, get_head_to_head |

## Response time (HTTP, in-process server, templates only)

200 calls per tool through a real HTTP client. Server and client share
one machine, so this is **server time plus loopback**: it shows the
server is not the slow part, **not** what a listener on a network or
through Alexa+ would see. Bedrock is off here.

| Tool | p50 ms | p95 ms | max ms |
|---|---|---|---|
| `get_match_state` | 0.2 | 0.5 | 0.7 |
| `get_lineups` | 0.2 | 0.2 | 0.3 |
| `get_officials` | 0.2 | 0.2 | 0.3 |
| `get_event_detail` | 0.2 | 0.2 | 0.3 |
| `get_player_context` | 0.2 | 0.3 | 0.3 |
| `get_head_to_head` | 0.2 | 0.2 | 0.3 |
| `sync_broadcast_delay` | 0.2 | 0.2 | 0.3 |
| `what_did_i_miss` (template) | 0.2 | 0.2 | 0.3 |

## Precomputed catch-up (mechanism only)

**The model here is a stand-in that sleeps 800 ms. This is not Bedrock and says
nothing about Bedrock's real latency, which has not been measured.** It shows
only where that wait lands: on the listener, or in the background.

| `SIDELINE_CATCHUP_MODE` | `summary_source` | `what_did_i_miss` time |
|---|---|---|
| live | live | 805.7 ms |
| cached | precomputed | 0.3 ms |

## Data volume

One `get_match_state` call per 15 s across a 90-minute match (364 calls):

| | |
|---|---|
| Response bodies only | 190 KB (534 bytes per call) |
| Estimated on the wire, both directions, incl. HTTP headers | 399 KB |
| Not included | the spoken audio Alexa+ would stream to the listener |

## Repository facts

| | |
|---|---|
| Tracked Python files | 49 (5469 lines) |
| Test suites | 16 (`make test`) |
| First commit | 2026-10-12 |
| Third-party imports in the server | boto3 and cryptography, both optional; the rest is the standard library |

## Not verified yet

These need credentials this script does not use. Until the command has
been run and its output kept, treat each as **unverified**.

| Claim | Status | Verify with |
|---|---|---|
| Bedrock catch-up works and its latency | not measured | `make aws-check` |
| The default Bedrock model id is available | not checked | `make aws-check` |
| Precomputed summaries with the real model (hit rate, latency) | tested with a simulated model only | `make aws-check`, then ask after a poll and read `summary_source` |
| DynamoDB state, incl. conditional-put dedupe | not run against DynamoDB or DynamoDB Local | `make create-table` then `make run` |
| Polly speech and word marks, Transcribe streaming | not run | `make aws-check`, then the simulator |
| Live football feed (API-Football) | tested against canned responses only | `make verify-data` |
| CloudFormation stack deploys | passes `cfn-lint`; never deployed | `make deploy` (costs money; tear down after) |
| Python 3.8 compatibility | not run locally (this machine: 3.14.8); CI is configured for 3.8 and 3.12 and has not run | push and read the CI result |
| Any real Alexa+ device or account link | **impossible**: the tooling is partner-only (Devpost FAQ) | n/a |
| Use by a blind or low-vision person | no one has tested it | a session with a real person |

Credentials detected in this environment when this ran: AWS keys: absent; football key: absent.
