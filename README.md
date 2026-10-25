# OpenHAL

The Open Hardware Abstraction Layer. AI agents read and control real hardware through OpenHAL, and a deterministic safety kernel decides every change before it reaches a device.

```
$ openhal write demo-fan.fan_speed 150%
blocked above_max  Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.
$ openhal write demo-fan.fan_speed 20%
done  Done. fan_speed is now 20 %.
```

OpenHAL is open source (Apache-2.0) and runs on your own machine. It works with any MCP client (Claude, ChatGPT, Cursor and others), a command line and a Python library.

## How it works

1. **Devices are described in files.** A `.hal.yaml` file lists what a device can read and change, with units and limits. Drivers speak the protocols (serial, SCPI, Modbus, MQTT, BLE, MIDI, HID, Klipper, Home Assistant and more).
2. **One hub owns every device.** `openhald` holds the connections and the safety kernel. The MCP server, the CLI, the Python library and the dashboard are all clients of its local API.
3. **The kernel decides.** Every write and action is checked against units, ranges, rate limits, interlocks, watchdogs and confirmation rules. A driver can only change hardware with a single-use grant the kernel issues for that exact command. Stop works in one call and puts every device in its safe state.

Limits come from a person. A device file stays read-only until someone confirms its limits, and nothing an AI proposes can confirm them.

## Status

Version 0.1 is in development. The spec, the safety kernel, the hub and its API, the MCP server, CLI and Python library, 17 Tier 1 drivers, the driver writer and the Arduino library are built and tested against simulators. The dashboard, the website, the device library and packaging are in progress. Nothing has been verified on real hardware yet, and every driver's hardware test plan is in `docs/hardware-tests/`.

## Quickstart

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/), on macOS or Raspberry Pi OS (64-bit).

```
git clone https://github.com/sohan-bhat/OpenHAL.git
cd OpenHAL
uv sync --all-extras
uv run openhal init
uv run openhald
```

In a second terminal.

```
uv run openhal status
uv run openhal read demo-fan.temperature
```

`openhal init` installs a simulated desk fan, so all of this runs without hardware. It starts read-only. Run `uv run openhal file confirm ~/.openhal/devices/demo-fan.hal.yaml` to confirm its limits, restart `openhald`, and writes work. To use it from Claude Desktop or another MCP client, see `docs/interfaces/MCP.md`.

## Repository

| Path | What it holds |
|---|---|
| `spec/` | The device file spec, its JSON Schema, examples and the firmware protocol |
| `openhal/kernel/` | The safety kernel |
| `openhal/hub/` | The hub daemon and its local API |
| `openhal/drivers/` | Protocol drivers and bridges |
| `openhal/writer/` | The driver writer, from an unknown device to a confirmed file |
| `openhal/mcp/`, `openhal/cli/`, `openhal/client/` | The MCP server, command line and Python library |
| `firmware/arduino/OpenHAL/` | The Arduino and ESP32 library |
| `docs/` | Safety model, threat model, architecture, decisions and driver docs |

## Development

```
uv run pytest
uv run ruff check openhal tests
uv run mypy openhal
```

## License

Apache-2.0. See `LICENSE`.
