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

TTL_SECONDS = 120            # an offer is about the next thing said, not the next hour
MAX_ITEMS = 80

# Thresholds were set against mispronunciations of real names in
# tests/test_resolve.py; change them with that file open.
OFFER_MIN = 0.66             # closest option must be at least this close...
OFFER_MARGIN = 0.08          # ...and this much closer than the runner-up
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

    def __init__(self, say, aliases=None, label=None, ref=None):
        self.say = say                              # what we show they meant
        self.label = label or say                   # what we speak and prompt with
        # What the model is told. A fixture carries its id: "Arsenal" alone would
        # be ambiguous again and the model cannot see ids in our error message.
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
        out.append(Item(say, aliases=[home, away, "%s v %s" % (home, away)], label=say,
                        ref=c.get("fixture_id")))
    return out


def items_from_names(names):
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(Item(n))
    return out


def offers_from_tool_results(tool_results):
    for r in tool_results or []:
        detail = r.get("detail") or {}
        if detail.get("candidates"):
            return items_from_candidates(detail["candidates"])
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
    for it in items:
        for w in re.findall(r"[^\W\d_]+", it.say, flags=re.UNICODE):
            if len(w) >= NAME_MIN_LETTERS:
                canon.setdefault(_fold(w), w)
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
        return canon[hit] if hit and best >= NAME_MIN else word

    return re.sub(r"[^\W\d_]+", repair, text, flags=re.UNICODE)


def snap(listener_id, text, names=(), now=None):
    """Decide what the listener meant. Returns a dict:

        {"text": what to act on, "heard": what was said, "changed": bool,
         "why": "ordinal" | "offer" | "name" | None, "matched": label or None}
    """
    heard = (text or "").strip()
    res = {"text": heard, "heard": heard, "agent_text": heard, "changed": False,
           "why": None, "matched": None}
    tokens = words(heard)
    if not tokens:
        return res

    offers = BOOK.get(listener_id, now)
    if offers:
        idx = _ordinal(tokens, len(offers))
        if idx is not None:
            it = offers[idx]
            res.update(text=it.say, agent_text=it.agent_say, changed=True, why="ordinal",
                       matched=it.label)
            BOOK.clear(listener_id)
            return res
        # An answer is short. A long sentence is a new question that happens to
        # contain a name, and is left to the name repair below.
        if len(tokens) <= 6:
            item, score, _ = choose(tokens, offers)
            if item is not None:
                if " ".join(tokens) != " ".join(item.aliases[0]):
                    res.update(text=item.say, agent_text=item.agent_say, changed=True,
                               why="offer", matched=item.label)
                BOOK.clear(listener_id)
                return res

    pool = list(items_from_names(names))
    if offers:
        pool += offers
    fixed = fix_names(heard, pool) if pool else heard
    if fixed != heard:
        # Capitals and accents restored ("hector" -> "Héctor") are tidying, not
        # a different understanding: use them, but do not announce a correction.
        real = _fold(fixed) != _fold(heard)
        res.update(text=fixed, changed=real, why="name" if real else None)
    return res


# ------------------------------------------------- the two calls the app makes
def match_names(ctx, listener_id, limit=60):
    """Teams and players of the match this listener follows (no feed requests)."""
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


def _teams_today(ctx, limit=40):
    fixtures = ctx.provider.fixtures_today()
    live = [f for f in fixtures if f.get("status") not in ("NS", "FT", "finished")]
    rest = [f for f in fixtures if f not in live]
    names = []
    for f in (live + rest)[:limit]:
        names += [f.get("home"), f.get("away")]
    return names
