from .store import Event, Listener, MemoryStore, Store, new_id

__all__ = ["Event", "Listener", "MemoryStore", "Store", "new_id"]


def build(kind, **kw):
    """Factory. SIDELINE_STATE=memory|dynamo."""
    if kind == "memory":
        return MemoryStore()
    if kind == "dynamo":
        from .dynamo import DynamoStore
        return DynamoStore(kw["table_name"], kw.get("region", "us-east-1"))
    raise ValueError("unknown state backend: %s" % kind)
