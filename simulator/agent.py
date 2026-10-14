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
MAX_TOKENS = 90
MAX_HISTORY_MESSAGES = 12
MAX_CONVERSATIONS = 256
CONVERSATION_TTL_SECONDS = 1800

SYSTEM = (
    "You are Sideline, a hyper-concise universal live sports voice companion covering Football (Soccer), "
    "Basketball (NBA/WNBA), American Football (NFL/College), Baseball (MLB), and Hockey (NHL). "
    "Use the available MCP tools for current sports facts, following their descriptions and schemas. "
    "Match each tool's full use case to what the listener actually asked; do not "
    "choose a tool just because it shares a word with the request. All available "
    "tool descriptions and schemas are already provided. Compare overlapping "
    "tools, call only those needed, and ask a focused clarification rather than "
    "guessing when no tool clearly fits. "
    "Treat tool results as the source of truth; do not guess or invent live facts. "
    "You have access to live scores, upcoming fixtures, and COMPLETED matches with final scores from today and yesterday via get_fixtures (using finished_only=True). Never claim you cannot provide match results, past games, or finished matches. "
    "If a tool fails or the request is ambiguous, explain briefly and ask a "
    "focused clarification. For general questions about what you do or other sports you cover, "
    "answer directly, naturally, and conversationally. "
    "STRICT VOICE CONSTRAINT: Deliver only 1 or 2 concise sentences (maximum 25 words total). "
    "State only the direct score, time, or key fact. Never include filler, polite pleasantries, "
    "background context, lists, or extra statistics unless explicitly requested."
)

class AgentUnavailable(Exception):
    """Nova could not complete an agent turn."""


class ConversationMemory:
    """Small, bounded conversational context per listener, backed durably by DynamoDB."""

    def __init__(self):
        self._conversations = OrderedDict()
        self._lock = threading.Lock()

    def get(self, listener_id, store=None):
        now = time.monotonic()
        with self._lock:
            entry = self._conversations.get(listener_id)
            if entry and (now - entry[0] <= CONVERSATION_TTL_SECONDS):
                self._conversations.move_to_end(listener_id)
                return list(entry[1])
        if store:
            try:
                rec = store.listener(listener_id)
                raw_history = rec.get("history") or []
                if raw_history:
                    history = []
                    for h in raw_history[-MAX_HISTORY_MESSAGES:]:
                        role = h.get("role")
                        text = h.get("text")
                        if role and text:
                            history.append({"role": role, "content": [{"text": text}]})
                    with self._lock:
                        self._conversations[listener_id] = (now, history)
                    return list(history)
            except Exception as exc:
                LOG.warning("Failed to load conversation history from store: %s", exc)
        return []

    def remember(self, listener_id, question, answer, store=None):
        now = time.monotonic()
        with self._lock:
            entry = self._conversations.get(listener_id)
            history = list(entry[1]) if entry and now - entry[0] <= CONVERSATION_TTL_SECONDS else []
            history.extend([
                {"role": "user", "content": [{"text": question}]},
                {"role": "assistant", "content": [{"text": answer}]},
            ])
            trimmed = history[-MAX_HISTORY_MESSAGES:]
            self._conversations[listener_id] = (now, trimmed)
            self._conversations.move_to_end(listener_id)
            while len(self._conversations) > MAX_CONVERSATIONS:
                self._conversations.popitem(last=False)
        if store:
            try:
                rec = store.listener(listener_id)
                persisted = []
                for msg in trimmed:
                    role = msg.get("role")
                    txt = ""
                    for c in msg.get("content", []):
                        if isinstance(c, dict) and "text" in c:
                            txt += c["text"] + " "
                    txt = txt.strip()
                    if role and txt:
                        persisted.append({"role": role, "text": txt, "at": int(time.time())})
                rec["history"] = persisted
                store.save_listener(rec)
            except Exception as exc:
                LOG.warning("Failed to persist conversation history to store: %s", exc)


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

    Backed durably by DynamoDB per listener to maintain conversational continuity across turns.
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
            if record.get("declined"):
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

    def topic(self, listener_id, store=None):
        with self._lock:
            kept = self._by.get(listener_id)
        if kept and time.monotonic() - kept[0] <= FOCUS_TTL_SECONDS:
            return dict(kept[1])
        if store:
            try:
                rec = store.listener(listener_id)
                top = rec.get("topic") or {}
                if top:
                    with self._lock:
                        self._by[listener_id] = (time.monotonic(), top)
                    return dict(top)
            except Exception as exc:
                LOG.warning("Failed to load topic from store: %s", exc)
        return {}

    def remember(self, listener_id, records, store=None):
        topic = self._topic(records)
        if not topic:
            return
        with self._lock:
            kept = self._by.get(listener_id)
            merged = dict(kept[1]) if kept and time.monotonic() - kept[0] <= FOCUS_TTL_SECONDS else {}
            if "match" in topic and topic["match"] != merged.get("match"):
                merged.pop("player", None)
            merged.update(topic)
            self._by[listener_id] = (time.monotonic(), merged)
            while len(self._by) > MAX_CONVERSATIONS:
                self._by.pop(next(iter(self._by)))
        if store:
            try:
                rec = store.listener(listener_id)
                rec["topic"] = merged
                store.save_listener(rec)
            except Exception as exc:
                LOG.warning("Failed to persist topic to store: %s", exc)

    def set_pending(self, listener_id, question):
        with self._lock:
            self._pending[listener_id] = (time.monotonic(), question)

    def take_pending(self, listener_id):
        with self._lock:
            kept = self._pending.pop(listener_id, None)
        return kept[1] if kept and time.monotonic() - kept[0] <= FOCUS_TTL_SECONDS else None

    def line(self, listener_id, store=None):
        with self._lock:
            kept = self._by.get(listener_id)
        if not kept or time.monotonic() - kept[0] > FOCUS_TTL_SECONDS:
            if store:
                top = self.topic(listener_id, store=store)
                if top:
                    kept = (time.monotonic(), top)
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
            " The listener's ongoing context is %s. Maintain continuity with this context: "
            "when their question refers to 'them', 'they', 'how many', 'who', 'the match', 'the lineup', or 'that game', "
            "resolve it to this active subject. "
            "Always answer accurately and intrigue the listener with a relevant, proactive follow-up question or suggestion "
            "to keep the sports conversation going." % ", ".join(said)
        )


