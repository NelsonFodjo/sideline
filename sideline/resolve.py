"""Understanding what a listener meant, not only what the recogniser heard.

Two situations make a recogniser's literal output the wrong thing to act on:

  1. **A choice was just offered.** "I can see more than one Arsenal match:
     Arsenal against Chelsea, or Arsenal Women against Everton?" The listener
     says the name, badly: "arsenal wimmin", "everton" as "ever ton". The words
     are not an open question any more; they are an answer to a short list, so
     the right move is to find which option they are closest to, by spelling
     and by sound, and to say so out loud when it is not obvious.
  2. **A name from the match was misheard.** "Bukaiyo Saka" is not a word
     anyone else means. When it is near enough to a name we know is in this
     match, it is that name.

This module keeps the short-lived list of what the listener was last offered
and decides, conservatively, when to rewrite what they said. It never rewrites
when two options are about equally close: a wrong guess spoken back as fact is
worse than asking again, and the listener cannot see the screen to catch it.
"""

import difflib
import re
import threading
import time
import unicodedata

from .status import OVER

TTL_SECONDS = 120            # an offer is about the next thing said, not the next hour
MAX_ITEMS = 80

# Thresholds were set against mispronunciations of real names in
# tests/test_resolve.py; change them with that file open.
OFFER_MIN = 0.66             # closest option must be at least this close...
OFFER_MARGIN = 0.08          # ...and this much closer than the runner-up
LOWERCASE_NAME_MIN = 0.93    # a lower-case word becomes a name only when it is almost exactly one ("arsenl")
NAME_MIN = 0.86              # fixing a misheard name inside a longer sentence
NAME_MIN_LETTERS = 5         # never "fix" short words: score, goal, half

_ORDINALS = {
    0: {"first", "1st", "one", "1", "top", "number one", "the first", "the first one",
        "first one", "option one", "number 1"},
    1: {"second", "2nd", "two", "2", "to", "too", "number two", "the second",
        "the second one", "second one", "option two", "number 2"},
    2: {"third", "3rd", "three", "3", "number three", "the third", "the third one",
        "third one", "option three", "number 3"},
}
_ORDINAL_COUNT = {0: 1, 1: 2, 2: 3}
_AFFIRMATIONS = {"yes", "yeah", "yep", "sure", "correct", "right", "that one", "yea", "yup", "ok", "okay"}

POPULAR_TEAMS = [
    "Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Chelsea",
    "Crystal Palace", "Everton", "Fulham", "Ipswich Town", "Leicester City", "Liverpool",
    "Manchester City", "Manchester United", "Newcastle United", "Nottingham Forest",
    "Southampton", "Tottenham Hotspur", "West Ham United", "Wolverhampton Wanderers",
    "Real Madrid", "Barcelona", "Atletico Madrid", "Athletic Bilbao", "Real Sociedad",
    "Real Betis", "Villarreal", "Sevilla", "Valencia", "Girona", "Bayern Munich",
    "Borussia Dortmund", "Bayer Leverkusen", "RB Leipzig", "PSG", "Monaco", "Marseille",
    "Lyon", "Lille", "Juventus", "Inter Milan", "AC Milan", "Napoli", "Roma", "Lazio",
    "Atalanta", "Benfica", "Sporting CP", "Porto", "Ajax", "Feyenoord", "Celtic", "Rangers",
    "Boston Celtics", "Los Angeles Lakers", "Golden State Warriors", "Miami Heat",
    "Milwaukee Bucks", "Denver Nuggets", "Kansas City Chiefs", "San Francisco 49ers",
    "Philadelphia Eagles", "Dallas Cowboys", "New York Yankees", "Los Angeles Dodgers",
    "Wolves", "Spurs", "Barca",
]

POPULAR_COMPETITIONS = [
    "UEFA Champions League", "Champions League", "English Premier League", "Premier League",
    "La Liga", "Serie A", "Bundesliga", "Ligue 1", "UEFA Europa League", "Europa League",
    "Major League Soccer", "MLS", "NBA", "NFL", "MLB", "NHL", "FA Cup", "Carabao Cup",
]

