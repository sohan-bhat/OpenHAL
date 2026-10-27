# Launch drafts

Drafts only. Nothing on this page has been posted, and the owner posts each draft. Every claim comes from the repository on 2026-10-25. Check each claim again on the day.

## Before any post

1. CI passes on `main`, so the README badge is green (DESIGN.md bans a failing badge).
2. The README quickstart works on a fresh machine, from `git clone` to `uv run openhal demo`.
3. The plant waterer plan (examples/plant-waterer/TEST-PLAN.md) has run on a real board.
4. NEEDS_HUMAN.md items 1 and 2, the PyPI name and the domain, are decided.
5. `uv run openhal driver list` still shows 34 drivers. Fix the counts below if it doesn't.
6. Each community's rules on self-promotion, flair and posting days are read and followed. One community at a time, a few days apart.
7. Someone is there for the first hours to answer. Hardware reports go to issues. Safety reports go through SECURITY.md.

## Show HN

**Title.** Show HN: OpenHAL, an open protocol for AI agents to control hardware

**URL.** https://github.com/sohan-bhat/OpenHAL

**Text.**

> OpenHAL is an open protocol and a local hub that sit between an AI agent and real devices. Every command goes through a safety kernel that checks the command against limits a person confirmed, and a command that passes gives the driver a single-use grant to act.
>
> The demo is an agent keeping an eye on a long 3D print, against a simulated Klipper printer and its camera. The demo needs only git and uv.
>
>     git clone https://github.com/sohan-bhat/OpenHAL
>     cd OpenHAL
>     uv run openhal demo
>
> You'll see the agent read camera frames and warm the bed from 60 °C to 70 °C. The hub refuses the agent's 300 °C nozzle at the 260 °C limit. When the print comes loose the agent pauses the print and asks to cancel, the owner approves the cancel, and the printer's state becomes cancelled.
>
> How OpenHAL works.
>
> - Each device has a .hal.yaml file with the device's readings, controls, units and limits. The file loads read-only until a person confirms the limits, and nothing an agent sends counts as a confirmation.
> - The kernel checks range, rate of change, interlocks, watchdog budgets and confirmation in a fixed order, with no model in the loop. A stale or unknown reading blocks the command.
> - One stop puts every device in its safe state and refuses everything until a person runs openhal unlock.
> - Every decision goes into a hash-chained audit log.
> - The hub speaks JSON-RPC 2.0 over WebSocket and stdio, with a dated specification (2026-10-24), an error registry and three conformance levels. An MCP server, a CLI and a Python client sit on top.
>
> Where it stands. 34 drivers pass a conformance suite against simulators, including Klipper through Moonraker, Marlin, OctoPrint, SCPI instruments, Home Assistant, ESPHome, MQTT, Modbus, BLE, MIDI, Raspberry Pi GPIO and camera, ROS 2, OPC UA, SiLA 2, ASCOM Alpaca and INDI. Each has a step-by-step hardware test plan, and the plant waterer's comes first. This is v0.1, in development.
>
> OpenHAL isn't affiliated with Anthropic. Anthropic's Model Hardware Standard is an invite-only research preview. OpenHAL is open now and plans to stay compatible once MHS has a public spec.
>
> I'd like feedback on the protocol and the kernel's check order, and hardware test reports from anyone who wants to try to break the limits. Safety bugs go through the private reporting in SECURITY.md.

## The HAL 9000 jokes

The demo shows the hub refusing a command, so someone will post "I'm sorry Dave, I'm afraid I can't do that" in the first ten minutes. The plan is to take it well and turn it toward the design.

1. Never make the joke first. Not in a title, a post, the README, the site or an image. DESIGN.md bans 2001 references in the design.
2. Answer it once per thread, briefly, then answer the next technical question.
3. Never use the red eye, "Daisy" or an ominous voice, even in a reply.
4. If the name keeps pulling threads away from the protocol, that is input for NEEDS_HUMAN.md item 1, which lists rename options.

Prepared replies.

| Comment | Reply |
|---|---|
| "I'm sorry Dave, I'm afraid I can't do that." | Fair. OpenHAL tells you why. The error names the limit, the file and who confirmed it, and openhal stop always works. |
| "Why call it HAL?" | Hardware agent layer, the layer between agents and hardware. It nods to the old embedded term hardware abstraction layer, as in STM32 HAL or Android HAL. We knew about the other HAL when we picked it. |
| "Open the pod bay doors." | There's no pod bay door driver yet. If there were, the doors would stay read-only until a person confirmed their limits. |
| "What could possibly go wrong?" | A lot, which is why the kernel fails closed, unknown readings block commands and an agent can never lift a stop. docs/SAFETY.md also lists what it doesn't guarantee. |

## r/arduino

**Title.** I made an open hub that lets an AI agent drive an Arduino sketch inside limits you set, and I need people to test it on a real Uno

**Body.**

