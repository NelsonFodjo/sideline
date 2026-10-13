"""Match states, in the short codes the rest of Sideline speaks (the feed's are mapped in the provider).

One place, so "is it over?" has one answer everywhere. "finished" is the word the test double uses;
the feed's own are the codes.
"""

FINISHED = ("finished", "FT", "AET", "PEN")     # played to the end (full time, after extra time, on penalties)
CALLED_OFF = ("PST", "CANC", "ABD")             # postponed, cancelled, abandoned: no more will be played
OVER = FINISHED + CALLED_OFF                    # nothing more will happen: the poller stops reading it
