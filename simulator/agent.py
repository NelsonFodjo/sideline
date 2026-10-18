"""Bedrock tool-use loop that lets Nova operate Sideline's MCP tools."""

import datetime
import html
import json
import logging
import re
import threading
import time
from collections import OrderedDict

from sideline import audit
from sideline.mcp.errors import InvalidParams, ToolError
from sideline.mcp.registry import public_tools
from sideline.mcp.schema import validate

LOG = logging.getLogger("sideline.agent")

MAX_TURNS = 4
MAX_TOOL_CALLS = 8
MAX_TOOL_RESULT_CHARS = 6000
# Room for a few complete spoken sentences (or a tool call plus a short preamble). Too small a budget cuts answers
# mid-sentence and leaves a truncated <thinking> preamble with nothing to say (AG-13).
MAX_TOKENS = 300
MAX_HISTORY_MESSAGES = 12
MAX_CONVERSATIONS = 256
CONVERSATION_TTL_SECONDS = 1800

SYSTEM = (
    "You are Sideline, a live sports companion people listen to, built first for blind and low-vision fans. "
    "You cover football (soccer), basketball, American football, baseball and ice hockey. "
    "Speak like a warm, knowledgeable commentator talking to a friend: lead with what matters (the score, who, "
    "when), then at most one vivid but factual detail. "
    "Make responses on scores and fixtures sound conversational rather than reading from a script: "
    "for scores, speak naturally like a live commentator (e.g. 'Arsenal are currently leading Chelsea 2-1 in the 65th minute' or 'It's full time, Arsenal took the win 2-1 against Chelsea'); "
    "for fixtures and schedules, never read out a rigid list with colons or repetitive 'against' lines like a timetable—weave matches conversationally into fluent sentences grouped by kickoff time or key matchups. "
    "Truth comes first: use only facts from tool results and this conversation. Never invent or guess scores, "
    "names, times, stats or weather; if the tools did not say it, say plainly that you don't know. "
    "Never mention a moment the tools did not return: the listener may be behind live and results are already "
    "held back to their point. "
    "You do have live scores, fixtures, results and tables: call a tool for any current fact rather than "
    "answering from memory or saying you can't. All available tool descriptions and schemas are already "
    "provided; pick the tool whose description fits the whole question, call only what you need, and ask one "
    "short question when the match or team is unclear. "
    "When a fan asks for 'the Champions League' without qualifying it, they mean the UEFA Champions League. "
    "If fixtures or results are from another competition like CAF Champions League or AFC Champions League, make that clear. "
    "Answer clarifying questions (such as 'is that the Champions League?') directly and honestly from the conversation history and tool data; never repeat a raw list of matches when asked to clarify. "
    "If the listener clarifies or corrects a name (e.g. 'I said Paris Saint-Germain'), apply that correction to their previous request by calling the appropriate tool with the corrected name. "
    "When a fan asks about a team's upcoming fixtures, matches or schedule (e.g. 'fixtures of Manchester City', 'when do Arsenal play next'), call get_schedule with team, not get_fixtures (get_fixtures is for all matches across a league or day and does not take a team argument). "
    "Statements are requests too: \"I support Arsenal\" saves a favourite, \"keep it short\" or \"speak French\" "
    "sets a preference, \"who was the best player\" asks for the standouts: call the matching tool, never just "
    "acknowledge. "
    "If a tool fails, say briefly that you couldn't get it just now; never read out errors, ids, field names "
    "or code. "
    "Reply only with the words to be spoken: 1 to 3 short, complete sentences unless asked for more; no lists, "
    "markdown, emojis or reasoning. Questions about you or what you cover, answer directly. "
    "Rules and word meanings (offside, VAR, formations) you may explain briefly. What the tools lack (honours, "
    "stadium size, weather, past winners): say you don't have it, never answer with a list of matches."
)

# For a rule or a meaning, a model with no tools and no match to talk about: short, plain, spoken.
_GENERAL_SYSTEM = ("You answer a sports fan's question about the rules of a game or what a word means, in one or two plain "
                   "spoken sentences, with no lists or markdown. You have no tools and no live data; do not mention either.")

# The tools whose call changes what the listener has been told or what they follow. A shortcut must never run
# one of them: if its result is then not spoken, the change has still happened (AG-01).
STATEFUL_TOOLS = frozenset(("what_did_i_miss", "get_lineups", "get_event_detail", "follow_match",
                            "set_preferences", "set_favourites", "sync_broadcast_delay"))

_SOCIAL = re.compile(r"^\W*(hi|hello|hey|thanks|thank you|cheers|ok|okay|great|nice|cool|bye|goodbye|good night|"
                    r"yes|yeah|yep|no|nope|never mind|nevermind|stop|cancel)\W*$", re.I)
_CLARIFY_OR_VERIFY = re.compile(
    r"^(?:is|are|was|were|which|why|did|do|does|can|could|how come|really|sure)\b|"
    r"\b(?:is that|are those|are they|was that|which one|really|are you sure|confirm|did you mean|do you mean)\b",
    re.I,
)
_REFUSAL = re.compile(
    r"\b(can't engage in this|cannot engage in this|not authorized|change the subject please|not something I can share|as an ai|as a language model)\b",
    re.I,
)
_FACT_OPENER = re.compile(r"\b(who|whom|whose|when|where|which|how (many|much|old|long|far|tall|big)|"
                          r"what time|what('s| is| was| were) (the|their|his|her|its)|tell me (more )?about|"
                          r"more about|did (they|he|she|we)|has (he|she|they)|have (they|we)|(was|were|is|are) there (a|an|any|another)|what did i miss|catch me up|"
                          r"what('s| has| have)? ?happened|anything (new|else)|any(thing)? update|the score|"
                          r"how('s| is) the (game|match) going|what('s| is| else is| else's) on)\b", re.I)


_CONVERSATIONAL = re.compile(
    r"\b(how (?:are you|are you doing|are things|is it going|r u|do you do)|how does (?:it|this) work|"
    r"what can you do|who are you|who made you|how do you work)\b", re.I)


# The rules of the game and what words mean: stable knowledge, answered without a tool (the feed has none of it).
_GENERAL_KNOWLEDGE = re.compile(
    r"\b(offside rule|the rules?\b|what does (?:var|xg|btts|ft|ht) (?:stand for|mean)|what is (?:a|an|the) "
    r"(?:offside|var|formation|false nine|clean sheet|hat.?trick|nutmeg|assist|corner|penalty shoot.?out)|"
    r"what(?:'s| is) a [\d-]+ formation|how many (?:substitutions?|subs|players|minutes) (?:are|is|can)|"
    r"how long is a (?:football|soccer|basketball|hockey|baseball)? ?(?:match|game)|explain (?:the )?(?:offside|var)|"
    r"what does (?:era|rbi|obp|ops|whip|mvp|qb|td|nba|nfl|nhl|mlb|mls|ppg|xa|pk|ot|erm) (?:mean|stand for)\b|"
    r"what(?:'s| is) (?:a|an|the) (?:triple.?double|double.?double|safety|icing|power play|penalty kill|balk|save|walk|bunt|infield fly|"
    r"touchdown|field goal|first down|two.?point conversion|punt|fumble|sack|blitz|hat.?trick|nutmeg|clean sheet|slam dunk|alley.?oop|"
    r"shot clock|free throw|three.?pointer|pick and roll|home run|strikeout|no.?hitter|grand slam|offside|face.?off|hat trick)\b|"
    r"how long is (?:a|an|the) (?:nba |nfl |nhl |mlb |college )?(?:quarter|period|half|inning|overtime|game|match)\b|"
    r"how many (?:innings|periods|quarters|downs|outs|strikes|balls|players|timeouts|fouls) (?:are|is|in|on|can|does|do)\b|"
    r"what(?:'s| is) the difference between (?:football|soccer) and (?:american football|football|soccer))", re.I)


# Things a fan wonders about that the feed does not carry. Said plainly and at once, with what she can do instead: sending
# them to a tool only ever produced a list of matches, and answering from memory would be a guess.
_OUT_OF_SCOPE = [
    (re.compile(r"\b(trophies|trophy|honou?rs|titles? (?:has|have|did)|how many (?:league |cup |champions league |world cup )?(?:titles|cups)|"
                r"how many times (?:has|have|did) .* won)\b", re.I),
     "I don't have honours or trophies: my feed doesn't carry them. I can tell you where a team stands this season."),
    (re.compile(r"\b(stadium|ground|arena)\b.*\b(capacity|seats|how big|how many (?:people|fans))\b|\b(capacity|how big)\b.*\b(stadium|ground|arena)\b|"
                r"\bhow big (?:is|was) .{0,30}(?:stadium|ground|arena)\b", re.I),
     "I don't have stadium sizes. I can tell you which ground a match is at, and where."),
    (re.compile(r"\b(best|greatest) (?:player|footballer|team|manager|coach)s?\b.*\b(world|ever|all time|history)\b|\bgoat\b", re.I),
     "That's a matter of opinion and I don't rank players across the world. I can tell you who stood out in a match."),
    (re.compile(r"\b(?:score|result) (?:at|by|in) (?:the )?(?:half.?time|the half|the break|the end of the (?:first|second|third) (?:quarter|period))\b|"
                r"\b(?:half.?time|quarter.?time) score\b", re.I),
     "I don't have half-time or quarter scores, only the final and, for football, the goals with their minutes."),
    (re.compile(r"\b(?:highest|lowest|biggest|largest|smallest) (?:score|scoring|margin|win|total)\b|\bmost points in a game\b", re.I),
     "I don't rank games by score. I can read out the day's results, or one game's score."),
    (re.compile(r"\bwho won\b.*\b(last year|last season|in (?:19|20)\d\d|back in)\b|\b(?:last year's|last season's) (?:winners?|champions?)\b", re.I),
     "I don't have past seasons: my feed covers this season's tables, results and fixtures."),
]


def _out_of_scope(question):
    """The plain answer to a question the feed cannot carry, or None."""
    q = question or ""
    for pattern, said in _OUT_OF_SCOPE:
        if pattern.search(q):
            return said
    return None


