"""'Tell me more about Nuno Mendes': who he is first (name, age, nationality), what the feed lacks said aloud, then an offer.

The profile is a real ESPN athlete response. ESPN carries no honours, so the answer says it has no major titles
rather than leaving them out and sounding complete.
"""

import json
import os

from conftest import make_ctx

from sideline.mcp.errors import ToolError
from sideline.providers.espn import EspnProvider
from sideline.tools import get_player_profile

HERE = os.path.dirname(os.path.abspath(__file__))
HITS = {"results": [{"type": "player", "contents": [
    {"displayName": "Nuno Mendes", "subtitle": "Paris Saint-Germain", "uid": "s:600~a:290591", "sport": "soccer"},
    {"displayName": "Nuno Mendes", "subtitle": "Plymouth Argyle", "uid": "s:600~a:22205", "sport": "soccer"}]}]}


def main():
    with open(os.path.join(HERE, "fixtures", "espn-athlete-profile-mendes.json")) as fh:
        profile = json.load(fh)
    p = EspnProvider()
    urls = []

    def fake(url, ttl=None, strict=False):
        urls.append(url)
        return HITS if "search/v2" in url else profile
    p._fetch_json = fake

    got = p.player_profile("Nuno Mendes", "Paris Saint-Germain")
    assert got == {"name": "Nuno Mendes", "age": 24, "nationality": "Portugal", "position": "defender",
                   "team": "Paris Saint-Germain", "number": "25", "gender": "male", "sport": "soccer", "honours": None}, got
    assert "athletes/290591" in urls[-1] and len(urls) == 2, urls
    print("ok  one search and one profile request: %s, %d, %s, %s" % (got["name"], got["age"], got["nationality"], got["position"]))

    ctx = make_ctx()
    ctx.provider.player_profile = p.player_profile
    spoken, structured, _ = get_player_profile.run(ctx, {"player": "Nuno Mendes", "team": "Paris Saint-Germain"}, "u")
    assert spoken == ("Nuno Mendes is a 24-year-old Portuguese defender at Paris Saint-Germain, shirt number 25. "
                      "I can't give his major titles: my feed doesn't carry honours. "
                      "Want his numbers this season, or how he did in the latest match?"), spoken
    assert structured["player"]["honours"] is None
    print("ok  who he is first, then what is missing, then an offer:\n    " + spoken)

    # when titles ARE known they are said
    ctx.provider.player_profile = lambda player, team=None: dict(got, honours=["Champions League", "Ligue 1"])
    spoken, _, _ = get_player_profile.run(ctx, {"player": "Nuno Mendes"}, "u")
    assert "Major titles: Champions League, Ligue 1." in spoken and "don't have" not in spoken, spoken
    print("ok  known titles are listed")

    # wording: an / a, unmapped country, no age
    assert get_player_profile._age_phrase(18) == "an 18-year-old" and get_player_profile._age_phrase(24) == "a 24-year-old"
    ctx.provider.player_profile = lambda player, team=None: {"name": "Ali Demir", "age": None, "nationality": "Narnia",
                                                               "position": "midfielder", "team": None, "number": None}
    spoken, _, _ = get_player_profile.run(ctx, {"player": "Ali Demir"}, "u")
    assert spoken.startswith("Ali Demir is a midfielder from Narnia."), spoken
    assert "their major titles" in spoken and "how they did" in spoken, "no stated gender: their, never a guess: " + spoken
    print("ok  gaps in the data are left out of the sentence, not filled in")

    ctx.provider.player_profile = lambda player, team=None: None
    try:
        get_player_profile.run(ctx, {"player": "Nobody Atall"}, "u")
        raise AssertionError("an unknown player must be said to be unknown")
    except ToolError as e:
        assert e.detail["reason"] == "no_match" and "Nobody Atall" in e.spoken
    print("ok  an unknown name is not guessed at")


if __name__ == "__main__":
    main()
    print("\nplayer profile: all good")
