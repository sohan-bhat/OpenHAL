"""Shared fixtures for kernel tests. A fake clock and helpers to register mock devices."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from openhal.drivers.mock import MockDriver
from openhal.kernel import Kernel
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FAN = """
device: Desk fan
id: desk-fan
connect: { mock: fan }
read:
  temperature: { unit: degC, every: 1 s }
write:
  fan_speed: { unit: percent, min: 0, max: 100, step: 1, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

HEATER = """
device: Curing heater
id: heater
connect: { mock: heater }
read:
  temp: { unit: degC, every: 1 s }
write:
  power: { unit: W, min: 0, max: 60 }
  mode: { type: enum, values: [off, eco, full] }
  enabled: { type: bool }
  label: { type: string, max_length: 8, pattern: "^[a-z]+$" }
actions:
  pulse:
    args:
      seconds: { unit: s, min: 1, max: 10 }
    require: ["enabled == true"]
    confirm: confirm
  purge: { confirm: confirm-each-time, effects: [power] }
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 W"
    require: "desk-fan.fan_speed >= 30 %"
    message: "The heater needs the fan at 30 % or more."
watchdog:
  max_duration:
    - when: "power > 40 W"
      for: 60 s
      reset_after: 30 s
hazard: medium
confirmed: { by: tester, at: 2026-10-24 }
"""

LASER = """
device: Laser
id: laser
connect: { mock: laser }
read:
  door_closed: { type: bool }
write:
  power: { unit: percent, min: 0, max: 30 }
actions:
  home: {}
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 %"
    require: "door_closed == true"
hazard: high
confirmed: { by: tester, at: 2026-10-24 }
"""


class FakeClock:
    """A monotonic clock tests can move forward."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def kernel(clock: FakeClock) -> Kernel:
    return Kernel(clock=clock, approval_key=b"test-approval-key-32-bytes-long!")


AddDevice = Callable[..., Coroutine[Any, Any, MockDriver]]


@pytest.fixture
def add(kernel: Kernel, clock: FakeClock) -> AddDevice:
    async def add_device(text: str, *, connect: bool = True, settle: float = 60.0, **overrides: Any) -> MockDriver:
        file: DeviceFile = loads(text)
        if overrides:
            data = file.model_dump(by_alias=True, exclude={"extensions"})
            data["connect"] = {"driver": "mock", "params": {**file.connect.params, **overrides}}
            file = DeviceFile.model_validate(data)
        driver = MockDriver(file)
        kernel.register(file, driver)
        if connect:
            await kernel.connect(file.device_id)
        clock.advance(settle)
        return driver

    return add_device
