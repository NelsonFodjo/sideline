"""Bedrock tool-use loop that lets Nova operate Sideline's MCP tools."""

import datetime
import html
import json
import logging
import re
import threading
import time
from collections import OrderedDict

from .. import audit
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
    "You are Sideline, a concise live-sports companion. Use the available MCP "
    "tools for current sports facts, following their descriptions and schemas. "
    "Match each tool's full use case to what the listener actually asked; do not "
    "choose a tool just because it shares a word with the request. All available "
    "tool descriptions and schemas are already provided. Compare overlapping "
    "tools, call only those needed, and ask a focused clarification rather than "
    "guessing when no tool clearly fits. "
    "Treat tool results as the source of truth; do not guess or invent live facts. "
    "If a tool fails or the request is ambiguous, explain briefly and ask a "
    "focused clarification. Reply naturally in one or two short sentences for "
    "spoken delivery. Do not expose internal reasoning or tool identifiers."
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
        self._pending = {}
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

    def set_pending(self, listener_id, question):
        """A list of matches was just read out for this question: the pick that follows is its answer."""
        with self._lock:
            self._pending[listener_id] = (time.monotonic(), question)

    def take_pending(self, listener_id):
        """The question awaiting a pick, once: any turn uses it up, so it can never answer a later, unrelated one."""
        with self._lock:
            kept = self._pending.pop(listener_id, None)
        return kept[1] if kept and time.monotonic() - kept[0] <= FOCUS_TTL_SECONDS else None

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
        return (" The listener was last talking about %s. Use that only when their question leaves out who or what it is about "
                "('and them?', 'what about him', 'that match', 'who came on'): then pass that team or player by name. If "
                "they ask something general (a day, what is on, a league) or name something else, ignore it. It is context, "
                "not a fact to state." % ", ".join(said))


FOCUSES = Focus()

def _usage(usage):
    """Bedrock's own token counts for one call (Converse returns them), as plain integers."""
    usage = usage if isinstance(usage, dict) else {}
    return {"input": int(usage.get("inputTokens") or 0), "output": int(usage.get("outputTokens") or 0)}


def _listener_answer(text):
    """Remove model-emitted private reasoning before display or speech."""
    text = re.sub(r"<thinking\b[^>]*>.*?</thinking\s*>", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<thinking\b[^>]*>.*$", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?[A-Za-z][^<>]{0,40}>", " ", text)         # a stray <response> wrapper is not for the listener
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


def _today(ctx, listener_id):
    """Today's date in the listener's own zone, so a date the model writes has the right year."""
    try:
        from .. import clock
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
    from . import bedrock
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


def run(ctx, question, listener_id, tool_runner, interrupted=None,
        mcp_tools=None, mcp_instructions=""):
    """Give Nova the MCP catalog, then execute its selected tool calls."""
    from . import bedrock

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
                 "is a follow-up to that, not a new subject.] %s" % (interrupted, question))
    tool_results = []
    weather_retried = live_retried = False
    if mcp_tools is None:
        mcp_tools = public_tools()
    tool_specs = {spec["name"]: spec for spec in mcp_tools}
    messages.append({"role": "user", "content": [{"text": asked}]})
    tool_config = {"tools": _bedrock_tools(mcp_tools)}

    for _ in range(MAX_TURNS):
        try:
            system = SYSTEM
            if mcp_instructions:
                system += "\n\nMCP server instructions: " + mcp_instructions
            system += (_today(ctx, listener_id) + _preference(ctx, listener_id)
                       + FOCUSES.line(listener_id))
            request = {
                "modelId": bedrock.MODEL_ID,
                "system": [{"text": system}],
                "messages": messages,
                "inferenceConfig": {"maxTokens": MAX_TOKENS,
                                    "temperature": 0.2,
                                    "topP": 0.9},
                "toolConfig": tool_config,
            }
            response = _converse(**request)
        except Exception as exc:
            LOG.warning("Nova agent request failed: %s", exc)
            raise AgentUnavailable("Bedrock Converse request failed") from exc

        audit.record("tokens", source="agent", model=bedrock.MODEL_ID, **_usage(response.get("usage")))
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
            called_tools_this_turn = True
            result_record["args"] = args if isinstance(args, dict) else {}
            tool_results.append(result_record)
            model_result = {
                "tool": name,
                "ok": not is_error,
                "spoken": result_record.get("spoken") or result_content,
            }
            structured = result_record.get("structured") or result_record.get("detail")
            if structured:
                model_result["data"] = structured
            results.append({
                "toolResult": {
                    "toolUseId": call_id,
                    "content": [{"text": json.dumps(model_result, ensure_ascii=False)}],
                    "status": "error" if is_error else "success",
                }
            })
            if len(tool_results) >= MAX_TOOL_CALLS:
                break
        for record in tool_results:
            if record.get("declined") and (record.get("detail") or {}).get("fork"):
                FOCUSES.set_pending(listener_id, question)
        results.append({"text": (
            "Combine the tool results into one concise, natural answer using only "
            "supported facts. Explain any errors or ambiguity plainly and ask a "
            "focused follow-up if needed. Call another tool only if essential facts "
            "are still missing.")})
        messages.append({"role": "user", "content": results})
        if len(tool_results) >= MAX_TOOL_CALLS:
            break

    raise AgentUnavailable("Nova exceeded the agent tool-use limit")


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
