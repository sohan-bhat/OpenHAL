"""A mock driver for tests, the demo and the conformance suite.

It keeps channel values in memory and records every operation that would have reached a real
transport in `transport_log`, so tests can prove that blocked commands never got this far.
Optional simulators give values some physics (the desk fan cools a warm room).
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading


class MockParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "mock"
    initial: dict[str, Any] = {}
    simulate: Literal["none", "desk-fan", "heater"] = "none"
    latency_s: float = Field(default=0.0, ge=0, le=5)
    fail_connect: bool = False
    fail_writes: bool = False
    fail_reads: bool = False
    disconnect_after_reads: int | None = None
    seed: int = 7
    ambient_c: float = 31.0


class MockDriver(Driver):
    """In-memory device. Never touches hardware."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="mock",
        protocols=("in-memory",),
        hazard_default="low",
        summary="A simulated device for tests, demos and the conformance suite.",
    )
    params_model: ClassVar[type[Any] | None] = MockParams

    def __init__(self, device: Any) -> None:
        super().__init__(device)
        self.settings = MockParams.model_validate(self.params)
        self.values: dict[str, Any] = {}
        self.transport_log: list[tuple[str, str, Any]] = []
        self.connected = False
        self.reads = 0
        self._random = random.Random(self.settings.seed)  # noqa: S311 (simulation, not security)
        self._temperature = self.settings.ambient_c

    @classmethod
    async def discover(cls) -> list[Discovered]:
        return [
            Discovered(
                driver="mock",
                address="mock://desk-fan",
                identifiers={"firmware.product": "desk-fan"},
                label="Simulated desk fan",
            )
        ]

    @property
    def simulated(self) -> bool:
        return True

    async def identify(self) -> dict[str, str]:
        return {"name": self.settings.name, "model": "mock"}

    async def connect(self) -> None:
        await self._delay()
        if self.settings.fail_connect:
            raise DriverError("The mock device refused the connection (fail_connect is set).")
        for name, spec in self.device.write.items():
            if name in self.settings.initial:
                self.values[name] = self.settings.initial[name]
            elif spec.type == "number":
                self.values[name] = spec.min
            elif spec.type == "bool":
                self.values[name] = False
            elif spec.type == "enum":
                self.values[name] = spec.values[0]
            else:
                self.values[name] = ""
        for name, read_spec in self.device.read.items():
            if name in self.settings.initial:
                self.values[name] = self.settings.initial[name]
            elif read_spec.type == "number":
                self.values[name] = self._temperature if self.settings.simulate != "none" else 0.0
            elif read_spec.type == "bool":
                self.values[name] = False
            elif read_spec.type == "enum":
                self.values[name] = read_spec.values[0]
            elif read_spec.type == "image":
                self.values[name] = b""
            else:
                self.values[name] = ""
        self.connected = True
        self.transport_log.append(("connect", "", None))

    async def describe(self) -> dict[str, Any] | None:
        return {
            "read": {name: spec.model_dump(exclude_none=True) for name, spec in self.device.read.items()},
            "write": {
                name: spec.model_dump(exclude_none=True, exclude={"confirmed"})
                for name, spec in self.device.write.items()
            },
        }

    async def read(self, channel: str) -> Reading:
        await self._delay()
        if not self.connected:
            raise DriverError("The mock device is not connected.")
        if self.settings.fail_reads:
            raise DriverError("The mock device didn't answer (fail_reads is set).")
        self.reads += 1
        if self.settings.disconnect_after_reads is not None and self.reads > self.settings.disconnect_after_reads:
            self.connected = False
            raise DriverError("The mock device disconnected.")
        if channel not in self.values:
            raise DriverError(f"The mock device has no channel {channel!r}.")
        self._step_simulation()
        unit = self.device.channel_unit(channel)
        return Reading(channel=channel, value=self.values[channel], unit=unit)

    def _step_simulation(self) -> None:
        if self.settings.simulate == "desk-fan":
            speed = float(self.values.get("fan_speed", 0.0))
            target = self.settings.ambient_c - 7.0 * speed / 100.0
            self._temperature += (target - self._temperature) * 0.25 + self._random.uniform(-0.05, 0.05)
            for name in self.device.read:
                if self.device.read[name].type == "number":
                    self.values[name] = round(self._temperature, 2)
        elif self.settings.simulate == "heater":
            power = float(self.values.get("power", 0.0))
            target = 22.0 + power * 1.2
            self._temperature += (target - self._temperature) * 0.2
            for name in self.device.read:
                if self.device.read[name].type == "number":
                    self.values[name] = round(self._temperature, 2)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        await self._delay()
        if not self.connected:
            raise DriverError("The mock device is not connected.")
        if self.settings.fail_writes:
            raise DriverError("The mock device rejected the write (fail_writes is set).")
        self.transport_log.append(("write", channel, value))
        self.values[channel] = value
        return Reading(channel=channel, value=value, unit=self.device.channel_unit(channel))

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        await self._delay()
        if not self.connected:
            raise DriverError("The mock device is not connected.")
        if self.settings.fail_writes:
            raise DriverError("The mock device rejected the action (fail_writes is set).")
        self.transport_log.append(("action", name, dict(args)))
        return {"ran": name}

    async def _safe_state(self) -> None:
        self.transport_log.append(("safe_state", "", None))

    async def health(self) -> Health:
        return Health(connected=self.connected, detail="mock")

    async def close(self) -> None:
        self.connected = False
        self.transport_log.append(("close", "", None))

    def hardware_writes(self) -> list[tuple[str, str, Any]]:
        """Operations that would have changed real hardware."""
        return [entry for entry in self.transport_log if entry[0] in ("write", "action")]

    async def _delay(self) -> None:
        if self.settings.latency_s:
            await asyncio.sleep(self.settings.latency_s)
