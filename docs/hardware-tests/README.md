# Hardware tests

Every driver passes its conformance suite against a simulator. These plans are how a person checks a driver and its device file on a real device. Run them in the order below. Nothing here runs in CI, and nothing here should run on hardware you don't own.

## Order

1. **The plant waterer first.** It is the canonical example and the cheapest complete rig. It runs the whole path, from discovery and a read-only file to confirmation, a blocked command, an interlock, an action, a stop and the board's own fallback, and its pump stays unplugged until the last step.
2. **Read-only plans next.** These drivers can't change their device.
3. **Low hazard plans**, ordered by what the smallest change moves. An LED or a register first, then lights and relays with nothing plugged in, then a camera's pan.
4. **Medium hazard plans.** Low voltage first, then relays that can switch mains with no load on them, then motors, heaters and mounts.
5. **High hazard plans last.** Machines that move with force or carry liquids.

Within a group, cheap and common hardware comes first. The hazard column is the driver's default from drivers/catalog.json.

| # | Plan | Hardware | Hazard | What the plan changes |
|---|---|---|---|---|
| 1 | [plant waterer](../../examples/plant-waterer/TEST-PLAN.md) | Arduino Uno, soil sensor, float switch, relay, pump | low | the relay with the pump unplugged, then 5 s of water |
| 2 | [uvc](uvc.md) | USB webcam | low | nothing |
| 3 | [rpi-camera](rpi-camera.md) | Raspberry Pi and a camera module | low | nothing |
| 4 | [openhal-firmware](openhal-firmware.md) | Arduino Uno or ESP32 with an LED | low | an LED's brightness |
| 5 | [firmata](firmata.md) | Arduino Uno with StandardFirmata | low | an LED, then a small fan and a servo |
| 6 | [serial](serial.md) | Arduino Uno with the test sketch | medium | an LED, then a small fan |
| 7 | [hid](hid.md) | macropad with key LEDs | low | a key LED |
| 8 | [midi](midi.md) | MIDI controller with pad LEDs | low | a pad LED |
| 9 | [ble](ble.md) | BLE sensor, then an LED board | low | an LED |
| 10 | [rpi-gpio](rpi-gpio.md) | Raspberry Pi, an LED and a button | low | an LED |
| 11 | [pi-i2c-spi](pi-i2c-spi.md) | Raspberry Pi and a TMP102 | low | an alert register |
| 12 | [esphome](esphome.md) | ESP32 running ESPHome | low | the onboard LED, then a restart |
| 13 | [homeassistant](homeassistant.md) | Home Assistant and a dimmable light | low | a lamp |
| 14 | [matter](matter.md) | Matter Server and a plug with nothing plugged in | low | identify, then the plug |
| 15 | [zigbee-zwave](zigbee-zwave.md) | Zigbee bulb and Z-Wave plug | low | a bulb, then the plug's relay |
| 16 | [knx](knx.md) | KNX installation | low | a light, a dimmer and a setpoint |
| 17 | [upnp](upnp.md) | UPnP speaker | low | mute, a low volume, play and pause |
| 18 | [onvif](onvif.md) | ONVIF PTZ camera | low | a short pan |
| 19 | [scpi](scpi.md) | bench supply with nothing connected | medium | 1 V at 10 mA |
| 20 | [modbus](modbus.md) | energy meter, then a relay module with nothing wired | medium | a relay |
| 21 | [http](http.md) | smart plug with nothing plugged in | medium | the plug's relay |
| 22 | [mqtt](mqtt.md) | Tasmota plug with nothing plugged in | medium | the plug's relay |
| 23 | [can](can.md) | VESC with an unloaded motor | medium | 300 rpm |
| 24 | [marlin](marlin.md) | printer running Marlin | medium | the part fan, a 35 °C bed, optional homing |
| 25 | [octoprint](octoprint.md) | printer behind OctoPrint | medium | the part fan, a 35 °C bed, optional homing |
| 26 | [moonraker](moonraker.md) | Klipper printer | medium | the part fan, a 35 °C bed, optional homing |
| 27 | [bambu](bambu.md) | Bambu Lab printer in Developer Mode | medium | the chamber light, the speed level, a pause |
| 28 | [opcua](opcua.md) | OPC UA server | medium | one variable that drives nothing |
| 29 | [sila2](sila2.md) | empty SiLA 2 device | medium | a 25 °C target, a short shake |
| 30 | [alpaca](alpaca.md) | mount over ASCOM Alpaca | medium | abort, tracking, a 5 degree slew |
| 31 | [indi](indi.md) | mount on indiserver | medium | abort, tracking, a 5 degree slew |
| 32 | [grbl](grbl.md) | CNC router or laser on GRBL | high | a 1 mm jog, a low spindle speed |
| 33 | [lerobot](lerobot.md) | SO-101 arm | high | one joint, 5 degrees |
| 34 | [ros2](ros2.md) | ROS 2 robot with its wheels off the floor | high | 0.05 m/s |
| 35 | [pylabrobot](pylabrobot.md) | liquid handler with water | high | one tip and 10 uL |

## Setup

### A checkout

