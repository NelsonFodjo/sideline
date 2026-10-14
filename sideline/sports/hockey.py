"""Ice Hockey (NHL) sport profile."""

from .. import clock
from ..status import FINISHED
from . import SportProfile, register

PERIOD = 20
_ORDINAL = ["first", "second", "third"]


class Hockey(SportProfile):
    key = "hockey"
    game = "game"
    domain = "hockey game"
    regulation_minutes = 3 * PERIOD
    all_kinds = ("goal", "penalty", "power_play", "shootout", "review", "score")

    score_kinds = ("goal", "score")
    review_kinds = ("review", "challenge")
    review_window = 2
    long_absence_minutes = 10
    start_word = "puck drop"
    score_word = "goal"

    period_anchors = {
        "kickoff": 0,
        "half_time": PERIOD * 60,
        "second_half": 2 * PERIOD * 60,
        "full_time": 3 * PERIOD * 60,
    }
    anchor_spoken = {
        "kickoff": "puck drop",
        "half_time": "end of the first period",
        "second_half": "start of the second period",
        "full_time": "the final horn",
        "goal": "that goal",
    }

    recency = (("goal", 2, "just scored"),
               ("penalty", 2, "just took a penalty"))

    def is_major(self, e):
        return e.get("kind") == "goal"

    def when(self, minute, stoppage=0):
        if minute >= self.regulation_minutes:
            return "in overtime"
        p = min(2, minute // PERIOD)
        left = PERIOD - (minute % PERIOD)
        return "with %d minutes left in the %s period" % (left, _ORDINAL[p])

    def say_score(self, fixture):
        h, a = fixture["score"]["home"], fixture["score"]["away"]
        home, away = fixture["home"], fixture["away"]
        if h == a:
            if h == 0:
                return "%s and %s, scoreless" % (home, away)
            return "%s and %s, tied at %d" % (home, away, h)
        lead = (home, h, away, a) if h > a else (away, a, home, h)
        return "%s %d, %s %d" % lead

    def say_match_state(self, fixture):
        score = self.say_score(fixture)
        status = fixture.get("status")
        minute = fixture.get("minute") or 0
        if status in FINISHED:
            return "Final. %s." % score
        if minute <= 0:
            return self.not_started(fixture)
        return "%s, %s." % (score, self.when(minute))

    def say_event(self, e, brief=False):
        kind = e["kind"]
        w = self.when(e["minute"])
        who = e.get("player") or "Someone"
        if kind == "goal":
            return "%s scored %s" % (who, w)
        if kind == "penalty":
            return "%s took a penalty %s" % (who, w)
        return "Play %s" % w

    def say_lineups(self, lineups, team=None):
        out = []
        for side, data in lineups.items():
            if team and team.lower() not in side.lower():
                continue
            first_line = data.get("xi") or []
            if first_line:
                out.append("%s starting line features %s." % (side, ", ".join(first_line[:3])))
            else:
                out.append("%s starting lines not confirmed yet." % side)
        return " ".join(out) or "Starting lineups not published yet."

    def say_officials(self, o):
        if o.get("referee"):
            return "%s is the referee." % o["referee"]
        return "On-ice officials details not published."

    def not_started(self, fixture):
        base = "%s against %s, waiting for puck drop." % (fixture["home"], fixture["away"])
        return (base + " " + clock.say_kickoff(fixture, self.start_word, tz_minutes=fixture.get("tz_offset_minutes"))).strip()


register(Hockey())
