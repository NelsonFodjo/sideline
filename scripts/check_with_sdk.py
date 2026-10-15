#!/usr/bin/env python3
"""Talk to a running Sideline server with the official MCP Python SDK: an implementation of the protocol that is not ours.

    pip install mcp                      # in a throwaway virtualenv: it is not a dependency of Sideline
    make run                             # in another terminal
    python3 scripts/check_with_sdk.py [http://127.0.0.1:8765/mcp]

Initialises, lists the tools, calls two read-only tools, and sends one bad argument to see it come back as a tool error.
Needs the live ESPN feed for the two calls. Written for `mcp` 2.x (`mcp.Client`).
"""

import asyncio
import sys

from mcp import Client


async def main(url):
    async with Client(url) as client:
        tools = await client.list_tools()
        print("tools:", len(tools.tools))
        assert len(tools.tools) >= 30, "expected the 30 tools"
        for name, args, should_fail in (("get_competitions", {}, False), ("get_fixtures", {}, False),
                                        ("get_event_detail", {"minute": "forty"}, True)):
            res = await client.call_tool(name, args)
            text = res.content[0].text if res.content else ""
            print("%-18s isError=%-5s %s" % (name, res.is_error, text[:110]))
            assert bool(res.is_error) == should_fail, name
    print("ok: the official MCP SDK client works against this server")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/mcp"))
