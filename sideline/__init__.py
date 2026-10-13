"""Sideline - live football for people who cannot see the screen.

Entry points:
    python3 -m sideline           start the MCP server (needs SPORTMONKS_TOKEN)
    python3 scripts/verify_data.py --tools   run every tool against the live feed

Read docs/ARCHITECTURE.md first. The one file that matters most is
sideline/state/store.py - `last_told_at` is the product.
"""

import os as _os

from . import envfile as _envfile

# Must run before any module that reads the environment at import time.
# Real environment variables always beat the file (see envfile.py).
_envfile.load()

# boto3 reads AWS_DEFAULT_REGION, the docs and this project say AWS_REGION.
# Bridge them once, here, so a client built without an explicit region
# (STS, say) still lands in the region you set.
_os.environ.setdefault("AWS_DEFAULT_REGION",
                       _os.environ.get("AWS_REGION", "us-east-1"))

__version__ = "1.0.0"