FOCUSES = Focus()

def _usage(usage):
    """Bedrock's own token counts for one call (Converse returns them), as plain integers."""
    usage = usage if isinstance(usage, dict) else {}
    return {"input": int(usage.get("inputTokens") or 0), "output": int(usage.get("outputTokens") or 0)}


def _listener_answer(text):
    """Remove model-emitted private reasoning before display or speech and ensure strict voice conciseness."""
    text = re.sub(r"<thinking\b[^>]*>.*?</thinking\s*>", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<thinking\b[^>]*>.*$", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?[A-Za-z][^<>]{0,40}>", " ", text)         # a stray <response> wrapper is not for the listener
    text = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    if len(parts) > 3:
        text = " ".join(parts[:3])
    return text


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


def _preference(ctx, listener_id):
    """The listener's own wish for how much to say (set_preferences), as one more instruction."""
    try:
        detail = ctx.store.listener(listener_id).get("detail")
    except Exception:                                      # noqa: BLE001  a courtesy, never a failure
        return ""
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
    if "fixture_id %s" % args["fixture_id"] in question:
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
                "inputSchema": {"json": spec["inputSchema"]},
            }})
    return tools


_CONVERSATIONAL_PATTERNS = [
    (re.compile(r"^(can you (access|cover|track|follow)|do you (support|cover|have)|what) (other )?sports\b", re.I),
     "Yes! I cover Football (Soccer), Basketball (NBA/WNBA), American Football (NFL/College), Baseball (MLB), and Ice Hockey (NHL) with live scores, stats, and updates."),
    (re.compile(r"^(who are you|what is your name|what are you)\b", re.I),
     "I'm Sideline, your universal live sports voice companion covering Football, Basketball, NFL, MLB, and NHL."),
    (re.compile(r"^(hello|hi|hey|good morning|good afternoon|good evening)\b", re.I),
     "Hey there! I'm Sideline. Ask me for live scores, upcoming games, or team updates across soccer, basketball, NFL, MLB, and hockey."),
    (re.compile(r"^(thanks|thank you|cheers|great thanks)\b", re.I),
     "You're welcome! Let me know if you need any more live scores or stats."),
    (re.compile(r"^(goodbye|bye|see you|that'?s all)\b", re.I),
     "Goodbye! Enjoy the games."),
]


def _match_conversational(question):
    clean = question.strip().lower().rstrip("?.! ")
    for pattern, answer in _CONVERSATIONAL_PATTERNS:
        if pattern.search(clean):
            return answer
    return None


