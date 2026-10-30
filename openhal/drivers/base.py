"""The driver interface. Every protocol driver and bridge subclasses `Driver`.

Drivers implement a protocol. Device files describe a specific device and its limits. A driver
never checks whether a change is safe. That is the safety kernel's job, and the only way a
change reaches `_write`, `_action` or `_safe_state` is through the final methods below, which
consume a single-use grant issued by the kernel (ADR 0004). A test checks that nothing else in
the package calls those protected methods.
"""

from __future__ import annotations

import abc
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final, Literal, final

from openhal.kernel.grants import GrantError
from openhal.spec.models import DeviceFile

Verifier = Callable[[object, str, str, object], None]
"""Consumes a grant for (device_id, target, value) or raises GrantError."""

SafeStateSupport = Literal["file", "native", "none"]
Conformance = Literal["core", "control", "full"]


@dataclass(frozen=True, slots=True)
class Reading:
    """One value read from a device, in the channel's declared unit."""

    channel: str
    value: float | bool | str | bytes | None
    unit: str | None = None
    at: float = field(default_factory=time.time)
    suspect: bool = False


@dataclass(frozen=True, slots=True)
class Discovered:
    """Something a driver found during discovery. Discovery never changes hardware."""

    driver: str
    address: str
    identifiers: dict[str, str] = field(default_factory=dict)
    label: str | None = None


@dataclass(frozen=True, slots=True)
class Health:
    connected: bool
    detail: str = ""
    latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class DriverInfo:
    """What a driver covers, shown in `openhal driver list` and the catalog.

    `conformance` is the protocol level the driver meets (ADR 0015). A read-only driver, such as a
    camera, is "core". Drivers that write through the safety kernel are "control".
    """

    name: str
    protocols: tuple[str, ...]
    hazard_default: Literal["low", "medium", "high"]
    summary: str
    safe_state_support: SafeStateSupport = "file"
    conformance: Conformance = "control"


class DriverError(RuntimeError):
    """The device or protocol failed. The message states what happened and the next step."""


_NO_VERIFIER: Final = "This driver is not attached to a safety kernel, so it can't change hardware."
_SEALED: Final = frozenset({"write", "action", "safe_state", "attach", "_consume"})


class Driver(abc.ABC):
    """Base class for protocol drivers and bridges."""

    info: ClassVar[DriverInfo]
    params_model: ClassVar[type[Any] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        sealed = _SEALED.intersection(cls.__dict__)
        if sealed:
            raise TypeError(
                f"{cls.__name__} may not override {', '.join(sorted(sealed))}. Implement _write and _action."
            )

    def __init__(self, device: DeviceFile) -> None:
        self.device = device
        self.params = self.validate_params(device.connect.params)
        self._verify: Verifier | None = None

    @final
    def attach(self, verifier: Verifier) -> None:
        if self._verify is not None:
            raise GrantError("This driver is already attached to a kernel.")
        self._verify = verifier

    @property
    def simulated(self) -> bool:
        """True when this driver connects to a simulator instead of hardware, so clients can label demo data."""
        return False

    @classmethod
    def validate_params(cls, params: dict[str, Any]) -> dict[str, Any]:
        """Check the device file's connect parameters. Override with a params_model or custom checks."""
        if cls.params_model is None:
            return dict(params)
        model = cls.params_model.model_validate(params)
        return dict(model.model_dump())

    @classmethod
    async def discover(cls) -> list[Discovered]:
        return []

    async def identify(self) -> dict[str, str]:
        return {}

    @abc.abstractmethod
    async def connect(self) -> None: ...

    async def describe(self) -> dict[str, Any] | None:
        """Map what the protocol exposes into device file sections, or None if it can't describe itself."""
        return None

    @abc.abstractmethod
    async def read(self, channel: str) -> Reading: ...

    @final
    async def write(self, channel: str, value: float | bool | str, grant: object) -> Reading | None:
        """Change one channel. `value` is already in the channel's unit. Needs a kernel grant."""
        self._consume(grant, f"write:{channel}", value)
        return await self._write(channel, value)

    @final
    async def action(self, name: str, args: dict[str, Any], grant: object) -> Any:
        """Run one action with already-validated arguments. Needs a kernel grant."""
        self._consume(grant, f"action:{name}", args)
        return await self._action(name, args)

    @final
    async def safe_state(self, grant: object) -> None:
        """Run the protocol's own emergency behavior (feed hold, outputs off). Needs a kernel grant."""
        self._consume(grant, "safe_state", None)
        await self._safe_state()

    async def health(self) -> Health:
        return Health(connected=True)

    async def close(self) -> None:
        return None

    @final
    def _consume(self, grant: object, target: str, value: object) -> None:
        if self._verify is None:
            raise GrantError(_NO_VERIFIER)
        self._verify(grant, self.device.device_id, target, value)

    @abc.abstractmethod
    async def _write(self, channel: str, value: float | bool | str) -> Reading | None: ...

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        raise DriverError(f"{self.info.name} has no action {name!r}.")

    async def _safe_state(self) -> None:
        """Protocol-native safe behavior. The kernel applies the device file's safe_state separately."""
        return None
