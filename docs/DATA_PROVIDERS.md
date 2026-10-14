# Match data & providers

Sideline connects to a live, zero-authentication CDN feed via **ESPN Universal Sports API** and ships **no recorded or demo data**. This page documents the provider architecture, normalising rules, coverage across 5 sports, and how to write additional providers.

## Universal Multi-Sport Feed Architecture

The feed uses ESPN's public real-time CDN scoreboards and summary endpoints. It requires zero API keys, imposes no rate limits or subscription tiers, and covers global sports in real time.

| Sport | Covered Competitions & Leagues | Primary Event Types |
|---|---|---|
| **Football (Soccer)** | UEFA Champions League, Premier League, La Liga, Serie A, Bundesliga, Ligue 1, MLS, Europa League, Scottish Premiership, Eredivisie, FA Cup, etc. | Goals, yellow/red cards, substitutions, penalties, VAR decisions |
| **Basketball** | NBA, NCAA Men's Basketball, WNBA | 2-pointers, 3-pointers, free throws, quarters/halves, fouls, time-outs |
| **American Football** | NFL, NCAA College Football | Touchdowns, field goals, extra points, safeties, quarters, turnovers |
| **Baseball** | MLB | Runs, home runs, innings, hits, outs, errors |
| **Hockey** | NHL | Goals, power play goals, periods, penalties, overtime |

## Verification and Capabilities

| Claim | Status |
|---|---|
| Zero API Key / Zero Auth | **Verified**: Connects directly to ESPN CDN endpoints without credentials. |
| Multi-Sport Live Normalisation | **Verified**: Automatically normalises scoreboards, game clocks, periods, boxscores, and rosters into Sideline's unified `Fixture`, `Event`, `Lineup`, and `Stats` data models. |
| Standings, Scorers, Schedules | **Verified**: Real-time league standings, leaderboards, upcoming fixtures, and head-to-head records across all 5 sports. |
| Low Latency Caching | **Verified**: Scoreboards and summaries are cached locally (10s for live fixtures, 300s for daily schedules) with parallel prefetching. |

## What each tool needs from the feed

A provider declares what it supplies in `capabilities`, and any tool whose requirement is missing is omitted from discovery (`registry.TOOL_REQUIRES`). The ESPN provider implements all capabilities:

| Capability | Tools it unlocks |
|---|---|
| `fixtures`, `events`, `lineups`, `officials`, `h2h` | `follow_match`, `get_match_state`, `get_fixtures`, `get_schedule`, `get_my_matches`, `get_match_preview`, `what_did_i_miss`, `get_event_detail`, `get_lineups`, `get_player_context`, `get_officials`, `get_head_to_head` |
| `stats` | `get_match_stats` |
| `injuries` | `get_injuries` |
| `form` | `get_team_form` (last 5 finished matches) |
| `standings`, `top_scorers` | `get_standings`, `get_top_scorers` |
| `player_stats` | `get_player_stats` |
| `search`, `competitions` | `search`, `get_competitions` |
| `team_matches` | `get_schedule` (next matches and recent results), candidate discovery |
| `team_stats` | `get_team_stats` |
| `squad` | `get_squad` |

## Running Against Live Feeds

```bash
make verify-data                  # verifies ESPN connection and lists today's fixtures across all sports
make verify-data ARGS="--tools"   # tests all core MCP tools on live games
make next-matches ARGS=14         # shows schedule for the next 14 days
make run                          # boots server with live multi-sport feeds
```

- **Time Zones:** The feed returns UTC kickoff timestamps. Tools convert them dynamically using the listener's local browser timezone offset (`tz_offset_minutes`).
- **Resilience:** Unreachable feeds raise `ProviderUnavailable` with clear diagnostic context, which the agent turns into an honest voice decline.

## Tests do not use the feed

Unit tests (`tests/test_*.py`) run 100% offline and deterministically:
- `tests/support.py` provides an offline `ReplayProvider` with synthetic fixtures.
- `tests/test_espn.py` validates ESPN response normalisation using offline mock structures.
- Product packages contain no static JSON data files; compliance is enforced by `tests/test_clean_clone.py`.

## Writing Another Provider

Subclass `sideline.providers.base.Provider`:
1. Implement core methods: `fixture()`, `fixtures_on()`, `events()`, `lineups()`, and `officials()`.
2. Implement optional capability methods: `search()`, `competitions()`, `standings()`, `top_scorers()`, `match_stats()`, `player_stats()`, `injuries()`, `form()`, `head_to_head()`, `squad()`.
3. Normalising rules:
   - **Minute is an integer:** Stoppage time is represented as elapsed minute with `stoppage` field.
   - **Overturned scores are never deleted:** Emits a review event (VAR/replay review) with `superseded_by`.
   - **Sport tagging:** Every fixture carries a `sport` field (e.g. `football`, `basketball`, `american_football`, `baseball`, `hockey`), invoking the corresponding `SportProfile`.