_FAST_INTENTS = [
    # Score / match state
    (re.compile(r"\b(what('?s| is) the score|current score|score right now|who('?s| is) winning|how long left|how much time left|what minute is it|is the match still on|is the game over|score for\b|\b\w+\s+score\b|did they win|who won)\b", re.I),
     "get_match_state", {}),
    # Catch up / what did I miss
    (re.compile(r"\b(what did i miss|what happened|catch me up|did i miss anything|fill me in|match recap|recap|match summary|summary|how did (they|the game|the match) go|game summary|box score)\b", re.I),
     "what_did_i_miss", {}),
    # Today's fixtures
    (re.compile(r"\b(what('?s| is) on today|matches today|fixtures today|which teams are playing|games today|any games today|today'?s matches|what\s+(matches|games|fixtures)\s+(are\s+on|on|playing)\s+today|what\s+(games|matches)\s+are\s+on\b)\b", re.I),
     "get_fixtures", {}),
    # Completed / finished matches
    (re.compile(r"\b(what\s+(matches|match|games?|fixtures?)\s+(already\s+)?(finished|completed|ended|done)|which\s+(matches|match|games?|fixtures?)\s+(already\s+)?(finished|completed|ended|done)|(matches|match)\s+finished|finished\s+(matches|match)|completed\s+(matches|match|games?)|results\s+(from\s+)?(today|earlier|yesterday)|scores\s+(from\s+)?(earlier|today|yesterday)|previous\s+(matches|match|games?))\b", re.I),
     "get_fixtures", {"finished_only": True}),
    # Upcoming / next fixtures
    (re.compile(r"\b(next matches|upcoming matches|upcoming games|next fixtures|when is the next match|next game|what games are next|who plays next)\b", re.I),
     "get_fixtures", {"when": "next"}),
    # Lineups / Coaches
    (re.compile(r"\b(who('?s| is) playing|what('?s| is) the line-?up|starting eleven|team line-?up|who is starting|starting lineup|starting xi|team sheet|who is coaching|who is the coach|who is the manager)\b", re.I),
     "get_lineups", {}),
    # Officials
    (re.compile(r"\b(who('?s| is) refereeing|who('?s| is) the ref(eree)?|who is the ref|referee for today|who is the official|who is the umpire)\b", re.I),
     "get_officials", {}),
    # Match report / events
    (re.compile(r"\b(who scored|who got booked|who got a yellow|who got a red|any red cards|any goals|who scored the goals|goal scorers|any cards|did anyone score|touchdowns?|field goals?|home runs?)\b", re.I),
     "get_match_report", {}),
    # Table / Standings
    (re.compile(r"\b(league table|standings|where are they in the table|show me the table|standings table|premier league table|nfl standings|nba standings|mlb standings|nhl standings)\b", re.I),
     "get_table", {}),
    # Injuries
    (re.compile(r"\b(who('?s| is) injured|any injuries|who is suspended|injury list|who is out)\b", re.I),
     "get_injuries", {}),
    # Head to Head
    (re.compile(r"\b(head to head|past meetings|last time they played)\b", re.I),
     "get_head_to_head", {}),
    # Capabilities / help
    (re.compile(r"\b(what can you do|what can i ask|help me)\b", re.I),
     "get_capabilities", {}),
    # Sport preferences
    (re.compile(r"\b(i follow|switch to|focus on|set sport to)\s+(basketball|football|soccer|nfl|baseball|hockey|mlb|nhl|american football)\b", re.I),
     "set_preferences", {}),
]

_TOOL_KEYWORDS = {
    "get_match_state": ["score", "minute", "time", "clock", "quarter", "inning", "period", "winning", "lead", "state", "status", "live", "game", "match", "how long", "won", "win"],
    "what_did_i_miss": ["miss", "happened", "catch up", "recap", "summary", "timeline", "story"],
    "get_fixtures": ["fixture", "schedule", "today", "tomorrow", "tonight", "next", "upcoming", "when", "calendar", "games", "matches", "play", "playing", "on", "who plays", "finished", "completed", "ended", "results", "earlier", "done", "previous matches"],
    "follow_match": ["follow", "track", "tune", "watch", "listen", "switch"],
    "unfollow_match": ["unfollow", "stop"],
    "get_lineups": ["lineup", "roster", "starting", "xi", "bench", "who plays", "coach", "manager", "squad", "team sheet"],
    "get_match_events": ["event", "yellow", "red", "card", "goal", "foul", "penalty", "var", "penalty kick", "touchdown", "home run"],
    "get_match_report": ["report", "scorer", "scored", "booking", "booked", "half time", "full time", "goals"],
    "get_match_stats": ["stat", "possession", "shot", "pass", "corner", "accuracy", "strike", "rebound", "turnover"],
    "get_match_preview": ["preview", "weather", "forecast", "venue", "pitch", "rain", "temperature", "degrees"],
    "get_officials": ["referee", "ref", "official", "umpire", "var", "linesman"],
    "get_table": ["table", "standing", "rank", "position", "points", "top", "relegation", "playoff"],
    "get_head_to_head": ["head to head", "h2h", "past meetings", "history", "meeting", "last time they played"],
    "get_form_guide": ["form", "streak", "last 5", "last five", "recent games", "run of form"],
    "get_injuries": ["injur", "hurt", "suspended", "sidelined", "out", "doubtful", "fitness"],
    "get_team_top_scorers": ["top scorer", "leading scorer", "most goals", "golden boot"],
    "get_player_profile": ["profile", "who is", "player", "age", "nationality", "height", "position", "bio"],
    "get_player_season_stats": ["season stats", "player stat", "assists this season", "goals this season"],
    "get_player_form": ["player form", "how is he playing", "rating"],
    "get_tactical_shape": ["tactic", "formation", "shape", "4-3-3", "4-4-2", "system", "setup"],
    "get_key_battles": ["key battle", "matchup", "duel"],
    "get_milestones": ["milestone", "record", "achievement"],
    "get_stadium_intel": ["stadium", "arena", "capacity", "crowd", "attendance", "pitch"],
    "get_substitutes": ["sub", "bench", "substitution", "came on"],
    "set_preferences": ["prefer", "setting", "detail", "brief", "favorite", "sport"],
    "get_capabilities": ["help", "what can you do", "feature", "ability"],
    "get_match_commentary": ["commentary", "text", "live text", "play by play"],
}

