"""A score is never wrong because of the event list, and a doubted score is read again.

Seen live: a listener was told that the team that was not winning had scored. A delayed listener's score was rebuilt by
counting goal events, and the event list can be missing goals or name a team differently. Now the feed's own score is the
authority and only the goals still held back are taken off it.
"""

import time

from conftest import make_ctx

from sideline.providers.espn import EspnProvider
from sideline.state.store import Event
from sideline.tools import REGISTRY, _shown_score
from sideline.tools import resolve_fixture


class Store(object):
    def __init__(self, events):
        self._e = events

    def events(self, fid):
        return self._e


class Ctx(object):
    def __init__(self, events):
        self.store = Store(events)


def goal(i, minute, team):
    e = Event.make(1, minute, "goal", team=team, player="P%d" % i)
    e["id"] = "e%d" % i
    return e


def main():
    fx = {"fixture_id": 1, "home": "Arsenal", "away": "Tottenham Hotspur", "score": {"home": 1, "away": 0}}

    held = goal(1, 60, "Arsenal FC")                       # a differently written team name: still the home side
    score, unsure = _shown_score(Ctx([held]), fx, [])
    assert score == {"home": 0, "away": 0} and not unsure, score
    print("ok  a held-back home goal comes off the home side, even when the feed writes the team's name differently")

    score, unsure = _shown_score(Ctx([goal(2, 60, "")]), fx, [])
    assert score == {"home": 1, "away": 0} and unsure, "a goal that cannot be placed leaves the feed's score, flagged"
    score, unsure = _shown_score(Ctx([goal(3, 60, "Spurs FC")]), fx, [])
    assert unsure, "a held goal whose side would make the score negative is not guessed"
    print("ok  a goal that cannot be placed on a side is never guessed: the feed's score stands, flagged unconfirmed")

    shown = [goal(4, 10, "Arsenal")]
    fx2 = dict(fx, score={"home": 2, "away": 1})           # the feed lists only one of its three goals
    score, unsure = _shown_score(Ctx(shown), fx2, shown)
    assert score == {"home": 2, "away": 1} and not unsure, score
    print("ok  an incomplete event list no longer changes the score (it used to give 1 to 0)")

    # a doubted score is read again, not answered from what is kept
    ctx = make_ctx(start_minute=40)
    forgotten = []
    ctx.provider.invalidate = lambda fid: forgotten.append(fid)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "ann")
    REGISTRY["get_match_state"](ctx, {}, "ann")
    assert not forgotten
    REGISTRY["get_match_state"](ctx, {"refresh": True}, "ann")
    assert forgotten, "refresh forgets what is kept about the match"
    print("ok  get_match_state(refresh) forgets what is kept and reads the feed again")

    p = EspnProvider()
    assert p._fixture_ttl({"status": "LIVE"}) <= 5 and p._fixture_ttl({"status": "NS"}) <= 30
    p._fixture_by_id["9"] = (time.time(), {"status": "LIVE"})
    p.cache.set("https://x/summary?event=9", {"a": 1}, 300)
    p.cache.set("https://x/summary?event=10", {"a": 2}, 300)
    p.invalidate(9)
    assert "9" not in p._fixture_by_id and p.cache.get("https://x/summary?event=9")[0] is False
    assert p.cache.get("https://x/summary?event=10")[0] is True, "only that match is forgotten"
    print("ok  a match in play is kept for seconds, not a minute; invalidate drops that match alone")
    print("\nscore truth: all good")


if __name__ == "__main__":
    main()
