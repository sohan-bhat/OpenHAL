# Writing a driver

A driver implements one protocol and a device file describes one device, so most new devices need only a device file. Write a driver only when no protocol driver can connect. The [tutorial](#tutorial) builds one with `openhal driver new`.

## The package

```
openhal/drivers/<name>/
  __init__.py        NAME and ENTRY only, no heavy imports
  driver.py          the Driver subclass, with a header docstring about the protocol and its quirks
  simulator.py       a mock or protocol simulator used by tests and the conformance case
  conformance.py     def case() -> ConformanceCase
  catalog.json       this driver's catalog entry (merged into docs/drivers/catalog.json)
  examples/          at least one complete example device file
tests/drivers/<name>/test_<name>.py
docs/drivers/<name>.md
docs/hardware-tests/<name>.md
```

`__init__.py` holds only this, so the registry finds the driver without importing its dependencies.

```python
NAME = "scpi"
ENTRY = "openhal.drivers.scpi.driver:ScpiDriver"
```

## The class

```python
class ScpiDriver(Driver):
    info = DriverInfo(name="scpi", protocols=("SCPI over VISA",), hazard_default="medium",
                      summary="Programmable test instruments over USB, LAN and serial.")
    params_model = ScpiParams          # a Pydantic model with extra="forbid"

    @classmethod
    async def discover(cls) -> list[Discovered]: ...   # read-only, never changes hardware
    async def identify(self) -> dict[str, str]: ...      # read-only (*IDN?, M115, firmware describe)
    async def connect(self) -> None: ...
    async def describe(self) -> dict[str, Any] | None: ...  # optional self-description
    async def read(self, channel: str) -> Reading: ...
    async def _write(self, channel: str, value: float | bool | str) -> Reading | None: ...
    async def _action(self, name: str, args: dict[str, Any]) -> Any: ...
    async def _safe_state(self) -> None: ...             # optional protocol-native safe behavior
    async def health(self) -> Health: ...
    async def close(self) -> None: ...
```

1. **Never override `write`, `action`, `safe_state`, `attach` or `_consume`.** Those methods consume the kernel's grant before calling `_write`, `_action` and `_safe_state`, and the base class raises `TypeError` for an override.
2. **Never call `_write`, `_action` or `_safe_state` yourself.** A test fails if anything outside `drivers/base.py` calls one.
3. **Values arrive checked and in the channel's declared unit.** Don't re-check limits. Convert only to what the protocol needs, such as percent to a 0 to 255 PWM byte, and document the mapping.
4. **Discovery and identification send only documented read-only commands**, with short timeouts, and never open a port another process holds.
5. **`read` returns the channel's declared unit**, with `Reading.unit` set for numeric channels.
6. **Errors raise `DriverError`** with what happened and what to try next. Timeouts may raise `TimeoutError`. Never swallow an error and return a fake value.
7. **`describe()`** maps what the protocol exposes, such as SCPI queries, Modbus registers, GATT characteristics, Home Assistant entities, ROS topics, OPC UA nodes or Moonraker objects, into a mapping with any of `device`, `match`, `read`, `write`, `actions` and `notes`. Every limit is marked `suggested: true`, since a driver never confirms limits.
8. **Safe state.** If the protocol has its own emergency behavior, such as GRBL feed hold or outputs off, set `DriverInfo.safe_state_support` to `"native"`, implement `_safe_state` and document what `_safe_state` does. If the protocol can't guarantee a safe state, say so in the docs page and the example file's `safe_state_note`.
9. **Bridges** such as Home Assistant, ESPHome and ROS 2 expose only the entities the device file selects, and the device file's limits apply even when the bridged system has its own.
10. **No secrets in device files.** A secret parameter takes an environment variable name, such as `token_env: HA_TOKEN`.
11. **Optional dependencies** go in a `pyproject.toml` extra named after the driver and are imported in `driver.py`, never in `__init__.py`.

## Tests

Tests cover normal operation for every supported channel type, disconnects, timeouts, malformed responses and every error path. The conformance case passes, and `tests/conformance/test_conformance.py` picks up the case. No test touches real hardware.

## Docs page

`docs/drivers/<name>.md` covers what the driver supports, setup, an example device file, known limitations, hazard defaults and the protocol sources.

## Hardware test plan

`docs/hardware-tests/<name>.md` is a plan for a person with real hardware, from read-only checks to the smallest safe writes, with exact commands, expected output, what to send back on failure and a template for a `verified-on-hardware` report.

## Catalog entry

`catalog.json` in the driver package holds the entry.

```json
{
  "name": "scpi",
  "tier": 1,
  "status": "implemented",
  "protocols": ["SCPI over USB-TMC", "SCPI over LAN (VXI-11, raw socket)", "SCPI over serial"],
  "families": ["bench power supplies", "multimeters", "oscilloscopes", "function generators", "electronic loads"],
  "hazard_default": "medium",
  "tests": "mock and pyvisa-sim",
  "estimate": {"devices": "thousands of models", "reasoning": "...", "sources": ["https://..."]}
}
```

## Tutorial

The scaffold is a complete driver of about 80 lines on an in-memory simulator, and the scaffold passes the conformance suite as generated. Swap in the real protocol one method at a time, keeping the suite passing.

1. **Scaffold the driver** from an OpenHAL checkout.

   ```
   uv run openhal driver new acme-pump --title "Acme pump"
   ```

   The command creates `openhal/drivers/x_acme_pump/`, `tests/drivers/x_acme_pump/`, `docs/drivers/x-acme-pump.md` and `docs/hardware-tests/x-acme-pump.md`. New drivers are named `x-...` and marked experimental.

2. **Run the conformance suite.**

   ```
   uv run openhal driver test x-acme-pump
   ```

3. **Write the protocol.** In `driver.py`, replace `connect`, `read` and `_write` with the real transport, and make `simulator.py` send and receive the device's bytes. Keep `discover()` and `identify()` read-only.

4. **Test every error path.** Disconnects, timeouts, malformed replies and error replies each get a test and raise `DriverError` with the next step.

5. **Run the suite again**, then fill in the docs page, the hardware test plan and the catalog entry's estimate with sources.

6. **Promote the driver.** After conformance and a person's hardware test run, a maintainer adds the plain name to `KNOWN_DRIVERS` in `openhal/spec/models.py` and sets the status to implemented.

`openhal driver list` shows every driver with its protocols, hazard default, conformance level and status.
