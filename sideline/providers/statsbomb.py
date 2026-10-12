"""StatsBomb Open Data adapter.

Free, genuinely open, and real. Released under a permissive licence for
public use with attribution, it carries full event detail for a set of
real matches: every pass, shot, card, substitution and VAR decision, with
body part, play pattern, assist and the minute and second.

WHY THIS AND NOT A PAID LIVE FEED

Three reasons, in order of how much they mattered:

1. **It is real.** Our earlier replay file held invented names and
   scores. Anything invented in a demo is a thing a judge has to take on
   trust, and this project's whole claim is that it reports what actually
   happened. Real data costs nothing and removes the question.

2. **It is deterministic.** The same match plays the same way every
   time, which makes the tests meaningful and the demo rehearsable at
   two in the morning.

3. **It is free and it has no rate limit.** The paid live tiers we
   evaluated are fine but they make development depend on a subscription
   and a fixture list. See docs/DATA_PROVIDERS.md.

THE TRADE, STATED PLAINLY

StatsBomb Open Data is historical. There is no live path through this
adapter. The hackathon rules permit a deterministic offline replay
harness, so this is allowed - but it changes what we may claim, and the
demo says "a real match, replayed" rather than implying live. The
honesty rule in DATA_PROVIDERS.md is not optional.

A live adapter (providers/apifootball.py) sits behind the same interface
and is wired. Swapping is a config change, which is the point of the
Provider abstraction.

ATTRIBUTION

StatsBomb's licence requires attribution wherever the data is used. It
appears in the README, in the demo video description, and in the
structuredContent of any tool whose answer came from it.
"""

import json
import os

from .base import Provider

ATTRIBUTION = "Match data from StatsBomb Open Data."

# Event type ids in the open-data schema. Mapping them here, once, means
# nothing else in the codebase has to know StatsBomb's taxonomy.
_SHOT, _FOUL, _CARD, _SUB, _VAR = 16, 22, 23, 19, 36
_GOAL_OUTCOME = "Goal"


class StatsBombProvider(Provider):
    name = "statsbomb"

    def __init__(self, events_path, lineups_path=None, match_path=None):
        self.events_path = events_path
        self.lineups_path = lineups_path
        self.match_path = match_path
        self._doc = None

    # ------------------------------------------------------- loading
    def _load(self):
        if self._doc is None:
            with open(self.events_path, "r", encoding="utf-8") as fh:
                self._doc = json.load(fh)
        return self._doc

    # ------------------------------------------------- normalising
    @staticmethod
    def _minute(raw):
        """StatsBomb gives period, minute, second. We want a match minute
        and stoppage separately - see base.py for why."""
        minute = raw.get("minute", 0)
        period = raw.get("period", 1)
        regulation = {1: 45, 2: 90, 3: 105, 4: 120}.get(period, 90)
        if minute > regulation:
            return regulation, minute - regulation
        return minute, 0

    def to_events(self, fixture_id):
        """Turn StatsBomb rows into our Event shape.

        Only the things a listener would ask about. A full open-data
        match is several thousand rows, of which perhaps twenty are
        events anyone would mention out loud.
        """
        out = []
        for raw in self._load():
            tid = (raw.get("type") or {}).get("id")
            minute, stoppage = self._minute(raw)
            team = (raw.get("team") or {}).get("name")
            player = (raw.get("player") or {}).get("name")

            if tid == _SHOT:
                shot = raw.get("shot") or {}
                if (shot.get("outcome") or {}).get("name") != _GOAL_OUTCOME:
                    continue
                body = (shot.get("body_part") or {}).get("name") or ""
                kp = ((raw.get("shot") or {}).get("key_pass_id"))
                out.append(self.mk_goal(
                    fixture_id, minute, player, team,
                    assist=self._assist_for(kp),
                    detail=self._shot_detail(body, shot),
                    stoppage=stoppage))

            elif tid == _CARD or (raw.get("foul_committed") or {}).get("card"):
                card = ((raw.get("bad_behaviour") or {}).get("card")
                        or (raw.get("foul_committed") or {}).get("card") or {})
                name = (card.get("name") or "").lower()
                if not name:
                    continue
                colour = "red" if "red" in name else "yellow"
                out.append(self.mk_card(fixture_id, minute, player, team, colour,
                                        reason=None, stoppage=stoppage))

            elif tid == _SUB:
                sub = raw.get("substitution") or {}
                out.append(self.mk_sub(
                    fixture_id, minute,
                    on=(sub.get("replacement") or {}).get("name"),
                    off=player, team=team, stoppage=stoppage))

            elif tid == _VAR:
                var = raw.get("video_assistant_referee") or {}
                out.append(self.mk_var(
                    fixture_id, minute,
                    decision=(var.get("action") or {}).get("name") or "Check",
                    player=player, team=team, stoppage=stoppage))

        out.sort(key=lambda e: (e["minute"], e.get("stoppage", 0)))
        # Deterministic ids: the same match must replay identically, or
        # the dedupe in the store cannot work and the tests go flaky.
        for i, e in enumerate(out):
            e["id"] = "sb-%s-%03d-%s-%d" % (fixture_id, e["minute"], e["kind"][:3], i)
        return out

    def _assist_for(self, key_pass_id):
        if not key_pass_id:
            return None
        for raw in self._load():
            if raw.get("id") == key_pass_id:
                return (raw.get("player") or {}).get("name")
        return None

    @staticmethod
    def _shot_detail(body, shot):
        """What a friend would actually say about a goal.

        StatsBomb gives us body part and play pattern. "Left foot from a
        corner" is what somebody says; "Shot/Open Play/Left Foot" is not.
        """
        bits = []
        if body and body not in ("Other",):
            bits.append(body)
        if shot.get("type", {}).get("name") == "Penalty":
            bits.append("from the penalty spot")
        elif shot.get("type", {}).get("name") == "Free Kick":
            bits.append("from a free kick")
        return ", ".join(bits)

    # ------------------------------------------------------- reads
    def fixture(self, fixture_id):
        raise NotImplementedError(
            "StatsBombProvider supplies events for the replay harness. "
            "Point SIDELINE_PROVIDER at replay with a file built by "
            "scripts/build_statsbomb_replay.py - see docs/DATA_PROVIDERS.md.")

    def fixtures_today(self):
        return []

    def events(self, fixture_id, since_minute=0):
        return [e for e in self.to_events(fixture_id) if e["minute"] > since_minute]

    def lineups(self, fixture_id):
        if not self.lineups_path or not os.path.exists(self.lineups_path):
            return {}
        with open(self.lineups_path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        out = {}
        for side in doc:
            xi, bench, numbers = [], [], {}
            for p in side.get("lineup", []):
                name = p.get("player_name")
                numbers[name] = p.get("jersey_number")
                started = any(
                    pos.get("start_reason") == "Starting XI"
                    for pos in (p.get("positions") or []))
                (xi if started else bench).append(name)
            out[side.get("team_name")] = {
                "formation": None, "xi": xi, "bench": bench, "numbers": numbers}
        return out

    def officials(self, fixture_id):
        # Open data does not name officials. We say so rather than
        # inventing one - get_officials derives the card count from our
        # own event log, which is the half that matters.
        return {"referee": None, "assistants": [],
                "note": "Officials are not published in this dataset."}