Every plan runs from a checkout, with its driver's extra. Run every command from the checkout's root.

```
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv sync --extra serial
```

Each plan names its extra in place of `serial`. `uv sync` installs only the extras you name, so name every one you need at once. To install OpenHAL as a tool or a service instead, see [docs/guide/install.md](../guide/install.md). The plans need a checkout, because they use its example files and scripts.

### On a Raspberry Pi

Use Raspberry Pi OS Trixie or later. Its Python 3.13 meets OpenHAL's minimum of 3.12, and the camera's libcamera bindings and lgpio come from apt for that system Python. Make the checkout's environment on the system Python, so it sees them.

```
sudo apt install -y python3-dev python3-lgpio python3-picamera2 i2c-tools
uv venv --system-site-packages --python /usr/bin/python3
uv sync --extra rpi-gpio --extra pi-i2c-spi
uv run python -c "import lgpio; print(lgpio.__file__)"
```

The last command prints a path under `/usr/lib/python3`. `uv sync` keeps the system packages visible.

### A test home and the hub

Every plan that runs the hub uses a test home of its own, so nothing touches your real config.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
bash docs/hardware-tests/hub.sh start
```

`--yes` asks nothing. `--no-sample` leaves out the simulated plant waterer, `--no-discover` adds no device files and `--no-service` installs no background service. `init` also makes an agent token in `$OPENHAL_HOME/agent.token` with the read scope.

[hub.sh](hub.sh) runs the hub from the checkout's environment and logs to `$OPENHAL_HOME/hub.log`.

| Command | What it does |
|---|---|
| `bash docs/hardware-tests/hub.sh start` | Start the hub and wait until it answers |
| `bash docs/hardware-tests/hub.sh stop` | Stop it with SIGTERM and wait until it has exited |
| `bash docs/hardware-tests/hub.sh restart` | Stop, then start, which loads changed device files |
| `bash docs/hardware-tests/hub.sh kill` | Stop it with SIGKILL, so it can send nothing on its way out |
| `bash docs/hardware-tests/hub.sh status` | Say whether it runs |

A plan that stops a command while it runs uses a second terminal. Open it in the checkout and run `export OPENHAL_HOME="$PWD/openhal-test"` there first.

### Confirming limits

Only you confirm limits. `uv run openhal file confirm` with the file's path prints every limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. The hub reads device files when it starts, so restart it after a confirmation. A changed limit makes the file read-only until you confirm it again. A command you send with your own human token counts as your confirmation, so plans that test the confirmation queue send the command with an agent token and approve it with `uv run openhal confirm approve`.

## Rules while testing

- Read-only steps come first. Stop at the first step that fails.
- Never widen a limit to make a step pass. The only limit changes are the ones a plan names, and the plan confirms the file again after each.
- Keep the device's own power switch or emergency stop in reach for anything that moves, heats or switches mains.
- A blocked command that reaches the device is a safety issue. Stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.
- Stop the hub with `bash docs/hardware-tests/hub.sh stop` at the end, and keep `$OPENHAL_HOME` until the report is filed.

## If a step fails

Open an issue titled `Hardware test: <driver>, step <N> fails` with these, and what the plan's own section adds.

1. The step number, the exact command and its full output.
2. The output of `uv run openhal --version` and `git rev-parse --short HEAD`.
3. The operating system and its version, and how the device connects.
4. For plans that run the hub, the output of `uv run openhal status` and `uv run openhal log -n 20`, and the end of `$OPENHAL_HOME/hub.log`.
5. The device file you used, without secrets.

## Reports

Every plan ends with a report template. A filled-in report names the plan, the tester and the date, the device and its firmware, the host, the OpenHAL version and commit, the device file and the `sha256` in its `confirmed` line at the end of the run, each step's result with its output, and one result.

| Result | When |
|---|---|
| `verified-on-hardware` | Every step passed, including the reads, at least one change, the stop, and the blocked command where the plan has one. A device file with no controls, such as a camera or a meter, needs every read step |
| `tested-reads` | Every read-only step passed, and the plan stopped before the changes or a change failed |
| `failed at step N` | A read-only step failed |

Save the report as `docs/hardware-tests/reports/<device id>-<date>.md` and open a pull request with it. For a `verified-on-hardware` or `tested-reads` result, the same pull request sets the device file's verification to that status and names the report.

```yaml
provenance:
  verification: { status: verified-on-hardware, report: docs/hardware-tests/reports/fan-board-2026-11-02.md }
```

Provenance is outside the limits hash, so the confirmation still holds. A library file gets only this change, and never a `confirmed` line. Check the file with `uv run openhal file validate` and its path. A maintainer reviews the report, sets the driver's `status` to `verified` in its package's `catalog.json` once a plan passes, and regenerates drivers/catalog.json and the README devices table.

```
uv run python -m openhal.drivers.catalog
```

## A new plan

Each plan has what you need, read-only steps first, exact commands with their expected output, the smallest safe change, a stop, a blocked command where the device has a limit, an "If something fails" section and a report template with the fields above. `uv run openhal driver new` writes a first draft next to a new driver.
