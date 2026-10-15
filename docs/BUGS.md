# Sideline bug register

Code review of every source file under `sideline/`, `simulator/`, `scripts/`, plus `run.sh` and `Makefile`, at commit `61d13e2` (2026-10-15). Docs were used only to understand intent; every finding below comes from the code.

**How findings were checked**

- **Repro**: reproduced with a script, a mocked provider or Bedrock, a live in-process server, or saved ESPN payloads.
- **Code**: the code unambiguously does this; not executed.
- **Plausible**: depends on data or timing not reproduced (e.g. an ESPN payload shape not seen live).
- ✔ in the ID column: re-read and confirmed a second time during triage.

Severity: **Critical** breaks a headline feature or is exploitable; **High** gives wrong answers in normal use; **Medium** wrong in common edge cases; **Low** cosmetic, rare or hygiene.

Duplicates reported from several angles are merged into one entry, with all locations listed.

> **Environment first:** `.venv` in this checkout was created on Linux (`/home/nelco/...`, Python 3.12) and its `python` symlink is dangling on this Mac. `run.sh` does not recover from that (see CFG-08). Rebuild with `python3 -m venv --clear .venv` before testing fixes. `make test` currently passes on system Python 3.14 — none of the bugs below are caught by the suite.

---

## Fix first (before the demo video)

These either break what the demo shows, or contradict the pitch a judge will read.

| # | ID | Why it matters |
|---|---|---|
| 1 | ST-01 | Spoiler guard does nothing at every realistic delay — the headline safety feature is inert. |
| 2 | AG-01 | "What did I miss?" can silently lose the goals — the headline feature. |
| 3 | AG-02, AG-03 | 14 real tools (standings, spoiler sync, favourites…) can never reach the model. |
| 4 | VO-03 | Screen-reader live region is `aria-live="off"` — the accessibility pitch fails for blind users. |
| 5 | VO-01 | One failed TTS call freezes the app until reload. |
| 6 | FR-01 | "No, the Rangers one" picks option 1. |
| 7 | ESPN-04, ESPN-05, ESPN-06 | Soccer events have no team, stoppage time is lost, scored penalties are not goals. |
| 8 | ESPN-01, ESPN-02, ESPN-03, ESPN-10 | NFL/NHL/MLB details empty; NFL games in soccer lists; evening US games vanish. |
| 9 | ST-05, ST-06 | The poller thread dies or gives up on a live match permanently. |
| 10 | MCP-01, MCP-02, MCP-03 | Unauthenticated hang / origin bypass — matters as soon as the server is exposed for judges. |

---

## 1. MCP server core — `sideline/mcp/`, `sideline/app.py`

| ID | Sev | Status | Location | Bug | Fix |
|---|---|---|---|---|---|
| MCP-01 | High | Repro | server.py:364, 405, 422-423, 465 | No body cap on `/mcp`; `Content-Length: -1` makes `rfile.read(-1)` block the thread forever on every POST route; non-numeric length on `/mcp` and `/agent/chat` raises unhandled. | Parse once; 400 on `<0` or non-numeric, 413 over a cap (e.g. 1 MiB); `close_connection=True`. |
| MCP-02 ✔ | High | Repro | server.py:355-356, 405-417 | Early 403 (bad Origin) is sent without reading the body and the connection stays open, so an HTTP request hidden in the body is parsed as the next request — with no Origin, it passes. Reproduced: smuggled `/voice/tts` ran `synthesize`. Works for `/voice/stt`+`X-Run-Agent` and `/mcp` too. | `self.close_connection = True` on every early 4xx. |
| MCP-03 | Medium | Repro | server.py:219-227 | Origin allow-list ignores scheme and port: `http://localhost:31337` is accepted and echoed in ACAO, so any page on any localhost port can call tools, STT/TTS and the agent. | Compare full origin (scheme, host, port). |
| MCP-04 | Medium | Repro | server.py:316-329 | SSE GET sends neither Content-Length nor chunking and keeps the connection alive; after its 300 s loop the client never sees EOF and the thread stays pinned. | `close_connection=True` on the SSE path. |
| MCP-05 | Medium | Repro | server.py:64-95, 436 | Session table grows without bound (200 `initialize` posts → 200 permanent entries); failed or notification-style `initialize` also mints sessions. Expiry is from creation, so an active session dies at 6 h (`seen` is never read, :87). | Sweep on create, cap, mint only on success, expire on `seen`. |
| MCP-06 | Medium | Code | server.py:214, 524 | No `Handler.timeout`; one thread per connection, so idle keep-alive or session-less `GET /mcp` exhausts threads. | Set a timeout; require a session for GET; cap SSE streams. |
| MCP-07 | Medium | Repro | server.py:432-443 | `Mcp-Session-Id` is not actually required after initialize (docstring at :16 says it is; spec says 400). | 400 for non-initialize requests without it. |
| MCP-08 | Medium | Repro | server.py:401-460 | `MCP-Protocol-Version` request header never checked; spec 2025-11-25 says MUST 400 on unsupported. | Validate when present. |
| MCP-09 | Medium | Repro | server.py:163; schema.py | Argument validation failures return JSON-RPC -32602; under 2025-11-25 they should be tool results with `isError: true` so the model can self-correct. `simulator/mcp_client.py:108` depends on -32602. | Return `isError`; update the client. |
| MCP-10 | Medium | Repro | schema.py:52-58 | `maxItems` never enforced (`set_favourites` accepts 50 teams). | Add the check. |
| MCP-11 | Medium | Code | registry.py:69 vs espn.py:297, 336; follow_match.py:133 | `fixture_id` typed `integer`, but ESPN ids are strings and tools return them as strings; a model echoing the id back gets -32602. | Accept digit strings, or emit integers consistently. |
| MCP-12 | Medium | Code | server.py:380-383 → app.py:101-107 → clock.py:129 | `/voice/stt` with `X-Run-Agent` passes `X-Tz-Offset` unchecked (`/agent/chat` caps ±840). 2000 is saved to the listener; every later `timezone(timedelta(minutes=2000))` raises, breaking that listener permanently (persists in DynamoDB). Same path passes `tz_name=None`, overwriting the stored zone, and leaves `X-Interrupted` uncapped. | Reuse `/agent/chat` validation; pass `tz_name`. |
| MCP-13 | Medium | Repro | app.py:125 | Agent bridge always dials `127.0.0.1` though the server binds `CONFIG.host`; with a LAN IP every `/agent/chat` is 503. | Build URL from `srv.server_address` (map 0.0.0.0 → 127.0.0.1). |
| MCP-14 | Medium | Code | registry.py:97, 151, 167; server.py:139 | `experimental.mcpApps` declared and three tools point to `mcp-apps://…`, but no `resources/*` handler exists (-32601) and `_meta.ui` is a bare string, not `{resourceUri: "ui://…"}`. | Implement MCP Apps resources or remove the claim. |
| MCP-15 | Low | Repro | registry.py:455-459 | `by_name` ignores `available()`: a tool hidden from `tools/list` still answers `tools/call`. | Check availability in `by_name`. |
| MCP-16 | Low | Repro | server.py:504-521 | Invalid messages (`5`, `[]`, no `jsonrpc`, `id: null`) get 202 and are dropped; a client *response* gets -32600 (spec expects 202). | Notification only if dict without `id`; else -32600/400. |
| MCP-17 | Low | Repro | server.py:445-455 | JSON-RPC batches still accepted (removed from MCP in 2025-06-18); a batched `initialize` gets no session id. | Reject arrays. |
| MCP-18 | Low | Repro | server.py:112, 128, 153 | Non-object `params` → AttributeError → -32603 (should be -32602), and still mints a session. | `isinstance(params, dict)` check. |
| MCP-19 | Low | Repro | server.py:331-347 | DELETE has no Origin check and returns 204 for unknown sessions (should be 404); preflight omits DELETE and the `X-*` headers the simulator sends. | Add check, 404, complete preflight lists. |
| MCP-20 | Low | Repro | server.py:287-411 | Routes compare the raw path, so `/mcp?x=1` is 404 (contradicts the comment at :284). | Route on `urlparse(path).path`. |
| MCP-21 | Low | Code | server.py:385-386 | Agent failure on the speech path is only logged; client gets a transcript with no answer and no error. | Audit and return `chat_error`. |
| MCP-22 | Low | Code | server.py:51, 143 | Server title and `initialize` instructions say football only, despite five sports. | Make sport-neutral. |

