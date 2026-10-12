# Match data

## What is and is not established about live data

The product needs structured match data. What this project can and cannot
support:

| Claim | Status |
|---|---|
| StatsBomb Open Data can drive a faithful replay (goals, cards, substitutions, a VAR event, line-ups) | **Verified**: the bundled match, `tests/test_statsbomb.py`, `docs/EVIDENCE.md` |
| The API-Football provider parses its documented response shape, and errors surface rather than reading as "no match" | **Verified against canned responses only**: `tests/test_apifootball.py` |
| API-Football's free plan allows about 100 requests a day; live data refreshes about every 15 s | **Unverified.** The vendor's site blocked automated reading (HTTP 403 bot challenge) and was not worked around. Check their pricing and documentation by hand before relying on either figure. |
| Any other free tier is delayed or capped | **Unverified**; none was examined here. |
| A provider's data arrives before a streamed broadcast shows the event | Plausible, **not measured**: no live match was observed. `sync_broadcast_delay` exists for it. |

Run `make verify-data` with a real key to see your own plan's quota; it
reads the figures from the API's `/status` endpoint rather than from this page.

## The replay harness

`providers/replay.py` plays a recorded match back at real speed through
the identical code path the live provider uses.

It goes through the same provider interface, normalising and dedupe as a
live provider; what differs is where the events come from. It replays real
events, so it is a recording, not live.

Two reasons it exists, both practical:

1. Development does not have to wait for a fixture.
2. The demo is repeatable: a live match could be dull or unavailable.

```bash
SIDELINE_REPLAY_SPEED=20 python3 -m sideline    # a match in 4.5 minutes
SIDELINE_REPLAY_START=60 python3 -m sideline    # start on the hour mark
```

### The honesty rule

Anything shown from replay is described as **"a recorded real match,
replayed"**. Never implied to be live.

The data is genuine; the clock is ours. Saying so costs nothing and
protects everything. See DEMO_SCRIPT.md.

> `data/replay/spurs-arsenal-2016.json` is the genuine default.
> `data/replay/arsenal-spurs.json` is an invented fixture used by the
> tests and labelled as such; never show it in a demo.

## Live data

```bash
# SIDELINE_PROVIDER=auto (the default) goes live as soon as a key is present
read -s -p "API-Football key: " SIDELINE_FOOTBALL_KEY; echo; export SIDELINE_FOOTBALL_KEY
make verify-data          # checks the key, shows your daily quota and today's fixtures
make run
```

Notes, so there are no surprises:

- **No key, no problem:** `SIDELINE_PROVIDER=apifootball` with no key logs a
  warning and serves the recorded match, so the server still works.
- **Quota.** A free plan allows about a hundred requests a day. The poller
  makes about one request per followed match per poll (the fixture
  response embeds its events and line-ups), so at the default 15 s a
  match burns the free day in under half an hour. Use
  `SIDELINE_POLL_SECONDS=60` or a paid plan.
- **Errors are surfaced.** API-Football reports a bad key or an exhausted
  quota as HTTP 200 with an `errors` field; the provider raises
  `ProviderUnavailable` rather than reading it as "no such match".
- **Not tested against the live service.** The provider is tested against
  canned responses in API-Football's shape (`tests/test_apifootball.py`),
  not a real key. First live run: expect to look at one log line.
- **Rules.** The hackathon requires you to be authorised to use any third
  party API or data under its terms, and judges must be able to run the
  project free of charge, which is why the default is the recorded match
  and live data is opt-in.

## The bundled match

`data/replay/spurs-arsenal-2016.json` is **Tottenham 2-2 Arsenal, 5 March
2016**, built from StatsBomb Open Data with
`scripts/build_statsbomb_replay.py` (referee from StatsBomb's matches
file). It is real, and it is the default. `arsenal-spurs.json` is a small
invented fixture used only by the tests.

StatsBomb's terms ask that anything you publish based on the data
"state the data source as StatsBomb and use our logo". We attribute in
text. **The logo is not included, and the video rules forbid third-party
trademarks without permission**, so before filming either get their
permission or keep the on-screen attribution to text, and say
"data from StatsBomb Open Data".

## Capturing a real match

```bash
export SIDELINE_FOOTBALL_KEY=...
python3 scripts/record_match.py --fixture 1208341 --out data/replay/real.json
```

Run it live and it polls to full time. Run it after the match and it
captures the finished record in one pass, which is usually what you want.

## Writing another provider

Subclass `providers/base.Provider`. Six methods. The normalising rules
are in that file and exist because every vendor gets these wrong in a
different way:

- **Minute is an integer.** `45+2` becomes minute 45 with `stoppage: 2`.
  A listener wants "just before half time", not "forty five plus two".
- **An overturned goal is not deleted.** It gets a `var` event and the
  original is marked superseded. Someone who heard the crowd needs to be
  told it was chalked off.
- **Penalties and own goals are goals with a `detail`.** Otherwise every
  consumer has to know that three kinds all mean "the score changed".

That adapter is the piece we extract for the Open Source mini challenge —
it is useful to anyone putting a sports feed behind MCP, not just us. See
MINI_CHALLENGES.md.
