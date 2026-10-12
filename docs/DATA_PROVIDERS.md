# Match data

## Stage one of the build, before any server code

The whole product rests on getting live structured match data. We
verified that before writing anything, because a project that discovers
this on day nine is dead.

## What we found

| Option | Live? | Events? | Verdict |
|---|---|---|---|
| Free tier A | Delayed | Limited | Useless. The listener hears the crowd before we know anything. |
| Free tier B | Live | Yes | ~100 calls/day. A 90-minute match polled every 15 s is ~360. |
| Paid tier | ~15 s refresh | Goals, cards, subs, VAR, line-ups, officials | What we use. |

**15 seconds is fine, and possibly better than fine.** The listener asks
*after* hearing the crowd react. Broadcast itself runs several seconds
behind. By the time the question arrives, our data has landed.

Recorded as FL-07, because the absence of a usable free tier shapes what
gets built in hackathons and organisers rarely hear about it.

## The replay harness

`providers/replay.py` plays a recorded match back at real speed through
the identical code path the live provider uses.

**It is not a mock.** Same interface, same normalising, same event
shapes, same dedupe. The only thing that differs is where the bytes come
from.

Two reasons it exists, both practical:

1. **You cannot develop a live-football product on a Tuesday night.**
   Without it, every change waits for a fixture.
2. **The demo has to be filmable.** A live match that turns out nil-nil
   with no cards is an unusable three minutes.

```bash
SIDELINE_REPLAY_SPEED=20 python3 -m sideline    # a match in 4.5 minutes
SIDELINE_REPLAY_START=60 python3 -m sideline    # start on the hour mark
```

### The honesty rule

Anything shown from replay is described as **"a recorded real match,
replayed"**. Never implied to be live.

The data is genuine; the clock is ours. Saying so costs nothing and
protects everything. See DEMO_SCRIPT.md.

> The file currently in `data/replay/` has illustrative placeholder
> names and scores so the repository runs with no API key. Replace it
> with a genuine capture via `scripts/record_match.py` before filming.

## Capturing a real match

```bash
export SIDELINE_FOOTBALL_KEY=...
python3 scripts/record_match.py --fixture 1208341 --out data/replay/real.json
```

Run it live and it polls to full time. Run it after the match and it
captures the finished record in one pass, which is usually what you want.

## Writing another provider

Subclass `providers/base.Provider`. Six methods. The normalising rules
are in that file and exist because every vendor gets these wrong in a
different way:

- **Minute is an integer.** `45+2` becomes minute 45 with `stoppage: 2`.
  A listener wants "just before half time", not "forty five plus two".
- **An overturned goal is not deleted.** It gets a `var` event and the
  original is marked superseded. Someone who heard the crowd needs to be
  told it was chalked off.
- **Penalties and own goals are goals with a `detail`.** Otherwise every
  consumer has to know that three kinds all mean "the score changed".

That adapter is the piece we extract for the Open Source mini challenge —
it is useful to anyone putting a sports feed behind MCP, not just us. See
MINI_CHALLENGES.md.
