"""'Any news on PSG?': three headlines with their age, then one in more detail; and what is not said.

The sample has ESPN's response shape with INVENTED headlines and summaries (the real ones are ESPN's editorial text, so they are not kept in the repo).
"""

import datetime
import json
import os

from conftest import make_ctx

from sideline.mcp.errors import ToolError
from sideline.providers.espn import EspnProvider
from sideline.tools import get_news

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH = {"results": [{"contents": [
    {"displayName": "Paris Saint-Germain", "uid": "s:600~t:160", "sport": "soccer", "defaultLeagueSlug": "fra.1"}]}]}


def main():
    with open(os.path.join(HERE, "fixtures", "espn-team-news-psg.json")) as fh:
        sample = json.load(fh)
    p = EspnProvider()
    urls = []

    def fake(url, ttl=None, strict=False):
        urls.append(url)
        return SEARCH if "search/v2" in url else sample
    p._fetch_json = fake

    news = p.news(team="Paris Saint-Germain")
    assert "soccer/fra.1/news?team=160" in urls[-1], urls
    assert news["scope"] == "Paris Saint-Germain" and len(news["articles"]) == 5, news["scope"]
    assert news["articles"][1]["headline"] == "Invented story two: the home side hold off a fightback"
    print("ok  one search and one news request for a team: %d headlines" % len(news["articles"]))

    ctx = make_ctx()
    ctx.provider.news = p.news
    spoken, structured, _ = get_news.run(ctx, {"team": "Paris Saint-Germain"}, "u")
    assert spoken.startswith("The latest on Paris Saint-Germain, from ESPN: First, Invented story one"), spoken
    assert "Second, Invented story two: the home side hold off a fightback" in spoken and "Third," in spoken, spoken
    assert "Fourth" not in spoken and spoken.endswith("Want more on any of them?"), "three, not five: it is read aloud"
    assert len(structured["articles"]) == 3
    print("ok  three headlines, in order, offered more:\n    " + spoken[:170] + "...")

    spoken2, _, _ = get_news.run(ctx, {"team": "Paris Saint-Germain", "which": 2}, "u")
    assert spoken2.startswith("Invented story two: the home side hold off a fightback. "), spoken2
    try:
        get_news.run(ctx, {"team": "Paris Saint-Germain", "which": 5 + 1}, "u")
        raise AssertionError("an item that does not exist must be said not to")
    except ToolError as e:
        assert e.detail["reason"] == "no_such_item"
    print("ok  'tell me about the second one' gives its summary; a missing one is said to be missing")

    now = datetime.datetime(2026, 10, 15, 10, 0, tzinfo=datetime.timezone.utc)
    assert get_news._age("2026-10-15T09:40:00Z", now) == "just now"
    assert get_news._age("2026-10-15T07:00:00Z", now) == "3 hours ago" and get_news._age("2026-10-15T09:00:00Z", now) == "1 hour ago"
    assert get_news._age("2026-10-14T08:00:00Z", now) == "yesterday" and get_news._age("2026-10-11T08:00:00Z", now) == "4 days ago"
    assert get_news._age("", now) == "" and get_news._age("not a time", now) == ""
    print("ok  each headline says how old it is, and says nothing when it cannot tell")

    ctx.provider.news = lambda team=None, competition=None, limit=5: None
    try:
        get_news.run(ctx, {"team": "Nobody FC"}, "u")
        raise AssertionError("no news must be said")
    except ToolError as e:
        assert e.detail["reason"] == "no_news" and "Nobody FC" in e.spoken
    print("ok  no news is said, not invented")


if __name__ == "__main__":
    main()
    print("\nnews: all good")