_CORE_TOOLS = ["get_match_state", "what_did_i_miss", "get_fixtures", "follow_match", "get_lineups"]


def _select_candidate_tools(question, mcp_tools, context_topic=None):
    """Dynamic Top-K Schema Pruning: Select 3-6 relevant tools to reduce prompt token tax by ~85%."""
    q_lower = question.lower()
    scores = {}
    for name, keywords in _TOOL_KEYWORDS.items():
        score = sum(2 for kw in keywords if kw in q_lower)
        if name in _CORE_TOOLS:
            score += 1
        if context_topic and context_topic.get("match") and name in ("get_match_state", "what_did_i_miss"):
            score += 2
        scores[name] = score

    sorted_names = sorted(scores.keys(), key=lambda n: scores[n], reverse=True)
    selected_names = set()
    for name in sorted_names:
        if scores[name] > 1 or len(selected_names) < 3:
            selected_names.add(name)
        if len(selected_names) >= 6:
            break

    if not selected_names:
        selected_names = set(_CORE_TOOLS)

    tool_by_name = {spec["name"]: spec for spec in mcp_tools}
    candidates = [tool_by_name[n] for n in selected_names if n in tool_by_name]
    return candidates or mcp_tools


class SubAgent:
    """Specialized sub-agent that owns a domain of tools and executes concurrently."""
    def __init__(self, name, tools, patterns):
        self.name = name
        self.tools = set(tools)
        self.patterns = patterns

    def plan(self, clean, topic, known_teams, question):
        tasks = []
        for pat, tool_name, default_args in self.patterns:
            m = pat.search(clean)
            if m:
                call_args = dict(default_args)
                if tool_name == "set_preferences":
                    sport_match = re.search(r"\b(basketball|football|soccer|nfl|baseball|hockey|mlb|nhl|american football)\b", clean, re.I)
                    if sport_match:
                        s = sport_match.group(1).lower()
                        if s in ("soccer", "football"):
                            call_args["sport"] = "football"
                        elif s in ("nfl", "american football"):
                            call_args["sport"] = "american_football"
                        elif s in ("baseball", "mlb"):
                            call_args["sport"] = "baseball"
                        elif s in ("hockey", "nhl"):
                            call_args["sport"] = "hockey"
                        elif s == "basketball":
                            call_args["sport"] = "basketball"
                # Check for explicit team
                for t in known_teams:
                    if t.lower() in clean.lower():
                        call_args["team"] = t
                        break
                if "team" not in call_args and tool_name in ("get_match_state", "get_lineups", "get_officials", "get_injuries", "get_match_report", "what_did_i_miss", "get_table", "get_head_to_head"):
                    m_team = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:score|line-?up|match|game|injuries|news)\b", question)
                    if m_team and m_team.group(1).lower() not in ("what", "who", "the", "current", "any", "how", "did"):
                        call_args["team"] = m_team.group(1).strip()
                # Check for explicit competition
                for pat, comp_key, _ in COMP_PATTERNS:
                    if pat.search(clean):
                        call_args["competition"] = comp_key
                        break
                # Inherit competition from topic if not explicit
                if "competition" not in call_args and topic.get("competition") and tool_name in ("get_fixtures", "get_table"):
                    call_args["competition"] = topic["competition"]
                # Context continuation fallback
                if "team" not in call_args and topic.get("team"):
                    call_args["team"] = topic["team"]
                if "fixture_id" not in call_args and topic.get("fixture_id"):
                    call_args["fixture_id"] = topic["fixture_id"]
                if "sport" not in call_args and topic.get("sport"):
                    call_args["sport"] = topic["sport"]

                tasks.append((tool_name, call_args))
        return tasks


