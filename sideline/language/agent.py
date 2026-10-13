"""Bedrock tool-use loop that lets Nova operate Sideline's MCP tools."""

import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict

from ..mcp.errors import InvalidParams, ToolError
from ..mcp.registry import public_tools
from ..mcp.schema import validate

LOG = logging.getLogger("sideline.agent")

MAX_TURNS = 4
MAX_TOOL_CALLS = 8
MAX_TOOL_RESULT_CHARS = 6000
MAX_TOKENS = 220
MAX_HISTORY_MESSAGES = 12
MAX_CONVERSATIONS = 256
CONVERSATION_TTL_SECONDS = 1800

SYSTEM = (
    "You are Sideline, a concise live-sports companion (football first, any "
    "match or game a provider supplies) for listeners "
    "following by ear. Your tools read live match data, so you CAN give scores, "
    "times, line-ups and previews: never say you cannot provide real-time or live "
    "information. Use the available tools to answer questions about "
    "the match and the listener's state. Call follow_match when they ask to "
    "follow or switch matches. Do not invent match facts: rely only on tool "
    "results. Ask a brief clarification if a tool reports ambiguity or the "
    "listener's request is unclear. When a message names a match with "
    "(fixture_id N), call follow_match with that fixture_id. For greetings or general conversation, "
    "respond naturally without claiming live match knowledge. Your response "
    "is spoken aloud: output only the answer to the listener, in at most two "
    "short sentences (up to five when the tool gave a match preview, which you "
    "read out almost word for word). Never say an id, a fixture number or any "
    "other technical detail, and say a time of day exactly as the tool wrote it, including the name of the time zone. "
    "Always call a tool for anything about a match, a time, the weather or a team: "
    "never answer those from memory, and never state weather, a score or a time "
    "that a tool did not give you in this conversation. "
    "Say only what the listener asked for: do not volunteer a match they did not "
    "mention. When a tool says it cannot find a match, say that in one plain sentence "
    "and stop: never suggest a typo, never blame the listener, never ask them to confirm "
    "an id. For 'when is X playing' or 'what time is X against Y', call "
    "get_schedule with the team and the opponent. If the listener names a team, pass it to the tool every time, even if they are following a different match, and never say they are following a team they did not follow. Do not include analysis, reasoning, a preamble, "
    "step-by-step explanation, or narration of actions/tool calls. Never say "
    "what you are thinking or about to do, and never refer to the listener as "
    "'the user': speak to them. You cannot speak first, so never promise to "
    "keep them updated; they will ask."
)


class AgentUnavailable(Exception):
    """Nova could not complete an agent turn."""


class ConversationMemory:
    """Small, bounded, in-process conversational context per listener."""

    def __init__(self):
        self._conversations = OrderedDict()
        self._lock = threading.Lock()

    def get(self, listener_id):
        now = time.monotonic()
        with self._lock:
            entry = self._conversations.get(listener_id)
            if not entry:
                return []
            if now - entry[0] > CONVERSATION_TTL_SECONDS:
                del self._conversations[listener_id]
                return []
            self._conversations.move_to_end(listener_id)
            return list(entry[1])

    def remember(self, listener_id, question, answer):
        now = time.monotonic()
        with self._lock:
            entry = self._conversations.get(listener_id)
            history = list(entry[1]) if entry and now - entry[0] <= CONVERSATION_TTL_SECONDS else []
            history.extend([
                {"role": "user", "content": [{"text": question}]},
                {"role": "assistant", "content": [{"text": answer}]},
            ])
            self._conversations[listener_id] = (
                now, history[-MAX_HISTORY_MESSAGES:])
            self._conversations.move_to_end(listener_id)
            while len(self._conversations) > MAX_CONVERSATIONS:
                self._conversations.popitem(last=False)


CONVERSATIONS = ConversationMemory()

FOCUS_TTL_SECONDS = 600


