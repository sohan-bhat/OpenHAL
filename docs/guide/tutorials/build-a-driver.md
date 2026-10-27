# Build a driver

A [Driver](glossary:driver) speaks one protocol, and most devices need only a [Device File](glossary:device-file) for an existing driver, so build a driver only when no existing driver speaks your device's protocol. This tutorial builds a driver for a simulated bench lamp and runs the conformance suite on the driver.

## The contract

1. A driver implements `connect`, `read` and `_write`, and never overrides `write`, `action`, `safe_state`, `attach` or `_consume`. The base class consumes the kernel's [Grant](glossary:grant), then calls `_write`.
2. Values arrive checked and in the channel's unit, so a driver converts only to what the protocol needs.
3. `discover` and `identify` send only read-only commands.
4. A failure raises a `DriverError` whose message says what happened and what to try, and a driver never returns a made-up value.
5. Every limit that `describe` proposes is marked `suggested`.

The [driver contract](../../drivers/WRITING-A-DRIVER.md) has the full rules.

## The driver

The lamp takes a duty byte from 0 to 255, and because the channel is in percent, `_write` converts the value.

```python tested file=lamp.py
from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading


class LampSimulator:
    def __init__(self) -> None:
        self.duty = 0
        self.online = True


class LampDriver(Driver):
    info = DriverInfo(name="x-lamp", protocols=("in-memory",), hazard_default="low", summary="A simulated bench lamp.")

    async def connect(self) -> None:
        self.sim = LampSimulator()

    async def read(self, channel: str) -> Reading:
        if not self.sim.online:
            raise DriverError("The lamp stopped answering. Check its cable, then reconnect.")
        return Reading(channel, round(self.sim.duty / 255 * 100, 1), "percent")

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        if not self.sim.online:
            raise DriverError("The lamp stopped answering. Check its cable, then reconnect.")
        self.sim.duty = round(float(value) / 100 * 255)
        return await self.read(channel)

    async def health(self) -> Health:
        return Health(connected=self.sim.online)
```

Names that start with `x-` are reserved for drivers outside the repository.

## Run the conformance suite

A conformance case pairs the driver with a confirmed device file and a hook that breaks the connection.

```python tested
import asyncio

from openhal.conformance import ConformanceCase, run
from openhal.drivers.base import Driver
from openhal.spec import loads

from lamp import LampDriver

FILE = loads(
    """
device: Bench lamp
id: bench-lamp
connect: { driver: x-lamp }
write:
  brightness: { unit: percent, min: 0, max: 80, max_change_per_s: 40 }
safe_state: { brightness: 0 }
hazard: low
confirmed: { by: tutorial, at: 2026-10-24 }
"""
)


async def unplug(driver: Driver) -> None:
    assert isinstance(driver, LampDriver)
    driver.sim.online = False


report = asyncio.run(run(ConformanceCase(name="x-lamp", file=FILE, make=LampDriver, break_connection=unplug)))
print(report.summary())
assert report.ok
```

```text
x-lamp: 11 passed, 0 failed, 1 skipped
```

The suite sends a brightness of 160 % and checks that the kernel blocks the value before `_write` runs. The skipped check needs a hook that slows the device down, and [Conformance](../conformance.md) lists every check.

## Add it to the repository

A driver in the repository is a package under `openhal/drivers/<name>/` with the driver, its simulator, a conformance case, a catalog entry, an example device file, tests and a docs page, and the suite picks up every case.

```sh tested
$ uv run pytest tests/conformance -q -k mock
```

Passing the suite marks a driver tested on simulator, and a person running the driver's hardware test plan on a real device marks the driver verified.