_COMMON_WORDS = {
    # everyday words a fan uses around the game: "last year" was once heard as "Bayer"
    "year", "years", "month", "months", "week", "weeks", "decade", "ever", "world", "history", "record", "records",
    "mean", "means", "stand", "size", "capacity", "trophies", "trophy", "honours", "honors", "rule", "rules", "weather",
    "greatest", "stadium", "ground", "pitch", "formation", "tactics", "explain",
    "started", "start", "starts", "starting", "starters", "starter", "scored", "scoring", "points", "passer", "passing", "quarterback",
    "goalie", "rebounds", "touchdowns", "innings", "inning", "sports", "cover", "difference",
    # numbers, and the words people use about time and delay ("my TV is about forty seconds behind" was heard as "Forest")
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "twenty", "thirty", "forty",
    "fifty", "sixty", "ninety", "hundred", "second", "seconds", "minutes", "hour", "hours", "about", "around",
    "behind", "ahead", "late", "early", "delay", "delayed", "slow", "slower", "quick", "quicker", "now", "just",
    "went", "gone", "goes", "going", "kick", "kickoff", "whistle", "stream", "streaming", "television",
    "screen", "picture", "broadcast", "radio", "sound", "audio", "voice", "speak", "speaking", "language",
    "what", "whats", "where", "when", "which", "who", "whom", "how", "why",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "can", "could", "will", "would", "should", "shall",
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with",
    "about", "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "from", "up", "down", "out", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "score", "match", "game",
    "fixture", "fixtures", "matches", "games", "today", "tomorrow", "yesterday",
    "tonight", "live", "minute", "time", "clock", "table", "standings", "lineup",
    "lineups", "squad", "roster", "stats", "statistics", "report", "recap", "summary",
    "update", "form", "injuries", "injury", "referee", "official", "tell", "show",
    "give", "look", "see", "hear", "listen", "total", "many", "them",
    "they", "their", "theirs", "him", "her", "his", "hers", "that", "this", "these", "those",
    "want", "please", "like", "play", "playing", "start", "starting", "next",
    "miss", "missed", "since", "halftime", "half", "full", "fulltime", "extra",
    "captain", "refereeing", "referee", "booked", "booking", "penalty", "card",
    "red", "yellow", "goal", "goals", "scored", "scorer", "decision", "var",
    "check", "substitution", "sub", "subs", "bench", "coach", "manager", "stadium",
    "pitch", "went", "gone", "already", "winning", "losing", "tied", "draw", "lead",
    "leading", "trail", "trailing", "kickoff", "just", "came", "come", "first", "second",
}

def popular_teams():
    return list(POPULAR_TEAMS)

def popular_competitions():
    return list(POPULAR_COMPETITIONS)

# Sounds a listener's accent or a recogniser cannot tell apart. Mapping them to
# one class makes "Gamba" and "Gamma", "Kyoto" and "Kioto", "Saka" and "Sacha"
# close, which spelling alone does not.
_CLASS = {"b": "p", "p": "p", "f": "v", "v": "v", "d": "t", "t": "t", "g": "k",
          "k": "k", "c": "k", "q": "k", "s": "s", "z": "s", "x": "s", "m": "m",
          "n": "m", "l": "l", "r": "r", "w": "w", "y": "y", "j": "s"}
_VOWELS = set("aeiou")


def _fold(s):
    s = unicodedata.normalize("NFKD", (s or "").lower().replace("ø", "o").replace("æ", "ae"))
    return "".join(c for c in s if not unicodedata.combining(c))


def words(text):
    """Lowercase, accent-free word tokens (possessive 's dropped)."""
    out = []
    for w in re.findall(r"[a-z0-9]+(?:['’][a-z]+)?", _fold(text)):
        w = re.sub(r"['’]s$", "", w).replace("'", "").replace("’", "")
        if w:
            out.append(w)
    return out


def skeleton(word):
    """A rough sound shape: first letter, then consonant classes, vowels gone."""
    w = word
    for a, b in (("ph", "f"), ("ck", "k"), ("sch", "s"), ("th", "t"), ("gh", ""),
                 ("ch", "s"), ("sh", "s"), ("wh", "w"), ("kn", "n"), ("wr", "r")):
        w = w.replace(a, b)
    out = []
    for i, c in enumerate(w):
        if c in _VOWELS or c == "h":
            if i == 0 and c in _VOWELS:
                out.append("a")
            continue
        k = _CLASS.get(c, c)
        if not out or out[-1] != k:
            out.append(k)
    return "".join(out)


