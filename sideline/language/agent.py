"""Bedrock tool-use loop that lets Nova operate Sideline's MCP tools."""

import json
import logging
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
MAX_TOKENS = 120
MAX_HISTORY_MESSAGES = 12
MAX_CONVERSATIONS = 256
CONVERSATION_TTL_SECONDS = 1800

SYSTEM = (
    "You are Sideline, a concise live-sports companion (football first, any "
    "match or game a provider supplies) for listeners "
    "following by ear. Use the available tools to answer questions about "
    "the match and the listener's state. Call follow_match when they ask to "
    "follow or switch matches. Do not invent match facts: rely only on tool "
    "results. Ask a brief clarification if a tool reports ambiguity or the "
    "listener's request is unclear. When a message names a match with "
    "(fixture_id N), call follow_match with that fixture_id. For greetings or general conversation, "
    "respond naturally without claiming live match knowledge. Your response "
    "is spoken aloud: output only the answer to the listener, in at most two "
    "short sentences. Do not include analysis, reasoning, a preamble, "
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


def _listener_answer(text):
    """Remove model-emitted private reasoning before display or speech."""
    text = re.sub(r"<thinking\b[^>]*>.*?</thinking\s*>", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<thinking\b[^>]*>.*$", " ",
                  text, flags=re.IGNORECASE | re.DOTALL)
    return " ".join(text.split())


def _bedrock_tools():
    return [
        {"toolSpec": {
            "name": spec["name"],
            "description": spec["description"],
            "inputSchema": {"json": spec["inputSchema"]},
        }}
        for spec in public_tools()
    ]


def run(ctx, question, listener_id, tool_runner):
    """Ask Nova to answer, executing any requested tools through the registry."""
    from . import bedrock

    if not bedrock.available():
        raise AgentUnavailable("Bedrock is disabled or boto3 is unavailable")

    messages = CONVERSATIONS.get(listener_id)
    messages.append({"role": "user", "content": [{"text": question}]})
    tool_results = []
    tool_config = {"tools": _bedrock_tools()}

    for _ in range(MAX_TURNS):
        try:
            response = bedrock.client().converse(
                modelId=bedrock.MODEL_ID,
                system=[{"text": SYSTEM}],
                messages=messages,
                toolConfig=tool_config,
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
            CONVERSATIONS.remember(listener_id, question, text)
            return {"text": text, "generated_by": "nova",
                    "tool_results": tool_results}

        results = []
        remaining = MAX_TOOL_CALLS - len(tool_results)
        for request in requests[:remaining]:
            name = request.get("name")
            call_id = request.get("toolUseId")
            args = request.get("input")
            result_content, is_error, result_record = _execute_tool(
                name, args, listener_id, tool_runner)
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
        record = {"name": name, "spoken": message}
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
