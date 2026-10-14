from .base import Provider, ProviderUnavailable
from .espn import EspnProvider

__all__ = ["Provider", "ProviderUnavailable", "EspnProvider", "build"]


def build(token=None):
    """The live multi-sport feed (ESPN). Zero-auth, real-time CDN."""
    return EspnProvider()
