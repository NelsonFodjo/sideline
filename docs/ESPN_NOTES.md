# ESPN endpoint notes

ESPN publishes no documentation for these endpoints; they are unofficial and can change without notice. These notes
are what we have **verified live** (marked "verified") and what community documentation says that we have **not**
(marked "documented"). Community sources: [pseudo-r/Public-ESPN-API](https://github.com/pseudo-r/Public-ESPN-API)
(MIT, 17 sports, 139 leagues; see docs/CREDITS.md) and BetTrack's `mcp/espn-api-spec.json`.

## What we use, and the tricks that matter

| Need | Request | Notes |
|---|---|---|
| Every soccer match on a day, every competition | `site/v2/sports/soccer/all/scoreboard?dates=YYYYMMDD&limit=500` | **verified.** One request instead of one per league. Without `limit` ESPN cuts the list at 100. The event carries only a numeric league id (`uid` `~l:ID~`). |
| League id to name and slug | `site.web.api.espn.com/apis/site/v2/leagues/dropdown?sport=soccer&limit=500` | **verified.** About 220 soccer leagues; keep for a day. |
| A team's matches | `site/v2/sports/soccer/all/teams/{id}/schedule` (played) and `...?fixture=true` (still to come) | **verified.** Never both in one answer: ask twice. |
| Find a team or player | `site.api.espn.com/apis/search/v2?query=...` | **verified.** `uid` is `s:600~t:ID` (team) or `s:600~a:ID` (athlete). The `id` field is a GUID, not what other endpoints want. |
| Match detail | `site/v2/sports/soccer/all/summary?event=ID` | **verified.** Works through `all`, so no league slug is needed. Has `keyEvents`, `commentary`, `rosters`, `boxscore`. |
| Player profile | `site.web.api.espn.com/apis/common/v3/sports/soccer/athletes/ID` | **verified.** Age, citizenship, jersey, position, club. No honours or titles. |
| Player season | `.../athletes/ID/overview` | **verified.** `statistics.splits` mixes club and national-team competitions: tell them apart by the split's name. |
| League table | `site.api.espn.com/apis/v2/sports/soccer/{league}/standings` | **verified.** Under `/apis/site/v2/` soccer standings come back empty. Competitions in groups have one `children` entry per group. |
| News | `site/v2/sports/soccer/{league or all}/news?limit=N` and `?team=ID` | **verified.** |
| Competitions not in a hard-coded list | the dropdown above | AFC Champions League Two is `afc.cup`, Elite is `afc.champions`. |

## Behaviour to know

- **Scoreboard date ranges** (`dates=A-B`) are documented as broken by an ESPN regression; request one date at a time.
  *documented (pseudo-r).* We already ask for single dates.
- **Core API links** (`sports.core.api.espn.com`) sometimes use a `.pvt` host in their `$ref`; replace `.pvt` with `.com`.
  *documented (pseudo-r).*
- ESPN's time and minute data are **cached by the CDN** and a schedule's clock for a match in play can be stale: read
  the match's own summary for the live minute. **verified.**
- Statistics: possession, shots, corners, fouls, cards, offsides, saves and pass counts are in the box score; **expected
  goals are not**. **verified.**
- A finished match's summary never changes, so the provider keeps it for hours (`espn.py`, `FINISHED_SUMMARY_TTL`).

## Tried and not worth using

| Endpoint | Result |
|---|---|
| `.../competitions/ID/probabilities` (win probability) | HTTP 400 for football, finished or live. *verified.* |
| `.../competitions/ID/situation` | A bare reference link only. *verified.* |
| `site/v2/.../teams/ID/injuries` and the core `.../teams/ID/injuries` | Empty for Paris Saint-Germain: cannot tell "no injuries" from "not tracked". *verified.* |
| `cdn.espn.com/core/soccer/scoreboard?xhr=1&league=...` | Works, but slower than the site API (about 1.5 s). *verified.* |
| `athletes/ID/stats`, `/gamelog`, `/splits` for soccer | 404 or 400. *documented (pseudo-r).* |
| `.../athletes/ID/awards` | 404: no honours from ESPN. *verified.* |

## Not built yet, and why

- **Odds** are in the match data (`odds`, `pickcenter`) but we have kept betting out of a product for blind football
  fans. It is a decision, not a gap.
- **Other sports** (rugby, cricket, tennis, golf, F1, MMA): pseudo-r's `docs/data/leagues.json` lists their league
  slugs. Each needs its own sport profile (how it is scored and spoken) before it is worth adding.