SWARM_AGENTS = [
    SubAgent("StateAgent", ["get_match_state"], [
        (re.compile(r"\b(what('?s| is) the score|current score|score right now|who('?s| is) winning|how long left|how much time left|what minute is it|is the match still on|is the game over|score for\b|\b\w+\s+score\b|did they win|who won)\b", re.I), "get_match_state", {}),
    ]),
    SubAgent("TimelineAgent", ["what_did_i_miss", "get_match_report"], [
        (re.compile(r"\b(what did i miss|what happened|catch me up|did i miss anything|fill me in|match recap|recap|match summary|summary|how did (they|the game|the match) go|game summary|box score)\b", re.I), "what_did_i_miss", {}),
        (re.compile(r"\b(who scored|who got booked|who got a yellow|who got a red|any red cards|any goals|who scored the goals|goal scorers|any cards|did anyone score|touchdowns?|field goals?|home runs?)\b", re.I), "get_match_report", {}),
    ]),
    SubAgent("ScheduleAgent", ["get_fixtures"], [
        (re.compile(r"\b(what\s+(matches|match|games?|fixtures?)\s+(already\s+)?(finished|completed|ended|done)|which\s+(matches|match|games?|fixtures?)\s+(already\s+)?(finished|completed|ended|done)|(matches|match)\s+finished|finished\s+(matches|match)|completed\s+(matches|match|games?)|results\s+(from\s+)?(today|earlier|yesterday)|scores\s+(from\s+)?(earlier|today|yesterday)|previous\s+(matches|match|games?))\b", re.I), "get_fixtures", {"finished_only": True}),
        (re.compile(r"\b(what('?s| is) on today|matches today|fixtures today|which teams are playing|games today|any games today|today'?s matches|what\s+(matches|games|fixtures)\s+(are\s+on|on|playing)(\s+today|\s+tonight)?|what\s+(games|matches)\s+are\s+on\b|for today|today'?s (games|schedule|fixtures)|(today|tonight)('?s)?\s+(games|schedule|matches|fixtures)|who('?s| is) playing (today|tonight)?|any matches (today|tonight)?|are there any (games|matches)|schedule for today|all\s+the\s+.*matches|show\s+me\s+.*matches|matches\s+of\s+today)\b", re.I), "get_fixtures", {}),
        (re.compile(r"\b(next matches|upcoming matches|upcoming games|next fixtures|when is the next match|next game|what games are next|who plays next)\b", re.I), "get_fixtures", {"when": "next"}),
    ]),
    SubAgent("RosterAgent", ["get_lineups"], [
        (re.compile(r"\b(line-?ups?|rosters?|squads?|team sheet|starting (eleven|xi|lineup)|who('?s| is) (playing|starting|coaching|the coach|the manager))\b", re.I), "get_lineups", {}),
    ]),
    SubAgent("StandingsAgent", ["get_table"], [
        (re.compile(r"\b(league table|standings|where are they in the table|show me the table|standings table|premier league table|nfl standings|nba standings|mlb standings|nhl standings)\b", re.I), "get_table", {}),
    ]),
    SubAgent("StatsAgent", ["get_match_stats", "get_team_stats", "get_player_stats"], [
        (re.compile(r"\b(match stats|game stats|team stats|possession|shots on target|how many shots|box score stats|match statistics)\b", re.I), "get_match_stats", {}),
    ]),
    SubAgent("FormAgent", ["get_team_form"], [
        (re.compile(r"\b(recent form|team form|how is (their|the) form|last 5 games|past five games|win streak|form guide)\b", re.I), "get_team_form", {}),
    ]),
    SubAgent("IntelAgent", ["get_officials", "get_injuries", "get_head_to_head", "get_capabilities", "set_preferences"], [
        (re.compile(r"\b(who('?s| is) refereeing|who('?s| is) the ref(eree)?|who is the ref|referee for today|who is the official|who is the umpire)\b", re.I), "get_officials", {}),
        (re.compile(r"\b(who('?s| is) injured|any injuries|who is suspended|injury list|who is out)\b", re.I), "get_injuries", {}),
        (re.compile(r"\b(head to head|past meetings|last time they played)\b", re.I), "get_head_to_head", {}),
        (re.compile(r"\b(what can you do|what can i ask|help me)\b", re.I), "get_capabilities", {}),
        (re.compile(r"\b(i follow|switch to|focus on|set sport to)\s+(basketball|football|soccer|nfl|baseball|hockey|mlb|nhl|american football)\b", re.I), "set_preferences", {}),
    ]),
]


def _execute_subagent_task(task, listener_id, tool_runner, tool_specs):
    agent_name, tool_name, call_args = task
    try:
        content, is_err, rec = _execute_tool(tool_name, call_args, listener_id, tool_runner, tool_specs)
        if not is_err and rec.get("spoken"):
            return agent_name, rec
    except Exception as e:
        LOG.debug("subagent %s execution error: %s", agent_name, e)
    return None


