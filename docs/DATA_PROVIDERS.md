# Match data

Sideline reads one live feed, [Sportmonks](https://www.sportmonks.com), and ships **no recorded or demo data**. This
page records what was observed about that feed, what each tool needs from it, and how to write another provider. Why
Sportmonks and not the feed the project started on: [FRICTION_LOG.md](FRICTION_LOG.md) FL-14.

## What is and is not established

Observed on 2026-10-13 on the **Free plan**, with the token the project was built with.

| Claim | Status |
|---|---|
| The provider turns Sportmonks' v3 shapes into ours | **Verified on a real, finished match** (AGF against Sønderjyske Fodbold, Superliga, 2026-10-12): the fixture, three goals with assists and running score, ten substitutions (`player_name` came on, `related_player_name` went off), a yellow card, two VAR notes, both line-ups with formations and shirt numbers, the referee, statistics, head to head. `make verify-data ARGS="--tools <fixture id>"` |
| Standings, top scorers, competitions, search, injuries, form, a player's season | **Verified on the same plan**: real tables and scorers for the Superliga, five absences with reasons, recent results as W/D/L, a player's appearances and goals |
| It works during a match in play | **Not yet seen**: the plan's four leagues had no match in play when it was checked. The live path (a ticking period gives the minute, events arrive as they happen) is read from the documentation and pinned by tests with invented data |
| The free plan | **Observed**: four leagues (Superliga and Superliga Play-offs in Denmark, Premiership and Premiership Play-Offs in Scotland), **180 calls an hour per kind of data** (`rate_limit.remaining` 179 after one call), football and cricket plans. Sportmonks' pricing page does not state these: they come from the dashboard and the `leagues` endpoint |
| Statistics on the free plan | **Observed**: possession, corners, goals, assists and cards; **no shots or fouls**, so the stats tool says only what exists |
| Win estimates | **Not available**: an add-on. A match preview does not say who is favoured |
| A day with no match | **Observed**: HTTP 200 with a `message` ("you don't have access to it via your current subscription"), the same as a quiet day. The provider returns an empty list |
| Basketball or other sports | **Not built.** The tools are sport-neutral and the `SportProfile` seam is tested on an invented basketball game; the free plan also lists cricket, which is not built either |
| The feed's data arrives before a streamed broadcast shows the event | Plausible, **not measured**. `sync_broadcast_delay` exists for it |

## What each tool needs from the feed

A provider lists what it can supply in `capabilities`, and a tool whose need is missing is not offered
(`registry.TOOL_REQUIRES`). Sportmonks' free plan supplies all of these.

| Capability | Tools it unlocks |
|---|---|
| fixtures, events, lineups, officials, h2h | `follow_match`, `get_match_state`, `get_fixtures`, `get_schedule`, `get_my_matches`, `get_match_preview`, `what_did_i_miss`, `get_event_detail`, `get_lineups`, `get_player_context`, `get_officials`, `get_head_to_head` |
| stats | `get_match_stats` |
| injuries | `get_injuries` (a fixture's `sidelined` list, dropping ended ones) |
| form | `get_team_form` (a team's fixtures between two dates, the last five finished) |
| standings, top_scorers | `get_standings`, `get_top_scorers` (the competition's current season, found from `leagues`) |
| player_stats | `get_player_stats` (the latest season in the player's statistics) |
| search, competitions | `search`, `get_competitions` |

## Running against it

```bash
cp .env.example .env              # put the token in SPORTMONKS_TOKEN
make verify-data                  # the token, the plan's leagues, calls left this hour, today's fixtures
make verify-data ARGS="--tools 19713909"   # every core tool, on a given fixture
make run
```

- **Days.** The feed lists a UTC day; a listener's day is their own. Tools read the UTC dates the listener's day touches and keep the matches inside it, so a 1 AM kick-off in Mauritius is tomorrow's, not today's.
- **Quota.** One followed match costs about one call per poll (the fixture response embeds its events and line-ups),
  so a match in play at the default 30 s uses two thirds of an hour's 180. A match not yet started is checked every 5 minutes, and a finished one is not polled again. A day's list is cached five minutes, a fixture twelve
  seconds, so several tools in one breath share a call. The provider logs a warning when fewer than 20 calls remain.
- **Errors are surfaced.** A refused request raises `ProviderUnavailable` carrying the vendor's own message and, for a
  rate limit, how long to wait; the tool then answers "The match data feed said: <that>. Try again shortly." and the
  voice agent says exactly that, without rewording.
- **A demo needs a match in one of the four leagues.** The free plan cannot see others, so Sideline cannot find them.
- **Real data found details that docs and tests did not**, all handled: a day with nothing returns 200 and an empty
  list; the free plan has no shots statistics; the `type` of an event is only a name when `events.type` is included.
- **TLS on macOS.** The python.org Python ships without a CA bundle until "Install Certificates.command" is run, so
  every HTTPS call fails with `CERTIFICATE_VERIFY_FAILED`. `sideline/tls.py` finds a real bundle and always verifies;
  it never disables verification.
- **Rules.** The hackathon requires authorisation to use any third-party API or data under its terms. Sportmonks'
  free-plan terms are not on its pricing page and were not read by the authors; check yours.

## Tests do not use the feed

`tests/support.py` holds a test double that plays back small **invented** fixtures (`tests/fixtures/`: made-up
teams, players and events, labelled as such) on a clock the test controls. `tests/test_sportmonks.py` pins the
provider against invented responses in Sportmonks' shape. They exist so the suite runs offline and deterministically.
Nothing in `sideline/` ships data files, and a test enforces that.

## Writing another provider

Subclass `providers/base.Provider`. The core reads are `fixture`, `fixtures_on`, `events`, `lineups` and
`officials`; the rest (`search`, `competitions`, `standings`, `top_scorers`, `match_stats`, `player_stats`,
`injuries`, `form`, `head_to_head`) are optional, and each one implemented is a capability that unlocks its tool. The
normalising rules are in that file and exist because every vendor gets these wrong in a different way:

- **Minute is an integer.** `45+2` becomes minute 45 with `stoppage: 2`. A listener wants "just before half
  time", not "forty five plus two".
- **An overturned goal is not deleted.** It gets a review event (`var` in football) and the original is marked
  superseded. Someone who heard the crowd needs to be told it was chalked off.
- **Penalties and own goals are goals with a `detail`.** Otherwise every consumer has to know that three kinds
  all mean "the score changed".
- **A fixture says which sport it is** with a `sport` key (absent means football), and emits that sport's event
  kinds: see [SPORTS.md](SPORTS.md).
- **A refusal is an error, never "no such match".** Raise `ProviderUnavailable` with the vendor's own words.
