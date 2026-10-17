"""The safety kernel. The only code that decides whether a command may reach hardware.

Names are loaded lazily, because the driver base class imports `openhal.kernel.grants` and the
kernel itself imports the driver base class.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openhal.kernel.commands import Action, Command, Decision, Write
    from openhal.kernel.grants import Grant, GrantBook, GrantError
    from openhal.kernel.kernel import Kernel, StopReport
    from openhal.kernel.principals import Principal, agent, human, routine

_EXPORTS = {
    "Action": "commands",
    "Command": "commands",
    "Decision": "commands",
    "Write": "commands",
    "Grant": "grants",
    "GrantBook": "grants",
    "GrantError": "grants",
    "Kernel": "kernel",
    "StopReport": "kernel",
    "Principal": "principals",
    "agent": "principals",
    "human": "principals",
    "routine": "principals",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module 'openhal.kernel' has no attribute {name!r}")
    return getattr(importlib.import_module(f"openhal.kernel.{module}"), name)
