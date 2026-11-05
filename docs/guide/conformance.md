# Conformance suite

Every driver passes the same checks before shipping. The suite runs the driver inside a real kernel against the driver's own mock or simulator and records every call into the driver's protocol code, so a blocked command that reaches the device fails the suite.

## What the suite checks

The suite tests the driver's declared [Conformance Level](glossary:conformance-level) and skips higher checks, with the reason in the report.

| Check | Level | What passes |
|---|---|---|
| `identify` | Core | Identification uses read-only commands |
| `connect` | Core | The kernel connects the device |
| `describe` | Core | Self-description, if any, uses only known sections |
| `read every channel` | Core | Each readable channel returns a value in the declared unit |
| `disconnect and reconnect` | Core | A lost connection is detected, then every channel reads again |
| `timeout handling` | Core | A slow device times out or raises a driver error instead of hanging |
| `close` | Core | The driver closes cleanly |
| `write inside limits` | Control | A passed change reaches the driver exactly once |
| `write outside limits is blocked before the driver` | Control | A change over the limit never reaches the protocol code |
| `no write without a kernel grant` | Control | A call without a grant fails before the protocol code |
| `action inside limits` | Full | An action inside the limits reaches the driver exactly once |
| `action outside limits is blocked before the driver` | Full | An action over a limit never reaches the driver |
| `no action without a kernel grant` | Full | An action call without a grant fails before the protocol code |
| `concurrent access` | Control | Racing commands each end done, blocked or failed |
| `safe state` | Control | A stop leaves the device in its safe state |

## Run the suite

The suite runs with the normal tests and includes every driver package with a `conformance.py`.

```sh tested
$ uv run pytest tests/conformance -q
```

`openhal driver test` runs the suite for one driver and prints each check. The mock driver declares Control, so the three Full checks are skipped.

```sh tested
$ uv run openhal driver test mock
12 passed, 3 skipped, 0 failed
```

From Python, run the suite on one driver's case and read the report.

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

A driver supplies one `ConformanceCase` in `openhal/drivers/<name>/conformance.py`, with a confirmed device file, a factory that builds the driver against the simulator, and optional hooks that break the connection or slow the device for the disconnect and timeout checks. This case runs the openhal-firmware driver against the simulated plant waterer.

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

The plant waterer has no control channel, so the four checks that need a control channel are skipped and the other 11 pass. Use a device file with the real device's units and limits, so the suite exercises the same conversions as real commands. The [driver contract](../drivers/WRITING-A-DRIVER.md) has every rule.

## Passing is not verified

Passing on a simulator marks a driver implemented in the catalog. A driver is marked verified only after a person runs the driver's hardware test plan on a real device and files a report.