def similarity(a_words, b_words):
    """0..1: how alike two phrases are, by spelling and by sound.

    Spaces are ignored as well as kept ("shang high" is "shanghai"), and
    spelling counts for more than sound: the sound code drops vowels, so on its
    own it cannot tell "Shanghai" from "Sanga".
    """
    a, b = " ".join(a_words), " ".join(b_words)
    if not a or not b:
        return 0.0

    def ratio(x, y):
        return difflib.SequenceMatcher(None, x, y).ratio()

    spell = max(ratio(a, b), ratio(a.replace(" ", ""), b.replace(" ", "")))
    sa = [skeleton(w) for w in a_words]
    sb = [skeleton(w) for w in b_words]
    sound = max(ratio(" ".join(sa), " ".join(sb)), ratio("".join(sa), "".join(sb)))
    return 0.6 * spell + 0.4 * sound


def _windows(tokens, n):
    for i in range(0, max(0, len(tokens) - n + 1)):
        yield i, tokens[i:i + n]


# Words that say little about which team: never an alias on their own, or
# "City" would pick whichever City came first.
_GENERIC = {"united", "city", "town", "club", "real", "sporting", "athletic", "athletico",
            "football", "academy", "youth", "women", "against", "county", "rovers",
            "wanderers", "albion", "borough", "olympic", "national", "south", "north",
            "east", "west", "university", "juniors", "reserves"}


class Item(object):
    """One thing the listener may have been offered."""

    def __init__(self, say, aliases=None, label=None, ref=None, agent_say=None):
        self.say = say                              # what we show they meant
        self.label = label or say                   # what we speak and prompt with
        # What the model is told. A fixture carries its id: "Arsenal" alone would
        # be ambiguous again and the model cannot see ids in our error message.
        if agent_say is not None:
            self.agent_say = agent_say
        else:
            self.agent_say = "%s (fixture_id %s)" % (say, ref) if ref else say
        seen, self.aliases = set(), []

        def add(t):
            t = tuple(t)
            if t and t not in seen:
                seen.add(t)
                self.aliases.append(t)

        for a in [say] + list(aliases or []):
            add(words(a))
        # A listener says "Pohang", not "Pohang Steelers": every distinctive word
        # is an alias too. A word two options share ties, and a tie is refused.
        for a in list(self.aliases):
            for w in a:
                if len(w) >= 4 and w not in _GENERIC:
                    add((w,))


class OfferBook(object):
    """What each listener was last offered, for a short while."""

    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def remember(self, listener_id, items, now=None):
        items = list(items)[:MAX_ITEMS]
        with self._lock:
            if items:
                self._d[listener_id] = (now if now is not None else time.time(), items)
            else:
                self._d.pop(listener_id, None)

    def get(self, listener_id, now=None):
        now = now if now is not None else time.time()
        with self._lock:
            hit = self._d.get(listener_id)
            if not hit:
                return []
            if now - hit[0] > TTL_SECONDS:
                del self._d[listener_id]
                return []
            return list(hit[1])

    def clear(self, listener_id):
        with self._lock:
            self._d.pop(listener_id, None)

    def labels(self, listener_id, limit=12, now=None):
        return [i.label for i in self.get(listener_id, now)][:limit]


BOOK = OfferBook()


# ------------------------------------------------------------- building offers
def items_from_candidates(candidates):
    """Offers from a tool's `candidates` (fixtures the listener must choose between)."""
    out = []
    for c in candidates or []:
        home, away = c.get("home"), c.get("away")
        if not home or not away:
            continue
        say = "%s against %s" % (home, away)
        aliases = [home, away, "%s v %s" % (home, away)]
        if c.get("sport"):
            aliases.extend([
                "%s in %s" % (home, c["sport"]),
                "%s %s" % (home, c["sport"]),
                "%s %s" % (c["sport"], home),
            ])
        out.append(Item(say, aliases=aliases, label=say,
                        ref=c.get("fixture_id")))
    return out


def items_from_names(names):
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(Item(n))
    return out


def items_from_sports(sports_list):
    out = []
    sport_aliases = {
        "football": ["soccer", "association football"],
        "basketball": ["hoops", "nba", "basket ball", "wnba"],
        "american_football": ["nfl", "football", "college football", "american football"],
        "baseball": ["mlb", "baseball"],
        "hockey": ["nhl", "ice hockey", "hockey"],
        "cricket": ["cricket", "ipl", "t20"],
        "rugby": ["rugby", "six nations"],
        "tennis": ["tennis", "grand slam"],
    }
    for s in sports_list or []:
        if s:
            aliases = sport_aliases.get(s.lower(), [])
            out.append(Item(s, aliases=aliases, label=s))
    return out


