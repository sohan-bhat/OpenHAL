<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/wordmark-dark.svg">
  <img alt="OpenHAL" src="docs/assets/wordmark-light.svg" height="44">
</picture>

An open-source protocol for AI agents to control hardware.

[![License](https://img.shields.io/github/license/sohan-bhat/OpenHAL?color=555)](LICENSE) [![CI](https://img.shields.io/github/actions/workflow/status/sohan-bhat/OpenHAL/ci.yml?branch=main&label=CI)](https://github.com/sohan-bhat/OpenHAL/actions/workflows/ci.yml)

<!-- demo-gif:start -->
<!-- demo-gif:end -->

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="docs/diagrams/flow-narrow-dark.svg">
  <source media="(max-width: 600px)" srcset="docs/diagrams/flow-narrow-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/flow-dark.svg">
  <img src="docs/diagrams/flow-light.svg" width="900" alt="OpenHAL flow. An agent sends hal/write to the hub. The safety kernel checks the command against the device file's limits. An allowed command gets a grant and goes through the driver to the 3D printer, and the reading comes back to the agent. Because the nozzle limit is 260 °C, a request for a nozzle temperature of 300 °C is blocked with LIMIT_EXCEEDED.">
</picture>

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

<!-- demo:start -->
Then run the demo. The demo uses simulated devices, so nothing touches real hardware.

```text
openhal demo
```
<!-- demo:end -->

<!-- outcome:start -->
You'll see the agent raise the bed target from 60 °C to 70 °C, have a request for a nozzle temperature of 300 °C blocked at the nozzle limit of 260 °C and pause the print when the camera shows the print has come loose. The owner then approves the cancel, and the printer's state becomes cancelled.
<!-- outcome:end -->

OpenHAL runs on Python 3.12 or newer. [The install guide](docs/guide/install.md) covers uv, pipx, a clone, the background service and Raspberry Pi.

## Why OpenHAL

Agents usually reach each printer or lab instrument through a script or MCP server made for that one device, with the limits in that server's code. OpenHAL is a universal driver specification instead. Agents discover, integrate and control lab and manufacturing equipment through one standard set of commands such as `read` and `write`, and every command is checked against the device's limits.

## How it works

- A `.hal.yaml` device file lists a device's channels and actions, with units and limits.
- The safety kernel checks range, rate, interlocks and confirmation before a driver acts. A command outside the limits is blocked with an error such as `LIMIT_EXCEEDED`.
- One driver covers a device family, such as SCPI for bench instruments.
- Agents connect over MCP, the CLI or the Python client, and the protocol is JSON-RPC 2.0 over WebSocket and stdio.

## Safety model

- Every channel and action has a risk level of low, medium or high. A device file's `hazard` sets the minimum level for every channel and action on the device.
- High risk channels and actions stay read-only until a person confirms the limits. An agent's proposal never counts as a confirmation.
- Low and medium channels and actions take commands within the device's own range. Only a person lowers a level, with `openhal risk set`.
- Each hardware change needs a single-use grant for that exact command.
- A stale or missing reading blocks the command.
- One stop puts every device in a safe state until a person lifts the stop.
- Every decision goes into a hash-chained audit log.

[docs/SAFETY.md](docs/SAFETY.md) has the details.

## Supported devices

OpenHAL has 36 drivers. Every driver passes the conformance suite on a simulator, and none is verified on real hardware yet. No driver covers clinical or patient-connected medical devices. To test a device you own, follow [the hardware test plans](docs/hardware-tests/README.md). [The device library](library/README.md) lists the bundled device files.

<details>
<summary>All 36 drivers</summary>

<!-- devices:start -->
| Driver | Devices covered | Status | Usual hazard |
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
| `micromanager` | research microscopes from Nikon, Zeiss, Olympus and Leica, scientific cameras from Hamamatsu, Andor, Photometrics and PCO, stages, focus drives, filter wheels, shutters and light sources from ASI, Prior, Ludl, Sutter, Lumencor and CoolLED | tested on simulator | medium |
| `onvif` | ONVIF IP cameras, ONVIF PTZ cameras, network video recorders with ONVIF | tested on simulator | low |
| `opcua` | PLCs with an OPC UA server, LADS lab instruments, process equipment and gateways | tested on simulator | medium |
| `pylabrobot` | Hamilton STAR and STARlet, Tecan Freedom EVO, Opentrons OT-2 | tested on simulator | high |
| `ros2` | ROS 2 mobile robots, ROS 2 arms, any ROS 2 graph with rosbridge | tested on simulator | high |
| `seabreeze` | Ocean Insight and Ocean Optics USB spectrometers (USB2000+, USB4000, Flame), Ocean HR, QE Pro and Maya spectrometers, Ocean STS and SPARK spectrometers | tested on simulator | low |
| `sila2` | SiLA 2 lab devices, SiLA 2 gateways, custom SiLA 2 servers | tested on simulator | medium |
| `bambu` | Bambu Lab X1 series, Bambu Lab P1 series, Bambu Lab A1 and A1 mini | tested on simulator | medium |
| `can` | motor controllers (VESC, ODrive, CubeMars), battery management systems, CAN sensor and IO nodes | tested on simulator | medium |
| `knx` | KNX switch and dimmer actuators, KNX blind actuators, KNX room thermostats | tested on simulator | low |
| `matter` | Matter lights and plugs, Matter sensors, Matter thermostats and fans | tested on simulator | low |
| `pi-i2c-spi` | I2C temperature and humidity sensors, SPI and I2C ADCs, SPI and I2C DACs | tested on simulator | low |
| `upnp` | UPnP AV media renderers and speakers, smart TVs with DLNA rendering, internet gateways (IGD) | tested on simulator | low |
| `zigbee-zwave` | Zigbee lights, plugs and sensors, Z-Wave switches, dimmers and plugs, Z-Wave multisensors | tested on simulator | low |
<!-- devices:end -->

</details>

## Connect Claude or another MCP client

`openhal init` sets up the hub, makes a token and offers to add OpenHAL to Claude Desktop, Claude Code and Cursor. The setup for every client is printed either way.

```text
openhal init
openhal start
```

Any other MCP client runs `openhal mcp` over stdio with a separate agent token, as [the MCP guide](docs/interfaces/MCP.md) shows. [Connect Claude](docs/guide/tutorials/connect-claude.md) covers the manual setup.

## Docs and specification

- [Documentation](https://sohan-bhat.github.io/OpenHAL/docs/)
- [Specification](https://sohan-bhat.github.io/OpenHAL/spec/), also in [spec/](spec/SPEC.md)
- [The demo step by step](docs/QUICKSTART.md), with the simulated [printer and camera](examples/print-babysitter/)
- [Mapping to Anthropic's MHS](spec/MHS-MAPPING.md). OpenHAL is not affiliated with Anthropic or the Model Hardware Standard.

## Contributing

Drivers, device files, hardware test reports and docs fixes are welcome. See [CONTRIBUTING.md](.github/CONTRIBUTING.md), [the driver guide](docs/drivers/WRITING-A-DRIVER.md) and issues labeled [good first issue](https://github.com/sohan-bhat/OpenHAL/labels/good%20first%20issue). Report security or safety problems privately through [SECURITY.md](.github/SECURITY.md).

## License

Apache-2.0, in [LICENSE](LICENSE). Device files in `library/` are CC0.
