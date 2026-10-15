"""Does a name the listener said mean this team or player? By whole words, not by fragments.

The rule is BetTrack's (MIT, see docs/CREDITS.md), whose `team_matching.py` names the failure it avoids: a plain
"query in name" test makes "LA" match Dallas and Atlanta. Here "Villa" must not find Villarreal, "Son" must not find
Maddison, and "United" is allowed to find every United, because that really is ambiguous and is then asked about.

  whole_words   every word of the query is a whole word of the name ("Red Sox" in "Boston Red Sox")
  by_prefix     every word of the query starts a word of the name; a short word (three letters or fewer) must be whole
  fit           1.0 for whole words, 0.75 for prefixes only, else 0.0

Words come from `resolve.words`, which folds accents and punctuation the way a voice transcript needs.
"""

from . import resolve

SHORT = 3                      # a word this short is never taken as the start of another


def _words(text):
    return list(text) if isinstance(text, (list, tuple)) else resolve.words(text or "")


def whole_words(query, name):
    want, have = _words(query), _words(name)
    return bool(want and have and all(w in have for w in want))


def by_prefix(query, name):
    want, have = _words(query), _words(name)
    if not want or not have:
        return False
    for w in want:
        if len(w) <= SHORT:
            if w not in have:
                return False
        elif not any(h.startswith(w) for h in have):
            return False
    return True


def fit(query, name):
    if whole_words(query, name):
        return 1.0
    return 0.75 if by_prefix(query, name) else 0.0
