"""A simulated SiLA 2 thermoshaker, served by the official sila2 package's own server.

The two features are written as SiLA Feature Definition Language and served without generated
code, through `FeatureImplementationBase` subclasses, so the driver runs against the real
gRPC protocol, real constraint validation and real defined execution errors.

    TemperatureController
      CurrentTemperature      observable property, Real, degC
      TargetTemperature       property, Real, degC
      DeviceState             property, Structure of LidClosed (Boolean) and Mode (String)
      SetTargetTemperature    command, TargetTemperature (Real, degC, 4 to 95), error TooHot above the lid limit
    ShakeController
      ShakingSpeed            observable property, Integer, rpm
      Shake                   observable command, Speed (Integer, rpm) and Duration (Real, s)
      StopShaking             command

Fault hooks. `delay_s` slows every property read, `restart()` stops and starts the server on the
same port, and `stop()` takes it away.
"""

from __future__ import annotations

import contextlib
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

REAL_C = (
    "<Constrained><DataType><Basic>Real</Basic></DataType><Constraints>"
    "<Unit><Label>degC</Label><Factor>1</Factor><Offset>273.15</Offset>"
    "<UnitComponent><SIUnit>Kelvin</SIUnit><Exponent>1</Exponent></UnitComponent></Unit>{extra}"
    "</Constraints></Constrained>"
)
INT_RPM = (
    "<Constrained><DataType><Basic>Integer</Basic></DataType><Constraints>"
    "<Unit><Label>rpm</Label><Factor>0.0166666667</Factor><Offset>0</Offset>"
    "<UnitComponent><SIUnit>Second</SIUnit><Exponent>-1</Exponent></UnitComponent></Unit>"
    "<MinimalInclusive>0</MinimalInclusive><MaximalInclusive>3000</MaximalInclusive>"
    "</Constraints></Constrained>"
)
REAL_S = (
    "<Constrained><DataType><Basic>Real</Basic></DataType><Constraints>"
    "<Unit><Label>s</Label><Factor>1</Factor><Offset>0</Offset>"
    "<UnitComponent><SIUnit>Second</SIUnit><Exponent>1</Exponent></UnitComponent></Unit>"
    "</Constraints></Constrained>"
)
HEAD = (
    '<?xml version="1.0" encoding="utf-8" ?>'
    '<Feature SiLA2Version="1.0" FeatureVersion="1.0" MaturityLevel="Verified" Originator="org.openhal" '
    'Category="examples" xmlns="http://www.sila-standard.org" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="http://www.sila-standard.org '
    'https://gitlab.com/SiLA2/sila_base/raw/master/schema/FeatureDefinition.xsd">'
)


def _named(tag: str, identifier: str, body: str = "") -> str:
    return (
        f"<{tag}><Identifier>{identifier}</Identifier><DisplayName>{identifier}</DisplayName>"
        f"<Description>{identifier} of the simulated thermoshaker.</Description>{body}</{tag}>"
    )


def _typed(tag: str, identifier: str, data_type: str, extra: str = "") -> str:
    return _named(tag, identifier, f"{extra}<DataType>{data_type}</DataType>")


TEMPERATURE_FDL = (
    HEAD
    + "<Identifier>TemperatureController</Identifier><DisplayName>Temperature Controller</DisplayName>"
    + "<Description>Heats and cools the block.</Description>"
    + _named(
        "Command",
        "SetTargetTemperature",
        "<Observable>No</Observable>"
        + _typed(
            "Parameter",
            "TargetTemperature",
            REAL_C.format(extra="<MinimalInclusive>4</MinimalInclusive><MaximalInclusive>95</MaximalInclusive>"),
        )
        + "<DefinedExecutionErrors><Identifier>TooHot</Identifier></DefinedExecutionErrors>",
    )
    + _typed("Property", "CurrentTemperature", REAL_C.format(extra=""), "<Observable>Yes</Observable>")
    + _typed("Property", "TargetTemperature", REAL_C.format(extra=""), "<Observable>No</Observable>")
    + _typed(
        "Property",
        "DeviceState",
        "<Structure>"
        + _typed("Element", "LidClosed", "<Basic>Boolean</Basic>")
        + _typed("Element", "Mode", "<Basic>String</Basic>")
        + "</Structure>",
        "<Observable>No</Observable>",
    )
    + _named("DefinedExecutionError", "TooHot")
    + "</Feature>"
)
SHAKE_FDL = (
    HEAD
    + "<Identifier>ShakeController</Identifier><DisplayName>Shake Controller</DisplayName>"
    + "<Description>Shakes the plate.</Description>"
    + _named(
        "Command",
        "Shake",
        "<Observable>Yes</Observable>"
        + _typed("Parameter", "Speed", INT_RPM)
        + _typed("Parameter", "Duration", REAL_S)
        + _typed("Response", "Completed", "<Basic>Boolean</Basic>"),
    )
    + _named("Command", "StopShaking", "<Observable>No</Observable>")
    + _typed("Property", "ShakingSpeed", INT_RPM, "<Observable>Yes</Observable>")
    + "</Feature>"
)


