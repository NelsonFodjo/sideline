"""Sideline - live football for people who cannot see the screen.

Entry points:
    python -m sideline            start the MCP server
    scripts/smoke_test.py         exercise every tool end to end

Read docs/ARCHITECTURE.md first. The one file that matters most is
sideline/state/store.py - `last_told_at` is the product.
"""

__version__ = "1.0.0"