def _asks_for_a_fact(question):
    """Does this ask for something a tool knows (a name in it, or who/when/where/how many), and not chat or thanks?

    Only these are held to a tool when the model first answers without one; "are you still around?" is left to the model.
    """
    q = (question or "").strip()
    if not q or _SOCIAL.match(q) or _GENERAL_KNOWLEDGE.search(q):
        return False
    if _CONVERSATIONAL.search(q):
        if not re.search(r"\b(score|scores|match|matches|game|games|fixture|fixtures|table|standings|lineup|lineups|goal|goals|who scored|who won)\b", q, re.I):
            return False

    if re.match(r"^\W*(?:i (?:said|meant|asked for|told you)|no(?:,?\s+i (?:said|meant))?)\b", q, re.I):
        return False

    sentences = re.split(r"[.!?]+", q)
    for sent in sentences:
        words = re.findall(r"[A-Za-z][A-Za-z'.-]*", sent)
        if len(words) > 1:
            for w in words[1:]:
                if w[:1].isupper() and w not in ("I", "I'm", "I'll", "I've", "I'd"):
                    return True
    return bool(_FACT_OPENER.search(q))


# What a listener can ask of the assistant's memory. Anchored to the start of what they say (after "please", "okay"...):
# "I'll never forget that goal" is conversation, not an instruction.
_ASK = r"^\W*(?:(?:please|ok|okay|hey|alright|now|just|can you|could you|will you)\W+)*"
_FORGET_ALL = re.compile(_ASK + r"(?:forget (?:everything|all) (?:about me|you (?:know|remember))|forget me\b|"
                         r"(?:delete|wipe|erase|clear) (?:all )?(?:of )?(?:my|everything about me)(?: (?:data|info|information|"
                         r"profile|details|settings|preferences))?\b|reset everything)", re.I)
_FORGET_CHAT = re.compile(_ASK + r"(?:forget (?:that|this|it|what (?:i|we) (?:just )?(?:said|asked|talked about)|"
                          r"(?:the|our|this) (?:conversation|chat|last (?:thing|question))|everything we (?:said|talked about))|"
                          r"start (?:over|afresh|fresh|again)|new topic|(?:clear|reset) (?:the |our |this )?(?:conversation|chat)|"
                          r"never ?mind (?:that|all that|what i said)|let'?s change the subject)", re.I)


def _forget_scope(question):
    """"everything" (the stored profile too), "conversation" (this session only), or None."""
    q = question or ""
    if _FORGET_ALL.match(q):
        return "everything"
    if _FORGET_CHAT.match(q):
        return "conversation"
    return None


def _forget(ctx, scope, listener_id, tool_runner, tool_specs):
    """Obey "forget that" and "forget everything about me" without a model call.

    The conversation and the topic are session memory and are dropped here. What is kept about a listener (the match
    they follow, their teams, settings and what they have heard) lives in the MCP server, so "everything" asks it
    to erase that through its own tool, as any other client would.
    """
    from sideline import resolve
    CONVERSATIONS.forget(listener_id)
    FOCUSES.forget(listener_id)
    resolve.BOOK.clear(listener_id)
    if scope == "everything":
        _, is_error, record = _run_tool("set_preferences", {"forget": "everything"}, listener_id, tool_runner, tool_specs)
        from sideline.mcp.errors import ERROR_SPOKEN
        return {"text": ERROR_SPOKEN if is_error else record.get("spoken") or ERROR_SPOKEN, "generated_by": "forget",
                "tool_results": [record]}
    text = "Okay, starting fresh."
    try:
        rec = ctx.store.listener(listener_id)
        fx = ctx.store.fixture(rec.get("following")) if rec.get("following") else None
        if fx:
            text += " I'm still following %s against %s." % (fx.get("home"), fx.get("away"))
    except Exception:                                      # noqa: BLE001  a courtesy
        pass
    return {"text": text, "generated_by": "forget", "tool_results": []}


class AgentUnavailable(Exception):
    """Nova could not complete an agent turn."""


class ConversationMemory:
    """What was said this session, per listener: in this process only, bounded, forgotten after 30 idle minutes.

    Not written to the listener's DynamoDB record. A restart clears it, which is intended: the conversation is
    disposable, while what the listener follows, supports and has heard, and their settings, are durable and live in the
    MCP server's state. Nothing the listener said is kept past the session, and `forget` ends it on request.
    """

    def __init__(self):
        self._conversations = OrderedDict()
        self._lock = threading.Lock()

    def get(self, listener_id):
        now = time.monotonic()
        with self._lock:
            entry = self._conversations.get(listener_id)
            if entry and (now - entry[0] <= CONVERSATION_TTL_SECONDS):
                self._conversations.move_to_end(listener_id)
                return list(entry[1])
        return []

    def remember(self, listener_id, question, answer):
        now = time.monotonic()
        with self._lock:
            entry = self._conversations.get(listener_id)
            history = list(entry[1]) if entry and now - entry[0] <= CONVERSATION_TTL_SECONDS else []
            history.extend([
                {"role": "user", "content": [{"text": question}]},
                {"role": "assistant", "content": [{"text": answer}]},
            ])
            self._conversations[listener_id] = (now, history[-MAX_HISTORY_MESSAGES:])
            self._conversations.move_to_end(listener_id)
            while len(self._conversations) > MAX_CONVERSATIONS:
                self._conversations.popitem(last=False)

    def forget(self, listener_id):
        with self._lock:
            self._conversations.pop(listener_id, None)


CONVERSATIONS = ConversationMemory()

FOCUS_TTL_SECONDS = 600

def _clean_comp_name(comp):
    c = str(comp or "").lower()
    if "uefa.champions" in c or "champions" in c:
        return "Champions League"
    if "eng.1" in c or "premier" in c:
        return "Premier League"
    if "esp.1" in c or "la liga" in c:
        return "La Liga"
    if "ita.1" in c or "serie a" in c:
        return "Serie A"
    if "ger.1" in c or "bundesliga" in c:
        return "Bundesliga"
    if "fra.1" in c or "ligue 1" in c:
        return "Ligue 1"
    if "usa.1" in c or "mls" in c:
        return "MLS"
    if "uefa.europa" in c or "europa" in c:
        return "Europa League"
    if "nba" in c:
        return "NBA"
    if "nfl" in c:
        return "NFL"
    return comp


COMP_PATTERNS = [
    (re.compile(r"\b(champions league|uefa champions league|ucl)\b", re.I), "uefa.champions", "Champions League"),
    (re.compile(r"\b(premier league|epl|english premier league)\b", re.I), "eng.1", "Premier League"),
    (re.compile(r"\b(la liga|spanish league)\b", re.I), "esp.1", "La Liga"),
    (re.compile(r"\b(serie a|italian league)\b", re.I), "ita.1", "Serie A"),
    (re.compile(r"\b(bundesliga|german league)\b", re.I), "ger.1", "Bundesliga"),
    (re.compile(r"\b(ligue 1|french league)\b", re.I), "fra.1", "Ligue 1"),
    (re.compile(r"\b(mls|major league soccer)\b", re.I), "usa.1", "MLS"),
    (re.compile(r"\b(europa league|uel)\b", re.I), "uefa.europa", "Europa League"),
    (re.compile(r"\b(nba|basketball)\b", re.I), "nba", "NBA"),
    (re.compile(r"\b(nfl|american football)\b", re.I), "nfl", "NFL"),
]


class Focus:
    """What the listener was last talking about: a match, competition, total, team, player.

    Session memory: in this process only, like the conversation (see ConversationMemory).
    """

    def __init__(self):
        self._by = {}
        self._pending = {}
        self._lock = threading.Lock()

    @staticmethod
    def _topic(records):
        """The latest match, competition, count, team and player named by answered tool calls."""
        topic = {}
        for record in records:
            if record.get("declined") or record.get("is_error"):
                continue
            args, structured = record.get("args") or {}, record.get("structured") or {}
            name = record.get("name")
            if structured.get("home") and structured.get("away"):
                topic["match"] = "%s against %s" % (structured["home"], structured["away"])
            elif structured.get("matches"):
                matches = structured["matches"]
                topic["matches"] = matches
                if len(matches) == 1:
                    first = matches[0]
                    if first.get("home") and first.get("away"):
                        topic["match"] = "%s against %s" % (first["home"], first["away"])
            if structured.get("fixture_id"):
                topic["fixture_id"] = structured["fixture_id"]
            elif args.get("fixture_id"):
                topic["fixture_id"] = args["fixture_id"]
            if structured.get("sport"):
                topic["sport"] = structured["sport"]
            elif args.get("sport"):
                topic["sport"] = args["sport"]
            comp = structured.get("competition") or args.get("competition")
            if comp:
                topic["competition"] = comp
                topic["competition_name"] = _clean_comp_name(comp)
            if "total" in structured:
                topic["total"] = structured["total"]
                topic["fixtures_kind"] = ("finished" if structured.get("finished_only")
                                          else "live" if structured.get("live_only") else "")
            if structured.get("when") or args.get("when"):
                topic["when"] = structured.get("when") or args.get("when")
            if args.get("team"):
                topic["team"] = args["team"]
            elif structured.get("team"):
                topic["team"] = structured["team"]
            player = args.get("player")
            if not player and isinstance(structured.get("player"), dict):
                player = structured["player"].get("name")
            if player and str(player).lower() not in ("he", "him", "his", "that player", "she", "her"):
                topic["player"] = player
            topic["last_tool"] = name
        return topic

    def topic(self, listener_id):
        with self._lock:
            kept = self._by.get(listener_id)
        if kept and time.monotonic() - kept[0] <= FOCUS_TTL_SECONDS:
            return dict(kept[1])
        return {}

    def remember(self, listener_id, records):
        topic = self._topic(records)
        if not topic:
            return
        with self._lock:
            kept = self._by.get(listener_id)
            merged = dict(kept[1]) if kept and time.monotonic() - kept[0] <= FOCUS_TTL_SECONDS else {}
            if "match" in topic and topic["match"] != merged.get("match"):
                merged.pop("player", None)
            merged.update(topic)
            self._by.pop(listener_id, None)            # re-inserted last: the oldest-used is evicted first
            self._by[listener_id] = (time.monotonic(), merged)
            while len(self._by) > MAX_CONVERSATIONS:
                self._by.pop(next(iter(self._by)))

    def forget(self, listener_id):
        with self._lock:
            self._by.pop(listener_id, None)
            self._pending.pop(listener_id, None)

    def set_pending(self, listener_id, question):
        with self._lock:
            self._pending[listener_id] = (time.monotonic(), question)

    def take_pending(self, listener_id):
        with self._lock:
            kept = self._pending.pop(listener_id, None)
        return kept[1] if kept and time.monotonic() - kept[0] <= FOCUS_TTL_SECONDS else None

    def line(self, listener_id):
        with self._lock:
            kept = self._by.get(listener_id)
        if not kept or time.monotonic() - kept[0] > FOCUS_TTL_SECONDS:
            return ""
        topic = kept[1]
        said = []
        if topic.get("match"):
            said.append("the match %s" % topic["match"])
        if topic.get("competition") or topic.get("competition_name"):
            c_name = topic.get("competition_name") or topic.get("competition")
            tot = (" with %d matches" % topic["total"]) if topic.get("total") is not None else ""
            said.append("the competition %s%s" % (c_name, tot))
        if topic.get("team"):
            said.append("the team %s" % topic["team"])
        if topic.get("player"):
            said.append("the player %s" % topic["player"])
        if not said:
            return ""
        return (
            " The listener was last talking about %s: read 'they', 'him', 'that game' and similar as this, "
            "unless they name something else. Offer a natural follow-up only when it truly helps." % ", ".join(said)
        )