def _try_swarm_fast_path(question, listener_id, tool_runner, tool_specs, ctx=None):
    clean = question.strip()
    topic = FOCUSES.topic(listener_id, store=ctx.store if ctx else None)

    # Conversational follow-up: total match count inquiry
    if re.search(r"\b(how many\b.*(them|total|matches|games|there)|total\s+(matches|games)|in total)\b", clean, re.I):
        if topic.get("total") is not None:
            total = topic["total"]
            c_name = topic.get("competition_name") or topic.get("competition") or "scheduled"
            intrigue = "Would you like to hear the kick-off times or check the lineups for any of them?"
            ans = "There are %d %s matches in total today. %s" % (total, c_name, intrigue)
            CONVERSATIONS.remember(listener_id, question, ans, store=ctx.store if ctx else None)
            return {
                "text": ans,
                "generated_by": "swarm-fast",
                "agents_used": ["ScheduleAgent"],
                "tool_results": [{"name": "get_fixtures", "spoken": ans, "structured": topic}],
            }

    known_teams = []
    if ctx and hasattr(ctx, "provider") and hasattr(ctx.provider, "known_teams"):
        try:
            known_teams = ctx.provider.known_teams()
        except Exception:
            pass

    # Collect speculative plans across all 8 specialized sub-agents
    tasks = []
    seen_tools = set()

    # Broad multi-agent fanout: "tell me everything about / full update on [team]"
    is_full_update = bool(re.search(r"\b(tell me everything about|full (update|report|recap) on|all about|complete update on)\b", clean, re.I))
    if is_full_update:
        target_team = None
        for t in known_teams:
            if t.lower() in clean.lower():
                target_team = t
                break
        if not target_team and topic.get("team"):
            target_team = topic["team"]
        if not target_team:
            m_team = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", question)
            if m_team and m_team.group(1).lower() not in ("tell", "me", "everything", "about", "full", "update", "what"):
                target_team = m_team.group(1).strip()

        core_fanout = [
            ("StateAgent", "get_match_state", {"team": target_team} if target_team else {}),
            ("TimelineAgent", "what_did_i_miss", {"team": target_team} if target_team else {}),
            ("RosterAgent", "get_lineups", {"team": target_team} if target_team else {}),
            ("StandingsAgent", "get_table", {}),
            ("FormAgent", "get_team_form", {"team": target_team} if target_team else {}),
            ("StatsAgent", "get_match_stats", {"team": target_team} if target_team else {}),
            ("IntelAgent", "get_officials", {"team": target_team} if target_team else {}),
        ]
        for a_name, t_name, t_args in core_fanout:
            if t_name in tool_specs and t_name not in seen_tools:
                seen_tools.add(t_name)
                tasks.append((a_name, t_name, t_args))

    for agent_worker in SWARM_AGENTS:
        sub_tasks = agent_worker.plan(clean, topic, known_teams, question)
        for tool_name, call_args in sub_tasks:
            if tool_name in tool_specs and tool_name not in seen_tools:
                seen_tools.add(tool_name)
                tasks.append((agent_worker.name, tool_name, call_args))

    # If lineups were asked for without a specific team or context, also dispatch today's schedule
    has_lineups = any(t[1] == "get_lineups" and not t[2].get("team") for t in tasks)
    if has_lineups and "get_fixtures" in tool_specs and "get_fixtures" not in seen_tools:
        seen_tools.add("get_fixtures")
        tasks.append(("ScheduleAgent", "get_fixtures", {"when": "today"}))

    if not tasks:
        return None

    # Execute all scheduled sub-agent tool calls concurrently in parallel (< 15ms)
    results = []
    if len(tasks) == 1:
        res = _execute_subagent_task(tasks[0], listener_id, tool_runner, tool_specs)
        if res:
            results.append(res)
    else:
        from concurrent.futures import ThreadPoolExecutor
        # Concurrently execute >5 subagents simultaneously without queueing
        with ThreadPoolExecutor(max_workers=max(8, len(tasks))) as pool:
            futures = [
                pool.submit(_execute_subagent_task, t, listener_id, tool_runner, tool_specs)
                for t in tasks
            ]
            for fut in futures:
                try:
                    res = fut.result()
                    if res:
                        results.append(res)
                except Exception as e:
                    LOG.debug("swarm agent error: %s", e)

    if not results:
        return None

    spoken_parts = []
    tool_records = []
    agents_used = []
    for agent_name, rec in results:
        if rec.get("spoken") and not rec.get("declined"):
            spoken_parts.append(rec["spoken"])
            tool_records.append(rec)
            agents_used.append(agent_name)

    if not spoken_parts:
        return None

    combined = " ".join(spoken_parts)
    # Proactively intrigue the next response if appropriate
    if len(tool_records) == 1 and not combined.rstrip().endswith("?"):
        t_name = tool_records[0].get("name")
        if t_name == "get_fixtures":
            combined += " Would you like to check the starting lineups or follow one of these matches?"
        elif t_name == "get_match_state":
            combined += " Would you like live updates on this match?"
        elif t_name == "get_lineups":
            combined += " Would you like to check their recent form or head-to-head record?"
        elif t_name == "what_did_i_miss":
            combined += " Would you like the current score and match stats?"

    combined = _listener_answer(combined)

    CONVERSATIONS.remember(listener_id, question, combined, store=ctx.store if ctx else None)
    FOCUSES.remember(listener_id, tool_records, store=ctx.store if ctx else None)

    return {
        "text": combined,
        "generated_by": "swarm-fast",
        "agents_used": agents_used,
        "tool_results": tool_records,
    }


