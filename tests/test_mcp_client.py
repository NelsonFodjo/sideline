"""The voice agent's tool calls really cross the MCP endpoint.

The hackathon FAQ says a simulator counts as the track's client when it does
initialize, tools/list and tools/call over Streamable HTTP. The agent used to run
tools in-process, so nothing crossed the protocol. Now Nova's calls go through
sideline/mcp/client.py to this server's own /mcp, as an external client's would.
This starts a real server and drives the client against it.
"""

import threading

from conftest import make_ctx

from sideline.app import resolve_listener, tool_runner
from sideline.language.agent import _bedrock_tools, _model_schema
from sideline.mcp import server as mcp_server
from sideline.mcp.client import McpClient
from sideline.mcp.errors import InvalidParams, ToolError


def main():
    ctx = make_ctx(start_minute=40)
    srv = mcp_server.serve("127.0.0.1", 0, tool_runner(ctx), resolve_listener,
                           ["localhost", "127.0.0.1"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = McpClient("http://127.0.0.1:%d/mcp" % srv.server_address[1], timeout=5)
    try:
        catalog = client.discover("ann")
        assert "Prefer what_did_i_miss" in catalog["instructions"]
        assert any(item["name"] == "get_match_state" for item in catalog["tools"])
        assert all("inputSchema" in item for item in catalog["tools"])
        model_tools = _bedrock_tools(catalog["tools"])
        assert [item["toolSpec"]["name"] for item in model_tools] == [
            item["name"] for item in catalog["tools"]]
        assert model_tools[0]["toolSpec"]["inputSchema"]["json"] == _model_schema(catalog["tools"][0]["inputSchema"])
        print("ok  Nova's host fetches MCP initialize instructions and the current tools/list catalog")

        spoken, structured, ui = client.call("follow_match", {"team": "Arsenal"}, "ann")
        assert "Following" in spoken and structured["fixture_id"] == 1208341, (spoken, structured)
        assert client._sid, "an MCP session was opened"
        print("ok  tools/call over HTTP returns the spoken text, the structured result:", spoken[:50])

        spoken, structured, ui = client.call("get_match_state", {}, "ann")
        assert structured["score"] is not None and ui["home"], (structured, ui)
        print("ok  the UI payload for the scoreboard comes back through _meta")

        # a tool that declines is a ToolError with its detail, not a crash
        try:
            client.call("follow_match", {"team": "Nonexistent United"}, "ann")
        except ToolError as e:
            assert e.detail["reason"] == "no_match", e.detail
        else:
            raise AssertionError("expected the tool to decline")
        # arguments are validated by the server, over the protocol
        try:
            client.call("get_event_detail", {"minute": "forty"}, "ann")
        except InvalidParams:
            pass
        else:
            raise AssertionError("expected the arguments to be refused")
        print("ok  a declined tool is a ToolError with its detail; bad arguments are refused by the server")

        # the listener travels in a header, so two listeners keep separate state
        client.call("follow_match", {"team": "Arsenal"}, "bob")
        assert ctx.store.listener("ann")["following"] == 1208341
        assert ctx.store.listener("bob")["following"] == 1208341
        assert ctx.store.listener("ann") is not ctx.store.listener("bob")
        print("ok  listener identity travels in X-Sideline-Listener")

        # the agent flag: facts for a model, not a second model-written paragraph
        spoken, structured, _ = client.call("what_did_i_miss", {}, "ann", agent=True)
        assert spoken == "" and structured["generated_by"] == "tool-data", (spoken, structured)
        spoken, structured, _ = client.call("what_did_i_miss", {"full": True}, "bob")
        assert spoken and structured["generated_by"] == "template", structured
        print("ok  the agent asks for event facts; any other client gets the paragraph")

        # a lost session is replaced transparently
        for sid in list(srv.sessions._s):
            srv.sessions.drop(sid)
        spoken, _, _ = client.call("get_match_state", {}, "ann")
        assert spoken
        print("ok  a dropped session is re-initialised on the next call")
    finally:
        srv.shutdown()
    print("\nmcp client: all good")


if __name__ == "__main__":
    main()