FOCUSES = Focus()


def _following(ctx, listener_id):
    """The match this listener follows, said to the model straight from the store: the agent's own memory of the
    conversation is lost with a restart, the follow is not. Without it a model rightly asks "which match?" of a listener
    who is already following one, on the first question after the server came back."""
    try:
        rec = ctx.store.listener(listener_id)
        fx = ctx.store.fixture(rec.get("following")) if rec.get("following") else None
    except Exception:                                          # noqa: BLE001 - a prompt line is never worth a failed answer
        return ""
    if not fx or not fx.get("home") or not fx.get("away"):
        return ""
    return (" The listener is following %s against %s. 'The score', 'the line-ups', 'what did I miss', 'who is booked' and "
            "similar are about THIS match: call the tool without a team or a fixture id, and do not ask which match." %
            (fx["home"], fx["away"]))

def _usage(usage):
    """Bedrock's own token counts for one call (Converse returns them), as plain integers."""
    usage = usage if isinstance(usage, dict) else {}
    return {"input": int(usage.get("inputTokens") or 0), "output": int(usage.get("outputTokens") or 0)}


def _listener_answer(text, max_sentences=3):
    """Remove model-emitted private reasoning before display or speech and keep it short enough for voice."""
    text = re.sub(r"<thinking\b[^>]*>.*?</thinking\s*>", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<thinking\b[^>]*>.*$", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?[A-Za-z][^<>]{0,40}>", " ", text)         # a stray <response> wrapper is not for the listener
    text = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    if len(parts) > max_sentences:
        text = " ".join(parts[:max_sentences])
    return text


_SENTENCE_END = re.compile(r"[.!?][\"')\]]*(?=\s|$)")


def _complete_sentences(text):
    """Only the whole sentences of an answer the token limit cut short: half a sentence is never spoken (AG-13)."""
    ends = list(_SENTENCE_END.finditer(text or ""))
    return text[:ends[-1].end()].strip() if ends else ""


_WEATHER_WORDS = re.compile(r"(\d\s*°|\bdegrees\b|\bforecast\b|\brain(y|ing)?\b|\bsunny\b|\bcloud(y|s)\b|"
                            r"\bovercast\b|\bwindy\b|\bshowers?\b|\bsnow(y|ing)?\b|\bhumid)", re.I)


def _invents_weather(text, tool_results):
    """Weather in the answer that no tool reported this turn.

    A small model asked "what's the weather" will happily make some up. Weather is
    only ever said if a tool result in this turn carried it.
    """
    if not _WEATHER_WORDS.search(text):
        return False
    for record in tool_results:
        structured = record.get("structured") or {}
        if structured.get("weather") or "forecast" in (record.get("spoken") or "").lower():
            return False
    return True


_FOLLOW_INTENT = re.compile(r"\b(follow|following|watch|watching|switch|tune|track|"
                            r"put on|listen to|keep me (up|updated)|(fixture_id \d+))", re.I)


def _asked_to_follow(question):
    """Did the listener ask to follow a match, or choose one we offered (the id handoff)?"""
    return bool(_FOLLOW_INTENT.search(question))


_DENIES_LIVE = re.compile(r"\b(can(?:no|')t|unable to|not able to|don't have access to|do not have access to)\b"
                          r"[^.]{0,80}\b(real-?time|live|match|matches|fixture|fixtures|result|results|score|scores|champions league|premier league)\b", re.I)


def _denies_live(text):
    """A model telling the listener Sideline cannot do the one thing it exists for."""
    return bool(_DENIES_LIVE.search(text))


def _today(ctx, listener_id):
    """Today's date in the listener's own zone, so a date the model writes has the right year."""
    try:
        from sideline import clock
        tz = clock.zone_from(ctx.store.listener(listener_id))
        day = (clock.now() + datetime.timedelta(minutes=int(tz or 0)))
        coming = ", ".join("%s is %s" % ((day + datetime.timedelta(days=n)).strftime("%A"),
                                         (day + datetime.timedelta(days=n)).strftime("%Y-%m-%d")) for n in range(1, 8))
        # the next seven days, spelled out: a small model gets "Saturday" wrong by a day when it must count
        return " Today is %s. The coming days: %s." % (day.strftime("%A %d %B %Y"), coming)
    except Exception:                                      # noqa: BLE001  a courtesy, never a failure
        return ""


def _detail(ctx, listener_id):
    """How much the listener asked us to say (set_preferences): "brief", "normal", "full" or None."""
    try:
        return ctx.store.listener(listener_id).get("detail")
    except Exception:                                      # noqa: BLE001  a courtesy, never a failure
        return None


def _preference(ctx, listener_id, detail=False):
    """The listener's own wish for how much to say (set_preferences), as one more instruction."""
    if detail is False:
        detail = _detail(ctx, listener_id)
    return {"brief": " The listener asked for brief answers: one short sentence.",
            "full": " The listener asked for more detail: up to five short sentences."}.get(detail, "")


_PARTS = (("substitutions", re.compile(r"\b(came on|come on|substitut\w*|subs?|replaced|brought on|came off|went off)\b", re.I)),
          ("cards", re.compile(r"\b(cards?|booked|bookings?|yellows?|reds?|sent off|dismissed|red card)\b", re.I)),
          ("var", re.compile(r"\b(var|video review|overturned|disallowed)\b", re.I)),
          ("goals", re.compile(r"\b(scored|scorers?|goals?|assists?|assisted|who got)\b", re.I)))


def _fill_arguments(name, args, question):
    """Arguments a small model leaves out although the question gives them away.

    Optional arguments are the first thing it drops: asked "who came on?" it called get_match_report with no `part`
    and the whole report was read out again. Where the words of the question say it, it is set here, never overriding
    what the model did pass.
    """
    if not isinstance(args, dict):
        return args
    if name == "get_match_report" and not args.get("part"):
        for part, pattern in _PARTS:
            if pattern.search(question):
                return dict(args, part=part)
    if name == "get_fixtures":
        filled = dict(args)
        if not filled.get("live_only") and re.search(r"\b(live|life|under way|right now|currently playing)\b", question, re.I):
            filled["live_only"] = True
        if not filled.get("competition"):
            for pat, slug, name_str in COMP_PATTERNS:
                if pat.search(question):
                    filled["competition"] = name_str
                    break
            if not filled.get("competition"):
                m = re.search(r"\b(korean?|south korea|japanese?|japan|scottish?|scotland|turkish?|turkey|danish|denmark|swedish|sweden)\b", question, re.I)
                if m:
                    country_map = {"korean": "Korea", "korea": "Korea", "south korea": "Korea", "japanese": "Japan", "japan": "Japan",
                                   "scottish": "Scotland", "scotland": "Scotland", "turkish": "Turkey", "turkey": "Turkey",
                                   "danish": "Denmark", "denmark": "Denmark", "swedish": "Sweden", "sweden": "Sweden"}
                    filled["competition"] = country_map.get(m.group(1).lower(), m.group(1).capitalize())
        return filled
    return args


def _plain_strings(value):
    """Text a model sometimes sends HTML-escaped (&quot;Celtic&quot;) or in quotes, as the listener said it."""
    if isinstance(value, str):
        return html.unescape(value).strip().strip("\"'").strip()
    if isinstance(value, dict):
        return {k: _plain_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain_strings(v) for v in value]
    return value


def _without_invented_id(args, question):
    """A fixture id the listener did not give is one the model made up: drop it.

    Tools default to the match being followed. The only ids a model may pass are the ones
    we put in the message ourselves ("(fixture_id 7)", resolve.py), after an offered choice.
    """
    if not isinstance(args, dict) or "fixture_id" not in args:
        return args
    # whole id only: "(fixture_id 12)" does not vouch for an invented 1 (AG-22)
    if re.search(r"\bfixture_id %s\b" % re.escape(str(args["fixture_id"])), question):
        return args
    return {k: v for k, v in args.items() if k != "fixture_id"}


def _without_invented_competition(args, question):
    """A competition the listener did not say is one the model took from the examples in a tool description.

    Asked "what are the next matches?" it passed "Premier League", and the answer was about a league this feed
    does not cover. A competition stays only when one of its words is in the question.
    """
    if not isinstance(args, dict) or not args.get("competition"):
        return args
    said = set(re.findall(r"[a-z0-9]+", question.lower()))
    words = [w for w in re.findall(r"[a-z0-9]+", str(args["competition"]).lower()) if w not in ("the", "league", "cup")]
    if any(w in said for w in words):
        return args
    return {k: v for k, v in args.items() if k != "competition"}


# AWS answers "capacity limit reached" or "slow down" at once, and the same request a moment later usually works. The
# client is set to no automatic retries (a retry after a timeout would double the wait), so this one retry is only for
# those quick refusals.
_BUSY = ("ServiceUnavailableException", "ThrottlingException", "ModelNotReadyException", "InternalServerException")
BUSY_RETRY_SECONDS = 0.6