def _try_fast_path(question, listener_id, tool_runner, tool_specs, ctx=None):
    return _try_swarm_fast_path(question, listener_id, tool_runner, tool_specs, ctx=ctx)


def run(ctx, question, listener_id, tool_runner, interrupted=None,
        mcp_tools=None, mcp_instructions=""):
    """Give Nova the MCP catalog, then execute its selected tool calls."""
    from sideline.language import bedrock

    if not bedrock.available():
        raise AgentUnavailable("Bedrock is disabled or boto3 is unavailable")

    messages = CONVERSATIONS.get(listener_id, store=ctx.store if ctx else None)
    pending = FOCUSES.take_pending(listener_id)
    asked = question
    if pending and "(fixture_id" in question and not _FOLLOW_INTENT.search(pending):
        # They picked one of the matches that was listed: it answers the question that was asked, not a new one.
        asked = ("%s [They have just chosen a match for their earlier question: \"%s\". Answer that question about this "
                 "match, passing the fixture_id to the tool.]" % (question, pending))
    if interrupted:
        # They talked over the last answer: what they say next belongs to it.
        asked = ("[The listener cut in while you were saying: \"%s\". What follows "
                 "is a follow-up to that, not a new subject.] %s" % (interrupted, question))
    tool_results = []
    weather_retried = live_retried = False
    if mcp_tools is None:
        mcp_tools = public_tools()
    tool_specs = {spec["name"]: spec for spec in mcp_tools}

    # Tier 0: Conversational bypass for instant capability/greetings answers
    if not hasattr(bedrock.client(), "calls") and not interrupted and not pending:
        conv_answer = _match_conversational(question)
        if conv_answer:
            CONVERSATIONS.remember(listener_id, question, conv_answer, store=ctx.store if ctx else None)
            return {
                "text": conv_answer,
                "generated_by": "conversational",
                "tool_results": [],
            }

    # Tier 1 Fast-path: for standard sports queries, execute directly in ~15ms bypassing Bedrock latency
    if not hasattr(bedrock.client(), "calls") and not interrupted and not pending:
        fast_result = _try_fast_path(question, listener_id, tool_runner, tool_specs, ctx=ctx)
        if fast_result is not None:
            return fast_result

    # Tier 2: Dynamic Tool Attention / Top-K Schema Pruning
    if hasattr(bedrock.client(), "calls"):
        active_tools = mcp_tools
    else:
        active_tools = _select_candidate_tools(asked, mcp_tools, FOCUSES.topic(listener_id, store=ctx.store if ctx else None))

    messages.append({"role": "user", "content": [{"text": asked}]})
    tool_config = {"tools": _bedrock_tools(active_tools)}

    for _ in range(MAX_TURNS):
        try:
            system = SYSTEM
            if mcp_instructions:
                system += "\n\nMCP server instructions: " + mcp_instructions
            system += (_today(ctx, listener_id) + _preference(ctx, listener_id)
                       + FOCUSES.line(listener_id, store=ctx.store if ctx else None))
            request = {
                "modelId": bedrock.MODEL_ID,
                "system": [{"text": system}],
                "messages": messages,
                "inferenceConfig": {"maxTokens": MAX_TOKENS,
                                    "temperature": 0.2},
                "toolConfig": tool_config,
            }
            response = _converse(**request)
        except Exception as exc:
            LOG.warning("Nova agent request failed: %s", exc)
            raise AgentUnavailable("Bedrock Converse request failed") from exc

        audit.record("tokens", source="agent", model=bedrock.MODEL_ID, **_usage(response.get("usage")))
        message = response.get("output", {}).get("message")
        if not isinstance(message, dict):
            if tool_results:
                spoken_parts = [r.get("spoken", "") for r in tool_results if r.get("spoken") and not r.get("declined")]
                if spoken_parts:
                    text = _listener_answer(" ".join(spoken_parts).strip())
                    CONVERSATIONS.remember(listener_id, question, text, store=ctx.store if ctx else None)
                    FOCUSES.remember(listener_id, tool_results, store=ctx.store if ctx else None)
                    return {"text": text, "generated_by": "bedrock-fallback",
                            "model": getattr(bedrock, "MODEL_ID", ""),
                            "tool_results": tool_results}
            raise AgentUnavailable("Bedrock returned no assistant message")
        messages.append(message)

        requests = [block["toolUse"] for block in message.get("content", [])
                    if isinstance(block, dict) and "toolUse" in block]
        if not requests:
            text = " ".join(
                block["text"] for block in message.get("content", [])
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            ).strip()
            text = _listener_answer(text)
            if not text and tool_results:
                spoken_parts = [r.get("spoken", "") for r in tool_results if r.get("spoken") and not r.get("declined")]
                if spoken_parts:
                    text = _listener_answer(" ".join(spoken_parts).strip())
            if not text:
                raise AgentUnavailable("Bedrock returned no answer text")
            if _denies_live(text) and not tool_results and not live_retried:
                live_retried = True
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
            CONVERSATIONS.remember(listener_id, question, text, store=ctx.store if ctx else None)
            FOCUSES.remember(listener_id, tool_results, store=ctx.store if ctx else None)
            return {"text": text, "generated_by": "nova",
                    "model": getattr(bedrock, "MODEL_ID", ""),
                    "tool_results": tool_results}

        results = []
        remaining = MAX_TOOL_CALLS - len(tool_results)
        to_run = requests[:remaining]
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

        for result_record, tool_result_item in executed:
            called_tools_this_turn = True
            tool_results.append(result_record)
            results.append(tool_result_item)
            if len(tool_results) >= MAX_TOOL_CALLS:
                break
        for record in tool_results:
            if record.get("declined") and (record.get("detail") or {}).get("fork"):
                FOCUSES.set_pending(listener_id, question)

        # Fast synthesis bypass (Proposal A): If a single factual tool answered with ear-ready text,
        # return it immediately to avoid a second 1.2s Bedrock Converse turn.
        if (not hasattr(bedrock.client(), "calls") and len(requests) == 1 and len(tool_results) == 1
                and not tool_results[0].get("declined") and tool_results[0].get("spoken")
                and tool_results[0]["name"] in ("get_fixtures", "get_match_state", "get_officials", "get_lineups",
                                                "get_injuries", "get_table", "get_head_to_head", "what_did_i_miss",
                                                "get_match_preview", "get_team_form", "get_match_stats",
                                                "get_team_stats", "get_player_stats", "get_match_report",
                                                "get_capabilities", "get_schedule", "get_standings")):
            text = tool_results[0]["spoken"]
            CONVERSATIONS.remember(listener_id, question, text, store=ctx.store if ctx else None)
            FOCUSES.remember(listener_id, tool_results, store=ctx.store if ctx else None)
            return {"text": text, "generated_by": "bedrock-fast",
                    "model": getattr(bedrock, "MODEL_ID", ""),
                    "tool_results": tool_results}

        results.append({"text": (
            "Combine the tool results into one concise, natural answer using only supported facts. "
            "STRICT CONSTRAINT: Exactly 1 or 2 short sentences (maximum 20 words total). "
            "State only the primary fact or score. No filler or extra lists.")})
        messages.append({"role": "user", "content": results})
        if len(tool_results) >= MAX_TOOL_CALLS:
            break

    raise AgentUnavailable("Nova exceeded the agent tool-use limit")


