<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/wordmark-dark.svg">
  <img alt="OpenHAL" src="docs/assets/wordmark-light.svg" height="44">
</picture>

An open-source protocol for AI agents to control hardware.

[![License](https://img.shields.io/github/license/sohan-bhat/OpenHAL?color=555)](LICENSE) [![CI](https://img.shields.io/github/actions/workflow/status/sohan-bhat/OpenHAL/ci.yml?branch=main&label=CI)](https://github.com/sohan-bhat/OpenHAL/actions/workflows/ci.yml)

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="docs/diagrams/flow-narrow-dark.svg">
  <source media="(max-width: 600px)" srcset="docs/diagrams/flow-narrow-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/flow-dark.svg">
  <img src="docs/diagrams/flow-light.svg" width="900" alt="OpenHAL flow. An agent sends hal/write to the hub. The safety kernel checks the command against the device file's limits. An allowed command gets a grant and goes through the driver to the 3D printer, and the reading comes back to the agent. Because the nozzle limit is 260 °C, a request for a nozzle temperature of 300 °C is blocked with LIMIT_EXCEEDED.">
</picture>

## Quickstart

You need [uv](https://docs.astral.sh/uv/) and git, and nothing in the demo touches hardware.

```
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```

<!-- outcome:start -->
You'll see the agent raise the bed target from 60 °C to 70 °C, have a request for a nozzle temperature of 300 °C blocked at the nozzle limit of 260 °C and pause the print when the camera shows the print has come loose. The owner then approves the cancel, and the printer's state becomes cancelled.
<!-- outcome:end -->

## Message trace

<!-- trace:start -->
```
# the agent checks the first layer
→ hal/read    { "device": "printer-cam", "channel": "frame" }
← result      { "value": { "mimeType": "image/jpeg", "bytes": 19409,
                "width": 640, "height": 480, "data": "…" } }

# a corner of the first layer is lifting
→ hal/write   { "device": "printer", "channel": "bed_target",
                "value": 70, "unit": "degC" }
← result      { "status": "done" }

# a hotter nozzle might help the corner stick
→ hal/write   { "device": "printer", "channel": "extruder_target",
                "value": 300, "unit": "degC" }
← error -32010 LIMIT_EXCEEDED
  extruder_target 300 degC exceeds the limit of 260 degC
  (printer.hal.yaml, confirmed by owner 2026-10-24)

# later the agent checks the print again
→ hal/read    { "device": "printer-cam", "channel": "frame" }
← result      { "value": { "mimeType": "image/jpeg", "bytes": 23567,
                "width": 640, "height": 480, "data": "…" } }

# the print has come loose
→ hal/action  { "device": "printer", "action": "pause" }
← result      { "status": "done" }

# cancelling can't be undone
→ hal/action  { "device": "printer", "action": "cancel" }
← result      { "status": "pending", "requestId": "REQUEST_ID",
                "expiresInS": 300 }

# the owner approves the cancel
→ hal/confirmations/approve { "requestId": "REQUEST_ID" }
← result      { "status": "done" }
```
<!-- trace:end -->

In this trace an agent keeps an eye on a long 3D print, and the agent watches the camera, judges what is going wrong and acts while the safety kernel checks every command against the limits a person confirmed. The owner approves the cancel, the kernel checks the cancel again, and the printer's state becomes cancelled. The trace is a real run of the hub against a simulated [printer and camera](examples/print-babysitter/), recorded in [docs/demo/scenario.yaml](docs/demo/scenario.yaml). The camera frames are line drawings, and `REQUEST_ID` stands in for the hub's random request id.

## Install

```
uv tool install --compile-bytecode git+https://github.com/sohan-bhat/OpenHAL
openhal init
```

`openhal init` sets up the hub, adds every device the hub finds as a read-only file and prints the setup for Claude Desktop, Claude Code or Cursor. [The install guide](docs/guide/install.md) covers pipx, the background service and Raspberry Pi.

## What OpenHAL does

- **One device file format.** A `.hal.yaml` file describes what a device can read and do, with units and limits a person confirmed.
- **One safety kernel.** Every command is checked for range, rate, interlocks and confirmation before any driver can act.
- **Drivers for whole device families.** One SCPI driver covers bench instruments and one Moonraker driver covers Klipper printers.

## Supported devices

v0.1, in development. Every driver passes the conformance suite on a simulator.

<!-- devices:start -->
| Driver | Devices covered | Status | Hazard default |
|---|---|---|---|
| `ble` | environmental sensors, battery powered sensors, BLE LED and relay boards | tested on simulator | low |
| `esphome` | ESP32, ESP8266, RP2040 and BK72xx boards running ESPHome, sensors, switches, lights, fans, numbers, selects and buttons defined in ESPHome YAML | tested on simulator | low |
| `firmata` | Arduino AVR boards, Arduino-compatible clones, Teensy | tested on simulator | low |
| `hid` | macropads and button boxes, knobs and jog wheels, foot switches | tested on simulator | low |
| `homeassistant` | lights, switches and smart plugs, fans | tested on simulator | low |
| `http` | smart plugs and relays, networked sensors, lab and bench gadgets with REST APIs | tested on simulator | medium |
| `marlin` | FDM 3D printers, pen plotters and other Marlin machines | tested on simulator | medium |
| `midi` | pad and knob controllers, keyboards, synthesizers | tested on simulator | low |
| `modbus` | energy and power meters, PLCs, variable frequency drives | tested on simulator | medium |
| `moonraker` | Klipper 3D printers (Voron, RatRig, Creality K1 and Sonic Pad, Sovol SV08, Elegoo Neptune 4, Qidi) | tested on simulator | medium |
| `mqtt` | Tasmota devices, Zigbee2MQTT bridged devices, ESPHome and Shelly devices with MQTT enabled | tested on simulator | medium |
| `octoprint` | 3D printers connected to OctoPrint (Marlin, Prusa, RepRapFirmware and Klipper with the OctoPrint connector) | tested on simulator | medium |
| `openhal-firmware` | Arduino boards, ESP32 boards, maker projects that run the OpenHAL library | tested on simulator | low |
| `rpi-camera` | Raspberry Pi Camera Module 1, 2 and 3, Raspberry Pi High Quality and Global Shutter cameras, Raspberry Pi AI Camera | tested on simulator | low |
| `rpi-gpio` | relays and relay boards, LEDs, buttons, reed switches and limit switches | tested on simulator | low |
| `scpi` | bench power supplies, multimeters, oscilloscopes | tested on simulator | medium |
| `serial` | Arduino and other microcontroller sketches, bench instruments with ASCII command sets, sensor modules with text output | tested on simulator | medium |
| `uvc` | USB webcams, USB microscopes, HDMI to USB capture cards | tested on simulator | low |
| `alpaca` | telescope mounts, focusers, cameras and power boxes, observatory domes | tested on simulator | medium |
| `grbl` | desktop CNC routers, diode and CO2 laser engravers, pen plotters | tested on simulator | high |
| `indi` | telescope mounts, focusers, astronomy cameras | tested on simulator | medium |
| `lerobot` | SO-100 and SO-101 arms, Koch and OMX arms, other LeRobot arms with joint goals | tested on simulator | high |
| `onvif` | ONVIF IP cameras, ONVIF PTZ cameras, network video recorders with ONVIF | tested on simulator | low |
| `opcua` | PLCs with an OPC UA server, LADS lab instruments, process equipment and gateways | tested on simulator | medium |
| `pylabrobot` | Hamilton STAR and STARlet, Tecan Freedom EVO, Opentrons OT-2 | tested on simulator | high |
| `ros2` | ROS 2 mobile robots, ROS 2 arms, any ROS 2 graph with rosbridge | tested on simulator | high |
| `sila2` | SiLA 2 lab devices, SiLA 2 gateways, custom SiLA 2 servers | tested on simulator | medium |
| `bambu` | Bambu Lab X1 series, Bambu Lab P1 series, Bambu Lab A1 and A1 mini | tested on simulator | medium |
| `can` | motor controllers (VESC, ODrive, CubeMars), battery management systems, CAN sensor and IO nodes | tested on simulator | medium |
| `knx` | KNX switch and dimmer actuators, KNX blind actuators, KNX room thermostats | tested on simulator | low |
| `matter` | Matter lights and plugs, Matter sensors, Matter thermostats and fans | tested on simulator | low |
| `pi-i2c-spi` | I2C temperature and humidity sensors, SPI and I2C ADCs, SPI and I2C DACs | tested on simulator | low |
| `upnp` | UPnP AV media renderers and speakers, smart TVs with DLNA rendering, internet gateways (IGD) | tested on simulator | low |
| `zigbee-zwave` | Zigbee lights, plugs and sensors, Z-Wave switches, dimmers and plugs, Z-Wave multisensors | tested on simulator | low |
<!-- devices:end -->

## Safety model

- A device file stays read-only until a person confirms its limits, and nothing an agent proposes counts as a confirmation.
- Every hardware change needs a single-use grant the kernel issues for that exact command.
- Unknown values never pass a check, so a stale or missing reading blocks the command.
- One stop puts every device in its safe state, and the hub blocks every command until a person lifts the stop.
- Every decision goes into a hash-chained audit log.

[docs/SAFETY.md](docs/SAFETY.md) has the details.

## Relationship to Anthropic's MHS

Anthropic's Model Hardware Standard is a limited research preview for invited labs, and OpenHAL is not affiliated with MHS or with Anthropic. OpenHAL is an open protocol you can use today, and we plan to stay compatible with MHS as MHS opens up ([mapping](spec/MHS-MAPPING.md)).

## Contributing

Build a driver with [the driver guide](docs/drivers/WRITING-A-DRIVER.md) and run the conformance suite with `uv run pytest tests/conformance`. Device files follow [spec/SPEC.md](spec/SPEC.md).

## License

OpenHAL is licensed under Apache-2.0, and the full text is in [LICENSE](LICENSE).
