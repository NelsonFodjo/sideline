# Which match do you mean?

A listener never says a fixture id. They say "the Celtic game", "the Rangers one", "their last match", "what happened on
the 11th", or nothing at all ("who scored?"), and expect Sideline to know. Most tools were once tied to a single match,
the one being followed, or one within a day of today. That is the wrong shape for a friend who knows football: you can ask
about a game from last month, about a team with no game on, or about a player, and a good friend answers, or asks "which
one?". This page is how that works. The code is [`sideline/finder.py`](../sideline/finder.py), and it is pinned by
[`tests/test_finder.py`](../tests/test_finder.py).

## What changed for the listener

| You ask | What happens |
|---|---|
| "Who are the members of the Celtic squad?" | No match is needed. Squad by position, manager and captain; "list their midfielders" gives the names. |
| "When do Celtic play next?" / "What were Celtic's last results?" | The team's own schedule is read as far ahead and back as the feed allows (on ESPN, 30 days each way), not only yesterday to tomorrow. |
| "How are Celtic doing this season?" | The season so far: games, results, goals, clean sheets, possession. |
| "What happened in the last Celtic match?" | The result and the goals first, then "there were also 4 cards and 10 substitutions: ask for any of them". Any match that has been played, logged or not. |
| "Who came on?" straight after | The same match: a follow-up that names no match means the one you were just asking about (ten minutes). |
| "What happened against Cove Town?" (two matches fit) | A **fork**: "I can see more than one match. Which one: 1, Harbour 1, Cove 0, on 10 October, or 2, Cove 2, Harbour 2, on 9 October?" You pick ("the second one", "the cup one") and the question you asked is answered about that match. |
| "Who scored?" with nothing followed or discussed | It asks: "I'm not following a match yet. Tell me which game to follow, or name a team." A match is **never picked for you**. |

## The algorithm

It has four steps, in this order.

1. **Reference.** What was actually given: a fixture id, a team, an opponent, a time (`last`, `next`, `yesterday`, `today`,
   `tomorrow`, or a date), and what the question is *about*: a match that was played ("who scored") or one still to come
   ("who's playing"). Each tool says which it is about; the finder uses it to break ties.
2. **Candidates.** Every match that could be meant, from the cheapest source that can answer: the team's matches from its own
   schedule (on ESPN 30 days back and 30 ahead, from two requests, played and `?fixture=true`, each kept 60 s; the
   provider interface defaults to 90 back and 45 ahead for a feed that can see further). When an opponent is named, the
   opponent's schedule is read too, so "Panthers" finds the game whether it is Florida's in hockey or Carolina's in
   football. Else yesterday, today and tomorrow on a feed that cannot list a team's matches, else what is on today.
3. **Score.** Each candidate gets a number from what was said.
   - What cannot be meant is removed first: a match called off, an opponent that does not fit (a near-match counts by
     spelling and sound, a clear miss rules the match out), the wrong day or date.
   - Then the survivors are ranked. For `last`, the played matches latest first: the latest scores 1, the next one half,
     then a third, and so on. This ranking is done **after** the opponent filter: an early version ranked first, so "last
     against Cove Town" counted Reef United games as more recent, and was caught by a test. For `next`, nearest upcoming
     first. A day or a date is a hit or a miss. With no time said, a match in play scores highest and the rest fade with
     distance from now (`exp(-days / 7)`, never below 0.1: a match three weeks ago is still the answer when it is the only one that fits the opponent named).
     Basketball, hockey and baseball teams play every day or two, so their matches fade over 1.5 days instead
     (`DAILY_DECAY_DAYS`): the nearest game is plainly the one meant.
   - An opponent named must fit one side by at least 0.6, or the match is ruled out.
   - For `last`, when a match is in play, each step down the played list costs a little more (×1.2), so the live one stays ahead.
   - A question about a match still to come ("their injuries", "who is on") with no time said takes the next match: any
     clearly later one (half a day or more after it) falls away with the square of its place in the list.
   - A day or date with **no team named** looks at that day's matches however far from today (a bare "the 5th of September" or "the match on the 20th"); several that day are a fork.
   - A match of the wrong kind for the question (a future match when asked "what happened") is multiplied by 0.35.
   - The match being followed gets a lift (×1.25). The match they were **just asking about** (the last ten minutes) gets a
     bigger one (×2) when no day or date was said, so "what's the score?" after a talk about Hearts against Dundee is that
     match, not a fork of every Hearts match. A day or date they say always wins over it. Following a match makes it the one
     they mean next.
   - A preferred sport (named in the question, or set with `set_preferences`) lifts that sport's matches (×1.35) and
     lowers the rest (×0.65).
