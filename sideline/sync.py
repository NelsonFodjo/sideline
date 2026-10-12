"""Broadcast delay estimation. The spoiler guard.

THE PROBLEM

Streams run behind the pitch. Satellite, cable and IP delivery each add
their own delay, and a viewer is typically 20-45 seconds behind real
match time. Data feeds arrive in 5-15 seconds.

So without correction, Sideline knows about a goal before the listener's
screen shows it. Ask the score and it reports a goal that, as far as
their television is concerned, has not happened yet.

For a blind fan that is the one unforgivable failure. We become the
thing that spoils the match. The sighted friend beside them cannot do
that, because they are watching the same delayed picture. We can.

THE DESIGN ERROR THIS MODULE AVOIDS

A spoiler guard must not ask the listener to read the clock on their
screen.

They cannot see the clock. That is the entire premise of the product. A
guard that required sight to arm would pass every test and be useless to
the person it is for.

WHAT A BLIND LISTENER ACTUALLY HAS

Their ears. The broadcast is audible, and it contains moments both they
and we can identify:

    "kick-off just went"        -> anchor against kickoff
    "that's half time"          -> anchor against 45:00
    "they've just scored"       -> anchor against the last logged goal
    "the whistle's gone"        -> anchor against full time

Each one gives us a point where their audio and our data describe the
same event, and the difference between them is the delay.

This is an anchor the listener owns independently. Nobody has to help
them, and nothing has to be on a screen.

ACCURACY, HONESTLY

An audio anchor is good to a few seconds, not exact. They speak a beat
after hearing it, speech recognition adds more, and a crowd reacts
before the commentator confirms. ANCHOR_REACTION_SECONDS compensates for
the typical human lag.

That margin is fine. We need to beat a 20-45 second stream delay, not
measure it to the frame.

But one source of error is NOT fine, and it caught us: match minutes are
60-second buckets. A goal "on 34" happened somewhere inside a minute we
cannot see into, so anchoring on minute arithmetic carries up to a
minute of error - as large as the delay we are trying to measure.

So goal anchors use WALL CLOCK instead. The poller stamps every event
with the moment it was logged. The listener hears the goal now; we
learned about it T seconds ago; T is the delay, with no rounding
anywhere. That is the precise path and it is the one listeners will
mostly use, because "they've just scored" is the easiest thing in a
match to call out.

Period anchors - kick-off, half time - have no logged event, so they
fall back to minute arithmetic and carry that 60-second uncertainty. We
round those TOWARDS a larger delay, because being slightly slow is
survivable and being slightly fast is the failure this module exists to
prevent.

FAILING SAFE

Uncalibrated used to mean zero offset, which meant spoiling by default.
That is backwards. We now start from a conservative regional prior and
converge on it as anchors arrive. The worst uncalibrated case is being
slightly slow, never being the thing that ruins the match.

WHERE THE PRIOR COMES FROM

Not a time API. Wall-clock time cannot tell us how far behind someone's
CDN is - we already know the real match minute from the feed, and the
unknown is a property of their stream, not of the clock.

What does help is the device locale, which Alexa+ already provides at no
cost and no latency. Delivery mix varies by region, and satellite is
typically slower than IP, which is typically slower than terrestrial. So
the locale gives a better starting guess than a global constant.

Be clear about what that is worth: the prior is a guess in better
clothes. It stops us spoiling before anyone has said anything. The real
accuracy comes from the first audio anchor.
"""

import logging
import time

LOG = logging.getLogger("sideline.sync")

# Seconds between a listener hearing something and us receiving the
# words. Human reaction plus wake word plus transcription. Subtracted
# from every anchor so we do not systematically over-estimate the delay.
ANCHOR_REACTION_SECONDS = 2

# Conservative global fallback, at the slow end of typical stream lag.
# Being slightly slow is survivable. Spoiling is not.
DEFAULT_PRIOR_SECONDS = 45

MAX_OFFSET_SECONDS = 15 * 60

# A measurement can land slightly negative without meaning anything is
# wrong: we subtract a reaction allowance, and a listener who is
# genuinely close to live will come out a second or two under zero.
# Inside this band we call it in sync. Only a clearly negative result
# means the data feed itself is lagging behind the broadcast, which is a
# different situation and worth saying out loud.
IN_SYNC_TOLERANCE_SECONDS = 8

# Starting guess by region, before any anchor. These are priors, not
# measurements: regions where satellite and IP delivery dominate sit at
# the slower end, regions with heavy terrestrial viewing at the faster.
# Any of them is replaced by the first audio anchor.
REGION_PRIOR = {
    "GB": 35, "IE": 35, "FR": 38, "DE": 38, "ES": 38, "IT": 38,
    "NL": 35, "PT": 38, "SE": 35, "NO": 35, "DK": 35,
    "US": 40, "CA": 40, "AU": 42, "NZ": 42, "JP": 40,
    "ZA": 48, "NG": 52, "KE": 52, "GH": 52, "TZ": 52, "UG": 52,
    "RW": 52, "SN": 52, "CI": 52, "CM": 52, "ET": 52, "MU": 50,
    "IN": 45, "PK": 48, "BD": 48, "BR": 42, "AR": 42, "MX": 42,
}

