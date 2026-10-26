# Quickstart

This guide runs the demo, an agent keeping an eye on a simulated 3D print, then a [Hub](glossary:hub) you control with the simulated Arduino plant waterer. Nothing in it touches real hardware.

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

## Run the demo

```sh tested
$ git clone https://github.com/sohan-bhat/OpenHAL
$ cd OpenHAL
$ uv run openhal demo
```

The demo starts a hub with a simulated Klipper printer and its camera, connects as an agent and watches a print. It reads camera frames, warms the bed, is refused a nozzle over the limit, pauses the print when it comes loose and asks to cancel, which waits for a person. This is the trace it prints.

```scenario
```

## Run the whole system

```sh tested
$ uv run openhal demo --full
  soil_moisture rises from 31 % to 46 %
<- error -32010 LIMIT_EXCEEDED
```

`--full` runs the whole system with the Arduino plant waterer. It starts a hub with no devices and discovers the simulated board. The driver writer drafts its [Device File](glossary:device-file) from the board and its sketch, and a script answers the limits interview as a person would. An agent then connects through `openhal mcp` and drafts a routine, which a person enables. The routine waters the plant, and the agent's 120 s request never reaches the board. [e2e.yaml](../demo/e2e.yaml) records every step.

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

The [Safety Kernel](glossary:safety-kernel) refused the first command before anything reached the board. Over the protocol, the same refusal is `error -32010 LIMIT_EXCEEDED`.

## Stop

Any client may stop. Only a person may lift the stop, by typing the phrase `unlock`.

```sh tested
$ uv run openhal stop
plant-waterer  safe
$ uv run openhal unlock
```

## Next

- [Concepts](concepts.md) defines the hub, device files, the kernel and the error codes.
- [Connect Claude](tutorials/connect-claude.md) gives an agent its own token.
- [Add a device](tutorials/add-a-device.md) describes your own hardware.
