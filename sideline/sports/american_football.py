"""American Football (NFL & College Football) sport profile."""

from .. import clock
from ..status import FINISHED
from . import SportProfile, register

QUARTER = 15
_ORDINAL = ["first", "second", "third", "fourth"]


class AmericanFootball(SportProfile):
    key = "american_football"
    game = "game"
    domain = "football game"
    regulation_minutes = 4 * QUARTER
    period_minutes = QUARTER
    period_word = "quarter"
    all_kinds = ("touchdown", "field_goal", "safety", "turnover", "interception",
                 "fumble", "timeout", "review", "score")

    score_kinds = ("touchdown", "field_goal", "safety", "score")
    review_kinds = ("review", "challenge")
    review_window = 2
    long_absence_minutes = 10
    start_word = "kickoff"
    score_word = "touchdown"

    period_anchors = {
        "kickoff": 0,
        "half_time": 2 * QUARTER * 60,
        "second_half": 2 * QUARTER * 60,
        "full_time": 4 * QUARTER * 60,
    }
    anchor_spoken = {
        "kickoff": "kickoff",
        "half_time": "halftime",
        "second_half": "the second half kickoff",
        "full_time": "the final whistle",
        "goal": "that touchdown",
    }

    recency = (("touchdown", 2, "just scored a touchdown"),
               ("field_goal", 2, "just kicked a field goal"),
               ("interception", 2, "just threw an interception"),
               ("fumble", 2, "just fumbled"))

    def score_delta(self, event):
        kind = event.get("kind")
        if kind == "touchdown":
            return int(event.get("points") or 6)
        if kind == "field_goal":
            return 3
        if kind == "safety":
            return 2
        return int(event.get("points") or 1)

    def is_major(self, e):
        return e.get("kind") in ("touchdown", "interception", "fumble")

    def when(self, minute, stoppage=0):
        if minute >= self.regulation_minutes:
            return "in overtime"
        q = min(3, minute // QUARTER)
        left = QUARTER - (minute % QUARTER)
        if left == QUARTER:
            return "at the start of the %s quarter" % _ORDINAL[q]
        return "with %d minutes left in the %s quarter" % (left, _ORDINAL[q])

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
        if status in ("HT",):
            return "Halftime. %s." % score
        if minute <= 0:
            return self.not_started(fixture)
        return "%s, %s." % (score, self.when(minute))

    def say_event(self, e, brief=False):
        kind = e["kind"]
        w = self.when(e["minute"])
        who = e.get("player") or "Someone"
        if kind == "touchdown":
            return "%s scored a touchdown %s" % (who, w)
        if kind == "field_goal":
            return "%s kicked a field goal %s" % (who, w)
        if kind == "interception":
            return "%s intercepted the pass %s" % (who, w)
        if kind == "fumble":
            return "%s recovered the fumble %s" % (who, w)
        return "Score %s" % w

    def say_lineups(self, lineups, team=None):
        out = []
        for side, data in lineups.items():
            if team and team.lower() not in side.lower():
                continue
            starters = data.get("xi") or []
            if starters:
                out.append("%s starters: %s." % (side, ", ".join(starters[:5])))
            else:
                out.append("%s have not confirmed starters yet." % side)
        return " ".join(out) or "Starting rosters not published yet."

    def say_officials(self, o):
        if o.get("referee"):
            return "%s is the referee." % o["referee"]
        return "Officiating crew details not published."

    def not_started(self, fixture):
        base = "%s against %s, waiting for kickoff." % (fixture["home"], fixture["away"])
        return (base + " " + clock.say_kickoff(fixture, self.start_word, tz_minutes=fixture.get("tz_offset_minutes"))).strip()


register(AmericanFootball())