# How much weight a new anchor gets against the running estimate. Low
# enough that one mis-heard anchor cannot wreck a good estimate, high
# enough to converge within two or three anchors.
ANCHOR_WEIGHT = 0.6


def prior_for(locale):
    """Starting offset from the device locale Alexa+ already gives us.

    Accepts 'en-GB', 'GB', 'en_KE' or None. Falls back to the
    conservative global default, which is the safe direction to be wrong
    in.
    """
    if not locale:
        return DEFAULT_PRIOR_SECONDS, "default"
    code = str(locale).replace("_", "-").split("-")[-1].upper()
    if code in REGION_PRIOR:
        return REGION_PRIOR[code], "locale:%s" % code
    return DEFAULT_PRIOR_SECONDS, "default"


# --------------------------------------------------------------- anchors
# Each anchor names a moment both the listener and our data can identify.
# `resolve` returns the real match time of that moment, in seconds from
# kickoff, or None when we cannot place it.

# Period anchors: no logged event, so minute arithmetic, +/- 60 seconds.
PERIOD_ANCHORS = {
    "kickoff": 0,
    "half_time": 45 * 60,
    "second_half": 45 * 60,
    "full_time": 90 * 60,
}

# Event anchors: measured on the wall clock, no rounding.
EVENT_ANCHORS = {"goal"}

ANCHORS = dict.fromkeys(list(PERIOD_ANCHORS) + list(EVENT_ANCHORS))

# A match minute is a 60-second bucket we cannot see inside. For period
# anchors we add the midpoint, which is unbiased on average. We do not
# add the full bucket: that stacks conservatism on top of an already
# conservative read and can double the estimate on an early anchor.
#
# The safety does not come from this number. It comes from the prior
# being conservative before any anchor, and from goal anchors - which
# are wall-clock exact - replacing this as soon as one is available.
MINUTE_BUCKET_SECONDS = 30

ANCHOR_SPOKEN = {
    "kickoff": "kick-off",
    "half_time": "half time",
    "second_half": "the restart",
    "full_time": "the final whistle",
    "goal": "that goal",
}


def estimate_from_anchor(ctx, fixture_id, anchor, real_now_seconds, now=None):
    """Seconds of delay implied by one audio anchor.

    The listener just heard `anchor`. We know when it really happened.
    The difference, less their reaction time, is how far their picture
    runs behind.

    Returns (offset_seconds, note) or (None, reason).
    """
    if anchor not in ANCHORS:
        return None, "unknown_anchor"

    if anchor in EVENT_ANCHORS:
        # Wall clock. No minute rounding anywhere on this path.
        goals = [e for e in ctx.store.events(fixture_id)
                 if e["kind"] == "goal" and not e.get("superseded_by")]
        if not goals:
            return None, "anchor_not_in_data"
        logged_at = goals[-1].get("at")
        if not logged_at:
            return None, "anchor_not_in_data"
        raw = (now or time.time()) - logged_at - ANCHOR_REACTION_SECONDS
        note_kind = "anchor:goal"
    else:
        at = PERIOD_ANCHORS[anchor]
        # Round towards a larger delay: the minute bucket could be hiding
        # up to 60 seconds, and we would rather be slow than early.
        raw = (real_now_seconds + MINUTE_BUCKET_SECONDS) - at - ANCHOR_REACTION_SECONDS
        note_kind = "anchor:%s" % anchor

    if raw < 0:
        if raw > -IN_SYNC_TOLERANCE_SECONDS:
            # Close enough to live. Clamp rather than refuse - telling
            # someone "you're ahead of me" because they were two seconds
            # quick off the mark would be nonsense.
            return 0, note_kind + ":in_sync"
        # Clearly ahead of our data: the feed is lagging, not the
        # stream. Nothing to hold back, and pretending otherwise would
        # make us skip events.
        return None, "viewer_ahead"
    if raw > MAX_OFFSET_SECONDS:
        return None, "offset_too_large"
    return int(raw), note_kind


def blend(current, measured, calibrated):
    """Fold a new measurement into the running estimate.

    The first real anchor replaces the prior outright - the prior was a
    guess and the anchor is a measurement. After that we average, so one
    mis-heard anchor cannot wreck a good estimate but two consistent
    ones will move it.
    """
    if not calibrated:
        return measured
    return int(round(current * (1 - ANCHOR_WEIGHT) + measured * ANCHOR_WEIGHT))


def describe(offset, source):
    """How we explain the current state, out loud."""
    if source.startswith("anchor"):
        return ("I'm about %d seconds behind the live feed now, matching your "
                "picture." % offset)
    if source.startswith("companion"):
        return "I'm holding everything back %d seconds to match your screen." % offset
    if source.startswith("locale"):
        return ("I'm holding everything back about %d seconds as a precaution, so "
                "I don't get ahead of your picture. Tell me when you hear kick-off "
                "and I'll get it exact." % offset)
    return ("I'm holding everything back about %d seconds so I don't spoil "
            "anything. Tell me when you hear kick-off and I'll tighten it up."
            % offset)