def offers_from_tool_results(tool_results):
    for r in tool_results or []:
        detail = r.get("detail") or {}
        if detail.get("candidates"):
            return items_from_candidates(detail["candidates"])
        if detail.get("sports"):
            return items_from_sports(detail["sports"])
    return []


# ------------------------------------------------------------------- deciding
def _ordinal(tokens, count):
    phrase = " ".join(tokens)
    if len(tokens) > 4:
        return None
    for idx, forms in _ORDINALS.items():
        if idx < count and (phrase in forms or phrase.replace("the ", "") in forms):
            return idx
    return None


def _best_for(item, tokens):
    """Best similarity between an offer's aliases and any stretch of the utterance."""
    best = 0.0
    for alias in item.aliases:
        n = len(alias)
        spans = []
        for size in (n - 1, n, n + 1):
            if size >= 1:
                spans.extend(w for _, w in _windows(tokens, size))
        for span in spans:
            # A match that accounts for more of what was said is worth more:
            # "Tottenham Hot Spur" means the fixture with "Tottenham Hotspur" in
            # it, not just any fixture with "Tottenham".
            coverage = len(span) / float(len(tokens))
            best = max(best, similarity(list(span), list(alias)) * (0.6 + 0.4 * coverage))
    return best


def choose(tokens, items):
    """The offer the listener means, or (None, reason).

    Returns (item, score, runner_up_score). Refuses (None) when the best is too
    far, or when two options are about equally near.
    """
    if not items:
        return None, 0.0, 0.0
    scored = sorted(((_best_for(i, tokens), n, i) for n, i in enumerate(items)),
                    key=lambda t: (-t[0], t[1]))
    best, _, item = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best >= OFFER_MIN and best - second >= OFFER_MARGIN:
        return item, best, second
    return None, best, second


def fix_names(text, items):
    """Repair misheard names inside a sentence, leaving everything else alone.

    Only whole words of a decent length that are very close to a known name:
    "Bukaiyo Saka" becomes "Bukayo Saka"; "score", "goal" and "half" are never
    touched however they sound.
    """
    canon = {}                                   # accent-free word -> its real spelling
    owners = {}                                  # accent-free word -> the names (as word sets) it is part of
    for it in items:
        said_words = {_fold(x) for x in re.findall(r"[^\W\d_]+", it.say, flags=re.UNICODE)}
        for w in re.findall(r"[^\W\d_]+", it.say, flags=re.UNICODE):
            if len(w) >= NAME_MIN_LETTERS:
                canon.setdefault(_fold(w), w)
                owners.setdefault(_fold(w), []).append(said_words)
    if not canon:
        return text

    def repair(m):
        word = m.group(0)
        norm = _fold(word)
        if len(norm) < NAME_MIN_LETTERS:
            return word
        if norm in canon:
            return canon[norm]                   # right word, restore "Ødegaard"
        best, hit = 0.0, None
        for cand in canon:
            sim = similarity([norm], [cand])
            if sim > best:
                best, hit = sim, cand
        # A name is capitalised; an ordinary word that merely resembles one ("triple" ~ "Tripoli") is not repaired.
        if not (hit and best >= (NAME_MIN if word[:1].isupper() else LOWERCASE_NAME_MIN)):
            return word
        # "Auston Matthews" is a person, not a misheard "Aston Villa": when the next word is a capitalised word that is no part
        # of the name this one would become, leave it alone.
        nxt = re.match(r"\s+([A-Z][^\W\d_]+)", m.string[m.end():], flags=re.UNICODE)
        if nxt and any(len(w) > 1 for w in owners.get(hit, [])) and all(_fold(nxt.group(1)) not in w for w in owners.get(hit, [])):
            return word
        return canon[hit]

    return re.sub(r"[^\W\d_]+", repair, text, flags=re.UNICODE)


_TOOL_WORDS = None


def _tool_words():
    """Every word our own tools are described with ("support", "player", "standouts", ...). A word we use to say what
    we do is never a misheard team: without this, "I support Arsenal" came back as "Did you mean Porto?" and "who was
    the best player" as "Did you mean Bayer Leverkusen?"."""
    global _TOOL_WORDS
    if _TOOL_WORDS is None:
        try:
            from .mcp import registry
            text = " ".join("%s %s" % (t["name"].replace("_", " "), t.get("description", ""))
                            for t in registry.public_tools())
            _TOOL_WORDS = {w for w in words(text) if len(w) >= 4}
        except Exception:                                      # noqa: BLE001  a courtesy: fall back to the fixed list
            return set()
    return _TOOL_WORDS


