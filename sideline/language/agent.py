"""Compatibility re-export.

The Bedrock Nova tool-use agent loop (the Alexa+ simulator's host brain)
now lives in simulator.agent.
The core Sideline MCP server exposes tools and state via the /mcp endpoint.
"""

import sys
import simulator.agent as _mod

sys.modules[__name__] = _mod
