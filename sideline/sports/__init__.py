"""Sport profiles: everything Sideline knows that depends on the sport.

The product (per-listener `last_told_at`, the event log, the spoiler guard,
grounding) does not care which sport is being played. What does vary is a
small, closed set of facts, and they all live in a `SportProfile`:

  * which event kinds change the score, and by how much
  * which kinds can overturn a score (VAR, a replay review)
  * what counts as a headline when a listener has been away a long time
  * how time is said aloud ("on 34" versus "with 5 minutes left in the
    second quarter")
  * how the score, the line-ups and the officials are phrased
  * the moments a listener can anchor the spoiler guard on

Nothing above this package names a sport. A fixture says which one it is
with a `sport` key (absent means football, so every pre-existing feed and
recording keeps working). To add a sport, subclass `SportProfile`, call
`register()`, and see docs/SPORTS.md.

Match time stays an integer count of *elapsed* minutes for every sport,
because the store, the gap logic and the broadcast offset all rely on
it. A sport that does not run on a clock (tennis, cricket) maps its own
progress onto elapsed minutes in its provider and says it its own way in
`when()`.
"""

DEFAULT = "football"
# Most headline events read out in one long-absence catch-up.
MAX_HEADLINES = 6


class SportProfile(object):
    key = "generic"
    # What the listener calls the thing they are watching.
    game = "match"
    # Used in prompts: "You turn a list of <domain> events into ..."
    domain = "sports match"
    regulation_minutes = 90
    # Every event kind this sport can emit (used for tool schemas).
    all_kinds = ()

    # Event kinds that change the score. Points per event default to 1 and
    # may be overridden per event with a `points` field.
    score_kinds = ()
    # Event kinds that can overturn a scoring event, the words in their
    # `decision` that mean "overturned", and how far back they reach.
    review_kinds = ()
    overturn_words = ("disallow", "cancel", "overturn", "wave")
    review_window = 3

    # A catch-up longer than this stops being readable by ear.
    long_absence_minutes = 15
    # The word a listener uses for the start of play, and for a score.
    start_word = "kick-off"
    score_word = "goal"

    # Seconds from the start of play, for anchors a listener can hear.
    period_anchors = {"kickoff": 0}
    anchor_spoken = {"kickoff": "the start", "goal": "that score"}

    # (event kind, window in minutes, why-phrase) for resolving "he".
    recency = ()
    # Keys `official_counts` fills in, in the order they are spoken.
    official_count_keys = ()

    # ------------------------------------------------------- scoring
    def score_delta(self, event):
        """Points this event adds to the scoring side; 0 if it adds none."""
        if event.get("kind") not in self.score_kinds:
            return 0
        if event.get("superseded_by") or event.get("superseded"):
            return 0
        return int(event.get("points") or 1)

    def score_from(self, events, home, up_to_minute=None):
        """The score implied by an event list, as {"home": n, "away": n}."""
        h = a = 0
        for e in events:
            if up_to_minute is not None and e["minute"] > up_to_minute:
                continue
            d = self.score_delta(e)
            if not d:
                continue
            if e.get("team") == home:
                h += d
            else:
                a += d
        return {"home": h, "away": a}

    def is_score(self, event):
        return event.get("kind") in self.score_kinds

    def overturned(self, review, events):
        """The scoring event a review event overturns, or None.

        We never delete the original: a listener who heard the crowd needs
        to be told the score was chalked off, and a missing row cannot
        tell them anything.
        """
        if review.get("kind") not in self.review_kinds:
            return None
        decision = (review.get("decision") or "").lower()
        if not any(w in decision for w in self.overturn_words):
            return None
        for e in reversed(events):
            if (e.get("kind") in self.score_kinds
                    and abs(e["minute"] - review["minute"]) <= self.review_window):
                return e
        return None

    def is_major(self, event):
        """A headline for a long absence."""
        return self.is_score(event) and not event.get("superseded_by")

    def key_events(self, events):
        return [e for e in events if self.is_major(e)]

    def headlines(self, events):
        """The headlines actually read out in a long-absence catch-up.

        Capped, because a list read by ear stops being a catch-up. The
        caller must mark only these as told: anything cut here is still
        owed to the listener.
        """
        return self.key_events(events)[:MAX_HEADLINES]

    # -------------------------------------------------------- phrasing
    def when(self, minute, stoppage=0):
        return "on %d" % minute

    def say_score(self, fixture):
        h, a = fixture["score"]["home"], fixture["score"]["away"]
        home, away = fixture["home"], fixture["away"]
        if h == a:
            return "%s %d, %s %d" % (home, h, away, a)
        lead = (home, h, away, a) if h > a else (away, a, home, h)
        return "%s %d, %s %d" % lead

    def say_match_state(self, fixture):
        raise NotImplementedError

    def say_event(self, e, brief=False):
        return "something happened %s" % self.when(e["minute"], e.get("stoppage", 0))

    def say_lineups(self, lineups, team=None):
        raise NotImplementedError

    def say_officials(self, o):
        raise NotImplementedError

    def official_counts(self, events):
        """Running counts from our own event log, for providers that give none."""
        return {}

    def not_started(self, fixture):
        return "%s against %s, not started yet." % (fixture["home"], fixture["away"])

    def spoken_anchor(self, anchor):
        return self.anchor_spoken.get(anchor, anchor)


# ------------------------------------------------------------ registry
_PROFILES = {}


def register(profile):
    _PROFILES[profile.key] = profile
    return profile


def get(key):
    """Profile by key; unknown or empty keys give the default sport."""
    return _PROFILES.get((key or DEFAULT).lower()) or _PROFILES[DEFAULT]


def resolve(x=None):
    """A profile from a profile, a key, a fixture dict, or None."""
    if isinstance(x, SportProfile):
        return x
    if isinstance(x, dict):
        return get(x.get("sport"))
    return get(x)


def for_fixture(fixture):
    return resolve(fixture)


def known():
    return sorted(_PROFILES)


def event_kinds():
    """Every event kind any registered sport can emit, for tool schemas."""
    kinds = []
    for p in _PROFILES.values():
        for k in p.all_kinds:
            if k not in kinds:
                kinds.append(k)
    return kinds


from . import basketball, football  # noqa: E402,F401  (registers the profiles)
