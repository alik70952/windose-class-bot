"""Site adapter registry."""

from __future__ import annotations

from src.sites.base import SiteAdapter
from src.sites.vadana_sum39 import VadanaSum39Adapter


def get_adapter(name: str) -> SiteAdapter:
    """Return a site adapter by stable config name."""
    if name == "vadana_sum39":
        return VadanaSum39Adapter()
    raise ValueError(f"Site adapter is not supported: {name}")
