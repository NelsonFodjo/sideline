#!/usr/bin/env python3
"""Create the DynamoDB table Sideline uses, with its TTL. Idempotent.

    python3 scripts/create_table.py                  # real table, your account
    SIDELINE_DYNAMO_ENDPOINT=http://localhost:8000 \\
        python3 scripts/create_table.py              # DynamoDB Local

Same design as docs/DEPLOYMENT.md and deploy/sideline.yaml: one table,
PK + SK, on-demand billing, TTL on `expires_at`. Reads SIDELINE_TABLE and
AWS_REGION like the server does.
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
    table = os.environ.get("SIDELINE_TABLE", "sideline")
    kw = {"region_name": os.environ.get("AWS_REGION", "us-east-1")}
    endpoint = os.environ.get("SIDELINE_DYNAMO_ENDPOINT")
    if endpoint:
        kw["endpoint_url"] = endpoint
    db = boto3.client("dynamodb", **kw)

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
        # Already enabled raises ValidationException; DynamoDB Local may
        # not implement TTL at all. Neither is a reason to fail.
        print("TTL: %s" % str(e).split(":")[-1].strip()[:100])

    print("\nnow:  just start the server; SIDELINE_STATE=auto will use this table")


if __name__ == "__main__":
    main()