def snap(listener_id, text, names=(), now=None):
    """Decide what the listener meant. Returns a dict:

        {"text": what to act on, "heard": what was said, "changed": bool,
         "why": "ordinal" | "offer" | "name" | "affirmation" | "typo_clarify" | "typo_autocorrect" | None,
         "matched": label or None, "clarify": bool, "suggestion": str or None}
    """
    heard = (text or "").strip()
    cleaned = heard
    for pat, rep in [
        (re.compile(r"\b(what|which)\s+march\b", re.I), r"\1 match"),
        (re.compile(r"\b(what|which)\s+marches\b", re.I), r"\1 matches"),
        (re.compile(r"\bprevious\s+mergers\b", re.I), "previous matches"),
        (re.compile(r"\bprevious\s+merger\b", re.I), "previous match"),
        (re.compile(r"\bmatches\s+that\s+fin\b", re.I), "matches that finished"),
        (re.compile(r"\btireny\b", re.I), "Tierney"),
    ]:
        cleaned = pat.sub(rep, cleaned)
    changed_acoustic = (cleaned != heard)
    res = {"text": cleaned, "heard": heard, "agent_text": cleaned, "changed": changed_acoustic,
           "why": "acoustic_repair" if changed_acoustic else None, "matched": None, "clarify": False, "suggestion": None}
    tokens = words(cleaned)
    if not tokens:
        return res

    offers = BOOK.get(listener_id, now)
    if offers:
        phrase = " ".join(tokens)
        m = re.match(r"^\W*(?:(?:yes|yeah|yep|sure|correct|right|ok|okay|yea|yup|that one)\b[\s,]*(?:please|thanks|thank you)?[\s,]*)+",
                     heard, re.I)
        tail = heard[m.end():].strip() if m else ""
        tail = re.sub(r"^[\s,;:?.-]+", "", tail).strip()
        # A "yes" takes the offer only when it starts a short reply. Anywhere in a sentence it took "Yeah, he's not here and he
        # has a meeting at 2" (the room, not the listener) as yes to Sydney FC: 15 seconds, five model calls, 88 feed requests.
        if (phrase in _AFFIRMATIONS or (m and len(words(tail)) <= 6)) and len(offers) >= 1:
            it = offers[0]
            if tail:
                combined_text = "%s, %s" % (it.say, tail)
                if tail.lower().rstrip("?.!") in it.agent_say.lower():
                    combined_agent = it.agent_say
                else:
                    combined_agent = "%s, %s" % (it.agent_say, tail)
                res.update(text=combined_text, agent_text=combined_agent, changed=True, why="affirmation",
                           matched=it.label)
            else:
                res.update(text=it.say, agent_text=it.agent_say, changed=True, why="affirmation",
                           matched=it.label)
            BOOK.clear(listener_id)
            return res

        idx = _ordinal(tokens, len(offers))
        if idx is not None:
            it = offers[idx]
            res.update(text=it.say, agent_text=it.agent_say, changed=True, why="ordinal",
                       matched=it.label)
            BOOK.clear(listener_id)
            return res

        if len(tokens) <= 6:
            item, score, _ = choose(tokens, offers)
            if item is not None:
                if " ".join(tokens) != " ".join(item.aliases[0]):
                    res.update(text=item.say, agent_text=item.agent_say, changed=True,
                               why="offer", matched=item.label)
                BOOK.clear(listener_id)
                return res

    candidate_pool = list(names) + POPULAR_TEAMS + POPULAR_COMPETITIONS
    pool_items = list(items_from_names(candidate_pool))
    if offers:
        pool_items += offers

    fixed = fix_names(heard, pool_items) if pool_items else heard
    if fixed != heard:
        real = _fold(fixed) != _fold(heard)
        res.update(text=fixed, agent_text=fixed, changed=real, why="name" if real else None)
        return res

    # If sentence was not repaired by fix_names, check for entity typos needing clarification
    best_typo_score = 0.0
    best_typo_cand = None
    best_typo_tok = None

    for tok in tokens:
        if len(tok) >= 4 and tok not in _COMMON_WORDS and tok not in _tool_words():
            exact_match = False
            for cand in candidate_pool:
                cand_toks = words(cand)
                if tok in cand_toks:
                    exact_match = True
                    break
            if exact_match:
                continue

            for cand in candidate_pool:
                cand_toks = words(cand)
                # Skip 3-letter acronym candidates (e.g. MLS, NBA, NFL) for 4+ letter tokens
                if len(cand) <= 3:
                    continue
                sub_sims = [similarity([tok], [cw]) for cw in cand_toks if len(cw) >= 4]
                # one word against a whole multi-word name is a coarse match ("raptors" ~ "real potosi"): compare it with each word
                sim = max(sub_sims) if (len(cand_toks) > 1 and sub_sims) else similarity([tok], cand_toks)
                if sim > best_typo_score:
                    best_typo_score = sim
                    best_typo_cand = cand
                    best_typo_tok = tok

    # "Did you mean...?" is for a close miss only. It was once offered for any name the feed's football pool lacked ("Seahawks" ~
    # "Hawks", "Brunson" ~ "Bruins", "Flames" ~ "Fulham"): in a hundred questions across five sports it blocked a fifth of them.
    # Anything this near is fixed outright above (NAME_MIN), so the band that is left for asking is empty on purpose.
    if best_typo_cand and 0.95 <= best_typo_score < NAME_MIN:
        repaired = heard
        if best_typo_tok:
            repaired = re.sub(r"\b" + re.escape(best_typo_tok) + r"\b", best_typo_cand, heard, flags=re.IGNORECASE)
            cand_words = words(best_typo_cand)
            if len(cand_words) > 1:
                for cw in cand_words:
                    repaired = re.sub(r"\b(" + re.escape(cw) + r")\s+\1\b", r"\1", repaired, flags=re.IGNORECASE)
        res.update(
            clarify=True,
            suggestion=best_typo_cand,
            repaired_text=repaired,
            changed=True,
            why="typo_clarify",
            matched=best_typo_cand
        )
        return res

    return res


