"""A player's season: his club's figures and his country's, never added together.

Real ESPN data for Nuno Mendes: this season his goal and three assists came for his country (World Cup, Nations
League); for Paris Saint-Germain he has five starts and no goals or assists. The tool used to add every
competition up and say "16 appearances, 1 goal, 3 assists" for the club.
"""

import json
import os

from conftest import make_ctx

from sideline.providers.espn import EspnProvider
from sideline.tools import get_player_stats

HERE = os.path.dirname(os.path.abspath(__file__))
HITS = {"results": [{"type": "player", "contents": [
    {"displayName": "Nuno Mendes", "subtitle": "Paris Saint-Germain", "uid": "s:600~a:290591", "sport": "soccer"},
    {"displayName": "Nuno Mendes", "subtitle": "Plymouth Argyle", "uid": "s:600~a:22205", "sport": "soccer"}]}]}


def main():
    with open(os.path.join(HERE, "fixtures", "espn-athlete-overview-mendes.json")) as fh:
        overview = json.load(fh)
    p = EspnProvider()
    urls = []

    def fake(url, ttl=None, strict=False):
        urls.append(url)
        return HITS if "search/v2" in url else overview
    p._fetch_json = fake

    s = p.player_stats("Nuno Mendes", "Paris Saint-Germain")
    assert (s["starts"], s["goals"], s["assists"]) == (5, 0, 0), s
    assert s["international"] == {"starts": 11, "goals": 1, "assists": 3}, s["international"]
    assert "appearances" not in s, "ESPN gives starts; an appearance count is not invented"
    assert "athletes/290591/" in urls[-1]
    print("ok  club: 5 starts, no goals, no assists. country: 11 starts, 1 goal, 3 assists")

    s2 = p.player_stats("Nuno Mendes", "Plymouth Argyle")
    assert "athletes/22205/" in urls[-1], "the Nuno Mendes on the named team is the one looked up: %s" % urls[-1]
    assert s2["team"] == "Plymouth Argyle"
    print("ok  two players share the name: the team asked about decides")

    ctx = make_ctx()
    ctx.provider.player_stats = lambda player, team=None: p.player_stats(player, team)
    spoken, structured, _ = get_player_stats.run(ctx, {"player": "Nuno Mendes", "team": "Paris Saint-Germain"}, "u")
    assert spoken == ("Nuno Mendes for Paris Saint-Germain this season: 5 starts, no goals and no assists. "
                      "For his country: 11 starts, 1 goal and 3 assists."), spoken
    print("ok  said plainly:", spoken)

    # a player with nothing from the feed is not given an invented "1 appearance"
    p._fetch_json = lambda url, ttl=None, strict=False: HITS if "search/v2" in url else {"statistics": {"names": [], "splits": []}}
    assert p.player_stats("Nuno Mendes", "Paris Saint-Germain")["starts"] is None
    print("ok  no figures from the feed means no figures, not 'one appearance'")


if __name__ == "__main__":
    main()
    print("\nplayer stats: all good")
