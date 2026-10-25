# Conformance suite

Every driver in the repository passes the same battery of checks before it ships. The suite runs the driver inside a real kernel, against its own mock or simulator, and watches the layer where the driver talks to the protocol. That is how it proves a blocked command never reaches the device.

## What it checks

| Check | What passes |
|---|---|
| identify | Identification answers using read-only commands |
| connect | The driver connects to its simulator |
| describe | Self-description, if the protocol has one, marks every limit as suggested |
| read every channel | Each read channel returns a value in its declared unit |
| write inside limits | A write the kernel allows reaches the driver once, already converted |
| write outside limits is blocked before the driver | A write over the limit never reaches the protocol layer |
| no write without a kernel grant | Calling the driver without a grant fails |
| concurrent access | Commands to one device run one at a time |
| safe state | The safe state is applied and reported |
| disconnect and reconnect | A lost connection is noticed and the driver comes back |
| timeout handling | A slow device times out or raises a driver error instead of hanging |
| close | The driver closes cleanly |

A check that can't apply to a driver is skipped with a reason, and the report says so.

## Run it

The suite runs as part of the normal tests. Every driver package with a `conformance.py` is picked up on its own.

```sh tested
$ uv run pytest tests/conformance -q
```

You can also run it from Python against one driver's case and read the report.

```python tested
import asyncio

from openhal.conformance import run
from openhal.drivers.mock import conformance

report = asyncio.run(run(conformance.case()))
print(report.summary())
for result in report.results:
    print("ok  " if result.ok else "skip" if result.skipped else "FAIL", result.name, result.detail)
assert report.ok
```

## Add a case for your driver

A driver supplies one `ConformanceCase` in `openhal/drivers/<name>/conformance.py`. It holds a confirmed device file, a factory that builds the driver against its simulator, and optional hooks that break the connection or slow the device down, so the disconnect and timeout checks mean something.

```python tested
from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.mock.driver import MockDriver
from openhal.spec import loads

FILE = loads(
    """
device: Conformance fan
id: conformance-fan
connect: { mock: conformance, simulate: desk-fan }
read:
  temperature: { unit: degC }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 50 }
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


async def break_connection(driver: Driver) -> None:
    assert isinstance(driver, MockDriver)
    driver.connected = False


def case() -> ConformanceCase:
    return ConformanceCase(name="mock", file=FILE, make=MockDriver, break_connection=break_connection)
```

The case should use a device file that looks like the real device, with real units and limits, so the suite exercises the same conversions the hardware will see. The driver contract is in [writing a driver](../drivers/WRITING-A-DRIVER.md).

## Passing is not verified

Conformance runs against a simulator. A driver that passes is marked implemented in the catalog. It becomes verified only after a person runs its hardware test plan on a real device and writes a report.
