# Quickstart

Run the demo of an agent watching a simulated 3D print, then a [Hub](glossary:hub) of your own with a simulated Arduino plant waterer. Nothing here touches real hardware.

## Install

<!-- install:start -->
On macOS and Linux, run this command in a terminal.

```text
curl -LsSf https://sohan-bhat.github.io/OpenHAL/install.sh | sh
```

On Windows, run this command in PowerShell.

```text
irm https://sohan-bhat.github.io/OpenHAL/install.ps1 | iex
```
<!-- install:end -->

[Install](install.md) also covers uv, pipx and a clone.

## Run the demo

```sh tested
$ openhal demo
```

The demo connects an agent to a hub with a simulated Klipper printer and camera, then prints each message.

```scenario
```

[The full example](/docs/examples/3d-print-watch/) shows the same run with the audit log.

## Run the whole system

```sh tested
$ openhal demo --full
  soil_moisture rises from 31 % to 46 %
<- error -32010 LIMIT_EXCEEDED
```

`--full` starts from an empty hub, discovers the simulated plant waterer board and drafts the board's [Device File](glossary:device-file) with the driver writer. A script fills in the limits interview, and an agent connects through `openhal mcp` and drafts a routine that a person enables. The duration limit blocks the agent's request to water for 120 s before the request reaches the board. [e2e.yaml](../demo/e2e.yaml) records every step.

## Run the hub yourself

`init` creates `~/.openhal` with a human token and a [Device File](glossary:device-file) for the simulated plant waterer, a medium risk board that takes commands at once within the board's own range. `openhal risk show plant-waterer` lists each level.

```sh tested
$ openhal init
sample device  ~/.openhal/devices/plant-waterer.hal.yaml created, risk 2 medium, every one takes commands
$ openhal start &
$ openhal status
devices 1 of 1 connected
```

The hub listens on `127.0.0.1:7420` only. A high risk channel such as a heater stays read-only until `openhal file confirm`, and a running hub loads each confirmed file with no restart.

## Your first device

Plug in a board running the OpenHAL firmware, or an ESPHome node, and run `openhal init` again. Low and medium channels such as an LED or a pump take commands at once. A high risk channel opens the limits interview, one question per limit, where Enter keeps the suggestion and you type `confirm` once at the end. The Inspector's Review limits action shows the same questions.

To raise a limit later, run `openhal limits set DEVICE.CHANNEL --max VALUE` and type `confirm`. A narrower limit applies at once. A wider limit from a script or an agent is held in `openhal confirm list` until you approve.

## Send two commands

```sh tested
$ openhal action plant-waterer.water duration=120s
blocked above_max  Blocked. The duration limit is 30 s (max). Requested 120 s.
$ openhal action plant-waterer.water duration=20s
done  Done. water ran.
```

The first duration is above the limit, so the [Safety Kernel](glossary:safety-kernel) blocked the command before the command reached the board. Over the protocol, the same command returns `error -32010 LIMIT_EXCEEDED`.

## Stop

Any client may stop every device. Lifting the stop takes the human token and the typed phrase `unlock`.

```sh tested
$ openhal stop
plant-waterer  safe
$ openhal unlock
```

## Next

- [Concepts](concepts.md) defines the hub, device files, the kernel and the error codes.
- [Connect Claude](tutorials/connect-claude.md) gives an agent a separate token.
- [Add a device](tutorials/add-a-device.md) describes your own hardware.