> OpenHAL sits between an AI agent (Claude, Cursor or any MCP client) and your board. Your sketch uses the OpenHAL Arduino library to say what it can read and do. A small device file holds the limits, and the hub checks every command against them before anything reaches the serial port.
>
> The example is a plant waterer. An Uno reads a capacitive soil sensor on A0 and a float switch on pin 4, and runs a pump through a relay on pin 7. The limits are 30 s per watering, 3 runs per hour, and never with the tank empty. The board enforces the 30 s and the tank check itself as well, and turns the pump off if the hub's heartbeats stop for 3 s.
>
> The honest part. The library compiles for the Uno and for ESP32, and the hub has run against a simulated board that speaks the same protocol. Nobody has run it on a real board yet. The test plan keeps the pump unplugged until the last step, so a mistake clicks a relay and nothing gets wet.
>
> If you have an Uno, a soil sensor, a float switch and a relay, a run of examples/plant-waterer/TEST-PLAN.md would help a lot. There are also drivers for StandardFirmata and for sketches with their own text protocol over serial, also tested on simulators only.
>
> https://github.com/sohan-bhat/OpenHAL

## r/esp32

**Title.** ESPHome nodes, BLE peripherals and a small ESP32 library behind one safety hub for AI agents

**Body.**

> OpenHAL is an open hub that lets AI agents read and control devices, with every command checked against limits you confirmed. Four of its drivers are for ESP32 boards.
>
> - esphome talks the native API, plaintext or Noise encrypted, and covers the sensors, switches, lights, fans, numbers, selects and buttons in your ESPHome YAML.
> - ble reads and writes GATT characteristics and maps the Environmental Sensing service by itself.
> - mqtt covers ESPHome and Tasmota devices with MQTT on.
> - openhal-firmware talks to boards running the OpenHAL Arduino library, which compiles for esp32:esp32:esp32.
>
> Only the entities you list in the device file are reachable, and the file's limits apply even when ESPHome allows more.
>
> All of this is tested against simulators. The esphome tests drive the real aioesphomeapi client against a native API simulator. None of it has run on a real ESP32 yet. If you have a node with an LED, docs/hardware-tests/esphome.md starts read-only and ends with switching that LED.
>
> https://github.com/sohan-bhat/OpenHAL

## r/3Dprinting

**Title.** An open hub that lets an AI agent watch a printer and change it only inside limits you confirm

**Body.**

> I've been building OpenHAL, an open protocol and local hub between AI agents and hardware. OpenHAL has drivers for Marlin over USB, for OctoPrint, for Klipper through Moonraker, and for Bambu Lab printers on the LAN in Developer Mode, which never contacts Bambu Cloud.
>
> Each printer gets a device file with its limits. The Ender-3 V2 example caps the hotend at 240 °C and the bed at 90 °C, limits how fast targets can rise, needs your confirmation for any hotend target and for homing, and refuses to home while an SD print runs. A stop sets every heater target and the part fan to 0. The file stays read-only until you confirm it yourself.
>
> Everything is tested on simulators, including a Marlin simulator that checks line numbers and checksums over a real pseudo-terminal. OpenHAL has not touched a real printer yet. The hardware test plans start read-only, then try the part fan, then a 35 °C bed target, and homing is optional.
>
> If you'd run docs/hardware-tests/marlin.md or octoprint.md on a printer you know well, I'd be grateful for the report, especially anything that surprised you.
>
> https://github.com/sohan-bhat/OpenHAL

## r/klippers

**Title.** A Moonraker driver for an open AI agent hub, with limits checked before anything reaches Klipper

**Body.**

> OpenHAL is an open hub between AI agents and hardware. The moonraker driver speaks Moonraker's JSON-RPC over HTTP and WebSocket, reads printer objects, and can draft a device file from what Moonraker reports, with every limit marked suggested until you confirm it.
>
> Klipper's own limits still apply. The device file adds limits of its own, such as a 110 °C bed cap on the Voron 2.4 example, a rate limit on heater targets, confirmation for the hotend and for homing, and no homing while printing. Whichever limit is lower wins, and a refusal names the limit and who confirmed it. The API key comes from an environment variable, never from the file.
>
> The driver is tested against a Moonraker simulator with a real local WebSocket server, and hasn't run against a real Klipper install yet. docs/hardware-tests/moonraker.md is read-only for the first four steps, then sets the part fan to 20 % and the bed to 35 °C.
>
> Reports from Voron, RatRig, K1 or Sovol owners would help most.
>
> https://github.com/sohan-bhat/OpenHAL

## r/homeassistant

**Title.** Putting a safety kernel between AI agents and Home Assistant entities

**Body.**

> Home Assistant has had its own MCP server since 2025.2, for the entities you expose to its assistant. OpenHAL is for when you want limits that Home Assistant doesn't hold, and one place that enforces them across devices.
>
> - A device file per device, with ranges, rate limits and confirmation tiers on each entity you choose. Only those entities are reachable.
> - Interlocks across devices, such as no heater while a window sensor reads open, including devices Home Assistant doesn't manage.
> - The file's limits win even when Home Assistant would allow more.
> - Every request, refusal and stop goes into a hash-chained log with who asked.
> - The token lives in an environment variable, never in the file.
>
> If you'd rather skip Home Assistant for some devices, there are direct drivers for ESPHome, Zigbee2MQTT, zwave-js-server, the Matter Server and KNX.
>
> All of it is tested against simulators, including a Home Assistant simulator with a real local WebSocket server. None of it has run against a real instance yet. docs/hardware-tests/homeassistant.md needs one dimmable lamp and starts read-only.
>
> https://github.com/sohan-bhat/OpenHAL

