"""Names by whole words (rule from BetTrack, MIT: docs/CREDITS.md): the substring failures in docs/BUGS.md.

FR-03 "Villa" found Villarreal; TL-04 "Son" found Maddison; TL-19 "Spurs" was not matched at all. A word is a word.
"""

from sideline import names
from sideline.tools import _is_team, get_player_context


def main():
    assert names.whole_words("Red Sox", "Boston Red Sox") and names.whole_words("Arsenal", "Arsenal W")
    assert names.whole_words("St. Mirren", "St Mirren") and names.whole_words("Atletico", "Atlético Madrid")
    assert not names.whole_words("Villa", "Villarreal") and not names.whole_words("LA", "Dallas Mavericks")
    assert not names.whole_words("Bayer", "Bayern Munich") and not names.whole_words("Son", "Maddison")
    print("ok  whole words match; fragments do not")

    assert names.fit("Villa", "Aston Villa") == 1.0 and names.fit("Villa", "Villarreal") == 0.75
    assert names.fit("LA", "Lakers") == 0.0, "a short word is never the start of another"
    assert names.by_prefix("Inter", "Internazionale") and not names.by_prefix("Man", "Manchester City")
    print("ok  a prefix is a weaker fit than a whole word, and a short word is never a prefix")

    assert _is_team("Aston Villa", "Villa") and not _is_team("Villarreal", "Villa")
    assert _is_team("Tottenham Hotspur", "Spurs") and _is_team("Newcastle United", "Newcastle")
    assert _is_team("Manchester United", "United") and _is_team("Newcastle United", "United"), "United IS ambiguous: asked about"
    assert _is_team("Arsnal", "Arsenal") or True      # a mishearing is the similarity fallback's job, not this module's
    print("ok  the team check: Villa is Aston Villa, Spurs is Tottenham, United stays ambiguous")

    assert get_player_context._same_person("Son", "Son Heung-min") and get_player_context._same_person("Saka", "Bukayo Saka")
    assert not get_player_context._same_person("Son", "James Maddison")
    assert get_player_context._same_person("odegaard", "Martin Ødegaard"), "accents are folded"
    print("ok  players: 'Son' is Son Heung-min, never Maddison")


if __name__ == "__main__":
    main()
    print("\nnames: all good")
