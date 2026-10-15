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
* Listener bookmarks (`last_told_at`, `told_event_ids`, `history`, `topic`)
* The broadcast lag spoiler guard and synchronization anchors
* All 30 conversational MCP tools and routing intents

None of the server plumbing or state handling hardcodes a sport.

---

## What is the sport's call: `SportProfile`

Everything that varies by sport is declared in a dedicated profile (`sideline/sports/<sport>.py`):

| The profile decides | Football (Soccer) | Basketball | American Football | Baseball | Hockey |
|---|---|---|---|---|---|
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
| **American Football Live Feed** | **Verified**: NFL and NCAA football down, distance, quarters, field goals, and touchdowns. |
| **Baseball Live Feed** | **Verified**: MLB innings, outs, runs, and standings. |
| **Hockey Live Feed** | **Verified**: NHL periods, goals, and penalty tracking. |
| **Multi-Sport Disambiguation** | **Verified**: The finder ranks and resolves matches across mixed-sport candidate pools or forks with clear sport tags. |
| **Offline Determinism** | **Verified**: `tests/test_sports.py` and `tests/test_espn.py` execute 100% offline using synthetic fixtures. |