# ------------------------------------------------- the two calls the app makes
def match_names(ctx, listener_id, limit=600):
    """Teams and players of the match this listener follows, then the teams on today (the cached day list)."""
    names = []
    try:
        fid = ctx.store.listener(listener_id).get("following")
        fx = (ctx.store.fixture(fid) or {}) if fid else {}
        names += [fx.get("home"), fx.get("away")]
        if fid:
            for e in ctx.store.events(fid):
                names += [e.get("player"), e.get("player_off"), e.get("assist")]
    except Exception:                                          # noqa: BLE001
        pass
    try:
        names += teams_today_ranked(ctx)
    except Exception:                                          # noqa: BLE001  a courtesy
        pass
    try:
        if hasattr(ctx, "provider") and hasattr(ctx.provider, "known_teams"):
            names += ctx.provider.known_teams()
    except Exception:                                          # noqa: BLE001
        pass
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out[:limit]


def understand(ctx, listener_id, text):
    """What the listener meant (see `snap`), with this match's names to hand."""
    try:
        return snap(listener_id, text, names=match_names(ctx, listener_id))
    except Exception:                                          # noqa: BLE001
        # Understanding is a courtesy. It must never be the reason a question
        # goes unanswered.
        t = (text or "").strip()
        return {"text": t, "heard": t, "agent_text": t, "changed": False, "why": None,
                "matched": None}


def learn(ctx, listener_id, result):
    """Remember what the answer just offered, for the next thing they say."""
    try:
        items = offers_from_tool_results((result or {}).get("tool_results"))
        if not items and ((result or {}).get("text") or "").rstrip().endswith("?"):
            # It asked something open ("which team?"), with no list. The likely
            # answers are the teams playing today, live ones first.
            items = items_from_names(_teams_today(ctx))
        BOOK.remember(listener_id, items)
    except Exception:                                          # noqa: BLE001
        BOOK.clear(listener_id)


def teams_today_ranked(ctx):
    """Every team on today (from the one cached date list): live ones first, then by kick-off.
    No extra feed request."""
    def rank(f):
        live = f.get("status") not in ("NS",) + OVER
        return (0 if live else 1, f.get("kickoff") or "")
    names, seen = [], set()
    for f in sorted(ctx.provider.fixtures_on(0), key=rank):
        for n in (f.get("home"), f.get("away")):
            if n and n not in seen:
                seen.add(n)
                names.append(n)
    return names


def _teams_today(ctx, limit=40):
    return teams_today_ranked(ctx)[:limit]
