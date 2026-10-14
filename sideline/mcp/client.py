"""Compatibility re-export. The MCP client implementation now lives in simulator.mcp_client."""

import sys
import simulator.mcp_client as _mod

sys.modules[__name__] = _mod

