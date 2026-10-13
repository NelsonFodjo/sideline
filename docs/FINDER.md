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
| "When do Celtic play next?" / "What were Celtic's last results?" | The feed is read as far ahead and back as the plan allows (six weeks ahead, three months back on the free plan), not only yesterday to tomorrow. |
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
2. **Candidates.** Every match that could be meant, from the cheapest source that can answer: the team's matches over the
   last 90 days and next 45 (one request, kept ten minutes), else yesterday, today and tomorrow on a feed that cannot look
   further, else what is on today.
3. **Score.** Each candidate gets a number from what was said.
   - What cannot be meant is removed first: a match called off, an opponent that does not fit (a near-match counts by
     spelling and sound, a clear miss rules the match out), the wrong day or date.
   - Then the survivors are ranked. For `last`, the played matches latest first: the latest scores 1, the next one half,
     then a third, and so on. This ranking is done **after** the opponent filter: an early version ranked first, so "last
     against Cove Town" counted Reef United games as more recent, and was caught by a test. For `next`, nearest upcoming
     first. A day or a date is a hit or a miss. With no time said, a match in play scores highest and the rest fade with
     distance from now (`exp(-days / 7)`, never below 0.1: a match three weeks ago is still the answer when it is the only one that fits the opponent named).
   - A match of the wrong kind for the question (a future match when asked "what happened") is multiplied by 0.35.
   - The match being followed gets a lift (×1.25). The match they were **just asking about** (the last ten minutes) gets a
     bigger one (×2) when no day or date was said, so "what's the score?" after a talk about Hearts against Dundee is that
     match, not a fork of every Hearts match. A day or date they say always wins over it. Following a match makes it the one
     they mean next.
4. **Decide.** A clear winner (the runner-up is under 60% of it) is used. Two or more plausible matches (at least half the
   best) are a **fork**: a numbered list of up to four, each with its score and day, read out for the listener to pick from.
   The list is remembered as an offer, so "the second one" or a mispronounced name snaps to an option
   ([SPEECH.md](SPEECH.md), "Understanding what you meant"), and the **question that was asked is remembered with it**, so
   the pick answers it rather than starting a new conversation. Nothing plausible is an honest "I can't find it", with what
   the feed does have ("I do see: Harbour 1, Cove 0, on 10 October").

Every threshold is a named constant at the top of the file, and `score_all` is a pure function that the tests drive with
fixed dates.

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
told what is true: "I'm not following a match right now." The poller likewise stops asking the feed about a fixture it does
not know after three misses, because each poll is a call against the hourly limit. This was found because the app's own
DynamoDB table had been written to by test runs; see FL-17 in [FRICTION_LOG.md](FRICTION_LOG.md). A server built with a test
provider now uses memory state only, whatever `SIDELINE_STATE` says, so that cannot happen again.

## Tried and rejected: choosing tools before the model

With 27 tools a small model routes worse, and every tool costs about 200 tokens in every request. So we tried retrieval:
show Nova only the tools that could plausibly answer. Measured on 47 questions **written to avoid the words in the tool
descriptions** ("gaffer", "armband", "anyone hurt", "who's blowing the whistle"):

| Method | Right tool in the shortlist (K=8) |
|---|---|
| IDF-weighted phrase and word matching over each tool's own "Say:" phrases | 38 of 47 |
| Bedrock Titan Text Embeddings v2, each tool as its phrases | 42 of 47, about 0.5 s a question warm |
| Both combined | 44 of 47 |

On the phrasings the descriptions themselves quote, matching reaches 71 of 71, which is circular and says nothing. As a
filter that hides the right tool one time in ten, it makes routing worse, and the embedding call adds latency. So it was
**not shipped**, and nothing of it is in the code: the model sees every tool and the routing is held by short descriptions
that each name their neighbour, a system prompt, and `make route-check`.

## When the team is real but not covered

A name the feed does not know is often a real team outside the leagues the plan covers: Arsenal, on a plan of the Danish and
Scottish leagues. "I can't find a team called Arsenal" is then misleading. The answer names what is covered ("I can't find
Arsenal in the leagues I cover: Superliga (Denmark) and Premiership (Scotland). Which team do you mean?"), read from the feed's
own list of competitions, and asks, so the listener can steer.

The conversation's topic (the match, team and player just discussed) is given to the model only for questions that leave out who
or what they are about ("and them?", "who came on"). A general question ("the matches of yesterday") must not inherit a team:
an earlier version of that instruction did, and answered an Arsenal question to someone asking what was on yesterday.

## Limits

- Team and player names are matched by the feed's own search, then by spelling and sound. An unusual spelling can miss.
- "Last month" and "in September" are not understood as ranges: the model must turn them into a date, and a date is one day.
- The free plan's reach (about three months back) is the plan's, not ours; an older match is not found.
- A fork lists up to four options. More than that is a signal to ask the listener to narrow it, which it does not yet do.
