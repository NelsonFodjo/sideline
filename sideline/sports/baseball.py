"""Baseball (MLB) sport profile."""

from .. import clock
from ..status import FINISHED
from . import SportProfile, register


class Baseball(SportProfile):
    key = "baseball"
    game = "game"
    domain = "baseball game"
    regulation_minutes = 9  # 9 innings mapped as elapsed progress
    period_minutes = 1
    period_word = "inning"
    all_kinds = ("run", "home_run", "hit", "strikeout", "walk", "error", "pitching_change")

    score_kinds = ("run", "home_run")
    review_kinds = ("review", "challenge")
    review_window = 1
    long_absence_minutes = 3
    start_word = "first pitch"
    score_word = "run"

    period_anchors = {
        "kickoff": 0,
        "half_time": 4,
        "second_half": 5,
        "full_time": 9,
    }
    anchor_spoken = {
        "kickoff": "first pitch",
        "half_time": "the middle of the 5th",
        "second_half": "the 6th inning",
        "full_time": "the final out",
        "goal": "that run",
    }

    recency = (("home_run", 2, "just hit a home run"),
               ("run", 2, "just scored"),
               ("strikeout", 1, "just struck out"))

    def is_major(self, e):
        return e.get("kind") in ("home_run", "run")

    def when(self, minute, stoppage=0):
        if minute > 9:
            return "in extra innings"
        return "in the %d inning" % max(1, minute)

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
        who = e.get("player") or "A batter"
        if kind == "home_run":
            return "%s hit a home run %s" % (who, w)
        if kind == "run":
            return "%s scored %s" % (who, w)
        return "Play %s" % w

    def say_lineups(self, lineups, team=None):
        out = []
        for side, data in lineups.items():
            if team and team.lower() not in side.lower():
                continue
            batters = data.get("xi") or []
            if batters:
                out.append("%s lineup leads off with %s." % (side, ", ".join(batters[:3])))
            else:
                out.append("%s have not posted their lineup yet." % side)
        return " ".join(out) or "Starting lineups not published yet."

    def say_officials(self, o):
        if o.get("referee"):
            return "%s is the home plate umpire." % o["referee"]
        return "Umpire crew details not published."

    def not_started(self, fixture):
        base = "%s against %s, waiting for first pitch." % (fixture["home"], fixture["away"])
        return (base + " " + clock.say_kickoff(fixture, self.start_word, tz_minutes=fixture.get("tz_offset_minutes"))).strip()


register(Baseball())
