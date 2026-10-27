"""OpenHAL, an open hardware agent layer, the layer between AI agents and hardware.

The public Python library lives here. Most users import `openhal` to connect to a running hub
or to run an embedded hub for scripts and tests.
"""

from __future__ import annotations

from typing import Any

from openhal._brand import PRODUCT_NAME, SPEC_VERSION

__version__ = "0.1.0.dev0"

__all__ = ["PRODUCT_NAME", "SPEC_VERSION", "__version__", "aconnect", "connect"]


def __getattr__(name: str) -> Any:
    if name in ("connect", "aconnect"):
        from openhal import client

        return getattr(client, name)
    raise AttributeError(f"module 'openhal' has no attribute {name!r}")
