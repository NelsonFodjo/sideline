from .apifootball import ApiFootballProvider
from .base import Provider, ProviderUnavailable

__all__ = ["ApiFootballProvider", "Provider", "ProviderUnavailable", "build"]


def build(api_key):
    """The live football feed. There is no recorded or demo provider."""
    return ApiFootballProvider(api_key)
