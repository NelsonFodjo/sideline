"""DynamoStore reads are kept for a few seconds and every write goes through, so a turn costs few round trips.

A fake table counts the calls; no AWS and no boto3 needed for the listener and fixture paths.
"""

import time

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

from sideline.state import dynamo
from sideline.state.dynamo import DynamoStore, to_ddb


class FakeTable(object):
    def __init__(self):
        self.items, self.gets, self.puts, self.deletes = {}, 0, 0, 0

    def get_item(self, Key):
        self.gets += 1
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": item} if item else {}

    def put_item(self, Item, **kw):
        self.puts += 1
        self.items[(Item["PK"], Item["SK"])] = Item

    def delete_item(self, Key):
        self.deletes += 1
        self.items.pop((Key["PK"], Key["SK"]), None)


def store():
    s = DynamoStore.__new__(DynamoStore)
    s._t = FakeTable()
    s._init_cache()
    return s


def main():
    s = store()
    rec = s.listener("ann")
    assert s._t.gets == 1
    for _ in range(10):
        s.listener("ann")
    assert s._t.gets == 1, "ten more reads within the window cost no round trip"
    print("ok  a listener read again within a few seconds is not fetched again")

    rec["following"] = "42"
    s.save_listener(rec)
    assert s.listener("ann")["following"] == "42" and s._t.gets == 1, "a write is visible at once, with no re-read"
    got = s.listener("ann")
    got["following"] = "mutated"
    assert s.listener("ann")["following"] == "42", "a caller changing what it read cannot change the kept copy"
    print("ok  writes go through to the cache; callers get copies")

    s.save_fixture({"fixture_id": 7, "home": "A", "away": "B"})
    gets = s._t.gets
    assert s.fixture(7)["home"] == "A" and s.fixture("7")["away"] == "B" and s._t.gets == gets
    print("ok  a saved fixture is read back without a round trip")

    s.forget_listener("ann")
    assert s.listener("ann")["following"] is None and s._t.deletes >= 1, "forgetting drops the profile and the kept copy"
    print("ok  forget_listener erases the record and the kept copy")

    # a listener's profile and its follower marker are written at the same time, and the "who follows" lists are dropped
    s2 = store()
    rec = s2.listener("zoe")
    rec["following"] = "77"
    s2._keep_set(("followers", "77"), ["stale"])
    puts = s2._t.puts
    s2.save_listener(rec)
    assert s2._t.puts == puts + 2, "the profile and the marker"
    assert s2._keep_get(("followers", "77"), 60)[0] is False, "a saved listener drops the kept follower lists"
    started = time.time()
    s2._together(lambda: time.sleep(0.2), lambda: time.sleep(0.2), lambda: time.sleep(0.2))
    assert time.time() - started < 0.45, "three independent calls take the time of one"
    print("ok  independent writes run together; saving a listener refreshes the follower lists")

    saved = dynamo.LISTENER_READ_SECONDS
    dynamo.LISTENER_READ_SECONDS = 0.05
    try:
        s.listener("zed")
        gets = s._t.gets
        time.sleep(0.1)
        s.listener("zed")
        assert s._t.gets == gets + 1, "an old copy is fetched again"
    finally:
        dynamo.LISTENER_READ_SECONDS = saved
    print("ok  a kept read expires")

    if dynamo.HAVE_BOTO3:
        class Client(object):
            class exceptions(object):
                ConditionalCheckFailedException = type("C", (Exception,), {})

        class Meta(object):
            client = Client

        s._t.meta = Meta
        queries = []

        def query(**kw):
            queries.append(1)
            return {"Items": [{"data": to_ddb({"id": "e1", "fixture_id": 9, "minute": 5, "kind": "goal", "at": 1.0})}]}
        s._t.query = query
        for _ in range(3):
            assert len(s.events(9)) == 1
        assert len(queries) == 1, "events are queried once per window"
        s.append_event({"id": "e2", "fixture_id": 9, "minute": 6, "kind": "card", "at": 2.0})
        s.events(9)
        assert len(queries) == 2, "an appended event drops the kept list"
        print("ok  the event log is kept briefly and dropped when an event is appended")
    print("\ndynamo cache: all good")


if __name__ == "__main__":
    main()