## 2. Simulator agent (the "simulated Alexa+" host) — `simulator/agent.py`, `simulator/mcp_client.py`

| ID | Sev | Status | Location | Bug | Fix |
|---|---|---|---|---|---|
| AG-01 ✔ | Critical | Repro | agent.py:692-700, 854-887; what_did_i_miss.py:82-96 | In agent mode `what_did_i_miss` returns `spoken=""` but still calls `mark_told`. The fast path discards empty-spoken results and falls through to Nova, whose own call finds the gap already consumed. Repro: told at 12', match at 64' — fast path sees 5 events, Nova sees 3; the goals are never told. Same in the full-update fan-out (:752) and for `get_lineups`. | Never fast-path state-changing tools, or accept structured-only results as answers. |
| AG-02 ✔ | Critical | Repro | agent.py:542-600 | Tool pruning scores only names in `_TOOL_KEYWORDS`. 14 real tools are absent (`get_standings`, `get_top_scorers`, `get_schedule`, `get_squad`, `get_team_stats`, `get_player_stats`, `get_player_context`, `get_event_detail`, `sync_broadcast_delay`, `set_favourites`, `get_my_matches`, `search`, `get_competitions`, `get_team_form`) and 14 invented names take the slots. Raw substring matching: "on" matches nearly everything, "ref" matches "prefer". | Build keywords from the live registry (or drop pruning); match on word boundaries. |
| AG-03 ✔ | High | Code | agent.py:527, 554, 635, 645, 675, 754, 997 | `get_table` is not a tool (it is `get_standings`). StandingsAgent never runs; full update skips standings. With AG-02, standings questions cannot reach `get_standings` by any path. `_FAST_INTENTS` (:500-540) is dead code. | Rename; delete dead table. |
| AG-04 | High | Repro | agent.py:640-653 | Fast path injects `competition`, `team`, `fixture_id`, `sport` into every call regardless of schema; all schemas have `additionalProperties: false`, so many calls fail ("team is not a known argument") and the failure is swallowed at DEBUG (:700). Also sets team to "Premier League" via the regex at :636. | Filter args to the tool's `inputSchema.properties`. |
| AG-05 | High | Repro | agent.py:515, 670 | `get_fixtures {"when": "next"}` is always invalid (enum is yesterday/today/tomorrow); "next game" never works on the fast path. | Route to `get_schedule {"which": "next"}`. |
| AG-06 | High | Repro | agent.py:922, 942, 994-1006 | Validation errors are read aloud: an `InvalidParams` record has `declined: False` and non-empty `spoken`, so the bedrock-fast bypass speaks "arguments.when must be one of yesterday, today, tomorrow". | Carry `is_error`; exclude errors from bypass and joins. |
| AG-07 | High | Repro | agent.py:479-497, 873 | Conversational bypass hijacks real questions: "Hey, what's the score?" → greeting; "Thanks, who scored?" → "You're welcome!"; "what sports are on today" → canned list. | Anchor patterns to the whole utterance. |
| AG-08 | High | Repro | agent.py:710-722 | "How many" shortcut answers any "how many" with the fixture total ("how many yellow cards" → "There are 5 scheduled matches… today"), always saying "today". | Fire only after `get_fixtures` with no other noun. |
| AG-09 | Medium | Repro | agent.py:661-689 | Regex fast-path false positives: "golden boot last season" → match state; "manager of Celtic" / "Celtic squad" → lineups; "what happened to Saka" → `what_did_i_miss` (burns the gap, see AG-01); "who is out of contract" → injuries; multiple matches get concatenated. | Tighten patterns; defer to the model when >1 SubAgent matches. |
| AG-10 | Medium | Repro | agent.py:746-748 | Full-update team fallback uses `re.search` (first capitalised word, "Tell", is excluded) so it never finds the team; "tell me everything about Arsenal" produces no tasks. | `re.findall`, skip stop-words. |
| AG-11 | Medium | Repro | agent.py:311-313, 830 | Combined multi-tool answer is truncated to 3 sentences, so a 7-tool full update mostly speaks the first tool. | Summarise per tool or don't truncate. |
| AG-12 | Medium | Repro | agent.py:969-1016, 19 | Hitting the 8-tool cap or `MAX_TURNS=4` raises "exceeded" and discards executed work instead of making a final answer call. | Final Converse call without `toolConfig`. |
| AG-13 | Medium | Repro | agent.py:22, 909, 919-966 | `MAX_TOKENS=90` and `stopReason` never checked: answers cut mid-sentence are spoken; a truncated `<thinking>` preamble becomes "no answer text" (503); truncated `toolUse` unhandled. | Check `stopReason`; raise to ~300; trim spoken text. |
| AG-14 | Medium | Repro | agent.py:1069-1079 | `_execute_tool` catches only `InvalidParams`/`ToolError`; transport errors (`RuntimeError`, `URLError`, timeouts) escape `run()` → 500 instead of 503. | Catch `Exception`, return error toolResult. |
| AG-15 | Medium | Code | mcp_client.py:47-51 | `_rpc` holds the lock for the whole HTTP round trip (60 s timeout); one shared client for all listeners serialises every tool call and defeats the parallel paths. | Lock only id increment / session read. |
| AG-16 | Medium | Code | agent.py:57-80, 215-230 | Stored topic and history never expire (the `at` field is ignored): next day, yesterday's `fixture_id`/team is injected into fast-path args and the prompt. | Persist timestamp; apply TTLs on load. |
| AG-17 | Low | Plausible | mcp_client.py:53-60, 68-69, 94-106 | Session init races outside the lock; no `Mcp-Session-Id` → re-init every call; `call()` crashes on 202/empty body; SSE response would fail `json.loads`. | Double-checked init under lock; guard `None`. |
| AG-18 | Low | Plausible | agent.py:243-255 | `Focus._by` evicts oldest-inserted, not least-recently-used; `_pending` unbounded. | `OrderedDict.move_to_end`; cap. |
| AG-19 | Low | Plausible | agent.py:96-112, 245-251, 789 | Read-modify-write on the listener record can overwrite concurrent tool writes (e.g. `mark_told` in the parallel fan-out). | Field-level updates or per-listener lock. |
| AG-20 | Low | Plausible | agent.py:459-475, 588-599 | Raw `inputSchema` passed to Bedrock (keywords Nova may reject); candidate order from a `set` is nondeterministic, defeating prompt caching. | Strip unsupported keywords; sort. |
| AG-21 | Low | Repro | agent.py:631-633 | Known-team detection is substring: "Inter" matches "interested". | Word boundaries. |
| AG-22 | Low | Repro | agent.py:411-421 | Fixture-id check is substring: `"fixture_id 1"` matches `"(fixture_id 12)"`. | Regex with `\b`. |
| AG-23 | Low | Repro | agent.py:862-865 | With both `pending` and `interrupted`, `asked` is rebuilt from `question`, dropping pending context. | Wrap `asked`. |
| AG-24 | Low | Repro | simulator/__main__.py:11 | Opens `127.0.0.1:8765` regardless of config, before the server is bound. | Open after `build()`, from config. |

