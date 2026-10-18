# Writing a driver

A driver speaks one protocol. A device file describes one device and its limits. Most new devices need only a device file on top of an existing driver. Write a new driver only when no protocol driver can talk to the device.

This page is the contract every driver in the repository follows. The full step-by-step tutorial with `openhal driver new` lives in the second half of this page once the driver SDK lands (M9).

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

Rules.

1. **Never override `write`, `action`, `safe_state`, `attach` or `_consume`.** The base class refuses to load a class that does. Those methods consume the kernel's grant and then call `_write`, `_action` and `_safe_state`.
2. **Never call `_write`, `_action` or `_safe_state` yourself**, from anywhere. A test walks the whole package and fails if anything outside `drivers/base.py` does.
3. **Values arrive already checked and converted** to the channel's declared unit. Don't re-check limits and don't convert units again. Do convert from the channel unit to whatever the protocol needs (for example percent to a 0 to 255 PWM byte), and document the mapping.
4. **Discovery and identification send only documented read-only commands**, with short timeouts, and never open a port another process holds.
5. **`read` returns values in the channel's declared unit**, with `Reading.unit` set for numeric channels.
6. **Errors raise `DriverError`** with a message that says what happened and what to try next. Timeouts may raise `TimeoutError`. Never swallow an error and return a fake value.
7. **`describe()`** maps whatever the protocol exposes (SCPI queries, Modbus registers, GATT characteristics, Home Assistant entities, ROS topics, OPC UA nodes, Moonraker objects) into device file sections. It returns a mapping with any of `device`, `match`, `read`, `write`, `actions` and `notes`. Every limit it proposes is marked `suggested: true`. Limits are never confirmed by a driver.
8. **Safe state.** Set `DriverInfo.safe_state_support` to `"native"` if the protocol has its own emergency behavior (GRBL feed hold, outputs off), implement `_safe_state`, and say in the docs what it does. If the protocol can't guarantee a safe state, say so in the docs page and in the example device file's `safe_state_note`.
9. **Bridges** (Home Assistant, ESPHome, ROS 2) expose only the entities the user selected in the device file, and the device file's limits apply even when the bridged system has its own.
10. **No secrets in device files.** Parameters that need a secret take an environment variable name (`token_env: HA_TOKEN`).
11. **Optional dependencies** go in a `pyproject.toml` extra named after the driver. Import them inside `driver.py`, never in `__init__.py`.

## Tests

- Normal operation for every channel type the driver supports.
- Disconnects, timeouts, malformed responses and every error path.
- The conformance case passes (`tests/conformance/test_conformance.py` picks it up automatically).
- No test touches real hardware.

## Docs page

`docs/drivers/<name>.md` covers what the driver supports, setup steps, an example device file, known limitations, hazard defaults, and the protocol sources used to write it.

## Hardware test plan

`docs/hardware-tests/<name>.md` is a step-by-step plan for a human with real hardware, ordered from read-only checks to the smallest safe writes, with exact commands, expected output, what to send back on failure and a report template that produces a `verified-on-hardware` report.

## Catalog entry

`catalog.json` in the driver package.

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
