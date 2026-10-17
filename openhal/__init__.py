"""OpenHAL, an open hardware abstraction layer for AI agents.

The public Python library lives here. Most users import `openhal` to connect to a running hub
or to run an embedded hub for scripts and tests.
"""

from __future__ import annotations

from openhal._brand import PRODUCT_NAME, SPEC_VERSION

__version__ = "0.1.0.dev0"

__all__ = ["PRODUCT_NAME", "SPEC_VERSION", "__version__"]