## 3. MCP tools — `sideline/tools/`

| ID | Sev | Status | Location | Bug | Fix |
|---|---|---|---|---|---|
| TL-01 | Critical | Repro | get_event_detail.py:18-42; get_match_report.py:40-69; get_player_context.py:39-41, 104; get_officials.py:26 | These tools read events unfiltered and ignore the delayed minute set by `resolve_fixture`: with a 120 s offset, `get_match_state` says 57' and 1-0, while `get_event_detail` says "Son scored on 58" — a spoiler. | One helper that drops events past the listener's minute; use everywhere. |
| TL-02 | High | Repro | get_lineups.py:20; get_event_detail.py:53; what_did_i_miss.py:94-96 | `last_told_at` is per listener, not per match: looking at another match's line-ups jumps the followed match's marker and loses its events. | Mark only for the followed fixture, or key by fixture. |
| TL-03 ✔ | High | Repro | get_event_detail.py:53 | Replaying one event advances the marker to the current minute, swallowing every untold event in between. | Add only the event id to `told_event_ids`. |
| TL-04 ✔ | High | Repro | get_player_context.py:77, 92 | Player match is raw substring: "Son" → "Maddison". A blind listener cannot catch the swap. | Whole-token match, prefer exact surname, ask on ties. |
| TL-05 | Medium | Repro | get_fixtures (via `__init__.py:297-301`); what_did_i_miss.py:59; sync_broadcast_delay.py:69 | For 10 min after discussing another match, "what did I miss" and sync anchors use that match instead of the followed one. | Use `following` unless a match is named. |
| TL-06 | Medium | Repro | follow_match.py:93-104 | After "stop following", a new follow keeps the old calibrated offset (reset only runs when `following` is still set). | Store calibration's fixture; reset when different. |
| TL-07 | Medium | Repro | sync_broadcast_delay.py:124 | Companion `their_minute` path doesn't add the minute bucket: up to 59 s of spoilers, marked calibrated. | Add bucket margin; blend like anchors. |
| TL-08 | Medium | Plausible | sync_broadcast_delay.py:124; `__init__.py:333` | Delay maths assumes an elapsed football clock; basketball screens show time remaining. | Football-only, or convert per sport. |
| TL-09 | Medium | Repro | set_preferences.py:14-28; follow_match.py:42 | Sport names not normalised: "nfl" (the schema's own example) and "American football" rejected; error reads "american_football" aloud; "Basketball" (capitalised) not recognised. | Shared alias map + `lower()`; spoken names. |
| TL-10 | Medium | Repro | get_standings.py:36-62; get_top_scorers.py:11-26 | Followed match's competition wins over the named team: following Arsenal, "Celtic standings" → "can't see Celtic in the Premier League table". | Fall back to the team's own league. |
| TL-11 | Medium | Code | get_match_report.py:46, 69 | VAR-overturned goals are listed as goals while the header score excludes them. | Skip or append "later disallowed". |
| TL-12 | Medium | Code | get_match_preview.py:92-95; get_lineups.py:16; get_officials.py:18; get_player_context.py:71; get_head_to_head.py:14 | Direct provider calls bypass `feed()`; `NotImplementedError` from a feed without line-ups crashes the whole preview. | Use `feed()` or catch it. |
| TL-13 | Medium | Code | get_top_scorers.py:34; get_standings.py:54-66 | Football wording for all sports: NBA leaders read as "27 goals"; US tables "first with 0 points". | Per-sport wording; W-L. |
| TL-14 | Medium | Code | get_fixtures.py:112 | `finished_only` intro always says "from yesterday" for any non-today date. | Use the `when` / `say_day` text. |
| TL-15 | Medium | Code | get_match_stats.py:10, 31 | Stat keys don't match ESPN (`field_goal_pct` vs `fieldGoalPct`); NFL/MLB/NHL get soccer labels → "no statistics yet". | Align keys; per-sport labels. |
| TL-16 | Medium | Code | get_schedule.py:62 | Says "not in the next six weeks" while the provider scans ±2 days (see ESPN-17) — states a falsehood. | Take window from provider. |
| TL-17 | Low | Repro | set_favourites.py:27-28 | 11th team silently dropped but reply says "I'll remember Arsenal". | Refuse or say full. |
| TL-18 | Low | Repro | get_head_to_head.py:23-25 | "Last 1 meetings"; scheduled games may be read as 0-0 results. | Singular; completed only. |
| TL-19 | Low | Repro | get_injuries.py:11 | Team filter is plain substring, no nickname map: "Spurs" → "No one is reported out" though Romero is listed. | Use `_is_team()` with NICKNAMES. |
| TL-20 | Low | Repro | follow_match.py:75, 127-131 | Says "more than one X match today" for other days; says "tell me when you hear kick-off" at 70'. | Use the match day; suggest a goal/half-time anchor. |
| TL-21 | Low | Plausible | get_player_context.py:114 | Reads "Saka, None." when team is missing. | Omit `None`. |
| TL-22 | Low | Plausible | store.gap_for via what_did_i_miss.py:62 | "Since half time" recap still filters already-told goals out. | Skip told-ids filter when `since_minute` given. |
| TL-23 | Low | Code | registry.py:302 vs get_squad.py:10 | `position` enum is football-only; tool supports guard/center/forward but schema blocks them. | Extend enum. |
| TL-24 | Low | Plausible | get_schedule.py:53 | `say_day(None)` crashes on a fixture without kickoff. | Guard. |

## 4. State, poller, spoiler guard, Bedrock wording — `sideline/state/`, `poller.py`, `sync.py`, `language/`

| ID | Sev | Status | Location | Bug | Fix |
|---|---|---|---|---|---|
| ST-01 ✔ | Critical | Repro | store.py:124-125; tools/`__init__.py`:333-335 | Spoiler guard uses `offset // 60`: every delay under 60 s — all regional priors (35-52 s) and the 45 s default — floors to 0, so nothing is held back. Above 60 s it still releases events early (119 s → ceiling 29). | Round up, or better gate on wall clock: `e["at"] + offset <= now`. |
| ST-02 | High | Repro | store.py:130; what_did_i_miss.py:96; get_lineups.py:20 | `gap_for` skips `minute <= last_told_at`; a goal in the same minute, logged after the listener asked, is lost for good. | Mark at highest told minute (or −1) and dedupe on `told_event_ids`. |
| ST-03 | High | Repro | sync.py:220-223, 249 | Period anchors (half time, second half, full time) measure the feed's frozen minute bucket, not the delay: always ≈28 s regardless of the true delay, and the first anchor replaces the prior. Baseball anchors are innings treated as seconds. | Anchor on the wall-clock time the poller saw the status change; never lower the prior from a period anchor. |
| ST-04 | High | Repro | sync.py:208-217 | Goal anchor uses the last *logged* goal however old: "they've just scored" before the poller logs it measures from the previous goal (repro: 598 s; >900 s → "same match?"). Poll lag also under-estimates by up to 30 s. | Accept only goals logged within ~120 s; add half a poll interval margin. |
| ST-05 ✔ | High | Repro | poller.py:48-51, 120-124 | Only `AttributeError` is caught around `all_followed_fixtures()` and `run()` has no try; one DynamoDB throttle or network error kills the poller thread permanently while the server keeps answering stale data. | `try/except Exception` around each cycle. |
| ST-06 ✔ | High | Repro | poller.py:60-66 | Miss counter never reset on success: 3 non-consecutive transient misses drop a live match for good. A far-off followed match misses 3× after restart and is never polled on match day. | Reset on success; back off instead of giving up. |
| ST-07 | High | Repro | store.py:209-212; dynamo.py:78-89; espn.py:596 | Event dedupe key (minute, kind, player) drops real events: two free throws by one player in a minute (lost points), two stoppage-time goals or cards by one player; feed revisions (assist added, yellow→red) can never land. | Key on the provider's play id; upsert mutable fields. |
| ST-08 | High | Plausible | dynamo.py:104-115 | Eventually consistent reads: chained tools can read the pre-follow profile and write it back (undoing `following`); poller's new-event detection by length misses VAR overturns. | `ConsistentRead=True`; return `created` from the conditional put. |
| ST-09 | Medium | Repro | dynamo.py:103-108 vs store.py:191-195 | MemoryStore returns the live dict, DynamoStore a copy: an unsaved mutation (`tools/__init__.py:311-312`) persists only in memory — tests can't catch missing saves. | Deep-copy in MemoryStore. |
| ST-10 | Medium | Repro | dynamo.py:180-182 vs store.py:210-212 | On duplicate, DynamoDB `append_event` returns the caller's new id (which doesn't exist); memory returns the stored one. | `get_item` and return stored event. |
| ST-11 | Medium | Code | dynamo.py:157-160 | Follower marker has a 48 h TTL refreshed only on save: a long-range follow is silently dropped before kickoff. | TTL = kickoff + 48 h. |
| ST-12 | Medium | Code | dynamo.py:142-146, 200-202 | `INDEX#FOLLOWED` rows never expire: one Query per fixture ever followed, every 30 s, forever. | `expires_at`, or delete when over and unfollowed. |
| ST-13 | Medium | Repro | state/`__init__`.py:18-21; bedrock.py:92-93 | `retries={"max_attempts": 1}` means 2 attempts in botocore legacy mode; a Bedrock timeout costs ~16 s. | `total_max_attempts: 1`. |
| ST-14 | Medium | Code | dynamo.py:100 | DynamoDB resource uses default 60 s connect/read timeouts; a blip stalls a voice request for minutes. | Short timeouts in `Config`. |
| ST-15 | Medium | Repro | templates.py:102; bedrock.py:161; what_did_i_miss.py:96 | Catch-up speaks at most 3 non-score events (template) or 12 events in ≤3 sentences (Bedrock) but marks *all* as told — the rest are never heard. | Mark only what was spoken, or say "and N more". |
| ST-16 | Medium | Repro | bedrock.py:231-244 | Score check treats any `\d+-\d+` as a scoreline ("4-4-2", "60-75" → rejected → `language_unavailable`), accepts reversed scorelines (set comparison), and raises KeyError when `score` is missing. | Check numbers near team names as an ordered pair; `.get`. |
| ST-17 | Low | Repro | bedrock.py:56 vs config.py:33 | Default model differs: config/.env.example document Claude Sonnet 4.5, code falls back to Nova Lite, docstring says Nova Micro. | Single source in `config.VARIABLES`. |
| ST-18 | Low | Plausible | bedrock.py:116-128 | `stopReason` not checked (`maxTokens=160`): truncated catch-ups spoken; translations not score-checked; `audit.record` failure inside the try turns a good answer into an error. | Check stop reason; move audit out. |
| ST-19 | Low | Plausible | store.py:157-173 | `mark_told` is an unlocked read-modify-write (memory and DynamoDB): concurrent calls can lose told ids. | Lock / conditional update. |
| ST-20 | Low | Plausible | dynamo.py:113-145 | No pagination on Query (truncates past 1 MB; long basketball logs). | Loop on `LastEvaluatedKey`. |
| ST-21 | Low | Plausible | poller.py:69-71 | Overlap window `high − 3` misses events the feed adds late for earlier minutes. | Periodic full re-read. |

