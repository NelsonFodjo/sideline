"""The DynamoDB store, against a fake table that behaves like the real one
where it matters.

No AWS account: the fake rejects floats (DynamoDB does) and honours the
`attribute_not_exists(PK)` condition. Both bit us the first time this ran
against a real table (2026-10-13): the poller could not log a single event,
and live providers' fresh event ids would have defeated the dedupe.
This is a pin for those two failures, not a substitute for the real service.
"""

import json
from decimal import Decimal

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

try:
    from boto3.dynamodb.conditions import Key  # noqa: F401
except ImportError:
    Key = None

from sideline.state.store import Event


class Conditional(Exception):
    pass


class FakeTable(object):
    def __init__(self):
        self.items = {}
        self.meta = type("M", (), {"client": type("C", (), {"exceptions": type(
            "E", (), {"ConditionalCheckFailedException": Conditional})})})

    @staticmethod
    def _no_floats(x):
        if isinstance(x, float):
            raise TypeError("Float types are not supported. Use Decimal types instead.")
        if isinstance(x, dict):
            for v in x.values():
                FakeTable._no_floats(v)
        if isinstance(x, list):
            for v in x:
                FakeTable._no_floats(v)

    def put_item(self, Item, ConditionExpression=None):
        self._no_floats(Item)
        k = (Item["PK"], Item["SK"])
        if ConditionExpression == "attribute_not_exists(PK)" and k in self.items:
            raise Conditional()
        self.items[k] = dict(Item)

    def get_item(self, Key):
        it = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": it} if it else {}

    def query(self, KeyConditionExpression):
        parts = [c.get_expression()["values"] for c in
                 KeyConditionExpression.get_expression()["values"]]
        pk = [v for k, v in parts if k.name == "PK"][0]
        prefix = [v for k, v in parts if k.name == "SK"][0]
        rows = sorted((k, v) for k, v in self.items.items()
                      if k[0] == pk and k[1].startswith(prefix))
        return {"Items": [self._decimals(v) for _, v in rows]}

    @staticmethod
    def _decimals(item):
        """Real DynamoDB hands numbers back as Decimal."""
        def conv(x):
            if isinstance(x, int) and not isinstance(x, bool):
                return Decimal(x)
            if isinstance(x, dict):
                return {k: conv(v) for k, v in x.items()}
            if isinstance(x, list):
                return [conv(v) for v in x]
            return x
        return conv(item)


def main():
    if Key is None:
        print("skip  DynamoDB store (boto3 not installed)")
        return
    from sideline.state.dynamo import DynamoStore, event_sk
    s = DynamoStore.__new__(DynamoStore)
    s._t = FakeTable()

    # 1. A float in an event (every event has one: `at`) must be written.
    e = Event.make(7, 34, "goal", player="Saka", team="Arsenal")
    assert isinstance(e["at"], float)
    s.append_event(e)
    assert len(s.events(7)) == 1
    print("ok  an event with a float timestamp is written (DynamoDB rejects floats)")

    # 2. Live providers mint a new id on every read; the same goal must not
    #    be stored again.
    for _ in range(3):
        again = Event.make(7, 34, "goal", player="Saka", team="Arsenal")
        assert again["id"] != e["id"]
        s.append_event(again)
    assert len(s.events(7)) == 1, len(s.events(7))
    s.append_event(Event.make(7, 34, "card", player="Saka", team="Arsenal"))
    s.append_event(Event.make(7, 35, "goal", player="Saka", team="Arsenal"))
    assert len(s.events(7)) == 3
    print("ok  the same event re-read with a new id is stored once; distinct ones are kept")

    # 3. Reads come back as plain ints and floats, so the response is JSON.
    got = s.events(7)
    assert [x["minute"] for x in got] == [34, 34, 35]
    assert type(got[0]["minute"]) is int and isinstance(got[0]["at"], float)
    json.dumps(got)
    print("ok  Decimals are turned back into numbers; events serialise to JSON")

    # 4. Superseding rewrites the same item rather than adding one.
    s.supersede(7, got[0]["id"], "var-1")
    assert len(s.events(7)) == 3
    assert [x for x in s.events(7) if x["id"] == got[0]["id"]][0]["superseded_by"] == "var-1"
    assert event_sk(e) == event_sk(Event.make(7, 34, "goal", player="Saka"))
    print("ok  supersede updates in place; the sort key ignores the event id")

    # 5. Listener and fixture round-trip, including a float and the marker.
    rec = s.listener("u")
    rec.update(following=7, last_told_at=34, broadcast_offset=45)
    s.save_listener(rec)
    s.save_fixture({"fixture_id": 7, "home": "Arsenal", "away": "Spurs", "ratio": 0.5})
    assert s.listener("u")["last_told_at"] == 34 and s.listener("u")["following"] == 7
    assert s.fixture(7)["ratio"] == 0.5 and s.all_followed_fixtures() == [7]
    print("ok  listener marker and fixture survive a round trip")

    print("\ndynamo: all good")


if __name__ == "__main__":
    main()
