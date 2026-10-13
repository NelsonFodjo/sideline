# Match data

Sideline reads one live feed, [API-Football](https://www.api-football.com) (api-sports.io), and ships **no recorded or
demo data**. This page records what was observed about that feed, and how to write another provider.

## What is and is not established

Observed on 2026-10-13 on a **Free plan** with the key the project was built with.

| Claim | Status |
|---|---|
| The provider parses the vendor's response shape, and errors surface rather than reading as "no match" | **Verified**: against canned responses (`tests/test_apifootball.py`) **and on the live service**: 292 fixtures listed, a live match and a finished one read through all nine tools. `make verify-data ARGS=--tools` |
| The free plan allows 100 requests a day | **Observed**: `/status` reported `limit_day: 100`. The refresh rate of live data is **unmeasured** |
| The free plan refuses some parameters | **Observed**: head-to-head with `last=` is refused, so the provider no longer sends it |
| Referee and line-ups are available | **Depends on the match**: a live women's international had neither. The tools say so rather than guess |
| Basketball has a live feed | **Same vendor, same key**: the basketball API listed 71 games, but is believed to give scores and status, not play-by-play, so it could not produce "X hit a three". **Not built, not verified** |
| The feed's data arrives before a streamed broadcast shows the event | Plausible, **not measured**. `sync_broadcast_delay` exists for it |
| Any other feed's free tier is delayed or capped | **Unverified**: none was examined |

`make verify-data` reads your own plan's quota from the API's `/status` endpoint rather than from this page.

## Running against it

```bash
cp .env.example .env              # put the key in SIDELINE_FOOTBALL_KEY
make verify-data                  # the key, your daily quota, today's fixtures
make verify-data ARGS=--tools     # every tool, against a live match if there is one
make run
```

- **Quota.** One followed match costs about one request per poll (the fixture response embeds its events and
  line-ups), so at the default 60 s it spends a free day in about an hour and a half. Use a paid plan for more.
  The provider caches for 12 seconds, so several tools in one breath share a request.
- **Errors are surfaced.** API-Football reports a bad key or an exhausted quota as HTTP 200 with an `errors`
  field; the provider raises `ProviderUnavailable` rather than reading it as "no such match", and the tool
  answers "I can't get that from the match data right now".
- **Real data found bugs that canned responses hid**, all fixed and pinned by tests: the vendor's "Normal Goal"
  filler was read aloud; an own goal read as an ordinary goal; head-to-head crashed on the free plan and listed
  the live match as a past meeting; a long-absence catch-up named three goals of five and marked all five as
  told (two were lost); a provider outage reached the listener as a protocol error; and a player lookup said "I
  can't find him" when line-ups simply were not published yet.
- **TLS on macOS.** The python.org Python ships without a CA bundle until "Install Certificates.command" is run,
  so every HTTPS call fails with `CERTIFICATE_VERIFY_FAILED`. `sideline/tls.py` finds a real bundle and always
  verifies; it never disables verification.
- **Rules.** The hackathon requires authorisation to use any third-party API or data under its terms. The
  vendor's terms were not read by the authors (its site blocked automated reading); check yours.

## Tests do not use the feed

`tests/support.py` holds a test double that plays back small **invented** fixtures (`tests/fixtures/`: made-up
teams, players and events, labelled as such) on a clock the test controls. They exist so the suite runs offline
and deterministically. Nothing in `sideline/` ships data files, and a test enforces that.

## Writing another provider

Subclass `providers/base.Provider`. Six methods. The normalising rules are in that file and exist because every
vendor gets these wrong in a different way:

- **Minute is an integer.** `45+2` becomes minute 45 with `stoppage: 2`. A listener wants "just before half
  time", not "forty five plus two".
- **An overturned goal is not deleted.** It gets a review event (`var` in football) and the original is marked
  superseded. Someone who heard the crowd needs to be told it was chalked off.
- **Penalties and own goals are goals with a `detail`.** Otherwise every consumer has to know that three kinds
  all mean "the score changed".
- **A fixture says which sport it is** with a `sport` key (absent means football), and emits that sport's event
  kinds: see [SPORTS.md](SPORTS.md).