## 5. ESPN provider and weather — `sideline/providers/`, `sideline/weather.py`

| ID | Sev | Status | Location | Bug | Fix |
|---|---|---|---|---|---|
| ESPN-01 ✔ | Critical | Repro (live 400) | espn.py:337-338 (and 192, 356, 500, 619, 682, 1045, 1083, 1152, 1181) | NFL/college fixtures store `espn_sport="american_football"`, so every summary/detail URL is `/sports/american_football/…` → HTTP 400, returned as empty data. All NFL detail tools silently empty. | One Sideline→ESPN sport map used everywhere. |
| ESPN-02 ✔ | High | Repro | espn.py:255 | `fixtures_on(sport="football")` also fetches NFL and college football ("football" means soccer in Sideline). | Drop `"football"` from the NFL condition. |
| ESPN-03 | High | Repro (live) | espn.py:188, 235-236; tools/`__init__.py`:53-91 | `?dates=` is the US-Eastern day, but the code asks for the UTC day: at 03:35Z, live MLS games are missed, and evening US games fall out of both days. | Query adjacent days and filter by real kickoff UTC. |
| ESPN-04 ✔ | High | Repro (live) | espn.py:530, 539 | Every soccer event has `team=""`: the team is on `keyEvent.team`, not on the participant. Who scored for whom is lost. | `(ke.get("team") or {}).get("displayName")`. |
| ESPN-05 ✔ | High | Repro (live) | espn.py:517-519 | Stoppage time never parsed: ESPN writes `45'+5'`; the regex stops at the apostrophe → minute 45, stoppage 0. Breaks phrasing and collides in dedupe (ST-07). | Strip apostrophes before matching. |
| ESPN-06 | High | Plausible | espn.py:542 | Goals detected by `"Goal" in type.text`; "Penalty - Scored" isn't a goal; shootout kicks not separated. | Use `ke["scoringPlay"]`; skip `ke["shootout"]`. |
| ESPN-07 | High | Repro | espn.py:563-565 | Substitution names truncated at apostrophes/dots ("Kevin O'Toole" → "Toole"; "Aiden O'Neill" → "Aiden O"). | Use participant athlete names. |
| ESPN-08 | High | Repro | espn.py:380-381, 451-452, 578-585 | Basketball minutes assume four 12-min quarters and clamp OT to Q4: OT plays get earlier minutes and the poller's `since` drops them; WNBA/NCAA wrong. | Per-league period length; OT periods; no clamp. |
| ESPN-09 | High | Repro (live NHL) | espn.py:505-507, 590 | NFL, MLB, NHL `events()` always return `[]` (they go through the soccer `keyEvents` parser; those sports have `plays`); basketball event teams always "" (plays carry only a team id). | Per-sport play parsers; map team id → name. |
| ESPN-10 | High | Plausible | espn.py:90-91, 302, 372, 446; poller.py:91 | Live `STATUS_OVERTIME`/`STATUS_SHOOTOUT` mapped to terminal AET/PEN: poller stops, fixture cached forever, score frozen in extra time; `STATUS_FINAL_AET/PEN` fall back to FT. | Use `type.state == "in"` for live. |
| ESPN-11 | High | Code | espn.py:161-182, 279-280, 290; base.py:36 | Outage looks like "no data": `_fetch_json` returns `{}` or stale cache of any age; urllib3 path never checks status, so 400/500 bodies are cached as data; empty results after a failure cached 60 s. `ProviderUnavailable` is never raised, so its handlers in server.py and get_match_preview are dead code. | Check status, don't cache errors, raise `ProviderUnavailable`. |
| ESPN-12 | Medium | Repro | espn.py:196-232 | `_resolve_league` silently falls back and substring-matches: "Scottish Premier League" → EPL; "World Cup", "League One" → EPL; "college basketball" → NBA. Another league's table is stated as fact. | Return None for unknown; specific before generic. |
| ESPN-13 | Medium | Repro (live) | espn.py:771-824 | US-league standings: no `rank` stat → everyone 1st; played=0; "points" is a different stat (−2.0); conferences merged. | Per-sport stat mapping; keep groups. |
| ESPN-14 | Medium | Repro | espn.py:189, 237-241, 296-303 | Live fixture can be ~90 s stale while events are 10 s fresh — store shows a goal while score reads 0-0; terminal fixtures cached forever. | Live TTL ≤ cache seconds; stamp with fetch time. |
| ESPN-15 | Medium | Repro (live) | espn.py:454-458, 476-477 | Full-time via summary path reports minute 0; null venue raises AttributeError. | Default FT to 90; `(… or {})`. |
| ESPN-16 | Medium | Repro | espn.py:1221-1251; base.py:106 | `team_matches` ignores `days_back`/`days_ahead`, scans only ±2 days, unsorted, lists live/postponed as upcoming, substring "man" hits both Manchester clubs. | Use ESPN team schedule; sort. |
| ESPN-17 | Medium | Repro (live) | espn.py:895-900, 1117-1128 | `search(kind="competition")` returns article headlines; search ids are GUIDs, so `squad()` builds a bad roster URL and returns `{"players": []}`. | Filter by type; parse numeric id from `uid`. |
| ESPN-18 | Medium | Repro (live) | espn.py:971-1031 | `player_stats` takes the first player of any sport (MMA, tennis), ignores `team`, sums all competitions (Saka "9 goals" vs 3 in EPL), invents "1 appearance". | Filter; pick league split; None not 1. |
| ESPN-19 | Medium | Plausible | espn.py:284-286, 836, 888; tools/`__init__.py`:70-73 | Shared dicts mutated by worker and poller threads while others iterate → "dictionary changed size during iteration". | Lock, or iterate a `list()` copy. |
| ESPN-20 | Medium | Code | espn.py:145-148, 165, 290 | All caches unbounded (summaries ~400 KB each); memory grows forever. | LRU / size cap. |
| ESPN-21 | Medium | Plausible | espn.py:27, 163, 172-174 | urllib3 default 3 retries × 6 s, then urllib fallback: ~30 s per URL when the network is down — fatal for voice. | `Retry(1)`, total timeout, no second fallback. |
| ESPN-22 | Low | Repro (live) | espn.py:1050-1058 | `form()` reverses an already oldest→newest list. | Drop `reversed()`. |
| ESPN-23 | Low | Repro | espn.py:544 | Assist over-captures ("Lionel Messi following a fast break"). | Use `participants[1]`. |
| ESPN-24 | Low | Repro | espn.py:383-387 | NFL/NHL/MLB minute from time *remaining* (`12:34` in Q2 → minute 12). | Per-sport elapsed. |
| ESPN-25 | Low | Plausible | weather.py:56-73; espn.py:390, 414 | Weather almost never found: ESPN gives no country and city is "Miami, Florida". | Pass country; split city. |
| ESPN-26 | Low | Repro | espn.py:916-917 | Unknown squad position defaults to "attacker" — a made-up fact. | Default None. |
| ESPN-27 | Low | Code | espn.py:484-487 | Dead code after `return` referencing undefined `res`. | Remove. |

