"""Compatibility re-export.

Speech in and speech out for the simulated Alexa+ client now live in simulator.voice.
The core Sideline MCP server does not process audio.
"""

import sys
import simulator.voice as _mod

sys.modules[__name__] = _mod
