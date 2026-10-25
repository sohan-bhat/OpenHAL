# Conformance suite

Every driver in the repository passes the same battery of checks before it ships. The suite runs the driver inside a real kernel, against its own mock or simulator, and watches the point where the driver talks to the protocol. That is how it proves a blocked command never reaches the device.

## What it checks

The suite tests the driver's declared [Conformance Level](glossary:conformance-level) and nothing above it. Checks above that level are skipped, and the report names the reason.

| Check | Level | What passes |
|---|---|---|
| `identify` | Core | Identification answers using read-only commands |
| `connect` | Core | The kernel connects the device |
| `describe` | Core | Self-description, if the protocol has one, uses only known sections |
| `read every channel` | Core | Each readable channel returns a value in its declared unit |
| `disconnect and reconnect` | Core | A lost connection is noticed, and every channel reads again afterwards |
| `timeout handling` | Core | A slow device times out or raises a driver error instead of hanging |
| `close` | Core | The driver closes cleanly |
| `write inside limits` | Control | A change the kernel allows reaches the driver exactly once |
| `write outside limits is blocked before the driver` | Control | A change over the limit never reaches the protocol code |
| `no write without a kernel grant` | Control | Calling the driver without a grant fails, and nothing reaches the protocol code |
| `action inside limits` | Full | An action with every argument inside its limits runs and reaches the driver exactly once |
| `action outside limits is blocked before the driver` | Full | An action with an argument over its limit never reaches the driver |
| `no action without a kernel grant` | Full | Calling an action without a grant fails, and nothing reaches the protocol code |
| `concurrent access` | Control | Racing commands each end done, blocked or failed |
| `safe state` | Control | A stop leaves the device in its safe state |

## Run it

The suite runs as part of the normal tests. Every driver package with a `conformance.py` is picked up on its own.

```sh tested
$ uv run pytest tests/conformance -q
```

`openhal driver test` runs it for one driver and prints each check. The mock driver declares Control, so the three Full checks are skipped.

```sh tested
$ uv run openhal driver test mock
12 passed, 3 skipped, 0 failed
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

The case should use a device file that looks like the real device, with real units and limits, so the suite exercises the same conversions the hardware will see. The [driver contract](../drivers/WRITING-A-DRIVER.md) has every rule.

## Passing is not verified

Conformance runs against a simulator. A driver that passes is marked implemented in the catalog. It becomes verified only after a person runs its hardware test plan on a real device and files a report.
