# Conformance suite

Every driver in the repository passes the same battery of checks before the driver ships. The suite runs the driver inside a real kernel, against the driver's own mock or simulator, and monitors every call from the driver into the driver's protocol code, which is how the suite checks that a blocked command never reaches the device.

## What the suite checks

The suite tests the driver's declared [Conformance Level](glossary:conformance-level) and nothing above it. Checks above that level are skipped, and the report names the reason.

| Check | Level | What passes |
|---|---|---|
| `identify` | Core | Identification returns a result using read-only commands |
| `connect` | Core | The kernel connects the device |
| `describe` | Core | Self-description, if the protocol has one, uses only known sections |
| `read every channel` | Core | Each readable channel returns a value in its declared unit |
| `disconnect and reconnect` | Core | A lost connection is detected, and every channel returns a value again afterwards |
| `timeout handling` | Core | A slow device times out or raises a driver error instead of hanging |
| `close` | Core | The driver closes cleanly |
| `write inside limits` | Control | A change the kernel passes reaches the driver exactly once |
| `write outside limits is blocked before the driver` | Control | A change over the limit never reaches the protocol code |
| `no write without a kernel grant` | Control | Calling the driver without a grant fails, and nothing reaches the protocol code |
| `action inside limits` | Full | An action with every argument inside its limits runs and reaches the driver exactly once |
| `action outside limits is blocked before the driver` | Full | An action with an argument over its limit never reaches the driver |
| `no action without a kernel grant` | Full | Calling an action without a grant fails, and nothing reaches the protocol code |
| `concurrent access` | Control | Racing commands each end done, blocked or failed |
| `safe state` | Control | A stop leaves the device in its safe state |

## Run it

The suite runs as part of the normal tests, and every driver package with a `conformance.py` is picked up automatically.

```sh tested
$ uv run pytest tests/conformance -q
```

`openhal driver test` runs the suite for one driver and prints each check. The mock driver declares Control, so the three Full checks are skipped.

```sh tested
$ uv run openhal driver test mock
12 passed, 3 skipped, 0 failed
```

You can also run the suite from Python against one driver's case and read the report.

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

A driver supplies one `ConformanceCase` in `openhal/drivers/<name>/conformance.py`. The case holds a confirmed device file, a factory that builds the driver against its simulator, and optional hooks that break the connection or slow the device down, so the disconnect and timeout checks mean something. This case runs the openhal-firmware driver against the simulated plant waterer.

```python tested
from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.openhal_firmware.driver import OpenHalFirmwareDriver
from openhal.drivers.openhal_firmware.simulator import SIMULATORS
from openhal.spec import loads

FILE = loads(
    """
device: Arduino plant waterer
id: plant-waterer
connect: { openhal-firmware: "sim:plant-waterer", timeout_s: 0.3 }
read:
  soil_moisture: { unit: "%", range: [0, 100] }
  tank: { type: enum, values: [empty, ok] }
actions:
  water:
    args:
      duration: { unit: s, min: 1, max: 30 }
    require: ["tank == ok"]
  stop: {}
safe_state: { action: stop }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


async def unplug(driver: Driver) -> None:
    assert isinstance(driver, OpenHalFirmwareDriver)
    assert driver._link is not None
    await driver._link.transport.close()


async def go_quiet(driver: Driver) -> None:
    SIMULATORS["plant-waterer"].silent = True


def case() -> ConformanceCase:
    SIMULATORS.pop("plant-waterer", None)
    return ConformanceCase(
        name="openhal-firmware", file=FILE, make=OpenHalFirmwareDriver, break_connection=unplug, make_slow=go_quiet
    )
```

The plant waterer has no control channel, so the four checks that need one are skipped, the report gives the reason, and the other 11 pass. The case should use a device file that matches the real device, with real units and limits, so the suite exercises the same conversions that commands to the real hardware go through. The [driver contract](../drivers/WRITING-A-DRIVER.md) has every rule.

## Passing is not verified

Because conformance runs against a simulator, a driver that passes is marked implemented in the catalog, and the driver is marked verified only once a person runs the driver's hardware test plan on a real device and files a report.
