"""Match states, in the short codes the rest of Sideline speaks (the feed's are mapped in the provider).

One place, so "is it over?" has one answer everywhere. "finished" is the word the test double uses;
the feed's own are the codes.
"""

FINISHED = ("finished", "FT", "AET", "PEN")     # played to the end (full time, after extra time, on penalties)
CALLED_OFF = ("PST", "CANC", "ABD")             # postponed, cancelled, abandoned: no more will be played
OVER = FINISHED + CALLED_OFF                    # nothing more will happen: the poller stops reading it

IN_PLAY = ("live", "LIVE", "1H", "2H", "HT", "ET")   # under way: the feed's own word, not the minute, says so


def is_live(fx):
    """Is this match being played now? From its status; the minute alone is not trusted (a match that has just
    kicked off, or one read from a schedule, can carry minute 0 while it is plainly in play)."""
    status = fx.get("status")
    if status in OVER:
        return False
    return status in IN_PLAY or (fx.get("minute") or 0) > 0


def has_started(fx):
    return is_live(fx) or fx.get("status") in FINISHED