@dataclass
class Block:
    """The thermoshaker's state, shared by every server instance across restarts."""

    temperature: float = 22.0
    target: float = 22.0
    lid_limit: float = 80.0
    lid_closed: bool = True
    mode: str = "idle"
    speed: int = 0
    shake_until: float = 0.0
    delay_s: float = 0.0
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    temperature_queue: queue.Queue[Any] = field(default_factory=queue.Queue)
    speed_queue: queue.Queue[Any] = field(default_factory=queue.Queue)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class ThermoShakerSim:
    """The SiLA server for one simulated thermoshaker."""

    def __init__(self) -> None:
        self.block = Block()
        self.port = 0
        self._server: Any = None
        self._features: tuple[Any, Any] | None = None
        self._lock = threading.Lock()

    @property
    def calls(self) -> list[tuple[str, tuple[Any, ...]]]:
        return self.block.calls

    def start(self) -> int:
        from openhal.drivers.sila2 import bootstrap

        bootstrap.ensure()
        from sila2.framework import Feature

        if self._features is None:
            self._features = (Feature(TEMPERATURE_FDL), Feature(SHAKE_FDL))
        if not self.port:
            self.port = _free_port()
        self._serve()
        return self.port

    def _serve(self) -> None:
        from sila2.server import SilaServer

        assert self._features is not None
        temperature, shake = self._features
        server = SilaServer(
            server_name="Simulated thermoshaker",
            server_type="ThermoShaker",
            server_description="OpenHAL SiLA 2 simulator",
            server_version="1.0",
            server_vendor_url="https://github.com/openhal",
            server_uuid="7c0e9a1e-56c4-4c37-9f43-6f5b1f0e2a11",
        )
        server.set_feature_implementation(temperature, _temperature_impl(server, self.block, temperature))
        server.set_feature_implementation(shake, _shake_impl(server, self.block))
        server.start_insecure("127.0.0.1", self.port, enable_discovery=False)
        self._server = server

    def restart(self) -> None:
        self.stop()
        self._serve()

    def push_temperature(self, value: float) -> None:
        self.block.temperature = value
        self.block.temperature_queue.put(value)

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            with contextlib.suppress(Exception):
                server.stop(grace_period=0.2)


def _temperature_impl(server: Any, block: Block, feature: Any) -> Any:
    from sila2.framework.errors.defined_execution_error import DefinedExecutionError
    from sila2.server import FeatureImplementationBase

    class TooHotError(DefinedExecutionError):
        def __init__(self, message: str) -> None:
            super().__init__(feature.defined_execution_errors["TooHot"], message)

    class Temperature(FeatureImplementationBase):
        def __init__(self, parent: Any) -> None:
            super().__init__(parent)
            self._CurrentTemperature_producer_queue = block.temperature_queue
            block.temperature_queue.put(block.temperature)

        def CurrentTemperature_on_subscription(self, *, metadata: Any) -> None:  # noqa: N802
            return None

        def get_TargetTemperature(self, *, metadata: Any) -> float:  # noqa: N802
            time.sleep(block.delay_s)
            return block.target

        def get_DeviceState(self, *, metadata: Any) -> Any:  # noqa: N802
            time.sleep(block.delay_s)
            return (block.lid_closed, block.mode)

        def SetTargetTemperature(self, TargetTemperature: float, *, metadata: Any) -> None:  # noqa: N802, N803
            block.calls.append(("SetTargetTemperature", (TargetTemperature,)))
            if TargetTemperature > block.lid_limit:
                raise TooHotError(f"{TargetTemperature} degC is above the lid limit of {block.lid_limit} degC.")
            block.target = TargetTemperature
            block.temperature = TargetTemperature
            block.temperature_queue.put(TargetTemperature)

    return Temperature(server)


def _shake_impl(server: Any, block: Block) -> Any:
    from sila2.server import FeatureImplementationBase

    class Shake(FeatureImplementationBase):
        def __init__(self, parent: Any) -> None:
            super().__init__(parent)
            self._ShakingSpeed_producer_queue = block.speed_queue
            block.speed_queue.put(block.speed)

        def ShakingSpeed_on_subscription(self, *, metadata: Any) -> None:  # noqa: N802
            return None

        def Shake(self, Speed: int, Duration: float, *, metadata: Any, instance: Any) -> bool:  # noqa: N802, N803
            block.calls.append(("Shake", (Speed, Duration)))
            instance.begin_execution()
            block.speed, block.mode = Speed, "shaking"
            block.speed_queue.put(Speed)
            block.shake_until = time.monotonic() + Duration
            while time.monotonic() < block.shake_until:
                time.sleep(0.02)
            completed = block.speed == Speed
            block.speed, block.mode = 0, "idle"
            block.speed_queue.put(0)
            return completed

        def StopShaking(self, *, metadata: Any) -> None:  # noqa: N802
            block.calls.append(("StopShaking", ()))
            block.shake_until = 0.0
            block.speed = 0
            block.speed_queue.put(0)

    return Shake(server)
