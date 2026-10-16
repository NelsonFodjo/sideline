"""Plugs the simulated Alexa+ into a running Sideline MCP server.

The MCP server (the `sideline` package) does not need this folder: without it the server still answers every tool
over /mcp, and the /agent/chat and /voice routes answer "not found". With it, the server gains the simulator's
agent (a Bedrock model acting as an MCP host) and its speech routes. `sideline.app` calls `attach` if this
package is importable.
"""

from .mcp_client import McpClient


def local_url(address):
    """The /mcp URL this process can reach its own server on: the address it is bound to, or
    loopback when it is bound to every interface."""
    host, port = address[0], address[1]
    if host in ("", "0.0.0.0"):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    if ":" in host:
        host = "[%s]" % host
    return "http://%s:%d/mcp" % (host, port)


def attach(srv, ctx, token=""):
    """Give `srv` an agent runner that calls its own /mcp endpoint, as an external client would."""
    from . import voice
    bridge = McpClient(local_url(srv.server_address), token=token)

    def run_agent(question, listener_id, tz_offset_minutes=None, interrupted=None, tz_name=None):
        from sideline import resolve
        from .agent import AgentUnavailable, run as run_agent_turn

        def run_agent_tool(name, args, tool_listener_id):
            # Nova's tool calls go through our own /mcp endpoint, as an external
            # client's would: the simulator really is an MCP client.
            try:
                return bridge.call(name, args, tool_listener_id, agent=True)
            finally:
                from .agent import note_tool_meta
                note_tool_meta(bridge.last_meta())             # for the Dev log: the feed requests and state changes

        # What did they mean? A short answer to a choice we just offered is
        # snapped to the closest option, and a misheard name from this match is
        # repaired, before the model ever sees it.
        understood = resolve.understand(ctx, listener_id, question)
        if understood.get("clarify"):
            suggestion = understood["suggestion"]
            repaired = understood.get("repaired_text") or suggestion
            resolve.BOOK.remember(listener_id, [
                resolve.Item(suggestion,
                             aliases=["yes", "yeah", "yep", "sure", "correct", "right", suggestion.lower()],
                             agent_say=repaired)
            ])
            clarify_text = "Did you mean %s?" % suggestion
            return {
                "text": clarify_text,
                "generated_by": "typo-clarification",
                "tool_results": [],
                "understood": suggestion,
                "heard": understood["heard"],
                "understood_why": "typo_clarify",
            }
        if tz_offset_minutes is not None:
            # Times are said in the listener's own clock, as the page reports it.
            rec = ctx.store.listener(listener_id)
            if rec.get("tz_offset_minutes") != tz_offset_minutes or rec.get("tz_name") != tz_name:
                rec["tz_offset_minutes"] = tz_offset_minutes
                rec["tz_name"] = tz_name
                ctx.store.save_listener(rec)
        try:
            catalog = bridge.discover(listener_id)
        except (OSError, RuntimeError, ValueError) as e:
            raise AgentUnavailable("MCP tool discovery failed") from e
        result = run_agent_turn(ctx, understood["agent_text"], listener_id, run_agent_tool,
                                interrupted=interrupted,
                                mcp_tools=catalog["tools"],
                                mcp_instructions=catalog["instructions"])
        resolve.learn(ctx, listener_id, result)
        if understood["changed"]:
            result["understood"] = understood["text"]
            result["heard"] = understood["heard"]
            result["understood_why"] = understood["why"]
        return result

    srv.agent_runner = run_agent
    srv.voice_hint = lambda listener_id: voice.vocabulary_hint(ctx, listener_id)
    return srv
