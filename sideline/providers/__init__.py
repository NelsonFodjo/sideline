from .base import Provider, ProviderUnavailable
from .sportmonks import SportmonksProvider

__all__ = ["Provider", "ProviderUnavailable", "SportmonksProvider", "build"]


def build(token):
    """The live football feed (Sportmonks). There is no recorded or demo provider."""
    return SportmonksProvider(token)