def _converse(**kwargs):
    from sideline.language import bedrock
    try:
        return bedrock.client().converse(**kwargs)
    except Exception as exc:                                    # noqa: BLE001
        code = ((getattr(exc, "response", None) or {}).get("Error") or {}).get("Code")
        if code not in _BUSY:
            raise
        LOG.info("bedrock busy (%s): trying once more", code)
        time.sleep(BUSY_RETRY_SECONDS)
        return bedrock.client().converse(**kwargs)


# The JSON Schema words a model needs to form a call. Length and range limits are left to the server, which still
# validates every call against the full schema; dropping them keeps the prompt small and avoids keywords a
# Bedrock model may refuse (AG-20).
_SCHEMA_KEYS = ("type", "description", "properties", "required", "enum", "items", "additionalProperties")


def _model_schema(schema):
    if not isinstance(schema, dict):
        return schema
    out = {}
    for key in _SCHEMA_KEYS:
        if key not in schema:
            continue
        value = schema[key]
        if key == "properties" and isinstance(value, dict):
            value = {name: _model_schema(sub) for name, sub in value.items()}
        elif key == "items":
            value = _model_schema(value)
        out[key] = value
    return out


def _bedrock_tools(mcp_tools):
    """Adapt the MCP server's current tools/list result to Bedrock's schema."""
    if not isinstance(mcp_tools, list):
        raise AgentUnavailable("MCP tools/list returned no tool catalog")
    tools = []
    for spec in mcp_tools:
        if (not isinstance(spec, dict)
                or not isinstance(spec.get("name"), str)
                or not isinstance(spec.get("inputSchema"), dict)):
            raise AgentUnavailable("MCP tools/list returned an invalid tool definition")
        tools.append(
            {"toolSpec": {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "inputSchema": {"json": _model_schema(spec["inputSchema"])},
            }})
    return tools




def _normalise(question):
    """The question as plain lower-case words, the way the patterns below are written."""
    text = (question or "").lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"[^\w'&-]+", " ", text)
    return " ".join(text.split())


_FILLER = re.compile(r"^(?:(?:hey|ok|okay|so|and|um|uh|right|well|sideline|alexa|alright|cool|great|nice|beautiful|good)\b ?)+")
_POLITE = re.compile(r"(?: please| then| now please)$")


def _core_words(question):
    """The question without a leading "hey sideline, so..." or a trailing "please"."""
    text = _FILLER.sub("", _normalise(question))
    return _POLITE.sub("", text).strip()


# Only for an utterance that is nothing but a greeting or a question about Sideline itself: "Hey, what's the score?"
# and "Thanks, who scored?" are real questions and go to the model (AG-07).
_CONVERSATIONAL_PATTERNS = [
    (re.compile(r"(?:can you (?:access|cover|track|follow|do)|do you (?:support|cover|have|do)) (?:any )?(?:other )?sports"
                r"|(?:what|which) (?:other )?sports (?:do|can) you (?:cover|support|do|track|follow|have)"),
     "I cover Football (soccer), Basketball, American Football (NFL), Baseball (MLB) and Hockey (NHL): live scores, "
     "fixtures, results and catch-ups on what you missed."),
    (re.compile(r"who are you|what(?: is|'s) your name|what are you"),
     "I'm Sideline, your live sports companion. Ask me for a score, what's on, or what you missed."),
    (re.compile(r"(?:how (?:are you|are you doing|are you doing today|is it going|are things|r u|do you do)|how's it going|how are you today)(?: sideline)?"),
     "I'm doing well, ready for the action! Ask me for a live score, what's on today, or what you missed."),
    (re.compile(r"(?:(?:so )?how does (?:it|this) work|what can you do|how do i use (?:this|sideline))"),
     "I'm Sideline, your live sports companion. Just ask me by voice or text for live scores, fixtures, standings, or catch-ups on what you missed in a match."),
    (re.compile(r"(?:hello|hi|hey|good (?:morning|afternoon|evening))(?: there)?(?: sideline)?"),
     "Hey there! Ask me for a live score, what's on today, or what you missed."),
    (re.compile(r"(?:thanks|thank you|cheers|great thanks)(?: very much| a lot| so much)?(?: sideline)?"),
     "You're welcome! Shout if you want another score."),
    (re.compile(r"(?:goodbye|bye|bye bye|see you|that's all|that is all)(?: for now)?"),
     "Goodbye! Enjoy the game."),
]


def _match_conversational(question):
    clean = _POLITE.sub("", _normalise(question)).strip()
    for pattern, answer in _CONVERSATIONAL_PATTERNS:
        if pattern.fullmatch(clean):
            return answer
    parts = [s.strip() for s in re.split(r"[.!?]+", question or "") if s.strip()]
    if len(parts) > 1:
        for part in reversed(parts):
            p_clean = _POLITE.sub("", _normalise(part)).strip()
            for pattern, answer in _CONVERSATIONAL_PATTERNS:
                if pattern.fullmatch(p_clean):
                    return answer
    return None


# ------------------------------------------------------------------ which tools the model is shown
# Words that point at a tool, keyed by the real tool names. The names themselves are words too, so a tool added to the
# server later still has a way in; a name in this table that the server does not list is simply never offered.
_TOOL_KEYWORDS = {
    "get_match_state": ["score", "scores", "winning", "losing", "leading", "minute", "clock", "quarter", "inning",
                        "period", "time left", "how long", "won", "win", "lost", "draw", "status"],
    "what_did_i_miss": ["miss", "missed", "happened", "catch me up", "catch up", "recap", "fill me in"],
    "get_fixtures": ["fixtures", "today", "tonight", "tomorrow", "yesterday", "games", "matches", "what's on", "live",
                     "finished", "results", "completed"],
    "get_schedule": ["next", "last", "when", "what time", "results", "fixtures", "playing next", "play next"],
    "follow_match": ["follow", "following", "track", "keep me updated", "watch", "watching", "listen", "switch",
                     "stop following"],
    "get_lineups": ["lineup", "lineups", "line-up", "line-ups", "starting", "xi", "eleven", "bench", "formation",
                    "team sheet", "playing"],
    "get_match_report": ["scored", "scorer", "scorers", "goals", "booked", "booking", "bookings", "card", "cards",
                         "yellow", "red", "sub", "subs", "substitute", "substitutes", "substitution", "came on", "var",
                         "report"],
    "get_match_stats": ["stats", "statistics", "possession", "shots", "corners", "fouls"],
    "get_match_preview": ["preview", "weather", "forecast", "venue", "stadium", "kick off", "kick-off", "kickoff",
                          "start", "starts", "where"],
    "get_officials": ["referee", "ref", "refereeing", "official", "officials", "umpire", "var"],
    "get_head_to_head": ["head to head", "head-to-head", "h2h", "beaten", "beat", "last time", "meetings", "history"],
    "get_team_form": ["form", "streak", "been playing", "recent"],
    "get_injuries": ["injured", "injury", "injuries", "suspended", "suspension", "fitness", "doubtful", "fit"],
    "get_top_scorers": ["top scorer", "top scorers", "golden boot", "leading scorer", "most goals"],
    "get_standings": ["table", "standings", "top of", "bottom", "position", "points", "relegation", "league",
                      "rank", "first place"],
    "get_squad": ["squad", "roster", "goalkeeper", "keeper", "manager", "coach", "players"],
    "get_team_stats": ["season", "stats", "doing this season"],
    "get_player_stats": ["this season", "goals", "assists", "has he scored", "has she scored"],
    "get_player_context": ["who is", "number", "he", "him", "his", "she", "her", "player"],
    "get_event_detail": ["that goal", "assisted", "assist", "again", "that card", "tell me about that"],
    "sync_broadcast_delay": ["kick-off just", "half time", "half-time", "just scored", "whistle", "sync", "delay",
                             "spoiled", "spoiler", "behind", "ahead", "stream", "radio", "broadcast"],
    "set_favourites": ["support", "my team", "favourite", "favourites", "favorite", "favorites"],
    "get_my_matches": ["my teams", "my matches", "for me", "my team"],
    "set_preferences": ["short", "shorter", "brief", "detail", "more detail", "speak", "language", "keep it"],
    "get_capabilities": ["help", "what can you do", "what can i ask"],
    "search": ["called", "find", "search", "is there a team"],
    "get_competitions": ["leagues", "competitions", "cover", "what leagues"],
}
_NAME_STOPWORDS = frozenset(("get", "set", "my", "match", "team", "player", "what", "did", "i", "of"))

# Always offered: the questions most listeners ask. Everything else must be pointed at by the question.
_CORE_TOOLS = ("get_fixtures", "get_match_state", "get_schedule", "what_did_i_miss")
MAX_EXTRA_TOOLS = 4

_KEYWORD_RES = {}


def _keyword_re(word):
    found = _KEYWORD_RES.get(word)
    if found is None:
        # whole words only: "on" is not in "Lyon", "ref" is not in "prefer" (AG-02)
        found = _KEYWORD_RES[word] = re.compile(r"(?<![\w'])%s(?![\w'])" % re.escape(word))
    return found


_EXAMPLE_FILLER = frozenset("the and for that this them they have does what when where which with about from into your you are was were "
                            "has had his her its our not any all can how who why get set".split())
_EXAMPLE_PHRASE = re.compile(r"'((?:[^']|(?<=\w)'(?=\w)){4,70})'")       # an apostrophe inside a word ("what's") is not a quote


def _example_keywords(spec):
    """Words and short phrases from the examples a tool's description gives ("Say: 'who is Haaland', 'how old is Saka'").

    The descriptions already say how a listener asks for each tool, so the shortlist reads them: a tool added tomorrow is
    reachable as soon as it is described, with no table to remember to extend. Capitalised words (names a listener
    would fill in) are dropped; what is left is how the question is put.
    """
    found = set()
    for phrase in _EXAMPLE_PHRASE.findall((spec or {}).get("description") or ""):
        tokens = [t for t in re.findall(r"[A-Za-z']+", phrase)]
        lower = []
        for t in tokens:
            if t[:1].isupper() and t != tokens[0]:
                break                                           # a name: the phrase is over
            lower.append(t.lower())
        if len(lower) >= 2:
            found.add(_normalise(" ".join(lower[:5])))          # "who is", "how old is", "whats the latest on"
        for t in lower:
            t = _normalise(t)
            if len(t) >= 4 and t not in _EXAMPLE_FILLER:
                found.update((t, t[:-1] if t.endswith("s") else t + "s"))      # goalkeeper / goalkeepers
    found.discard("")
    return found