## r/raspberry_pi

**Title.** A local hub for AI agents on a Pi, with GPIO, camera and I2C and SPI drivers and a physical stop button

**Body.**

> OpenHAL is an open hub that sits between AI agents and hardware and checks every command against limits you confirmed. The hub runs on a Pi or a laptop.
>
> - rpi-gpio drives relays and LEDs and reads buttons, reed switches and limit switches through gpiozero.
> - rpi-camera captures stills through picamera2 and never changes the camera.
> - pi-i2c-spi reads and sets chips such as the TMP102, MCP3008 and MCP4921.
> - A helper in rpi-gpio watches a push button on a GPIO input and calls the hub's stop, which puts every device in its safe state until a person lifts the stop. The button doesn't replace an e-stop that cuts power.
>
> One detail I'd like checked on real boards. When the hub exits, gpiozero releases the pins, and an active-low relay board without a pull-up can switch on. The docs say to fit a pull resistor so a released pin means off.
>
> The Pi drivers are tested against gpiozero's mock pin factory and fakes of picamera2, smbus2 and spidev, and haven't run on a real Pi yet. If you have a Pi 4 or 5 with an LED and a button, docs/hardware-tests/rpi-gpio.md is the plan.
>
> https://github.com/sohan-bhat/OpenHAL

## r/astrophotography

**Title.** Letting an AI agent run an Alpaca or INDI mount, with every slew waiting for you to approve it

**Body.**

> I know how that title sounds, so here is what OpenHAL does and doesn't do.
>
> OpenHAL is an open hub between AI agents and hardware. The alpaca driver covers ASCOM Alpaca mounts, focusers, cameras, power boxes and domes, and the indi driver covers INDI mounts, focusers and cameras. In the example files every slew waits for a person each time, and a slew needs the mount unparked, tracking and not already slewing. A stop aborts slews, halts focusers and aborts exposures, and the examples turn tracking off as well. Nothing parks the mount unless your file says so.
>
> Both drivers are tested against an Alpaca server simulator and an INDI server simulator speaking the XML protocol. Before real gear, the most useful report would be a run against ASCOM's Alpaca simulators or INDI's telescope simulator. After that, the hardware plans try abort, tracking on and off, and one short slew of a few degrees.
>
> OpenHAL lets an assistant read the mount and the focuser and propose a slew you approve, while you stay with the telescope.
>
> https://github.com/sohan-bhat/OpenHAL

## r/synthesizers

**Title.** A MIDI driver that lets AI agents play with your gear inside ranges you set

**Body.**

> OpenHAL is an open hub between AI agents and hardware. The midi driver uses mido and python-rtmidi to read knobs, faders and pads, and to send notes and control changes that light pad LEDs, move motorised faders and set synth parameters.
>
> Each control is a channel with a range and an optional rate limit, so an agent can sweep a filter but can't jump the volume to full. A stop sends the values your file names as safe. Everything is logged, so you can see what the agent asked for and when.
>
> The driver is tested against a fake mido backend with a simulated pad controller, and hasn't run against a real controller yet. The example is an Akai LPD8, and docs/hardware-tests/midi.md lights one pad and then stops.
>
> If you try it with something more interesting than pads, I'd like to hear what the device file looked like.
>
> https://github.com/sohan-bhat/OpenHAL

## r/labrats

**Title.** An open protocol for AI agents and lab instruments where every high hazard action waits for a person

**Body.**

> I'm building OpenHAL, an open protocol and local hub between AI agents and instruments. Anthropic's Model Hardware Standard covers similar ground but is invite-only. OpenHAL isn't affiliated with MHS and plans to stay compatible once MHS has a public spec.
>
> Drivers cover SCPI bench instruments through PyVISA, SiLA 2 devices, OPC UA servers including LADS, and liquid handlers through PyLabRobot (Hamilton STAR and STARlet, Tecan Freedom EVO, Opentrons OT-2).
>
> - A liquid handler is high hazard, so every action waits for a person each time, and approving an action takes the human token.
> - Volumes, temperatures and speeds are checked against limits a person confirmed, with units converted before the comparison.
> - A stop cancels running operations and moves nothing, because any move on a deck can spill or crash a tip.
> - Every request, refusal and approval goes into a hash-chained audit log.
>
> The drivers are tested against PyLabRobot's chatterbox backend, the sila2 package's own server, an asyncua server and pyvisa-sim. OpenHAL doesn't replace your SOPs.
>
> The smallest useful test is docs/hardware-tests/scpi.md on a bench supply, which sets 1 V at 10 mA with nothing connected.
>
> https://github.com/sohan-bhat/OpenHAL