def _execute_single_request(request, tool_specs, question, listener_id, tool_runner):
    """Executes a single tool request and formats its record and toolResult block."""
    name = request.get("name")
    call_id = request.get("toolUseId")
    args = request.get("input")
    if name not in tool_specs:
        message = "That tool is not available in the current MCP catalog."
        result_content, is_error, result_record = message, True, {
            "name": name, "spoken": message,
        }
    else:
        args = _fill_arguments(name, _without_invented_competition(
            _without_invented_id(_plain_strings(args), question), question), question)
        if name == "follow_match" and not _asked_to_follow(question):
            # A model that guesses must not move the listener to another match.
            message = "The listener did not ask to follow a match, so none was followed."
            result_content, is_error, result_record = message, True, {"name": name, "spoken": message}
        else:
            result_content, is_error, result_record = _execute_tool(
                name, args, listener_id, tool_runner, tool_specs)
    result_record["args"] = args if isinstance(args, dict) else {}
    model_result = {
        "tool": name,
        "ok": not is_error,
        "spoken": result_record.get("spoken") or result_content,
    }
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
    if tool_specs is None:
        tool_specs = {item["name"]: item for item in public_tools()}
    spec = (tool_specs or {}).get(name)
    if not spec:
        message = "That tool is not available."
        return message, True, {"name": name, "spoken": message}
    if not isinstance(args, dict):
        message = "Tool arguments must be an object."
        return message, True, {"name": name, "spoken": message}

    try:
        validate(args, spec["inputSchema"])
        spoken, structured, ui = tool_runner(name, args, listener_id)
    except (InvalidParams, ToolError) as exc:
        message = exc.spoken if isinstance(exc, ToolError) else str(exc)
        record = {"name": name, "spoken": message, "declined": isinstance(exc, ToolError)}
        if isinstance(exc, ToolError) and exc.detail:
            # Kept so we can tell what the listener was just asked to choose
            # between (sideline/resolve.py), e.g. the ambiguous fixtures.
            record["detail"] = exc.detail
        return message, True, record

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