def _keywords(name, spec=None):
    words = set(_TOOL_KEYWORDS.get(name, ()))
    words.update(w for w in name.split("_") if len(w) > 2 and w not in _NAME_STOPWORDS)
    words.update(_example_keywords(spec))
    return words


def _select_candidate_tools(question, mcp_tools, context_topic=None):
    """The live tools worth showing the model for this question: a fixed core plus the best keyword matches.

    Names come from the server's own tools/list, never from a list of our own (AG-02, AG-03). The result is sorted
    by name, so the same question always produces the same prompt.
    """
    live = {spec["name"]: spec for spec in mcp_tools if isinstance(spec, dict) and spec.get("name")}
    text = _normalise(question)
    chosen = set(n for n in _CORE_TOOLS if n in live)
    scored = []
    words_of = {name: _keywords(name, live[name]) for name in live}
    shared = {}                                          # in how many tools' vocabularies each word appears
    for words in words_of.values():
        for word in words:
            shared[word] = shared.get(word, 0) + 1
    for name in live:
        if name in chosen:
            continue
        # a word many tools share ("what's the") says little; one only this tool uses ("table", "news") says a lot
        score = sum((2 if " " in word else 1) / float(shared[word]) for word in words_of[name] if _keyword_re(word).search(text))
        if score:
            scored.append((-score, name))
    chosen.update(name for _, name in sorted(scored)[:MAX_EXTRA_TOOLS])
    if not chosen:
        return list(mcp_tools)
    return [live[name] for name in sorted(chosen)]


# ------------------------------------------------------------------ shortcuts that skip the model
# Each is the WHOLE question, so "what's the score" fires and "what's the score of the golden boot race" does not
# (AG-09). They only ever run tools that change nothing (AG-01): if a shortcut fails, nothing is lost and the model
# answers instead. A (?P<team>...) must be a team the feed knows, or the model is asked instead.
_ON = r"(?: on| playing| there)?(?: today| tonight)?"
_FAST_PATTERNS = [
    (r"(?:what's|what is|whats) the score(?: now| right now| at the moment)?", "get_match_state", {}),
    (r"(?:what's|what is|whats) the score (?:in|of) the (?P<team>.+?) (?:game|match)", "get_match_state", {}),
    (r"(?:what's|what is|whats) the (?P<team>.+?) score", "get_match_state", {}),
    (r"(?:who's|who is|whos) winning(?: the (?P<team>.+?) (?:game|match))?", "get_match_state", {}),
    (r"(?:how long|how much time)(?: is)? left", "get_match_state", {}),
    (r"what minute is it", "get_match_state", {}),
    (r"(?:what's|what is|whats) on(?: today| tonight)?", "get_fixtures", {}),
    (r"what (?:games|matches|fixtures) are" + _ON, "get_fixtures", {}),
    (r"(?:are there )?any (?:games|matches)" + _ON, "get_fixtures", {}),
    (r"which teams are playing(?: today| tonight)?", "get_fixtures", {}),
    (r"(?:today's|tonight's) (?:games|matches|fixtures)", "get_fixtures", {}),
    (r"(?:games|matches|fixtures) (?:today|tonight)", "get_fixtures", {}),
    (r"(?:what|which) (?:games|matches) (?:have )?(?:already )?(?:finished|ended)(?: today)?", "get_fixtures",
     {"finished_only": True}),
    (r"(?:today's )?results(?: today| so far)?", "get_fixtures", {"finished_only": True}),
    (r"(?:what's|what is|whats) live(?: now)?", "get_fixtures", {"live_only": True}),
    (r"(?:(?:show me|what's|what is|whats) )?the (?:league )?(?:table|standings)", "get_standings", {}),
    (r"(?:league )?(?:table|standings)", "get_standings", {}),
    (r"(?:who's|who is|whos) (?:the )?(?:ref|referee|refereeing)(?: today)?", "get_officials", {}),
    (r"(?:who's|who is|whos) (?:injured|suspended)", "get_injuries", {}),
    (r"any injuries|injury (?:news|list)", "get_injuries", {}),
    (r"(?:when's|when is|whens) the next (?:game|match)", "get_schedule", {"which": "next"}),
    (r"(?:when's|when is|whens) (?P<team>.+?)'s next (?:game|match)", "get_schedule", {"which": "next"}),
    (r"when (?:is|are|do|does) (?P<team>.+?) play(?:ing)?(?: next)?", "get_schedule", {"which": "next"}),
    (r"(?:(?:what are|tell me about|i want to know about|show me|any)\s+)?(?:the\s+)?(?:next\s+)?fixtures\s+(?:of|for)\s+(?P<team>.+)", "get_schedule", {"which": "next"}),
    (r"(?:(?:what are|tell me about|i want to know about|show me)\s+)?(?P<team>.+?)'s\s+(?:next\s+)?fixtures", "get_schedule", {"which": "next"}),
    (r"(?P<team>.+?)\s+(?:next\s+)?fixtures", "get_schedule", {"which": "next"}),
    (r"what can you do|what can i ask(?: you)?|help", "get_capabilities", {}),
]
_FAST_PATTERNS = [(re.compile(p), tool, args) for p, tool, args in _FAST_PATTERNS]

_HOW_MANY = re.compile(r"how many (?:matches|games)(?: are there| is that| in total| total| are on)?(?: today)?")
_SPORT_KEYS = {"nba": "basketball", "nfl": "american_football"}
_SAID_DAYS = ("today", "tonight", "tomorrow", "yesterday")


def _schema_args(name, args, tool_specs):
    """Only the arguments the tool's schema has: every schema refuses anything else (AG-04)."""
    props = ((tool_specs.get(name) or {}).get("inputSchema") or {}).get("properties") or {}
    return {k: v for k, v in args.items() if k in props and v not in (None, "")}


def _known_team(ctx, said):
    """The one team the feed knows by this name (whole words), or None: a guess is never passed on."""
    said = _normalise(said)
    if not said:
        return None
    from sideline.tools import NICKNAMES
    norm_nick = NICKNAMES.get(said)
    teams = []
    if ctx and hasattr(getattr(ctx, "provider", None), "known_teams"):
        try:
            teams = list(ctx.provider.known_teams() or [])
        except Exception:                                      # noqa: BLE001  the model can still answer
            teams = []
    from sideline.resolve import POPULAR_TEAMS
    seen = set(teams)
    for pt in POPULAR_TEAMS:
        if pt not in seen:
            teams.append(pt)
            seen.add(pt)
    exact = [t for t in teams if _normalise(t) == said or (norm_nick and _normalise(t) == norm_nick)]
    if exact:
        return exact[0]
    near = [t for t in teams if re.search(r"(?<!\w)%s(?!\w)" % re.escape(said), _normalise(t))]
    return near[0] if len(near) == 1 else None


def _scope(text):
    """A competition or sport named in the question: (text without it, {argument: value}) or (text, None)."""
    for pat, key, name in COMP_PATTERNS:
        m = pat.search(text)
        if m:
            rest = " ".join((text[:m.start()] + " " + text[m.end():]).split())
            sport = _SPORT_KEYS.get(key)
            return rest, ({"sport": sport} if sport else {"competition": name})
    return text, None


def _how_many(question, topic):
    """"How many is that?" straight after a fixture list: the count it already gave (AG-08)."""
    if topic.get("last_tool") != "get_fixtures" or topic.get("total") is None:
        return None
    text = _core_words(question)
    if not _HOW_MANY.fullmatch(text):
        return None
    when = str(topic.get("when") or "")
    if "today" in text and when != "today":
        return None
    total = int(topic["total"])
    kind = topic.get("fixtures_kind") or ""
    comp = topic.get("competition_name") or ""
    where = (" in %s%s" % ("the " if comp.lower().endswith(("league", "cup")) else "", comp)) if comp else ""
    day = (" " + when) if when in _SAID_DAYS or when.startswith("on ") else ""
    return "That's %d %s%s%s%s." % (total, (kind + " ") if kind else "", "match" if total == 1 else "matches",
                                     where, day)


def _fast_plan(question, tool_specs, topic, ctx):
    """The one read-only tool call a question plainly asks for, or None when the model should decide."""
    text = _core_words(question)
    rest, scope = _scope(text)
    plans = []
    for pattern, tool, fixed in _FAST_PATTERNS:
        if tool not in tool_specs or tool in STATEFUL_TOOLS:
            continue
        props = (tool_specs[tool].get("inputSchema") or {}).get("properties") or {}
        if scope:
            # A competition only narrows a tool that takes one; "the Premier League score" is for the model.
            if not set(scope) <= set(props):
                continue
            m = pattern.fullmatch(rest)
        else:
            m = pattern.fullmatch(text)
        if m:
            plans.append((tool, dict(fixed, **(scope or {})), m.groupdict().get("team")))
    if len(set(p[0] for p in plans)) != 1:
        return None                                   # nothing, or more than one tool fits: the model decides
    tool, args, said_team = plans[0]
    if said_team:
        team = _known_team(ctx, said_team)
        if not team:
            return None
        args["team"] = team
    required = (tool_specs[tool].get("inputSchema") or {}).get("required") or []
    if "team" in required and not args.get("team"):
        if not topic.get("team"):
            return None
        args["team"] = topic["team"]
    return tool, _schema_args(tool, args, tool_specs)


