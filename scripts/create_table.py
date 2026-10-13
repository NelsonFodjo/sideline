#!/usr/bin/env python3
"""Create the DynamoDB table Sideline uses, with its TTL. Idempotent.

    python3 scripts/create_table.py        # or: make create-table

One table, PK + SK, on-demand billing, TTL on `expires_at` (design:
sideline/state/dynamo.py). Reads SIDELINE_TABLE and AWS_REGION like the server.
Needs the permissions in docs/AWS_SETUP.md.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env, environment wins)


def main():
    try:
        import boto3
    except ImportError:
        sys.exit("boto3 is not installed:  pip3 install boto3")
    from sideline.config import CONFIG
    table = CONFIG.table
    db = boto3.client("dynamodb", region_name=CONFIG.region)

    try:
        db.describe_table(TableName=table)
        print("table %r already exists - nothing to do" % table)
    except db.exceptions.ResourceNotFoundException:
        db.create_table(
            TableName=table,
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                                  {"AttributeName": "SK", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                       {"AttributeName": "SK", "KeyType": "RANGE"}],
            BillingMode="PAY_PER_REQUEST")
        db.get_waiter("table_exists").wait(TableName=table)
        print("created table %r" % table)

    try:
        db.update_time_to_live(
            TableName=table,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "expires_at"})
        print("TTL enabled on expires_at")
    except Exception as e:                                     # noqa: BLE001
        # Already enabled raises ValidationException: not a reason to fail.
        print("TTL: %s" % str(e).split(":")[-1].strip()[:100])

    print("\nnow:  just start the server; SIDELINE_STATE=auto will use this table")


if __name__ == "__main__":
    main()
