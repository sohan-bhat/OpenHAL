# Writing a driver

A driver implements one protocol and a device file describes one device and its limits, so most new devices need only a device file on top of an existing driver. Write a new driver only when no protocol driver can connect to the device.

This page is the contract every driver in the repository follows, and the tutorial at the end builds a working driver with `openhal driver new`.

## The package

```
openhal/drivers/<name>/
  __init__.py        NAME and ENTRY only, no heavy imports
  driver.py          the Driver subclass, with a header docstring about the protocol and its quirks
  simulator.py       a mock or protocol simulator used by tests and the conformance case
  conformance.py     def case() -> ConformanceCase
  catalog.json       this driver's catalog entry (merged into drivers/catalog.json)
  examples/          at least one complete example device file
tests/drivers/<name>/test_<name>.py
docs/drivers/<name>.md
docs/hardware-tests/<name>.md
```

`__init__.py` holds exactly this, so the registry can find the driver without importing its dependencies.

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

Every driver follows these rules.

1. **Never override `write`, `action`, `safe_state`, `attach` or `_consume`.** Because those methods consume the kernel's grant and then call `_write`, `_action` and `_safe_state`, the base class raises `TypeError` for a subclass that overrides them.
2. **Never call `_write`, `_action` or `_safe_state` yourself**, from anywhere. A test walks the whole package and fails if anything outside `drivers/base.py` does.
3. **Values arrive already checked and converted** to the channel's declared unit, so don't re-check limits or convert units again, but do convert from the channel unit to whatever the protocol needs (for example percent to a 0 to 255 PWM byte), and document the mapping.
4. **Discovery and identification send only documented read-only commands**, with short timeouts, and never open a port another process holds.
5. **`read` returns values in the channel's declared unit**, with `Reading.unit` set for numeric channels.
6. **Errors raise `DriverError`** with a message that states what happened and what to try next. Timeouts may raise `TimeoutError`, but never swallow an error and return a fake value.
7. **`describe()`** maps whatever the protocol exposes (SCPI queries, Modbus registers, GATT characteristics, Home Assistant entities, ROS topics, OPC UA nodes, Moonraker objects) into device file sections. `describe()` returns a mapping with any of `device`, `match`, `read`, `write`, `actions` and `notes`. Every limit `describe()` returns is marked `suggested: true`, because a driver never confirms limits.
8. **Safe state.** Set `DriverInfo.safe_state_support` to `"native"` if the protocol has its own emergency behavior (GRBL feed hold, outputs off), implement `_safe_state`, and describe in the docs what `_safe_state` does. If the protocol can't guarantee a safe state, state that limit in the docs page and in the example device file's `safe_state_note`.
9. **Bridges** (Home Assistant, ESPHome, ROS 2) expose only the entities the user selected in the device file, and the device file's limits apply even when the bridged system has its own.
10. **No secrets in device files.** Parameters that need a secret take an environment variable name (`token_env: HA_TOKEN`).
11. **Optional dependencies** go in a `pyproject.toml` extra named after the driver. Import the optional dependencies inside `driver.py`, never in `__init__.py`.

## Tests

A driver's tests cover these cases.

- Normal operation for every channel type the driver supports.
- Disconnects, timeouts, malformed responses and every error path.
- The conformance case passes (`tests/conformance/test_conformance.py` picks it up automatically).
- No test touches real hardware.

## Docs page

`docs/drivers/<name>.md` covers what the driver supports, setup steps, an example device file, known limitations, hazard defaults, and the protocol sources used to write the driver.

## Hardware test plan

`docs/hardware-tests/<name>.md` is a step-by-step plan for a human with real hardware, ordered from read-only checks to the smallest safe writes, with exact commands, expected output, what to send back on failure and a report template that produces a `verified-on-hardware` report.

## Catalog entry

The catalog entry is `catalog.json` in the driver package.

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

The scaffold is a complete driver of about 80 lines that connects to an in-memory simulator, and the scaffold passes the conformance suite before you change anything. You then replace the simulator transport with the real protocol, one method at a time, and keep the suite passing.

1. **Scaffold the driver** from an OpenHAL checkout.

   ```
   uv run openhal driver new acme-pump --title "Acme pump"
   ```

   The command creates `openhal/drivers/x_acme_pump/` (driver, simulator, conformance case, catalog entry and an example device file), `tests/drivers/x_acme_pump/`, `docs/drivers/x-acme-pump.md` and `docs/hardware-tests/x-acme-pump.md`. New drivers are named `x-...` and marked experimental.

2. **Run the conformance suite.**

   ```
   uv run openhal driver test x-acme-pump
   ```

   Every check passes against the simulator.

3. **Write the protocol.** In `driver.py`, replace `connect`, `read` and `_write` with the real transport, and make `simulator.py` send and receive the same bytes as the device. Keep `discover()` and `identify()` read-only. Because only the safety kernel's grant may reach `_write`, never call `_write` yourself.

4. **Test every error path.** Disconnects, timeouts, malformed replies and error replies each get a test, and each raises `DriverError` with a message that states what to do.

5. **Run the suite again**, then fill in the docs page, the hardware test plan and the catalog entry's estimate with sources.

6. **Promote the driver.** When the driver passes conformance and a person has run the hardware test plan, a maintainer adds the plain name to `KNOWN_DRIVERS` in `openhal/spec/models.py` and sets the driver's status to implemented.

`openhal driver list` shows every driver with its protocols, hazard default, conformance level and status.