def _conversationalize_score(text, structured):
    if not isinstance(structured, dict):
        return text
    home = structured.get("home")
    away = structured.get("away")
    score = structured.get("score")
    if not home or not away or not isinstance(score, dict):
        return text
    h_score = score.get("home")
    a_score = score.get("away")
    if h_score is None or a_score is None:
        return text
    status = str(structured.get("status") or "")
    minute = structured.get("minute")
    series = structured.get("series")
    unconf = structured.get("score_unconfirmed")

    # Finished match
    if status in ("FT", "AET", "PEN", "finished"):
        if h_score > a_score:
            out = f"It's full time: {home} took the win {h_score}-{a_score} against {away}."
        elif a_score > h_score:
            out = f"It's full time: {away} took the win {a_score}-{h_score} against {home}."
        elif h_score == 0:
            out = f"It's full time: it finished goalless between {home} and {away}."
        else:
            out = f"It's full time: it finished all square, {h_score}-{a_score} between {home} and {away}."
    elif status in ("HT", "half time"):
        if h_score > a_score:
            out = f"At half time, {home} are leading {away} {h_score}-{a_score}."
        elif a_score > h_score:
            out = f"At half time, {away} are leading {home} {a_score}-{h_score}."
        elif h_score == 0:
            out = f"At the break, {home} and {away} are still goalless at 0-0."
        else:
            out = f"At half time, it's level at {h_score}-{a_score} between {home} and {away}."
    elif minute and minute > 0:
        if h_score > a_score:
            out = f"{home} are leading {away} {h_score}-{a_score}, {minute} minutes in."
        elif a_score > h_score:
            out = f"{away} are leading {home} {a_score}-{h_score}, {minute} minutes in."
        elif h_score == 0:
            out = f"{home} and {away} are still goalless, {minute} minutes in."
        else:
            out = f"It's all square between {home} and {away} at {h_score}-{a_score}, {minute} minutes in."
    elif minute == 0 and "just under way" in text:
        out = f"{home} against {away} is just under way, still goalless."
    elif "kick-off is" in text or "kicking off" in text:
        m = re.search(r"kick-off is (.+?)(?:\.|$)", text)
        if m:
            ko_part = m.group(1).rstrip(".")
            out = f"{home} play {away}, kicking off {ko_part}."
        else:
            out = f"{home} play {away}."
    else:
        out = text

    if series:
        out = out.rstrip(".") + f". {series.rstrip('.')}."
    if unconf:
        out = out.rstrip(".") + ". I can't be sure that is where your screen is."
    return out


def _conversationalize_fixtures(text, structured):
    if not text or not isinstance(text, str):
        return text
    if ":" not in text:
        return text

    m_intro = re.match(r"^(.*?):\s*(.+)$", text)
    if not m_intro:
        return text
    intro_part, body_part = m_intro.group(1), m_intro.group(2)

    more_suffix = ""
    m_more = re.search(r"\s*And (\d+) more\..*$", body_part)
    if m_more:
        more_count = m_more.group(1)
        body_part = body_part[:m_more.start()]
        more_suffix = f" Plus {more_count} more matches on the schedule."

    match_items = [item.strip() for item in body_part.split(". ") if item.strip()]
    if not match_items:
        return text

    conv_intro = intro_part
    if conv_intro.startswith("Nothing "):
        conv_intro = re.sub(r"^Nothing\s+(\w+)\s+(in\s+.+?)\.\s*The next matches are\s+", r"There are no matches \1 \2. Looking ahead to ", conv_intro)
        conv_intro = re.sub(r"^Nothing\s+(\w+)\.\s*The next matches are\s+", r"There are no matches \1. Looking ahead to ", conv_intro)
    elif conv_intro.startswith("Today in ") or conv_intro.startswith("Tomorrow in ") or conv_intro.startswith("Yesterday in "):
        conv_intro = "Here's what's on " + conv_intro[:1].lower() + conv_intro[1:]
    elif conv_intro.lower() in ("today", "tomorrow", "yesterday"):
        conv_intro = f"Looking at {conv_intro.lower()}'s fixtures"

    time_groups = OrderedDict()
    live_items = []
    finished_items = []
    other_items = []

    for item in match_items:
        comp_prefix = ""
        if ": " in item:
            comp_prefix, item = item.split(": ", 1)

        m_at = re.match(r"^(.+?)\s+against\s+(.+?)\s+at\s+(.+?)$", item.rstrip("."))
        m_live = re.match(r"^(.+?)\s+against\s+(.+?),\s*live(?:,\s*(.+?))?$", item.rstrip("."))
        m_fin_score = re.match(r"^(.+?)\s+(\d+),\s*(.+?)\s+(\d+),\s*finished$", item.rstrip("."))
        m_fin = re.match(r"^(.+?)\s+against\s+(.+?),\s*finished$", item.rstrip("."))

        if m_at:
            h, a, t = m_at.group(1), m_at.group(2), m_at.group(3)
            time_groups.setdefault(t, []).append((h, a, comp_prefix))
        elif m_live:
            h, a, min_info = m_live.group(1), m_live.group(2), m_live.group(3)
            live_items.append((h, a, min_info))
        elif m_fin_score:
            h, hs, a, ascore = m_fin_score.group(1), m_fin_score.group(2), m_fin_score.group(3), m_fin_score.group(4)
            finished_items.append((h, hs, a, ascore))
        elif m_fin:
            h, a = m_fin.group(1), m_fin.group(2)
            finished_items.append((h, None, a, None))
        else:
            other_items.append(item.rstrip("."))

    if not time_groups and not live_items and not finished_items:
        return text

    spoken_sentences = []

    for h, a, min_info in live_items:
        detail = f", {min_info}" if min_info else ", live"
        spoken_sentences.append(f"{h} are playing {a}{detail}")

    for item in finished_items:
        h, hs, a, ascore = item
        if hs is not None and ascore is not None:
            if int(hs) > int(ascore):
                spoken_sentences.append(f"{h} beat {a} {hs}-{ascore}")
            elif int(ascore) > int(hs):
                spoken_sentences.append(f"{a} beat {h} {ascore}-{hs}")
            else:
                spoken_sentences.append(f"{h} and {a} drew {hs}-{ascore}")
        else:
            spoken_sentences.append(f"{h} against {a} has finished")

    num_groups = len(time_groups)
    for g_idx, (kickoff_time, matchups) in enumerate(time_groups.items()):
        if num_groups == 1:
            time_intro = f"At {kickoff_time}, "
        elif g_idx == 0:
            time_intro = f"First at {kickoff_time}, "
        elif g_idx == num_groups - 1:
            time_intro = f"Later at {kickoff_time}, "
        else:
            time_intro = f"Then at {kickoff_time}, "

        if len(matchups) == 1:
            h, a, cp = matchups[0]
            cp_str = f" in the {cp}" if cp else ""
            spoken_sentences.append(f"{time_intro}{h} take on {a}{cp_str}")
        elif len(matchups) == 2:
            (h1, a1, cp1), (h2, a2, cp2) = matchups
            spoken_sentences.append(f"{time_intro}{h1} host {a1}, while {h2} face {a2}")
        else:
            first = f"{matchups[0][0]} host {matchups[0][1]}"
            mid = f"{matchups[1][0]} face {matchups[1][1]}"
            last = f"and {matchups[2][0]} take on {matchups[2][1]}"
            spoken_sentences.append(f"{time_intro}{first}, {mid}, {last}")

    for oi in other_items:
        spoken_sentences.append(oi)

    if not spoken_sentences:
        return text

    games_text = ". ".join(spoken_sentences) + "."
    return f"{conv_intro}: {games_text}{more_suffix}"


def _conversationalize_schedule(text, structured):
    if not text or not isinstance(text, str):
        return text
    m_header = re.match(r"^(.+?)'s next (\d+) fixtures:\s*(.+)$", text)
    if not m_header:
        return text
    team = m_header.group(1)
    body = m_header.group(3)
    items = [i.strip() for i in body.split(". ") if i.strip()]
    if not items:
        return text

    parsed = []
    for it in items:
        it_clean = it.rstrip(".")
        m_game = re.match(r"^(?:(?:On|on)\s+)?(\w+)\s+against\s+(.+?)(?:\s+at\s+(.+))?$", it_clean)
        if m_game:
            day, opp, time_part = m_game.group(1), m_game.group(2), m_game.group(3)
            time_str = f" at {time_part}" if time_part else ""
            day_str = day if day.lower() in ("today", "tomorrow", "yesterday") else f"on {day}"
            parsed.append(f"{opp} {day_str}{time_str}")
        else:
            parsed.append(it_clean)

    if not parsed:
        return text

    if len(parsed) == 1:
        return f"{team} are in action against {parsed[0]}."
    elif len(parsed) == 2:
        return f"{team} play {parsed[0]}, followed by {parsed[1]}."
    else:
        return f"{team} play {parsed[0]}, followed by {parsed[1]}, and {parsed[2]}."


def _conversational_text(text, tool_name, structured=None):
    if not text or not isinstance(text, str):
        return text
    try:
        if tool_name == "get_match_state":
            return _conversationalize_score(text, structured)
        if tool_name == "get_fixtures":
            return _conversationalize_fixtures(text, structured)
        if tool_name == "get_schedule":
            return _conversationalize_schedule(text, structured)
    except Exception:
        return text
    return text


def _try_fast_path(question, listener_id, tool_runner, tool_specs, ctx=None):
    """Answer a plain, unambiguous question with one read-only tool and no model call, or return None."""
    topic = FOCUSES.topic(listener_id)
    counted = _how_many(question, topic)
    if counted:
        CONVERSATIONS.remember(listener_id, question, counted)
        return {"text": counted, "generated_by": "fast", "tool_results": []}

    plan = _fast_plan(question, tool_specs, topic, ctx)
    if not plan:
        return None
    name, args = plan
    _, is_err, record = _execute_tool(name, args, listener_id, tool_runner, tool_specs)
    record["args"] = args
    if is_err or not record.get("spoken"):
        # Read-only, so nothing was used up: the model takes it from here and can explain.
        return None
    text = _conversational_text(" ".join(record["spoken"].split()), name, record.get("structured"))
    CONVERSATIONS.remember(listener_id, question, text)
    FOCUSES.remember(listener_id, [record])
    return {"text": text, "generated_by": "fast", "tool_results": [record]}


# ------------------------------------------------------------------ the model loop
# A single factual tool whose sentence is already ear-ready is said as it is, saving a second model call. Never a tool
# that only returns facts for the model (what_did_i_miss for the agent speaks "").
_SAID_AS_IS = frozenset(("get_player_profile", "get_news", "get_standouts",
                         "get_fixtures", "get_match_state", "get_officials", "get_lineups", "get_injuries",
                         "get_head_to_head", "get_match_preview", "get_team_form", "get_match_stats", "get_team_stats",
                         "get_player_stats", "get_match_report", "get_capabilities", "get_schedule", "get_standings",
                         "get_top_scorers", "get_squad"))

