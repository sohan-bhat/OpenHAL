"""Find driver classes by name. Drivers are imported lazily so optional dependencies stay optional."""

from __future__ import annotations

import importlib
from typing import Final

from openhal.drivers.base import Driver

_MODULES: Final = {
    "mock": "openhal.drivers.mock.driver:MockDriver",
}
"""Driver name to `module:Class`. Each driver package adds its line here when it lands."""


class UnknownDriver(LookupError):
    """No driver with that name is installed."""


def register(name: str, path: str) -> None:
    """Register a driver class path, for drivers outside this package."""
    _MODULES[name] = path


def names() -> list[str]:
    return sorted(_MODULES)


def load(name: str) -> type[Driver]:
    """Import and return the driver class registered under `name`."""
    path = _MODULES.get(name)
    if path is None:
        raise UnknownDriver(f"No driver named {name!r} is installed. Installed drivers are {', '.join(names())}.")
    module_name, _, class_name = path.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise UnknownDriver(
            f"The {name} driver needs an optional dependency that isn't installed ({exc.name}). "
            f"Install it with: uv pip install 'openhal-hub[{name}]'"
        ) from exc
    driver = getattr(module, class_name)
    if not (isinstance(driver, type) and issubclass(driver, Driver)):
        raise UnknownDriver(f"{path} is not a Driver subclass.")
    return driver