## 6. Match finding, name repair, clock and sport profiles — `finder.py`, `resolve.py`, `clock.py`, `sports/`

| ID | Sev | Status | Location | Bug | Fix |
|---|---|---|---|---|---|
| FR-01 ✔ | High | Repro | resolve.py:408 | Any yes-like token anywhere picks option 1: "no, the right one is Rangers", "sure, Rangers", "the second one yeah", "ok what about the Celtic game" all choose Arsenal v Chelsea. Runs before ordinal and name matching. | Whole-phrase affirmation only, after ordinal/name checks. |
| FR-02 | High | Repro | finder.py:153-156 | Opponent scored against both sides including the named team: "Man United v Man City last" picks United v Fulham. | Score opponent only against the other side. |
| FR-03 | High | Repro | finder.py:156 | Character substring gives fit 1.0: "Villa"→Villarreal, "Bayer"→Bayern, "Inter"→Internacional, "United"→any United. | Whole-word token subset. |
| FR-04 ✔ | High | Repro | sports/american_football.py:45-53 | `score_delta` defaults every unhandled kind to 1 point: interceptions, fumbles, timeouts, reviews score; overturned TDs still count 6. | 0 unless a scoring kind and not superseded. |
| FR-05 | High | Repro | finder.py:99 | Live decided by `minute > 0`, not status: start of any game, Q1 tip-off, and *all* baseball (minute always 0) count as upcoming — "first pitch was due 1 hour ago" mid-game. | Live = status not over and not NS/TBD. |
| FR-06 | High | Repro | finder.py:199 | "Last match" while a match is live: live and latest-played tie at 1.0 → fork every time. | Explicit rule; offset index when live. |
| FR-07 | High | Repro | finder.py:202-205 | No time said, daily sports (MLB, NBA, NHL) fork on almost every question; `DECAY_DAYS=7` assumes weekly football. | Strongly prefer a live match; per-sport decay. |
| FR-08 | Medium | Repro | resolve.py:437-440 | `fix_names` runs on `heard`, not `cleaned`, discarding acoustic repairs and resetting `changed`. | Run on `cleaned`; OR the flags. |
| FR-09 | Medium | Repro | resolve.py:348-377 | Ordinary words rewritten as teams: "place"→"Palace", "enter"→"Inter", "chief"→"Chiefs", "Atlanta"→"Atalanta" (breaks every Atlanta question). | Stop-list; add US cities to canon. |
| FR-10 | Medium | Repro | resolve.py:39-47; finder.py:34 | Forks offer up to 4 options but ordinals stop at "third"; "the fourth one", "the last one" fail. | Add fourth and last. |
| FR-11 | Medium | Repro | resolve.py:443-477 | Typo-clarify fires on sports words: "who are the leaders" → "did you mean Los Angeles Lakers?" | Extend `_COMMON_WORDS`. |
| FR-12 | Medium | Repro | clock.py:125-154; finder.py:104-106, 137 | Today's UTC offset applied to dates across a DST change while the zone is named: "8 PM US Eastern" for a 7 PM EST kickoff; day bucketing off near midnight. | `zoneinfo` when the zone name is known. |
| FR-13 | Medium | Repro | sports/hockey.py:25-35 | "second_half" anchor is 40 min (start of P3) but spoken as "start of the second period": spoiler anchor 20 min off. | Fix value or wording. |
| FR-14 | Medium | Repro | sports/baseball.py:12, 22-27, 43-46 | Anchors in innings where seconds are expected; regulation in innings vs clock minutes; "in the 3 inning". | One inning→elapsed mapping; ordinals. |
| FR-15 | Medium | Repro | sports/american_football.py:89-101; hockey.py:72-80 | Unhandled kinds fall through to "Score …" / "Play …": a timeout is read out as a score. | Explicit branches; neutral fallback. |
| FR-16 | Medium | Repro | sports/`__init__`.py:104-105 | Overturn detected by substring: "Goal confirmed - not overturned" overturns the goal; ignores team and already-superseded. | Reject negations; skip superseded. |
| FR-17 | Medium | Repro | sports/`__init__`.py:174-176; finder.py:213-217 | Unknown sport keys ("soccer", "nfl", "ice_hockey") silently become football — scored with goals, and penalise the correct candidate. | Alias map (shared with TL-09). |
| FR-18 | Low | Repro | finder.py:231 | `say_option` indexes `score["home"]` without a None guard → TypeError on the fork message. | Reuse `say_fixture` guard. |
| FR-19 | Low | Repro | finder.py:68-82 | `_near_year` moves a date 188 days ago into next year: "what happened on 10 April" finds nothing. | Prefer past when asking about played matches. |
| FR-20 | Low | Repro | resolve.py:112-120 | Letters NFKD can't fold are dropped and split words: "Wisła"→["wis","a"], "Kasımpaşa", "Þór", "Fußball". | Pre-fold map (ł ı đ þ ð ß œ). |
| FR-21 | Low | Repro | clock.py:173-177, 198 | "Kick-off… in 0 minutes" when 30-59 s away. | "less than a minute". |
| FR-22 | Low | Repro | clock.py:220-222 | `say_fixture` always says "live, N minutes in" (wrong for baseball, hockey, basketball). | Delegate to the sport profile. |
| FR-23 | Low | Repro | resolve.py:42 | "to"/"too" count as ordinal 2: a clipped "to" selects the second option. | Only inside "number two" phrases. |
| FR-24 | Low | Plausible | finder.py:187-188 | Sorted by raw kickoff string; mixed offsets sort wrongly. | Sort by parsed kickoff. |
| FR-25 | Low | Plausible | finder.py:251 | `time.time()` where the rest uses `clock.now()`. | Use `clock.now()`. |