COMBINE = ("Combine the tool results into one concise, natural spoken answer using only facts they contain: most "
           "important first, in complete sentences. "
           "Do not read out raw lists, colons, or schedules like a timetable; weave scores and fixtures into conversational spoken sentences. "
           "If a result failed, do not read it out; say briefly what you couldn't get.")
FINAL = "[No more tools now. Answer the listener from what you already have, or say briefly what you couldn't get.]"


def _spoken_from_tools(tool_results):
    """What the tools themselves said, when the model gave nothing: answers first, then a tool's own refusal.

    An error (bad arguments, a transport failure) is never spoken (AG-06).
    """
    for usable in (lambda r: not r.get("is_error"), lambda r: r.get("declined")):
        parts = [_conversational_text(" ".join(r["spoken"].split()), r.get("name"), r.get("structured"))
                 for r in tool_results if r.get("spoken") and usable(r)]
        if parts:
            return " ".join(parts)
    return ""


def _text_only(messages):
    """The conversation with tool calls and results written out as text, for a call that offers no tools.

    Bedrock refuses toolUse and toolResult blocks without a toolConfig, so the last answer call reads them as text.
    """
    out = []
    for message in messages:
        parts = []
        for block in message.get("content", []):
            if not isinstance(block, dict):
                continue
            if isinstance(block.get("text"), str) and block["text"].strip():
                parts.append(block["text"])
            elif "toolUse" in block:
                use = block["toolUse"]
                parts.append("[Called %s with %s]" % (use.get("name"), json.dumps(use.get("input"), ensure_ascii=False)))
            elif "toolResult" in block:
                said = " ".join(c.get("text", "") for c in block["toolResult"].get("content", []) if isinstance(c, dict))
                parts.append("[Result: %s]" % said)
        text = "\n".join(parts) or "..."
        if out and out[-1]["role"] == message.get("role"):
            out[-1]["content"][0]["text"] += "\n" + text
        else:
            out.append({"role": message.get("role"), "content": [{"text": text}]})
    return out


_TRACE = threading.local()


def note(**fields):
    """Something worth showing in the Dev log about how this turn was handled (the shortlist, a retry, a shortcut)."""
    if not hasattr(_TRACE, "notes"):
        _TRACE.notes = {}
    _TRACE.notes.update(fields)


def note_tool_meta(meta):
    _TRACE.tool_meta = meta or {}


def _trim_json(obj, cap=1800):
    if not obj:
        return ""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(obj)
    return text if len(text) <= cap else text[:cap - 1] + "\u2026"


def _trace_calls():
    """The model calls made so far for this question: each one's time, tokens and stop reason. For the developer log."""
    if not hasattr(_TRACE, "calls"):
        _TRACE.calls = []
    return _TRACE.calls


def _ask(system, messages, tool_config=None):
    """One Converse call. Any failure is AgentUnavailable: the listener hears that we're unavailable, not why."""
    from sideline.language import bedrock
    request = {
        "modelId": bedrock.MODEL_ID,
        "system": [{"text": system}],
        "messages": messages,
        "inferenceConfig": {"maxTokens": MAX_TOKENS, "temperature": 0.2},
    }
    if tool_config:
        request["toolConfig"] = tool_config
    started = time.time()
    try:
        try:
            response = _converse(**request) or {}
        except Exception as first:
            # A read timeout or a throttle is usually fine a moment later: one more try, rather than "Sorry, an error
            # occurred" for the first question of a session (logged three times in two days). Anything else fails at once.
            if not re.search(r"timeout|timed out|throttl|too many requests|serviceunavailable", "%s %s" % (type(first).__name__, first), re.I):
                raise
            LOG.warning("Nova agent request failed (%s); trying once more", first)
            _trace_calls().append({"ms": round((time.time() - started) * 1000), "error": type(first).__name__, "retried": True})
            started = time.time()
            response = _converse(**request) or {}
    except Exception as exc:
        _trace_calls().append({"ms": round((time.time() - started) * 1000), "error": type(exc).__name__})
        LOG.warning("Nova agent request failed: %s", exc)
        raise AgentUnavailable("Bedrock Converse request failed") from exc
    used = _usage(response.get("usage"))
    _trace_calls().append({"ms": round((time.time() - started) * 1000), "input_tokens": used["input"],
                           "output_tokens": used["output"], "stop": response.get("stopReason")})
    audit.record("tokens", source="agent", model=bedrock.MODEL_ID, **used)
    if response.get("stopReason") in ("guardrail_intervened", "content_filtered"):
        raise AgentUnavailable("Bedrock withheld the answer (%s)" % response["stopReason"])
    return response


def _answer_text(response, message, max_sentences):
    """The words to speak from an assistant message: no reasoning, no half sentence, short enough for voice."""
    text = " ".join(block["text"] for block in message.get("content", [])
                    if isinstance(block, dict) and isinstance(block.get("text"), str))
    text = _listener_answer(text, max_sentences=99)
    if response.get("stopReason") == "max_tokens":
        text = _complete_sentences(text)
    return _listener_answer(text, max_sentences=max_sentences)


def run(ctx, question, listener_id, tool_runner, interrupted=None,
        mcp_tools=None, mcp_instructions=""):
    """Give Nova the MCP catalog, then execute its selected tool calls.

    Every failure leaves as AgentUnavailable, so /agent/chat answers 503 and never a 500 (AG-14).
    """
    _trace_calls()[:] = []
    _TRACE.notes = {}
    started = time.time()
    try:
        result = _run(ctx, question, listener_id, tool_runner, interrupted, mcp_tools, mcp_instructions)
        if isinstance(result, dict):
            from sideline.language import bedrock
            result["debug"] = {"ms": round((time.time() - started) * 1000), "model": getattr(bedrock, "MODEL_ID", ""),
                               "model_calls": list(_trace_calls()), "notes": dict(getattr(_TRACE, "notes", {})),
                               "tools": [{"name": r.get("name"), "args": r.get("args"), "ms": r.get("ms"),
                                          "ok": not r.get("is_error"), "declined": bool(r.get("declined")),
                                          "spoken": (r.get("spoken") or "")[:700],
                                          "data": _trim_json(r.get("structured") or r.get("detail")),
                                          "reason": (r.get("detail") or {}).get("reason"),
                                          "meta": r.get("meta") or {}}
                                         for r in result.get("tool_results") or []]}
        return result
    except AgentUnavailable:
        raise
    except Exception as exc:                               # noqa: BLE001
        LOG.exception("agent turn failed")
        raise AgentUnavailable("The agent turn failed") from exc


