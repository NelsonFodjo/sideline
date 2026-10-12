"""CloudWatch metrics with no API calls and no extra permissions.

Uses the Embedded Metric Format: one JSON line on stdout, which
CloudWatch Logs (App Runner, Lambda, ECS all ship stdout there)
turns into real metrics under the `Sideline` namespace. The alarms in
deploy/sideline.yaml read these.

Off by default so local output stays readable. SIDELINE_EMF=on to enable.
"""

import json
import os
import sys
import time

ENABLED = os.environ.get("SIDELINE_EMF", "off").lower() in ("1", "true", "on", "yes")
NAMESPACE = "Sideline"


def emit(name, value, unit="Count", **dims):
    if not ENABLED:
        return
    doc = {
        "_aws": {"Timestamp": int(time.time() * 1000),
                 "CloudWatchMetrics": [{
                     "Namespace": NAMESPACE,
                     "Dimensions": [sorted(dims)] if dims else [[]],
                     "Metrics": [{"Name": name, "Unit": unit}]}]},
        name: value,
    }
    doc.update(dims)
    sys.stdout.write(json.dumps(doc) + "\n")
    sys.stdout.flush()
