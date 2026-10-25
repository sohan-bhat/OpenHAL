"""Find driver classes by name.

Each driver is a package under openhal/drivers/ whose `__init__.py` declares two constants and
imports nothing heavy.

    NAME = "scpi"
    ENTRY = "openhal.drivers.scpi.driver:ScpiDriver"

The registry reads those constants and imports the driver module only when it is used, so a
missing optional dependency only affects the driver that needs it. Drivers outside this package
can call `register`.
"""

from __future__ import annotations

import importlib
import pkgutil
from functools import cache
from typing import Any, Final

from openhal.drivers.base import Driver

_EXTRA: dict[str, str] = {}
_SKIP: Final = frozenset({"base", "registry"})


class UnknownDriver(LookupError):  # noqa: N818
    """No driver with that name is installed."""


@cache
def _discovered() -> dict[str, str]:
    import openhal.drivers as package

    found: dict[str, str] = {}
    for module in pkgutil.iter_modules(package.__path__):
        if not module.ispkg or module.name in _SKIP:
            continue
        declared = importlib.import_module(f"openhal.drivers.{module.name}")
        name = getattr(declared, "NAME", None)
        entry = getattr(declared, "ENTRY", None)
        if isinstance(name, str) and isinstance(entry, str):
            found[name] = entry
    return found


def _all() -> dict[str, str]:
    return {**_discovered(), **_EXTRA}


def register(name: str, path: str) -> None:
    """Register a driver class path (`module:Class`), for drivers outside this package."""
    _EXTRA[name] = path


def names() -> list[str]:
    return sorted(_all())


def package_for(name: str) -> str | None:
    """The module that holds a driver's conformance case, if it lives in this package."""
    entry = _discovered().get(name)
    if entry is None:
        return None
    return entry.split(":", 1)[0].rsplit(".", 1)[0]


def load(name: str) -> type[Driver]:
    """Import and return the driver class registered under `name`."""
    path = _all().get(name)
    if path is None:
        raise UnknownDriver(f"No driver named {name!r} is installed. Installed drivers are {', '.join(names())}.")
    module_name, _, class_name = path.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise UnknownDriver(
            f"The {name} driver needs an optional dependency that isn't installed ({exc.name}). "
            f"Install it with uv sync --extra {name} in a checkout, or reinstall the hub with "
            f'uv tool install --compile-bytecode "openhal-hub[{name}] @ git+https://github.com/sohan-bhat/OpenHAL", '
            "listing every extra you use."
        ) from exc
    driver = getattr(module, class_name)
    if not (isinstance(driver, type) and issubclass(driver, Driver)):
        raise UnknownDriver(f"{path} is not a Driver subclass.")
    return driver


def connect_params(driver: str, address: str) -> dict[str, Any]:
    """Driver parameters for a discovered address. A `host:port` address fills both for drivers with a port."""
    from openhal.spec.models import PRIMARY_PARAM

    primary = PRIMARY_PARAM.get(driver, "target")
    try:
        model = load(driver).params_model
    except UnknownDriver:
        model = None
    fields = getattr(model, "model_fields", {})
    host, sep, port = address.rpartition(":")
    if primary == "host" and "port" in fields and sep and port.isdigit() and host:
        return {primary: host.strip("[]"), "port": int(port)}
    return {primary: address}
