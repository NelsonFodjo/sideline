"""AWS Secrets Manager, for the football API key.

Precedence: the SIDELINE_FOOTBALL_KEY environment variable always wins.
Only when it is unset and SIDELINE_FOOTBALL_SECRET names a secret (name
or ARN) is the key fetched, once, at startup. The secret value may be the
bare key or JSON like {"SIDELINE_FOOTBALL_KEY": "..."}.

(On App Runner the stack can instead inject the secret as the
SIDELINE_FOOTBALL_KEY variable itself, in which case this is never used.)

Never raises: a failure returns "" and the caller carries on with
whatever it already had, so a Secrets Manager outage cannot stop the
replay demo from starting.
"""

import json
import logging

LOG = logging.getLogger("sideline.secrets")


def football_key(secret_id, region, name="SIDELINE_FOOTBALL_KEY", client=None):
    if not secret_id:
        return ""
    try:
        if client is None:
            import boto3
            client = boto3.client("secretsmanager", region_name=region)
        raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
    except Exception as e:                                     # noqa: BLE001
        LOG.warning("could not read secret %s: %s", secret_id, e)
        return ""
    try:
        doc = json.loads(raw)
        if isinstance(doc, dict):
            return str(doc.get(name, "")).strip()
    except ValueError:
        pass
    return raw.strip()
