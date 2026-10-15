"""Football (association football). The sport Sideline launched with.

The phrasing here is what templates.py used to hold directly; it moved
unchanged so existing behaviour and tests are the same.
"""

from ..status import FINISHED, is_live
from . import SportProfile, register


class Football(SportProfile):
    key = "football"
    game = "match"
    domain = "football match"
    regulation_minutes = 90
    all_kinds = ("goal", "card", "substitution", "var", "penalty", "period")

    score_kinds = ("goal",)
    review_kinds = ("var",)
    review_window = 3
    long_absence_minutes = 15
    start_word = "kick-off"
    score_word = "goal"

    period_anchors = {
        "kickoff": 0,
        "half_time": 45 * 60,
        "second_half": 45 * 60,
        "full_time": 90 * 60,
    }
    anchor_spoken = {
        "kickoff": "kick-off",
        "half_time": "half time",
        "second_half": "the restart",
        "full_time": "the final whistle",
        "goal": "that goal",
    }

    recency = (("card", 2, "just booked"), ("goal", 3, "just scored"),
               ("substitution", 2, "just came on"),
               ("var", 2, "just checked by VAR"), ("penalty", 3, "just took a penalty"))
    official_count_keys = ("yellows_shown", "reds_shown")

    # Goals and red cards are what changes a football match.
    def is_major(self, e):
        if e.get("kind") == "goal":
            return not e.get("superseded_by")
        return e.get("kind") == "penalty" or (e.get("kind") == "card" and e.get("colour") == "red")

    def key_events(self, events):
        # Goals first, then reds: the listener wants the score change first.
        goals = [e for e in events if e.get("kind") == "goal" and self.is_major(e)]
        pens = [e for e in events if e.get("kind") == "penalty"]
        reds = [e for e in events if e.get("kind") == "card" and self.is_major(e)]
        return goals + pens + reds

    # ------------------------------------------------------- phrasing
    def when(self, minute, stoppage=0):
        if stoppage:
            if minute == 45:
                return "just before half time"
            if minute == 90:
                return "deep into stoppage time"
            return "on %d plus %d" % (minute, stoppage)
        return "on %d" % minute

    def say_score(self, fixture):
        h, a = fixture["score"]["home"], fixture["score"]["away"]
        home, away = fixture["home"], fixture["away"]
        if h == a and h == 0:
            return "%s and %s, still goalless" % (home, away)
        return SportProfile.say_score(self, fixture)

    def say_match_state(self, fixture):
        score = self.say_score(fixture)
        status = fixture.get("status")
        minute = fixture.get("minute") or 0
        if status in FINISHED:
            return "Full time. %s." % score
        if status in ("HT",):
            return "Half time. %s." % score
        if minute <= 0:
            if is_live(fixture):
                return "%s, just under way." % score
            return self.not_started(fixture)
        return "%s, %d minutes in." % (score, minute)

    def say_event(self, e, brief=False):
        kind = e["kind"]
        w = self.when(e["minute"], e.get("stoppage", 0))
        if kind == "goal":
            if (e.get("detail") or "").lower() == "own goal":
                # The feed credits the team that benefits; the player is
                # the one who put it into his own net.
                return "%s scored an own goal %s" % (e.get("player") or "Someone", w)
            if (e.get("detail") or "").lower() == "penalty":
                return "%s scored a penalty %s" % (e.get("player") or "Someone", w)
            bits = ["%s scored %s" % (e.get("player") or "Someone", w)]
            if e.get("detail"):
                # Only lowercase the first letter. Lowercasing the whole
                # string turns "Left foot, past Raya" into "past raya".
                d = e["detail"]
                bits.append(d[:1].lower() + d[1:])
            if e.get("assist") and not brief:
                bits.append("set up by %s" % e["assist"])
            return ", ".join(bits)
        if kind == "card":
            colour = e.get("colour", "yellow")
            verb = "was sent off" if colour == "red" else "was booked"
            out = "%s %s %s" % (e.get("player") or "A player", verb, w)
            if e.get("reason") and not brief:
                out += " for %s" % e["reason"]
            return out
        if kind == "substitution":
            return "%s came on for %s %s" % (
                e.get("player") or "a substitute", e.get("player_off") or "someone", w)
        if kind == "var":
            return "VAR %s: %s" % (w, e.get("decision") or "checked")
        if kind == "penalty":
            return self._say_penalty(e, w)
        return "something happened %s" % w

    def _say_penalty(self, e, w):
        outcome, who, team = e.get("outcome"), e.get("player"), e.get("team")
        if outcome == "awarded":
            head = "%s were awarded a penalty %s" % (team, w) if team else "a penalty was awarded %s" % w
            if who and e.get("conceded_by"):
                return "%s, after %s was fouled by %s" % (head, who, e["conceded_by"])
            if e.get("conceded_by"):
                return "%s, after a foul by %s" % (head, e["conceded_by"])
            return head
        who = who or "the taker"
        if outcome == "saved":
            by = " by %s" % e["keeper"] if e.get("keeper") else ""
            return "%s's penalty was saved%s %s" % (who, by, w)
        if outcome == "missed":
            return "%s missed a penalty %s" % (who, w)
        return "%s's penalty, %s, %s" % (who, outcome or "taken", w)

    def say_lineups(self, lineups, team=None):
        if not any(d.get("xi") for d in lineups.values()):
            return "The line-ups aren't out yet. They usually come about an hour before kick-off."
        out = []
        for side, data in lineups.items():
            if team and team.lower() not in side.lower():
                continue
            xi = data.get("xi") or []
            line = "%s in a %s." % (side, data.get("formation") or "standard shape")
            if xi:
                # Keeper first, then the rest. A listener building a mental
                # picture needs the shape, not an alphabetical list.
                line += " %s in goal. Then %s." % (xi[0], ", ".join(xi[1:]))
            out.append(line)
        return " ".join(out) or "No line-up published yet."

    def say_officials(self, o):
        bits = []
        over = o.get("match_over")
        if o.get("not_started"):
            return ("%s is refereeing." % o["referee"]) if o.get("referee") else "The referee hasn't been named yet."
        if o.get("referee"):
            bits.append("%s %s." % (o["referee"], "refereed" if over else "is refereeing"))
        else:                                    # leaving it out would sound as if there were no referee to name
            bits.append("The feed doesn't name the referee for this match.")
        y, r = o.get("yellows_shown"), o.get("reds_shown")
        if y is not None:
            if not y and not r:
                card_line = "No cards"
            else:
                card_line = " and ".join(p for p in (
                    "%d yellow%s" % (y, "" if y == 1 else "s") if y else "",
                    "%d red%s" % (r, "" if r == 1 else "s") if r else "") if p)
            bits.append("%s %s." % (card_line, "in the match" if over else "so far"))
        if o.get("assistants"):
            bits.append("Assistants: %s." % ", ".join(o["assistants"]))
        return " ".join(bits) or "No official details published."

    def official_counts(self, events):
        cards = [e for e in events if e.get("kind") == "card"]
        return {"yellows_shown": sum(1 for c in cards if c.get("colour") == "yellow"),
                "reds_shown": sum(1 for c in cards if c.get("colour") == "red")}


register(Football())
