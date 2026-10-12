"""The small AWS-facing pieces that can be checked with no AWS account:
reading the football key from Secrets Manager, and the CloudWatch
metric line the alarms depend on."""

import io
import json
from contextlib import redirect_stdout

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

from sideline import metrics, secretsmanager


class FakeSM:
    def __init__(self, value=None, boom=False):
        self.value, self.boom, self.asked = value, boom, None

    def get_secret_value(self, SecretId):
        self.asked = SecretId
        if self.boom:
            raise RuntimeError("AccessDeniedException")
        return {"SecretString": self.value}


def main():
    sm = FakeSM('{"SIDELINE_FOOTBALL_KEY": " abc123 "}')
    assert secretsmanager.football_key("sideline/football-key", "us-east-1", client=sm) == "abc123"
    assert sm.asked == "sideline/football-key"
    print("ok  JSON secret -> the named field, trimmed")

    assert secretsmanager.football_key("x", "us-east-1", client=FakeSM("rawkey\n")) == "rawkey"
    print("ok  a bare-string secret works too")

    assert secretsmanager.football_key("x", "us-east-1", client=FakeSM(boom=True)) == ""
    assert secretsmanager.football_key("", "us-east-1") == ""
    print("ok  failure or no secret id -> empty string, never an exception")

    metrics.ENABLED = False
    buf = io.StringIO()
    with redirect_stdout(buf):
        metrics.emit("ToolLatency", 120, "Milliseconds", Tool="get_match_state")
    assert buf.getvalue() == ""
    print("ok  metrics are silent unless SIDELINE_EMF=on")

    metrics.ENABLED = True
    buf = io.StringIO()
    with redirect_stdout(buf):
        metrics.emit("ToolLatency", 120, "Milliseconds", Tool="what_did_i_miss")
    doc = json.loads(buf.getvalue())
    m = doc["_aws"]["CloudWatchMetrics"][0]
    assert m["Namespace"] == "Sideline"
    assert m["Dimensions"] == [["Tool"]]
    assert m["Metrics"] == [{"Name": "ToolLatency", "Unit": "Milliseconds"}]
    assert doc["ToolLatency"] == 120 and doc["Tool"] == "what_did_i_miss"
    print("ok  EMF line has the namespace, dimension and metric the alarm reads")
    metrics.ENABLED = False

    print("\naws helpers: all good")


if __name__ == "__main__":
    main()
