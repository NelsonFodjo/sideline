"""Run the simulated Alexa+ voice client and Sideline server together."""

import sys
import webbrowser

from sideline.app import main

if __name__ == "__main__":
    if "--no-open" not in sys.argv:
        try:
            webbrowser.open("http://127.0.0.1:8765/")
        except Exception:
            pass
    main()
