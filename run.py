#!/usr/bin/env python3
"""Start Sideline.

    python3 run.py

Exists so the server starts whatever the layout and whatever the python
is called. `python3 -m sideline` is equivalent on a current checkout;
this also works if you have an older copy with the package under src/,
and it says something useful rather than "No module named sideline" when
you are in the wrong directory.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Current layout: package at the repo root. Older copies had it under
# src/, so accept both rather than make anyone care.
for candidate in (HERE, os.path.join(HERE, "src")):
    if os.path.isdir(os.path.join(candidate, "sideline")):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
        break
else:
    sys.exit(
        "Could not find the sideline package.\n"
        "  You are in : %s\n"
        "  Expected   : a 'sideline' folder here, next to docs/ and tests/.\n"
        "  Fix        : cd into the repository root and try again." % os.getcwd())

if sys.version_info < (3, 8):
    sys.exit("Needs Python 3.8 or newer. You have %d.%d."
             % sys.version_info[:2])

from sideline.app import main  # noqa: E402

main()
