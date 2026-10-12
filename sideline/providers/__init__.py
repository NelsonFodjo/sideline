from .base import Provider

__all__ = ["Provider", "build"]


def build(kind, **kw):
    """SIDELINE_PROVIDER=replay|apifootball."""
    if kind == "replay":
        from .replay import ReplayProvider
        return ReplayProvider(kw["path"], speed=kw.get("speed", 1.0),
                              start_minute=kw.get("start_minute", 0))
    if kind == "statsbomb":
        from .statsbomb import StatsBombProvider
        return StatsBombProvider(kw["events_path"], kw.get("lineups_path"))
    if kind == "apifootball":
        from .apifootball import ApiFootballProvider
        return ApiFootballProvider(kw.get("api_key"))
    raise ValueError("unknown provider: %s" % kind)
