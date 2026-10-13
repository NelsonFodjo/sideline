# Sports

Sideline is built for any live match or game. Football is the sport with a live
feed; basketball is here to prove the seam is real.

## What is sport-independent

The product itself: the event log, `last_told_at` and `told_event_ids`,
the spoiler guard, the grounding rule, the tools and their routing
descriptions. None of it names a sport.

## What is the sport's call: `SportProfile`

Everything that varies lives in one class per sport
([sideline/sports/](../sideline/sports/)). A fixture says which sport it is
with a `sport` key; **no key means football**, so every older feed,
recording and test keeps working.

| The profile decides | Football | Basketball |
|---|---|---|
| Which event kinds change the score, and by how much | `goal` (1) | `basket` (1, 2 or 3 via `points`) |
| What can overturn a score | `var` | `review` |
| What is a headline after a long absence | goals, red cards | threes, ejections |
| How long an absence is "long" | 15 min | 10 min |
| How time is said | "on 34", "just before half time" | "with 5 minutes left in the second quarter" |
| Spoken anchors for the spoiler guard | kick-off, half time (45:00), the restart, final whistle, a goal | tip-off, half time (24:00), the restart, final buzzer, a basket |
| How "he" is resolved from recent play | booked, scored, came on, VAR | ejected, fouled, scored, came on, reviewed |
| What the officials tool counts | yellows and reds | fouls and technicals |
| Line-ups | formation, keeper first | starting five |

The tool names and the `heard` anchor names (`kickoff`, `half_time`,
`second_half`, `full_time`, `goal`) are the same for every sport, so Alexa+
routing does not change when a sport is added. `goal` in an anchor or in
`get_event_detail`'s `kind: "score"` means "whatever scores in this sport".

Match time is still an integer count of **elapsed** minutes for every
sport: the store, the gap logic and the broadcast offset depend on it. A
sport that does not run on a clock maps its own progress onto elapsed
minutes in its provider and says it its own way in `when()`.

## Adding a sport

1. Subclass `SportProfile` in `sideline/sports/<sport>.py`, set the class
   attributes (`score_kinds`, `review_kinds`, `period_anchors`,
   `recency`, ...), implement `when`, `say_event`, `say_match_state`,
   `say_lineups`, `say_officials`, and call `register()`.
2. Import it at the bottom of `sideline/sports/__init__.py`.
3. Provide data: a provider that emits events of your kinds and a fixture
   with `"sport": "<key>"`, or, for a test, a small invented fixture like
   `tests/fixtures/basketball-harbour-reef.json`.
4. Add a suite modelled on `tests/test_sports.py`.

## What is and is not established

| Claim | Status |
|---|---|
| Football behaviour is unchanged by the profile refactor | **Verified**: every pre-existing suite passes unmodified |
| The store, poller, tools, spoiler guard and prompts run on a second sport | **Verified** by `tests/test_sports.py`, and over HTTP with both sports on one server |
| The basketball data is real | **No.** `tests/fixtures/basketball-harbour-reef.json` is **invented**: made-up teams and players, abridged events, a score that is only what those events add up to. It exists to exercise the seam |
| There is a live basketball (or any non-football) data provider | **No.** Only football has a real provider (Sportmonks, whose free plan also lists cricket; none is built) |
| Time-free or period-based sports (tennis, cricket) fit | **Not tried.** Elapsed minutes may be a poor fit; this is the next thing to test |
| A non-football fan would find the phrasing natural | **Not tested** with anyone |