## 7. Voice and simulator UI — `simulator/voice.py`, `simulator/index.html`

| ID | Sev | Status | Location | Bug | Fix |
|---|---|---|---|---|---|
| VO-01 ✔ | Critical | Repro (node) | index.html:1472-1482 | TTS retry deadlocks: the retry passes `again=0`, `!0` is true, so it returns its own pending promise. One 503 freezes the app (`speaking` stuck true, mic never re-armed); the hung promise is cached, so the intro or error line hangs forever after. | Separate bypass flag; drop cache entry on rejection. |
| VO-02 | High | Repro (node) | index.html:1229 | Spoken text sent in the `X-Interrupted` header: any `’ — “` (the intro has one) makes `fetch` throw, which is treated as server STT failure → permanent switch to browser recognition (audio to Google). | Percent-encode or send in body. |
| VO-03 ✔ | High | Code | index.html:368, 385-386, 406, 1485 | Screen-reader region is `aria-live="off"` (overrides `role="status"`); everything else is `aria-hidden`; status messages go to the hidden element. A blind user gets no text feedback at all. | `aria-live="polite"`; route status to `#sr`. |
| VO-04 | High | Code | index.html:1241-1255 | Any single STT error (one throttle, a blip, a 413) disables server recognition for the session; with no browser SR, the session dies. | Per-clip fallback; disable after N failures. |
| VO-05 | High | Code | voice.py:108-113, 139, 188, 224 | Provider order contradicts "audio never leaves AWS": Groq first for STT when its key is set; Cartesia/ElevenLabs before Polly; live caption defaults to the browser's cloud recogniser. | AWS-only by default; others only when named. |
| VO-06 | High | Repro | voice.py:659, 705-722 | `echoes_hint` drops real answers: "Real Madrid", "Manchester United" treated as the model echoing its prompt. Voxtral never receives the hint, so the premise doesn't hold. | Only for hinted providers; stricter rule. |
| VO-07 | High | Code | index.html:1234-1235, 1793 | Answer arriving while paused is discarded although the server already ran the agent — a catch-up is silently consumed. | Call `renderAgentAnswer` anyway. |
| VO-08 | Medium | Repro | voice.py:625-629, 655; index.html:1265 | Hallucination filter drops real words for every provider: "Goodbye", "Thank you", "You". | Whisper only, short clips only. |
| VO-09 | Medium | Code | voice.py:826-909 | Nova Sonic stream never closed; a fresh event loop and CRT client per clip is closed with live resources — leaks per clip. | `async with stream`; reuse loop/client. |
| VO-10 | Medium | Code | voice.py:144, 789-790, 917-919, 987-989 | `_DISABLED` is global and permanent: one bad clip's ValidationException disables Sonic for the run; rotated creds never recover. | TTL; don't count validation errors. |
| VO-11 | Medium | Repro | voice.py:377-385 | Speech-marks failure fails the whole TTS answer after wasted calls, with a misleading log. | Catch marks separately; use fitted marks. |
| VO-12 | Medium | Plausible | voice.py:17, 121 | Model id is Voxtral **Mini** 3B; docstring and docs quote Voxtral Small accuracy. | Pin the measured model or fix claims. |
| VO-13 | Medium | Code | index.html:434-443, 1862-1869 | 12 s mic-permission timeout: slow consent strands the user (button disabled, late stream never stopped, mic light stays on). | No race; stop late stream; re-enable. |
| VO-14 | Medium | Code | index.html:960-987 | Pause doesn't release the microphone (tracks never stopped). | Stop tracks; re-acquire on resume. |
| VO-15 | Medium | Plausible | index.html:1484-1496, 1802 | `say()` doesn't stop listening/speech: assistant voice captured as a new question; cancelled utterance's `onerror` ends the new one; aborted request says "can't get an answer". | Stop first; ignore `AbortError`. |
| VO-16 | Medium | Plausible | index.html:1553-1555 | `play()` rejection (Safari autoplay) silently skips speech. | Fall back to browser voice. |
| VO-17 | Medium | Code | index.html:1035, 1069-1075 | Stop words ("okay", "wait"…) anywhere stop playback without echo check — Sideline cuts itself off on "Okay, Arsenal lead…". | Leading/whole utterance only; keep echo check. |
| VO-18 | Medium | Code | index.html:912, 1115-1122, 1487 | Level-based barge-in can never fire (`capText` always empty while speaking); in Firefox, talking over never works. | Allow VAD barge-in without SR. |
| VO-19 | Medium | Plausible | index.html:1224-1230 | No client timeout on `/voice/stt` (server worst case 50 s+). | ~15 s abort; spoken "still working". |
| VO-20 | Low | Code | index.html:1874-1880 | `connect()` races the intro; failure text interleaves with intro words. | Await connect first. |
| VO-21 | Low | Plausible | index.html:1005, 1885-1890 | "Go live" before capabilities load picks browser voice, then flips mid-session. | Disable until loaded. |
| VO-22 | Low | Plausible | index.html:1910-1922 | Passive ticker calls `/agent/chat` every 45 s (LLM cost, may move "told" state). | Read-only score endpoint. |
| VO-23 | Low | Code | index.html:321, 989-995 | Subtitles toggle has no visible focus; Space on it pauses instead of toggling. | Focus style; skip shortcut on buttons. |
| VO-24 | Low | Plausible | index.html:844-856, 1533 | Audio nodes created per capture/answer, never disconnected. | Reuse nodes. |
| VO-25 | Low | Plausible | index.html (no `ctx.resume()`) | Suspended `AudioContext` (iOS call, device change) → silent mic and playback. | Resume on state change. |
| VO-26 | Low | Repro | server.py:368-394; voice.py:548 | Uncaught `hinter()` error drops the connection; `{"text":123}` to TTS raises AttributeError. | try/except → 400/500. |
| VO-27 | Low | Code | voice.py:559-562, 749, 785, 906, 939, 953-978; index.html:1471 | Duplicate STT audit; "0.4 s" comments vs 0.2 s check; `SIDELINE_TTS=browser` still calls Polly; streaming errors silently retried (double cost); `ttsCache` unbounded. | Individually small. |