def _run(ctx, question, listener_id, tool_runner, interrupted, mcp_tools, mcp_instructions):
    from sideline.language import bedrock

    if not bedrock.available():
        raise AgentUnavailable("Bedrock is disabled or boto3 is unavailable")

    messages = CONVERSATIONS.get(listener_id)
    pending = FOCUSES.take_pending(listener_id)
    asked = question
    if pending and "(fixture_id" in question and not _FOLLOW_INTENT.search(pending):
        # They picked one of the matches that was listed: it answers the question that was asked, not a new one.
        asked = ("%s [They have just chosen a match for their earlier question: \"%s\". Answer that question about this "
                 "match, passing the fixture_id to the tool.]" % (question, pending))
    if interrupted:
        # They talked over the last answer: what they say next belongs to it.
        asked = ("[The listener cut in while you were saying: \"%s\". What follows "
                 "is a follow-up to that, not a new subject.] %s" % (interrupted, asked))
    if mcp_tools is None:
        mcp_tools = public_tools()
    tool_specs = {spec["name"]: spec for spec in mcp_tools}
    # A scripted test model (it records .calls) sees the whole catalog and every turn, with no shortcuts.
    scripted = hasattr(bedrock.client(), "calls")

    scope = _forget_scope(question)
    if scope:
        return _forget(ctx, scope, listener_id, tool_runner, tool_specs)

    if not scripted and not interrupted:
        conv_answer = _match_conversational(question)           # "what sports do you cover" is never an answer to an offer
        if conv_answer:
            CONVERSATIONS.remember(listener_id, question, conv_answer)
            return {"text": conv_answer, "generated_by": "conversational", "tool_results": []}
    if not scripted and not interrupted and not pending:
        fast_result = _try_fast_path(question, listener_id, tool_runner, tool_specs, ctx=ctx)
        if fast_result is not None:
            return fast_result

    if not scripted:
        said_scope = _out_of_scope(question)
        if said_scope:
            note(out_of_scope=True)
            CONVERSATIONS.remember(listener_id, question, said_scope)
            return {"text": said_scope, "generated_by": "scope", "tool_results": []}
    if not scripted and _GENERAL_KNOWLEDGE.search(question):
        # A rule or what a word means: answered on its own, with no tools and no match history to pull it off course
        # (a model that is shown get_fixtures will sometimes answer "what does VAR stand for" with the day's matches).
        general = _ask(_GENERAL_SYSTEM, [{"role": "user", "content": [{"text": asked}]}])
        said = _answer_text(general, general.get("output", {}).get("message") or {}, 3)
        if not said or re.search(r"\bAction:|\bget_\w+\(|\{\"", said):          # a model that tries to call a tool it was not given
            said = "I don't have that to hand. I can give you scores, fixtures, line-ups, tables and player facts."
        note(general_knowledge=True)
        CONVERSATIONS.remember(listener_id, question, said)
        return {"text": said, "generated_by": "nova", "model": getattr(bedrock, "MODEL_ID", ""), "tool_results": []}
    active_tools = mcp_tools if scripted else _select_candidate_tools(asked, mcp_tools)
    note(tools_offered=len(active_tools), tools_total=len(mcp_tools), session_turns=len(messages) // 2)
    tool_config = {"tools": _bedrock_tools(active_tools)}
    messages.append({"role": "user", "content": [{"text": asked}]})

    detail = _detail(ctx, listener_id)
    max_sentences = {"brief": 1, "full": 5}.get(detail, 3)
    system = SYSTEM
    if mcp_instructions:
        system += "\n\nMCP server instructions: " + mcp_instructions
    system += (_today(ctx, listener_id) + _preference(ctx, listener_id, detail) + FOCUSES.line(listener_id)
               + _following(ctx, listener_id))

    tool_results = []
    weather_retried = live_retried = tool_forced = False

    def finish(text, how):
        if _REFUSAL.search(text):
            text = "I'm here to talk live sports. Which game or team would you like to check?"
            CONVERSATIONS.forget(listener_id)
        else:
            CONVERSATIONS.remember(listener_id, question, text)
            FOCUSES.remember(listener_id, tool_results)
        return {"text": text, "generated_by": how, "model": getattr(bedrock, "MODEL_ID", ""),
                "tool_results": tool_results}

    for _ in range(MAX_TURNS):
        # After a first answer given with no tool, the next call must use one (Converse toolChoice "any").
        response = _ask(system, messages, dict(tool_config, toolChoice={"any": {}}) if tool_forced and tool_config
                        else tool_config)
        message = response.get("output", {}).get("message")
        if not isinstance(message, dict):
            text = _spoken_from_tools(tool_results)
            if text:
                return finish(text, "bedrock-fallback")
            raise AgentUnavailable("Bedrock returned no assistant message")
        messages.append(message)

        requests = [block["toolUse"] for block in message.get("content", [])
                    if isinstance(block, dict) and isinstance(block.get("toolUse"), dict)]
        if not requests:
            text = _answer_text(response, message, max_sentences) or _spoken_from_tools(tool_results)
            if not text and not tool_results and tool_forced:
                # Held to a tool that fits nothing (trophies, say) and nothing came of it: say so, plainly.
                text = "I don't have that. I can give you scores, fixtures, line-ups, tables and player facts."
            if not text:
                raise AgentUnavailable("Bedrock returned no answer text")
            if not tool_results and not tool_forced and _asks_for_a_fact(question):
                # A fact about a match, team or player must come from a tool, never from what the model remembers
                # ("tell me more about Nuno Mendes" was once answered from memory, with no tool called).
                tool_forced = True
                note(forced_tool_retry=True)
                messages.append({"role": "user", "content": [{"text": (
                    "[Do not answer from memory. Call the tool that fits what the listener asked, and say only what it "
                    "returns.]")}]})
                continue
            if _denies_live(text) and not tool_results and not live_retried:
                live_retried = True
                note(retried="the model said it had no live data")
                messages.append({"role": "user", "content": [{"text": (
                    "[You do have live and completed match data: your tools (like get_fixtures) read it. Call the right tool for what "
                    "the listener asked, and answer directly from its result. Never deny having access.]")}]})
                continue
            if _invents_weather(text, tool_results):
                if not weather_retried:
                    weather_retried = True
                    messages.append({"role": "user", "content": [{"text": (
                        "[That gave weather that no tool reported. Call get_match_preview for the "
                        "match the listener means, passing the team they named, and say only what "
                        "it returns. If it has no weather, say you do not have it.]")}]})
                    continue
                text = "I don't have the weather for that match."
            return finish(text, "nova")

        remaining = MAX_TOOL_CALLS - len(tool_results)
        to_run, skipped = requests[:remaining], requests[remaining:]
        if len(to_run) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(4, len(to_run))) as executor:
                executed = list(executor.map(
                    lambda req: _execute_single_request(
                        req, tool_specs, question, listener_id, tool_runner),
                    to_run))
        else:
            executed = [_execute_single_request(
                to_run[0], tool_specs, question, listener_id, tool_runner)] if to_run else []

        results = []
        for result_record, tool_result_item in executed:
            tool_results.append(result_record)
            results.append(tool_result_item)
        for req in skipped:
            # Bedrock wants an answer for every call it asked for, even one we will not run.
            results.append({"toolResult": {"toolUseId": req.get("toolUseId"), "status": "error", "content": [
                {"text": json.dumps({"tool": req.get("name"), "ok": False,
                                     "error": "Not run: the tool-call limit for one question was reached."})}]}})
        for record in tool_results:
            if record.get("declined") and (record.get("detail") or {}).get("fork"):
                FOCUSES.set_pending(listener_id, question)

        # One factual tool that answered with ear-ready text: say it, and save a second model call.
        # But if the listener is asking a clarification, verification, or confirmation ("is that..."),
        # the model must answer rather than re-reading the tool's template spoken string.
        if (not scripted and len(requests) == 1 and len(tool_results) == 1
                and not tool_results[0].get("is_error") and tool_results[0].get("spoken")
                and tool_results[0]["name"] in _SAID_AS_IS
                and not _CLARIFY_OR_VERIFY.search(question)):
            return finish(" ".join(tool_results[0]["spoken"].split()), "bedrock-fast")

        results.append({"text": COMBINE})
        messages.append({"role": "user", "content": results})
        if len(tool_results) >= MAX_TOOL_CALLS:
            break

    # Out of turns or tool calls: what was found is still said, from one last call that offers no tools (AG-12).
    final = _text_only(messages)
    if final and final[-1]["role"] == "user":
        final[-1]["content"][0]["text"] += "\n" + FINAL
    else:
        final.append({"role": "user", "content": [{"text": FINAL}]})
    response = _ask(system, final)
    message = response.get("output", {}).get("message")
    text = (_answer_text(response, message, max_sentences) if isinstance(message, dict) else "") \
        or _spoken_from_tools(tool_results)
    if not text:
        raise AgentUnavailable("Nova used every turn without an answer")
    return finish(text, "nova")


def _execute_single_request(request, tool_specs, question, listener_id, tool_runner):
    """Executes a single tool request and formats its record and toolResult block."""
    name = request.get("name")
    call_id = request.get("toolUseId")
    args = request.get("input")
    if name not in tool_specs:
        message = "That tool is not available in the current MCP catalog."
        result_content, is_error, result_record = message, True, {
            "name": name, "spoken": message, "is_error": True,
        }
    else:
        args = _fill_arguments(name, _without_invented_competition(
            _without_invented_id(_plain_strings(args), question), question), question)
        if name == "get_fixtures" and "get_schedule" in tool_specs:
            team_match = re.search(r"\bfixtures\s+(?:of|for)\s+(?P<team>[A-Za-z\s]+?)(?:'s)?(?:\s+(?:tomorrow|today|this week|next week))?[\s.?!]*$", question, re.I)
            cand_team = args.get("team") if isinstance(args, dict) else None
            if not cand_team and team_match:
                cand_team = team_match.group("team").strip()
            if cand_team:
                matched_team = _known_team(None, cand_team) or cand_team
                name = "get_schedule"
                args = {"team": matched_team, "which": "last" if (isinstance(args, dict) and (args.get("when") == "yesterday" or args.get("finished_only"))) else "next"}
        if name == "follow_match" and not _asked_to_follow(question):
            # A model that guesses must not move the listener to another match.
            message = "The listener did not ask to follow a match, so none was followed."
            result_content, is_error, result_record = message, True, {"name": name, "spoken": message,
                                                                       "is_error": True}
        else:
            result_content, is_error, result_record = _execute_tool(
                name, args, listener_id, tool_runner, tool_specs)
    result_record["args"] = args if isinstance(args, dict) else {}
    model_result = {"tool": name, "ok": not is_error}
    if not is_error or result_record.get("declined"):
        # a tool's own words: an answer, or its refusal written for the listener
        model_result["spoken"] = result_record.get("spoken") or result_content
    else:
        model_result["error"] = result_record.get("error") or result_record.get("spoken") or result_content
        model_result["note"] = "Not for the listener's ears: fix the call, or say briefly what you couldn't get."
    structured = result_record.get("structured") or result_record.get("detail")
    if structured:
        model_result["data"] = structured
    tool_result_item = {
        "toolResult": {
            "toolUseId": call_id,
            "content": [{"text": json.dumps(model_result, ensure_ascii=False)}],
            "status": "error" if is_error else "success",
        }
    }
    return result_record, tool_result_item


def _execute_tool(name, args, listener_id, tool_runner, tool_specs=None):
    """_run_tool, with the arguments and the time it took noted on the record (for the developer log)."""
    started = time.time()
    _TRACE.tool_meta = {}
    content, is_error, record = _run_tool(name, args, listener_id, tool_runner, tool_specs)
    record["args"] = args if isinstance(args, dict) else None
    record["ms"] = round((time.time() - started) * 1000)
    record["meta"] = dict(getattr(_TRACE, "tool_meta", None) or {})
    return content, is_error, record


def _run_tool(name, args, listener_id, tool_runner, tool_specs=None):
    """Validate and run one tool. Returns (content, is_error, record); never raises.

    A record with is_error is never spoken: a tool's own refusal (declined) is for the model to relay, and bad
    arguments or a failed transport only ever reach the model, as text it must not read out (AG-06, AG-14).
    """
    if tool_specs is None:
        tool_specs = {item["name"]: item for item in public_tools()}
    spec = (tool_specs or {}).get(name)
    if not spec:
        message = "That tool is not available."
        return message, True, {"name": name, "spoken": "", "error": message, "is_error": True}
    if not isinstance(args, dict):
        message = "Tool arguments must be an object."
        return message, True, {"name": name, "spoken": "", "error": message, "is_error": True}

    try:
        validate(args, spec["inputSchema"])
        spoken, structured, ui = tool_runner(name, args, listener_id)
    except ToolError as exc:
        record = {"name": name, "spoken": exc.spoken, "declined": True, "is_error": True}
        if exc.detail:
            # Kept so we can tell what the listener was just asked to choose
            # between (sideline/resolve.py), e.g. the ambiguous fixtures.
            record["detail"] = exc.detail
        return exc.spoken, True, record
    except InvalidParams as exc:
        message = str(exc)
        return message, True, {"name": name, "spoken": "", "error": message, "is_error": True}
    except Exception as exc:                               # noqa: BLE001  transport: timeouts, refused, bad JSON
        LOG.warning("tool %s failed: %s", name, exc)
        message = "The tool could not be reached (%s)." % type(exc).__name__
        return message, True, {"name": name, "spoken": "", "error": message, "is_error": True}

    record = {"name": name, "spoken": spoken, "structured": structured, "ui": ui}
    encoded = json.dumps(record, ensure_ascii=False)
    if len(encoded) > MAX_TOOL_RESULT_CHARS:
        encoded = json.dumps({
            "name": name,
            "spoken": spoken,
            "structured": {"truncated": True},
        }, ensure_ascii=False)
        record = {"name": name, "spoken": spoken, "structured": {"truncated": True},
                  "ui": None}
    return encoded, False, record