4. **Decide.** A clear winner (the runner-up is under 60% of it) is used. Two or more plausible matches (at least half the
   best) are a **fork**: a numbered list of up to four, each with its score and day, read out for the listener to pick from.
   The list is remembered as an offer, so "the second one" or a mispronounced name snaps to an option
   ([SPEECH.md](SPEECH.md), "Understanding what you meant"), and the **question that was asked is remembered with it**, so
   the pick answers it rather than starting a new conversation. Nothing plausible is an honest "I can't find it", with what
   the feed does have ("I do see: Harbour 1, Cove 0, on 10 October").

Most thresholds are named constants at the top of the file (`PLAUSIBLE`, `CLEAR_WIN`, `FOLLOWED_LIFT`, `DISCUSSED_LIFT`,
`DECAY_DAYS`, `DAILY_DECAY_DAYS`, `FLOOR`, `MISMATCH`). A few are still inline literals in `score_all` and `decide` (the
0.6 opponent fit, the ×1.35 / ×0.65 sport factor, the ×1.2 live step, the half-day gap, the 0.02 floor for "nothing
plausible"); naming them is next. `score_all` is a pure function that the tests drive with fixed dates.

## Where the events come from

Matches that were not followed have nothing in the log of what this listener has been told. `events_for` reads the feed's
events once and keeps them, so any match that has been played can be asked about: the result, goals with scorers and
assists, cards, substitutions and VAR, plus line-ups, statistics and the referee through the tools that already read the
feed by fixture id. `get_match_report` reads them out in parts that suit the ear: the result and the goals first, the rest
by name, because fifteen substitutions in one breath are not usable. Its answer is returned as written (`verbatim`), because
a model asked to shorten it drops the goals.

## What the spoiler guard does here

The broadcast delay applies to **one** thing: the match being followed, while it is in play. A match that has been played,
or one the listener is not watching, has no delay to hold back.

## State that has gone stale

A followed match that the feed has never heard of (an id left from an earlier feed, say) used to make every match question
fail with "I can't find that match any more", for ever. It is now forgotten the first time it is seen, and the listener is
told what is true: "I'm not following a match right now." The poller likewise backs off a fixture the feed does
not know: after three misses in a row it waits 300 s and tries again (not never, because a blip must not lose a live
match for good). ESPN publishes no limit, but every poll is still a request, so an unknown id is not asked about every
cycle. This was found because the app's own
DynamoDB table had been written to by test runs; see FL-17 in [FRICTION_LOG.md](FRICTION_LOG.md). A server built with a test
provider now uses memory state only, whatever `SIDELINE_STATE` says, so that cannot happen again.

## Tried and rejected: choosing tools before the model

With 30 tools a small model routes worse, and every tool costs about 200 tokens in every request. So we tried retrieval:
show Nova only the tools that could plausibly answer. Measured on 47 questions **written to avoid the words in the tool
descriptions** ("gaffer", "armband", "anyone hurt", "who's blowing the whistle"):

| Method | Right tool in the shortlist (K=8) |
|---|---|
| IDF-weighted phrase and word matching over each tool's own "Say:" phrases | 38 of 47 |
| Bedrock Titan Text Embeddings v2, each tool as its phrases | 42 of 47, about 0.5 s a question warm |
| Both combined | 44 of 47 |

On the phrasings the descriptions themselves quote, matching reaches 71 of 71, which is circular and says nothing. As a
filter that hides the right tool one time in ten, it makes routing worse, and the embedding call adds latency. So the
**embedding filter was not shipped**. What the simulator's agent does use is the cheap half: a shortlist by keywords and by
the example phrases in each tool's own description (`simulator/agent.py`, pinned by `tests/test_tool_shortlist.py`, which
checks every tool is reachable from the way a listener asks). Beyond that, routing is held by short descriptions that
each name their neighbour, a system prompt, and `make route-check`. A real Alexa+ host sees the full catalog from
`tools/list`, so the descriptions are what carry it there.

## When the team is real but not covered

A name the feed does not know may be a real team outside what it covers, and "I can't find a team called X" is then
misleading. So the answer is built to help the listener steer. A name that sounds like a team in today's fixtures gets
"Did you mean ...?". A feed that covers six leagues or fewer has them named ("I can't find X in the leagues I cover: ...").
ESPN covers far more (18 soccer leagues, plus the NBA, NFL, MLB, NHL and others), and a list that long read aloud helps
nobody, so the answer is "I can't find X. Try the full name, or tell me which league they play in."

The conversation's topic (the match, team and player just discussed) is given to the model only for questions that leave out who
or what they are about ("and them?", "who came on"). A general question ("the matches of yesterday") must not inherit a team:
an earlier version of that instruction did, and answered an Arsenal question to someone asking what was on yesterday.

## Limits

- Team and player names are matched by the feed's own search, then by spelling and sound. An unusual spelling can miss.
- "Last month" and "in September" are not understood as ranges: the model must turn them into a date, and a date is one day.
- ESPN's team schedules are read 30 days each way; an older match is not found by team. The window is a parameter of
  `team_matches`, so widening it is a one-line change once the feed's reach is measured.
- A fork lists up to four options. More than that is a signal to ask the listener to narrow it, which it does not yet do.