## 8. Config, scripts, tooling

| ID | Sev | Status | Location | Bug | Fix |
|---|---|---|---|---|---|
| CFG-01 | Low | Repro | app.py:18, 135; config.py:85-91; state/`__init__`.py:49 | `ConfigError` never raised; bad `SIDELINE_PORT`/`POLL_SECONDS`/`STATE` give raw tracebacks at import. | Validate in config. |
| CFG-02 | Low | Repro | audit.py:125 | One oddly named file in `logs/` stops the server starting. | try/except per file. |
| CFG-03 | Low | Repro | envfile.py:34-37 | `KEY="abc" # note` keeps the quotes. | Strip comment first. |
| CFG-04 | Low | Plausible | Makefile:19-20 | "Offline" tests blank only AWS secrets; Groq/Cartesia/ElevenLabs keys and other .env settings leak into tests. | Blank all secrets or skip `.env`. |
| CFG-05 | Low | Repro (<3.11) | scripts/next_matches.py:39 | `fromisoformat` on `…Z` fails on Python 3.8-3.10 (CI runs 3.8). | Use `clock` parser. |
| CFG-06 | Low | Repro | scripts/verify_data.py:33, 41, 72-74 | String ids compared to `int(arg)`; uncaught `ProviderUnavailable`; dead branch. | Compare strings; catch. |
| CFG-07 | Low | Code | Makefile:11, 29 | `make sim` / `make logs` hardcode port and log folder. | Read from env. |
| CFG-08 | Low | Plausible | run.sh:31-44 | Dangling `.venv/bin/python` (as in this checkout) is not recovered cleanly. | `python -m venv --clear`. |
| CFG-09 | Low | Plausible | tls.py:19-21 | Empty CA directory counts as "has CAs", skipping the certifi fallback. | Check certs actually load. |
| CFG-10 | Low | Code | tests/support.py:8, tests/README.md:26 and several docs | Stale Sportmonks references after the ESPN switch (code no longer reads `SPORTMONKS_TOKEN`). | Remove. |

