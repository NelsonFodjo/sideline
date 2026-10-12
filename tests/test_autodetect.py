"""Integrations switch on when their credentials are present, and an
explicit value always wins."""

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

from sideline import autodetect as a

KEYS = {"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "y"}


def main():
    # --- AWS credentials
    assert a.aws_credentials(KEYS)
    assert not a.aws_credentials({})
    assert not a.aws_credentials({"AWS_ACCESS_KEY_ID": "x"})        # half a pair
    assert a.aws_credentials({"AWS_PROFILE": "work"})
    assert a.aws_credentials({"AWS_WEB_IDENTITY_TOKEN_FILE": "/t"})
    print("ok  credentials: key pair, profile, or web-identity; half a pair is not enough")

    # --- Bedrock
    assert a.bedrock_enabled(KEYS)                                  # auto + keys -> on
    assert not a.bedrock_enabled({})                                # auto, none -> off
    assert a.bedrock_enabled({"SIDELINE_BEDROCK": "on"})            # forced on
    assert not a.bedrock_enabled({**KEYS, "SIDELINE_BEDROCK": "off"})  # forced off wins
    assert a.bedrock_enabled({**KEYS, "SIDELINE_BEDROCK": "auto"})
    print("ok  bedrock: auto follows the keys; on/off always win")

    # --- provider
    assert a.provider_kind({}) == "replay"
    assert a.provider_kind({"SIDELINE_FOOTBALL_KEY": "k"}) == "apifootball"
    assert a.provider_kind({"SIDELINE_FOOTBALL_SECRET": "arn"}) == "apifootball"
    assert a.provider_kind({"SIDELINE_FOOTBALL_KEY": "k", "SIDELINE_PROVIDER": "replay"}) == "replay"
    assert a.provider_kind({"SIDELINE_PROVIDER": "apifootball"}) == "apifootball"
    print("ok  provider: a football key means live; explicit replay still wins")

    # --- state
    assert a.state_kind({}) == "memory"
    assert a.state_kind(KEYS) == "auto"                             # try dynamo, may fall back
    assert a.state_kind({"SIDELINE_DYNAMO_ENDPOINT": "http://localhost:8000"}) == "auto"
    assert a.state_kind({**KEYS, "SIDELINE_STATE": "memory"}) == "memory"
    assert a.state_kind({"SIDELINE_STATE": "dynamo"}) == "dynamo"
    print("ok  state: credentials mean try DynamoDB; explicit memory/dynamo win")

    # --- the state factory really falls back, not crashes
    from sideline import state
    import sideline.state as st
    st._table_answers = lambda t, r: (_ for _ in ()).throw(RuntimeError("no such table"))
    store = state.build("auto", table_name="sideline", region="us-east-1")
    assert type(store).__name__ == "MemoryStore"
    print("ok  auto state with an unreachable table falls back to memory, with a warning")

    print("\nautodetect: all good")


if __name__ == "__main__":
    main()
