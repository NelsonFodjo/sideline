"""Basketball. The second sport, here to prove the seam is real.

Differences from football that the profile has to absorb:

  * A score event is worth 1, 2 or 3 points (`points` on the event).
  * Time is a count down inside four 12-minute quarters, so "on 34"
    means nothing; a listener wants "with five minutes left in the
    second quarter". Match time is still stored as elapsed minutes.
  * There are no cards, formations or VAR: there are fouls, timeouts and
    replay reviews, and the officials are a crew.
  * A game has far more scoring events than a football match, so the
    headline for a long absence is the three-pointer, not every basket.
"""

from .. import clock
from ..status import FINISHED
from . import SportProfile, register

QUARTER = 12
_ORDINAL = ["first", "second", "third", "fourth"]
_NUMBER = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


class Basketball(SportProfile):
    key = "basketball"
    game = "game"
    domain = "basketball game"
    regulation_minutes = 4 * QUARTER
    all_kinds = ("basket", "foul", "timeout", "ejection", "review",
                 "substitution", "period")

    score_kinds = ("basket",)
    review_kinds = ("review",)
    review_window = 1
    long_absence_minutes = 10
    start_word = "tip-off"
    score_word = "basket"

    period_anchors = {
        "kickoff": 0,
        "half_time": 2 * QUARTER * 60,
        "second_half": 2 * QUARTER * 60,
        "full_time": 4 * QUARTER * 60,
    }
    anchor_spoken = {
        "kickoff": "tip-off",
        "half_time": "half time",
        "second_half": "the restart",
        "full_time": "the final buzzer",
        "goal": "that basket",
    }

    recency = (("ejection", 2, "just got ejected"), ("foul", 2, "just fouled"), ("basket", 2, "just scored"),
               ("substitution", 1, "just came on"),
               ("review", 1, "just reviewed"))
    official_count_keys = ("fouls_called", "technicals")

    # Threes and ejections change a basketball game; a layup does not.
    def is_major(self, e):
        if e.get("kind") == "basket":
            return int(e.get("points") or 1) >= 3 and not e.get("superseded_by")
        return e.get("kind") == "ejection"

    # ------------------------------------------------------- phrasing
    def when(self, minute, stoppage=0):
        if minute >= self.regulation_minutes:
            return "in overtime"
        q = minute // QUARTER
        left = QUARTER - (minute % QUARTER)
        if left == QUARTER:
            return "at the start of the %s quarter" % _ORDINAL[q]
        return "with %s left in the %s quarter" % (_plural(left, "minute"), _ORDINAL[q])

    def say_score(self, fixture):
        h, a = fixture["score"]["home"], fixture["score"]["away"]
        home, away = fixture["home"], fixture["away"]
        if h == a:
            if h == 0:
                return "%s and %s, still nil all" % (home, away)
            return "%s and %s, level at %d" % (home, away, h)
        return SportProfile.say_score(self, fixture)

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
        w = self.when(e["minute"], e.get("stoppage", 0))
        who = e.get("player")
        if kind == "basket":
            pts = int(e.get("points") or 1)
            if pts >= 3:
                bits = ["%s hit a three %s" % (who or "Someone", w)]
            elif pts == 2:
                bits = ["%s scored two %s" % (who or "Someone", w)]
            else:
                bits = ["%s made a free throw %s" % (who or "Someone", w)]
            d = e.get("detail") or ""
            if d and not (who and who.lower() in d.lower()):         # keep a note like "dunk"; drop a sentence that restates him
                bits.append(d[:1].lower() + d[1:])
            if e.get("assist") and not brief:
                bits.append("set up by %s" % e["assist"])
            return ", ".join(bits)
        if kind == "foul":
            what = (e.get("detail") or "foul").lower()
            out = "%s picked up a %s %s" % (who or "A player", what, w)
            if e.get("reason") and not brief:
                out += " for %s" % e["reason"]
            return out
        if kind == "ejection":
            return "%s was ejected %s" % (who or "A player", w)
        if kind == "timeout":
            return "%s called a timeout %s" % (e.get("team") or "A team", w)
        if kind == "substitution":
            return "%s came on for %s %s" % (
                who or "a substitute", e.get("player_off") or "someone", w)
        if kind == "review":
            return "Replay review %s: %s" % (w, e.get("decision") or "checked")
        return "something happened %s" % w

    def say_lineups(self, lineups, team=None):
        out = []
        for side, data in lineups.items():
            if team and team.lower() not in side.lower():
                continue
            five = data.get("xi") or []
            if five:
                out.append("%s start %s." % (side, _join(five)))
            else:
                out.append("%s have not named a starting five yet." % side)
        return " ".join(out) or "No starting fives published yet."

    def say_officials(self, o):
        bits = []
        if o.get("referee"):
            bits.append("%s is the crew chief." % o["referee"])
        f, t = o.get("fouls_called"), o.get("technicals")
        if f is not None:
            line = "%s called so far" % _plural(f, "foul")
            if t:
                line += ", %s of them technical" % _NUMBER.get(t, t)
            bits.append(line + ".")
        if o.get("assistants"):
            bits.append("With %s." % _join(o["assistants"]))
        return " ".join(bits) or "No official details published."

    def official_counts(self, events):
        fouls = [e for e in events if e.get("kind") == "foul"]
        return {"fouls_called": len(fouls),
                "technicals": sum(1 for e in fouls
                                  if "technical" in (e.get("detail") or "").lower())}

    def not_started(self, fixture):
        base = "%s against %s, waiting for tip-off." % (fixture["home"], fixture["away"])
        return (base + " " + clock.say_kickoff(fixture, self.start_word, tz_minutes=fixture.get("tz_offset_minutes"))).strip()


def _join(names):
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return "%s and %s" % (", ".join(names[:-1]), names[-1])


register(Basketball())