---

## Counts

| Area | Critical | High | Medium | Low | Total |
|---|---|---|---|---|---|
| MCP server core | 0 | 2 | 12 | 8 | 22 |
| Simulator agent | 2 | 6 | 8 | 8 | 24 |
| Tools | 1 | 3 | 12 | 8 | 24 |
| State / poller / sync / Bedrock | 1 | 7 | 8 | 5 | 21 |
| ESPN provider | 1 | 10 | 10 | 6 | 27 |
| Finder / resolve / sports | 0 | 7 | 10 | 8 | 25 |
| Voice / UI | 1 | 6 | 12 | 8 | 27 |
| Config / scripts | 0 | 0 | 0 | 10 | 10 |
| **Total** | **6** | **41** | **72** | **61** | **180** |

## Patterns worth fixing once, not 180 times

1. **Substring matching for names** (FR-03, TL-04, TL-19, AG-02, AG-21, AG-22, ESPN-16, FR-16) — one shared whole-token matcher.
2. **Sport-name aliases** (FR-17, TL-09, ESPN-01, ESPN-02) — one alias map used by tools, profiles and provider.
3. **Football clock assumed everywhere** (FR-05, FR-22, ESPN-08, ESPN-24, TL-08, TL-13, TL-15, ST-03) — one per-sport "elapsed / phase / phrase" contract in `SportProfile`.
4. **"Told" marker as a single minute per listener** (AG-01, TL-02, TL-03, ST-02, ST-15) — track told event ids per fixture; drop the minute shortcut.
5. **Spoiler guard in minutes** (ST-01, TL-01, TL-07, ST-03, ST-04) — gate on wall-clock `at + offset ≤ now`, applied in one helper every tool calls.
6. **Errors swallowed into "no data"** (ESPN-11, AG-04, AG-14, ST-05) — raise, log, and say "the feed is down".
7. **Early-reject HTTP paths** (MCP-01, MCP-02, MCP-04, MCP-06) — one request-parsing guard.
