# Quickstart

This guide runs the demo, an agent keeping an eye on a simulated 3D print, then a [Hub](glossary:hub) you control with the simulated Arduino plant waterer. Nothing in this guide touches real hardware.

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

## Run the demo

```sh tested
$ git clone https://github.com/sohan-bhat/OpenHAL
$ cd OpenHAL
$ uv run openhal demo
```

The demo starts a hub with a simulated Klipper printer and its camera, and connects an agent to watch a print. The agent reads camera frames and warms the bed, the hub refuses the agent's request for a nozzle temperature above the limit, and the agent pauses the print and requests a cancel. Because a cancel can't be undone, the cancel waits for a person, and the owner approves the cancel over the same protocol. The demo prints this trace.

```scenario
```

[The full example](/docs/examples/3d-print-watch/) walks through the same run step by step, with every message and the audit log.

## Run the whole system

```sh tested
$ uv run openhal demo --full
  soil_moisture rises from 31 % to 46 %
<- error -32010 LIMIT_EXCEEDED
```

`--full` runs the whole system with the Arduino plant waterer, starting from a hub with no devices that discovers the simulated board. The driver writer drafts the board's [Device File](glossary:device-file) from the board and the sketch, and a script answers the limits interview as a person would. An agent then connects through `openhal mcp` and drafts a routine, which a person enables. The routine waters the plant. Because 120 s is above the duration limit, the agent's request to water for 120 s never reaches the board. Every step is recorded in [e2e.yaml](../demo/e2e.yaml).

## Run the hub yourself

`init` creates `~/.openhal` with a human token and a [Device File](glossary:device-file) for the simulated plant waterer. The file is read-only until a person confirms its limits.

```sh tested
$ uv run openhal init
sample device  ~/.openhal/devices/plant-waterer.hal.yaml created, read-only until you confirm it
$ uv run openhal file confirm ~/.openhal/devices/plant-waterer.hal.yaml
action  water
$ uv run openhald &
$ uv run openhal status
devices 1 of 1 connected
```

The hub listens on `127.0.0.1:7420` only.

## Send two commands

```sh tested
$ uv run openhal action plant-waterer.water duration=120s
blocked above_max  Blocked. The duration limit is 30 s (max). Asked for 120 s.
$ uv run openhal action plant-waterer.water duration=20s
done  Done. water ran.
```

Because the duration in the first command is above the limit, the [Safety Kernel](glossary:safety-kernel) refused the command before anything reached the board. Over the protocol, the hub returns the same refusal as `error -32010 LIMIT_EXCEEDED`.

## Stop

Any client may stop every device, but lifting the stop takes the human token and the typed phrase `unlock`.

```sh tested
$ uv run openhal stop
plant-waterer  safe
$ uv run openhal unlock
```

## Next

- [Concepts](concepts.md) defines the hub, device files, the kernel and the error codes.
- [Connect Claude](tutorials/connect-claude.md) gives an agent its own token.
- [Add a device](tutorials/add-a-device.md) describes your own hardware.
