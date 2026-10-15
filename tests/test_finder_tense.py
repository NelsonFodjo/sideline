"""'Is anyone injured on their side?' with nothing said about when: the NEXT match, not a question about which one.

Found in conversation batch 1: once a team's upcoming matches were visible, a question about the future forked between
last night's match, Saturday's and Tuesday's. Two kick-offs on the same evening are still a real ambiguity.
"""

import datetime

from sideline import clock, finder

NOW = datetime.datetime(2026, 10, 15, 10, 0, tzinfo=datetime.timezone.utc)


def fx(fid, home, away, days, hour, status):
    ko = (NOW + datetime.timedelta(days=days)).replace(hour=hour, minute=0)
    return {"fixture_id": fid, "home": home, "away": away, "status": status, "minute": 90 if status == "FT" else 0,
            "kickoff": ko.strftime("%Y-%m-%dT%H:%MZ"), "score": {"home": 4, "away": 2} if status == "FT" else {"home": 0, "away": 0},
            "sport": "football"}


def best(cands, prefers):
    ref = finder.Reference({"team": "Paris Saint-Germain"}, prefers=prefers)
    scored = finder.score_all(cands, ref, None, 0, now=NOW)
    return finder.decide(scored)


def main():
    played = fx(1, "Manchester City", "Paris Saint-Germain", -1, 19, "FT")
    sat = fx(2, "Strasbourg", "Paris Saint-Germain", 2, 15, "NS")
    tue = fx(3, "Paris Saint-Germain", "Barcelona", 5, 19, "NS")
    outcome, picked = best([played, sat, tue], "coming")
    assert outcome == "one" and picked["fixture_id"] == 2, (outcome, picked)
    print("ok  about the future, with Saturday and Tuesday ahead: Saturday, no question asked")

    same_a, same_b = fx(4, "Arsenal", "Lille", 0, 19, "NS"), fx(5, "Arsenal", "Everton", 0, 15, "NS")
    outcome, picked = best([same_a, same_b], "coming")
    assert outcome == "fork" and {f["fixture_id"] for f in picked} == {4, 5}, (outcome, picked)
    print("ok  two kick-offs on the same day are still a real question")


if __name__ == "__main__":
    main()
    print("\nfinder tense: all good")
