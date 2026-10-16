# Universal Multi-Sport Architecture

Sideline is built for any live match or game across global sports. Through its polymorphic `SportProfile` design, Sideline natively supports:
1. **Football (Soccer)**
2. **Basketball (NBA, WNBA, NCAA)**
3. **American Football (NFL, College Football)**
4. **Baseball (MLB)**
5. **Hockey (NHL)**

Live data is provided by the real-time ESPN Universal Provider without requiring API keys.

---

## What is sport-independent

The core engine is completely decoupled from any single sport:
* The append-only event log and event deduplication
* Listener bookmarks on the server (`last_told_at`, `told_event_ids`, and `discussed`, the match just asked about); the
  conversation history and topic are the simulator agent's own session memory, not server state
* The broadcast lag spoiler guard and synchronization anchors
* All 30 conversational MCP tools and routing intents

None of the server plumbing or state handling hardcodes a sport.

---

## What is the sport's call: `SportProfile`

Everything that varies by sport is declared in a dedicated profile (`sideline/sports/<sport>.py`):

| The profile decides | Football (Soccer) | Basketball | American Football | Baseball | Hockey |
|---|---|---|---|---|---|
| **Game term** | match | game | game | game | game |
| **Score kinds** | `goal` (1) | `basket` (1, 2 or 3, from the event's `points`) | `touchdown` (6, or the event's `points`), `field_goal` (3), `safety` (2), `score` (the event's `points`) | `run`, `home_run` (the event's `points`, default 1) | `goal`, `score` (1) |
| **Review / overturn** | `var` | `review` | `review`, `challenge` | `review`, `challenge` | `review`, `challenge` |
| **Long-absence headline** | goals (not disallowed ones), penalties, red cards | three-pointers and ejections | touchdowns, interceptions, fumbles | runs and home runs | goals |
| **Long-absence threshold** | 15 min | 10 min | 10 min | 3 innings | 10 min |
| **Clock phrasing** | "on 34", "on 45 plus 2", "just before half time", "deep into stoppage time" | "with 5 minutes left in the second quarter", "at the start of the third quarter", "in overtime" | "with 3 minutes left in the fourth quarter", "at the start of the second quarter", "in overtime" | "in the 7 inning" (the number as a figure, not yet an ordinal), "in extra innings" | "with 8 minutes left in the second period", "in overtime" |
| **Officials** | referee, yellows and reds so far, assistants | crew chief, fouls called and how many were technical, the rest of the crew | the referee | the home plate umpire | the referee |
| **Line-ups** | formation, keeper first, then the rest | the starting five | the first five starters | the first three batters ("leads off with") | the first three names ("starting line features") |

The clock, per sport (`period_word`, `period_minutes`, `regulation_minutes`, `start_word` in each profile). Match time is
stored as elapsed minutes for every sport; baseball counts one "minute" per inning.

| Sport | Period | Minutes per period | Regulation total | Start of play |
|---|---|---|---|---|
| Football | half | 45 | 90 | kick-off |
| Basketball | quarter | 12 | 48 | tip-off |
| American football | quarter | 15 | 60 | kickoff |
| Baseball | inning | 1 | 9 | first pitch |
| Hockey | period | 20 | 60 | puck drop |

Each row above is a field or a method on the profile, so richer phrasing for a sport ("top of the 7th", "two outs") is a
change to one file, not to the product.

---|---|---|---|---|---|
| **Game term** | match | game | game | game | game |
| **Score kinds** | `goal` (1 pt) | `basket` (1, 2, or 3 pts) | `touchdown` (6), `field_goal` (3), `extra_point` (1/2), `safety` (2) | `run` (1), `home_run` (1-4) | `goal` (1) |
| **Review / Overturn** | `var` | `review` | `review` / `challenge` | `review` | `review` |
| **Long absence headline** | goals, red cards | 3-pointers, dunks, ejections | touchdowns, turnovers | home runs, run scoring plays | goals, major penalties |
| **Absence threshold** | 15 min | 8 min | 12 min | 20 min | 10 min |
| **Clock phrasing** | "on 34", "just before half-time" | "with 5 minutes left in the 2nd quarter" | "with 3 minutes left in the 4th quarter" | "top of the 7th with 2 outs" | "8 minutes into the 2nd period" |
| **Officials count** | yellows and reds | personal and technical fouls | penalties and yards | warnings and ejections | penalty minutes and minors/majors |
| **Rosters / Lineups** | starting 11 + formation | starting five | offense / defense / starters | starting lineup and batting order | starting six / forward lines |

---

## Adding a New Sport

To add a new sport (e.g., Formula 1, Tennis, Cricket):
1. Subclass `SportProfile` in `sideline/sports/<sport>.py`.
2. Implement class fields and methods:
   - `score_kinds`, `review_kinds`, `period_anchors`, `recency`
   - `when()`, `say_event()`, `say_match_state()`, `say_lineups()`, `say_officials()`
   - Register it with `register()`.
3. Import the new sport module in `sideline/sports/__init__.py`.
4. Add live score mapping in `sideline/providers/espn.py` and unit tests in `tests/test_sports.py`.

---

## Verified Multi-Sport Capabilities

| Capability | Status |
|---|---|
| **Soccer Live Feed** | **Verified**: Real-time scoreboards, events, rosters, and tables for UCL, EPL, La Liga, Serie A, MLS, etc. |
| **Basketball Live Feed** | **Verified**: NBA and College Basketball quarters, points breakdown, boxscores, and standings. |
| **American Football Live Feed** | **Verified**: NFL and NCAA football scores, quarters and clock, team stats (yards, first downs, turnovers, penalties), standings and leaders. Down and distance are not tracked yet. The feed gave no NFL play-by-play in our checks, so match reports say so. |
| **Baseball Live Feed** | **Verified**: MLB scores by inning, standings, leaders, the pitchers used (`get_match_report`, `part: pitching`) and box-score lines. Outs are not tracked, and the feed gave no baseball play events in our checks. |
| **Hockey Live Feed** | **Verified**: NHL scores, periods, playoff series, standings, leaders, and team stats including penalties, penalty minutes and power plays. Goal-by-goal match reports depend on the feed's key events, which are thinner than football's. |
| **Multi-Sport Disambiguation** | **Verified**: The finder ranks and resolves matches across mixed-sport candidate pools or forks with clear sport tags. |
| **Offline Determinism** | **Verified**: `tests/test_sports.py` and `tests/test_espn.py` run fully offline, on data built inside the tests; no request reaches the feed. |