class Focus:
    """What the listener was last talking about: a match, a team, a player.

    The chat history holds only words, and a small model reading its own last sentence loses who "they",
    "him" and "that match" are, especially when the listener asks about a match they do not follow.
    So after each turn the real tool results (not the model's wording) are reduced to a topic, and the
    next turn is told it. The topic is a hint to the model, never a fact it may state, and it expires
    with the conversation moving on.
    """

    def __init__(self):
        self._by = {}
        self._lock = threading.Lock()

    @staticmethod
    def _topic(records):
        """The latest match, team and player named by this turn's answered tool calls."""
        topic = {}
        for record in records:
            if record.get("declined"):
                continue
            args, structured = record.get("args") or {}, record.get("structured") or {}
            if structured.get("home") and structured.get("away"):
                topic["match"] = "%s against %s" % (structured["home"], structured["away"])
            elif structured.get("matches"):
                first = structured["matches"][0]
                if first.get("home") and first.get("away") and len(structured["matches"]) == 1:
                    topic["match"] = "%s against %s" % (first["home"], first["away"])
            if args.get("team"):
                topic["team"] = args["team"]
            player = args.get("player")
            if not player and isinstance(structured.get("player"), dict):
                player = structured["player"].get("name")
            if player and str(player).lower() not in ("he", "him", "his", "that player", "she", "her"):
                topic["player"] = player
        return topic

    def remember(self, listener_id, records):
        topic = self._topic(records)
        if not topic:
            return
        with self._lock:
            kept = self._by.get(listener_id)
            merged = dict(kept[1]) if kept and time.monotonic() - kept[0] <= FOCUS_TTL_SECONDS else {}
            if "match" in topic and topic["match"] != merged.get("match"):
                merged.pop("player", None)          # a new match: the old player is not "him" any more
            merged.update(topic)
            self._by[listener_id] = (time.monotonic(), merged)
            while len(self._by) > MAX_CONVERSATIONS:
                self._by.pop(next(iter(self._by)))

    def line(self, listener_id):
        """One instruction for the model, or "" when there is nothing recent."""
        with self._lock:
            kept = self._by.get(listener_id)
        if not kept or time.monotonic() - kept[0] > FOCUS_TTL_SECONDS:
            return ""
        topic = kept[1]
        said = [("the match %s" % topic["match"]) if topic.get("match") else None,
                ("the team %s" % topic["team"]) if topic.get("team") else None,
                ("the player %s" % topic["player"]) if topic.get("player") else None]
        said = [x for x in said if x]
        if not said:
            return ""
        return (" The listener was last talking about %s. For 'they', 'them', 'him', 'that match' or 'and what "
                "about...', mean that, and pass the team or player to the tool by name; it is context, not a "
                "fact to state." % ", ".join(said))


FOCUSES = Focus()


