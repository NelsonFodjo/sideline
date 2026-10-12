import logging

from .store import Event, Listener, MemoryStore, Store, new_id

__all__ = ["Event", "Listener", "MemoryStore", "Store", "new_id"]

LOG = logging.getLogger("sideline.state")


def _table_answers(table_name, region):
    """Does the DynamoDB table exist and respond, within a few seconds?

    Short timeouts and one attempt, because this runs at startup and a
    restricted network must not stall the server for a minute.
    """
    import os
    import boto3
    from botocore.config import Config
    kw = {"region_name": region,
          "config": Config(connect_timeout=3, read_timeout=3,
                           retries={"max_attempts": 1})}
    if os.environ.get("SIDELINE_DYNAMO_ENDPOINT"):
        kw["endpoint_url"] = os.environ["SIDELINE_DYNAMO_ENDPOINT"]
    boto3.client("dynamodb", **kw).describe_table(TableName=table_name)


def build(kind, **kw):
    """Factory. SIDELINE_STATE=auto|memory|dynamo.

    "auto" tries DynamoDB (credentials are present) and falls back to
    memory with a warning if the table is not there or not reachable, so
    present credentials never stop the server from starting. An explicit
    "dynamo" does not fall back: you asked for it, so a failure is loud.
    """
    table, region = kw.get("table_name", "sideline"), kw.get("region", "us-east-1")
    if kind == "memory":
        return MemoryStore()
    if kind == "auto":
        try:
            _table_answers(table, region)
            from .dynamo import DynamoStore
            LOG.info("state: DynamoDB table %r", table)
            return DynamoStore(table, region)
        except Exception as e:                                 # noqa: BLE001
            LOG.warning("state: DynamoDB table %r not usable, using memory "
                        "(create it with `make create-table`): %s", table, e)
            return MemoryStore()
    if kind == "dynamo":
        from .dynamo import DynamoStore
        return DynamoStore(table, region)
    raise ValueError("unknown state backend: %s" % kind)