def _listener_answer(text):
    """Remove model-emitted private reasoning before display or speech."""
    text = re.sub(r"<thinking\b[^>]*>.*?</thinking\s*>", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<thinking\b[^>]*>.*$", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    return " ".join(text.split())


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


_CHITCHAT = re.compile(r"^\W*(hi|hello|hey|thanks?|thank you|ok(ay)?|cheers|bye|goodbye|great|cool|"
                       r"good (morning|afternoon|evening|night))\b", re.I)


def _is_chitchat(question):
    """A greeting or a thank-you: the only turns that need no tool."""
    return len(question.split()) <= 5 and bool(_CHITCHAT.match(question))


_FOLLOW_INTENT = re.compile(r"\b(follow|following|watch|watching|switch|tune|track|"
                            r"put on|listen to|keep me (up|updated)|(fixture_id \d+))", re.I)


def _asked_to_follow(question):
    """Did the listener ask to follow a match, or choose one we offered (the id handoff)?"""
    return bool(_FOLLOW_INTENT.search(question))


_DENIES_LIVE = re.compile(r"\b(can(?:no|')t|unable to|not able to|don't have access to|do not have access to)\b"
                          r"[^.]{0,60}\b(real-?time|live)\b", re.I)


def _denies_live(text):
    """A model telling the listener Sideline cannot do the one thing it exists for."""
    return bool(_DENIES_LIVE.search(text))


def _preference(ctx, listener_id):
    """The listener's own wish for how much to say (set_preferences), as one more instruction."""
    try:
        detail = ctx.store.listener(listener_id).get("detail")
    except Exception:                                      # noqa: BLE001  a courtesy, never a failure
        return ""
    return {"brief": " The listener asked for brief answers: one short sentence.",
            "full": " The listener asked for more detail: up to five short sentences."}.get(detail, "")


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


def _bedrock_tools():
    # SIDELINE_AGENT_TOOLS=core offers the voice agent only the core eleven tools: fewer choices
    # route more reliably on a small model. The MCP server lists them all.
    core = os.environ.get("SIDELINE_AGENT_TOOLS", "all").strip().lower() == "core"
    return [
        {"toolSpec": {
            "name": spec["name"],
            "description": spec["description"],
            "inputSchema": {"json": spec["inputSchema"]},
        }}
        for spec in public_tools(core_only=core)
    ]


def run(ctx, question, listener_id, tool_runner, interrupted=None):
    """Ask Nova to answer, executing any requested tools through the registry."""
    from . import bedrock

    if not bedrock.available():
        raise AgentUnavailable("Bedrock is disabled or boto3 is unavailable")

    messages = CONVERSATIONS.get(listener_id)
    asked = question
    if interrupted:
        # They talked over the last answer: what they say next belongs to it.
        asked = ("[The listener cut in while you were saying: \"%s\". What follows "
                 "is a follow-up to that, not a new subject.] %s" % (interrupted, question))
    messages.append({"role": "user", "content": [{"text": asked}]})
    tool_results = []
    weather_retried = live_retried = False
    tool_config = {"tools": _bedrock_tools()}

    for _ in range(MAX_TURNS):
        # A small model left to choose will answer a match question from memory, or ask which
        # Arsenal match, instead of looking. So the first step of any turn that is not a
        # greeting must be a tool; after that it chooses freely.
        choice = dict(tool_config)
        if not tool_results and not _is_chitchat(question):
            choice["toolChoice"] = {"any": {}}
        try:
            response = bedrock.client().converse(
                modelId=bedrock.MODEL_ID,
                system=[{"text": SYSTEM + _preference(ctx, listener_id) + FOCUSES.line(listener_id)}],
                messages=messages,
                toolConfig=choice,
                inferenceConfig={"maxTokens": MAX_TOKENS,
                                 "temperature": 0.2,
                                 "topP": 0.9},
            )
        except Exception as exc:
            LOG.warning("Nova agent request failed: %s", exc)
            raise AgentUnavailable("Bedrock Converse request failed") from exc

        message = response.get("output", {}).get("message")
        if not isinstance(message, dict):
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
            if not text:
                raise AgentUnavailable("Bedrock returned no answer text")
            if _denies_live(text) and not tool_results and not live_retried:
                live_retried = True
                messages.append({"role": "user", "content": [{"text": (
                    "[You do have live match data: your tools read it. Call the right tool for what "
                    "the listener asked, with the team they named, and answer from its result.]")}]})
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
            CONVERSATIONS.remember(listener_id, question, text)
            FOCUSES.remember(listener_id, tool_results)
            return {"text": text, "generated_by": "nova",
                    "tool_results": tool_results}

        results = []
        remaining = MAX_TOOL_CALLS - len(tool_results)
        for request in requests[:remaining]:
            name = request.get("name")
            call_id = request.get("toolUseId")
            args = _without_invented_id(request.get("input"), question)
            if name == "follow_match" and not _asked_to_follow(question):
                # A model that guesses must not move the listener to another match.
                message = "The listener did not ask to follow a match, so none was followed."
                result_content, is_error, result_record = message, True, {"name": name, "spoken": message}
            else:
                result_content, is_error, result_record = _execute_tool(
                    name, args, listener_id, tool_runner)
            result_record["args"] = args if isinstance(args, dict) else {}
            tool_results.append(result_record)
            results.append({
                "toolResult": {
                    "toolUseId": call_id,
                    "content": [{"text": result_content}],
                    "status": "error" if is_error else "success",
                }
            })
            if len(tool_results) >= MAX_TOOL_CALLS:
                break
        for record in tool_results:
            if record.get("declined"):
                # The tool said no, and said why. The listener hears that, word for word,
                # not a model's apology for it ("I can't provide real-time updates").
                return {"text": record["spoken"], "generated_by": "tool",
                        "tool_results": tool_results}
        messages.append({"role": "user", "content": results})
        if len(tool_results) >= MAX_TOOL_CALLS:
            break

    raise AgentUnavailable("Nova exceeded the agent tool-use limit")


def _execute_tool(name, args, listener_id, tool_runner):
    from ..tools import REGISTRY

    spec = next((item for item in public_tools() if item["name"] == name), None)
    if not spec or name not in REGISTRY:
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
