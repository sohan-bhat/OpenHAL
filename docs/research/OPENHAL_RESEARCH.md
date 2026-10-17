# OpenHAL research (earlier working name Plugsy)

The product is now called OpenHAL (Open Hardware Abstraction Layer). Older sections below say Plugsy.

## Later findings (October 24, 2026)

While checking names, these open projects turned up. They change the competitive picture.

- **OpenMHP** (https://pypi.org/project/openmhp/, https://github.com/kushalsinha/openmhp). "An open protocol for AI agents to operate physical devices safely", "MCP for lab and factory hardware". Apache-2.0, v0.9.0 published September 16, 2026, one maintainer. Device packages with a DEVICE.md card and descriptor.yaml (signals, settings with limits, actions, interlocks, safety rules), six safety gates enforced on every write, plan mode, mDNS and /mhp.json discovery, an MCP bridge with eleven tools, onboarding interview, simulated twins, community registry, adapters for OPC UA, ROS 2, SiLA 2, MADSci, PyLabRobot and MQTT. Tested only against simulators and fakes. Lab and factory focus.
- **Device Context Protocol (DCP)** (https://arxiv.org/abs/2605.26159, PyPI pydcp, GitHub device-context-protocol/dcp). MIT, roughly 62 stars. Compact frames for microcontrollers, a manifest with capability scoping and range checks, a host bridge that rejects malformed or hallucinated calls, ESP32 reference firmware. Requires firmware on the device.
- **Octopus Protocol** (https://arxiv.org/abs/2605.09055). Research. A coding agent enumerates OS-visible hardware, infers identity and capabilities, generates typed MCP tools and hardware code. Reported failure mode of unattended repair loops. No public code.
- **HACP** (https://datatracker.ietf.org/doc/draft-sunyi-hacp-protocol/). IETF individual draft, April 2026, JSON-RPC for agents on edge hardware (GPIO, I2C, UART).
- **EMQ Device Agent** (https://www.emqx.com/en/blog/turning-every-iot-device-into-an-ai-agent). Commercial, generates edge SDKs with MQTT.

### Where OpenHAL leads
1. Real hardware on day one, with verified drivers for the most common maker devices (the others are simulator-tested or research).
2. Automatic onboarding from what already exists (self-describing protocols, the user's own sketch, the manual), with human-approved limits and no unattended loops, and no firmware requirement.
3. Makers, teaching labs and small labs, while the others chase labs and factories.
4. Compatibility rather than another rival standard (import and export OpenMHP packages and DCP manifests, MHS the day it is public).
5. The largest verified device library as the network effect.
6. Speed, since Anthropic reportedly plans hobbyist coverage later.

## The pitch

**How is it different from MHS?**
MHS is invite-only for labs and factories, while this is open source and anyone can plug in a device and use it today with any AI.

**How does it work, in two sentences?**
Each device gets a small file listing what can be read, what can be changed and its safe limits, and our tool writes that file automatically from the device itself, its code or its manual, with the human confirming. A local hub connects your AI to the device over MCP and checks every command against those limits before anything reaches the hardware.

## What Anthropic's Model Hardware Standard (MHS) is

- Anthropic previewed it on August 27, 2026. It started with HHMI Janelia Research Campus.
- It's a standard driver layer that sits between a computer and a device. Every device exposes simple read commands (get the temperature) and write commands (set the temperature), and it's discoverable on a network in a standard format.
- Each driver carries plain-language tags, like a robot arm's weight or a laser's safe power range. You can write them yourself, or an agent interviews you. The driver turns them into a reference file covering what can be measured, what can be adjusted and which limits are enforced.
- Agents reach devices three ways. Through MCP, through a command line, or through code files. The code files chain commands so routines can run without the model thinking at every step.
- The driver blocks any command outside the limits. At Carnegie Mellon, six deliberately triggered faults were all blocked before anything moved.
- It's built for labs and advanced manufacturing, with microscopes, liquid handlers, robot arms, lasers and quantum computer parts.
- Partners include AWS (Strands Robots), Automata (LINQ), Danaher, Doosan Robotics, MBF Bioscience (a ScanImage driver), QIAGEN, Tecan (Fluent), Universal Robots, Hugging Face (LeRobot) and Raspberry Pi (a camera driver).
- These are partner results, reported by Anthropic and not independently verified.
  - **Janelia.** A microscopy rig that needed seven vendor programs now starts with one click.
  - **QuEra.** A laser relock script recovered 695 of 700 faults, running without the model.
  - **Carnegie Mellon.** A liquid handler, plate reader, robot arm and cameras were connected in about 8 hours instead of weeks. The plate reader only had a graphical app.
  - **Genentech.** It ran a protein assay. Claude mistook foam for a software bug until a human explained the physics.
- It only works with hardware that has a programmable interface.

## Is MHS open source? (checked October 24, 2026)

- No. The official site says "MHS is starting as a limited research preview." Access is by application, and it will be open sourced later with no date.
- There's no public spec, schema, SDK, reference driver, license, conformance tests, security guidance or governance.
- Anthropic has no GitHub repo. The only GitHub hit is a third-party notes page.
- I found no news after the August 27 launch.
- One report says Anthropic plans to cover hobbyist hardware later through Claude Code, so the maker space may not stay empty.

## How MHS knows what a device can do

- It doesn't detect it. A person writes a driver for each device, wrapping that device's existing control interface. Vendors and partners are building these now.
- The plain-language tags, written by a human or gathered by an agent interview, supply the rest. The reference file is generated from them.
- Public material doesn't explain the tag format, or whether anything is detected automatically.
- So MHS has the same problem as us, and it solves it with hand-written drivers. Our edge is the automatic part.

## The open landscape today (scattered single-device tools)

- **Arduino and serial.** arduino-mcp-server (MIT), BufrAI arduino-mcp, mcp-serial, serial-mcp.
- **ESP32.** esp32-mcp and several demos. One README says it was only tested against a simulated board.
- **Robots.** ROS MCP Server, about 1.3k stars and Apache-2.0, release v3.1.0 in June 2026. Listed as having no built-in safety validation.
- **3D printers.** Kiln (AGPL-3.0, covers OctoPrint, Moonraker, Bambu, Prusa and Elegoo), OctoEverywhere cloud MCP, Klipper MCP, mcp-3D-printer-server.
- **Bench instruments.** labmcp-scpi, LabMCP, pyMSO5000, SkippyMCP, Instrument MCP Server. Several haven't been tested on real hardware.
- **Lab robots.** plr-mcp for PyLabRobot.
- **Smart home.** Home Assistant has an official MCP since 2025.2, limited to entities exposed to its voice assistant.
- **Standards.** LAP, a June 2026 paper with no code. SiLA 2 and OPC UA LADS, which are industry device standards not built for agents. Viam is a robotics platform with no MCP found.

**The gap.** Each tool is an island with its own shape and its own safety rules or none. Nobody has one shared device description, one place where limits are enforced, routines that span several devices, a shared library of drivers, or tools that write the driver for you.

## How it would work

**1. The device file (the open spec).** One small file per device, using the same read and write idea as MHS so it can become compatible later.

```yaml
device: Desk fan controller
connect: { serial: auto, board: arduino-uno }
read:
  temperature: { unit: degC, every: 1s }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
notes: "Fan is next to the plant. Never run above 80 for more than 10 minutes."
```

**2. The local hub, where safety lives.** It runs on a laptop or a Raspberry Pi.
- Limits are enforced in code before any write reaches hardware. The model is never trusted to respect them.
- One stop command puts every device into its safe state.
- Confirmation gates make risky actions wait for one-tap approval.
- A dry run checks a plan against the limits without moving anything.
- A full log records every read and write, with who asked.
- It discovers devices over USB by matching device IDs, and on the local network.
- It's local-first, never reachable from the internet by default. Text from devices is treated as data, never as instructions.

**3. Three ways in, like MHS.**
- An MCP server that works with Claude, ChatGPT, Cursor or any MCP client.
- A command line, for example `plugsy read fan.temperature`.
- A Python library for routines that run on their own, inside the same limits.

**4. Adapters that wrap existing tools rather than rebuilding them.** pyserial and Firmata (Arduino), PyVISA (bench instruments), Moonraker and OctoPrint (printers), rosbridge (robots), PyLabRobot (lab robots), Home Assistant, GRBL (CNC), MQTT, and Raspberry Pi pins and camera.

**5. The driver writer, the part nobody has.**
1. Detect the device by its USB ID, an identify command, your sketch or its network service.
2. Learn from the manual, using read-only probing only, so nothing moves during discovery.
3. Interview the user about limits. Limits always come from the human, never from the AI.
4. Test the read commands first, then each write at its smallest value, with approval.
5. Share the file to an open library keyed by device model, so the next person gets it instantly. A verified badge means it was tested on real hardware. This is the network effect.

**6. An automatic dashboard.** Every device gets a live page with its readings and controls, built from its file.

## How it knows what a device can do

You can only control a device through the interface its firmware exposes. Knowing its functions means learning that interface's vocabulary. There are three cases.

**1. The device describes itself, so it's automatic and exact.**
- USB device classes. Webcams, keyboards, game controllers, microphones and MIDI gear declare their controls when plugged in.
- Bluetooth LE. Services list each value as readable, writable or streaming.
- Matter smart home devices, UPnP devices and ONVIF cameras publish their capabilities and actions.
- OPC UA and SiLA 2 let you browse every variable and command.
- ROS lists its topics and commands. A web API with an OpenAPI description lists its endpoints.

**2. It has an interface but doesn't describe it**, like custom serial protocols, most hobby boards and many gadgets.
- **The code.** The AI reads your Arduino or ESP32 sketch, where every command is defined.
- **The manual or SDK.** The AI extracts the command list.
- **The official app.** You run the vendor's app on a device you own while the tool passively records the traffic, and the AI learns which messages do what.
- **Listening.** It passively reads values the device already streams.
- It only sends read-only or documented-safe commands while it learns, never unknown commands. You confirm before anything can be changed.

**3. No interface at all.** Nothing outside can control it, including MHS. For devices you program yourself, a tiny firmware library makes the device announce its own functions, which turns it into case 1.

**The honest claim.** It covers any device with an interface. It's automatic for self-describing ones and learned with your confirmation for the rest.

## How the device file gets made, in order

1. **Someone already made it.** Match the USB ID or model to the shared library.
2. **The device describes itself.** Bench instruments, Klipper printers, Home Assistant and ROS all list their capabilities.
3. **It reads your code** for Arduino and ESP32 projects.
4. **It reads the manual**, then confirms each command with read-only queries.

Then the limits interview. Nothing can be changed until you confirm.

## The 30-second demo

1. Plug in an Arduino with a temperature sensor and a fan.
2. "Found an Arduino. Your sketch has a temperature sensor and a fan. What's the max fan speed?" You answer 100.
3. In Claude, "Keep it under 28 degrees." Claude writes a routine, and the dashboard shows the fan responding live.
4. Claude tries 150%, and the hub blocks it on screen with "limit is 100."

## First version

- Platforms are Mac and Raspberry Pi.
- Device types are Arduino over serial, bench instruments, Klipper printers, Home Assistant, and Raspberry Pi pins and camera.
- It ships spec v0.1 and the hub with limits, stop, log, MCP, command line and Python.
- The driver writer handles Arduino sketches and bench instruments.
- It includes about 20 starter device files.
- First users are makers, university teaching labs, small research labs, robotics clubs and small hardware startups. None of them can get into the MHS preview.

## Risks

1. **Anthropic open sources MHS.** Keep the same read and write model and reference file idea, and ship MHS import and export the day the spec is public. The driver writer, the library and the maker focus still have value as MHS-compatible tools.
2. **Physical safety.** Limits are enforced in the hub and set by humans, with confirmation gates and a global stop. Start with low-power maker gear. High-voltage and laser devices need extra confirmation.
3. **Demand.** Makers may be happy with one-off servers. The reasons to switch are the driver writer and the shared library.
4. **Driver quality.** Community files can be wrong. Verified-on-hardware badges and automatic tests are the answer.

## Sources

- Anthropic announcement: https://www.anthropic.com/news/model-hardware-standard-research-preview
- MHS site: https://modelhardwarestandard.com/
- CNBC: https://www.cnbc.com/2026/08/27/anthropic-pushes-into-physical-world-with-new-standard-to-help-ai-agents-operate-machines.html
- The Decoder: https://the-decoder.com/anthropic-wants-to-do-for-physical-hardware-what-its-model-context-protocol-did-for-software/
- Kingy AI analysis: https://kingy.ai/blog/anthropic-model-hardware-standard-mhs/
- DataNorth explainer: https://datanorth.ai/blog/model-hardware-standard-mhs-what-it-is-how-it-works-and-why-it-matters
- AlphaSignal: https://alphasignal.ai/news/anthropic-s-model-hardware-standard-lets-claude-control-lab-robots-overnight
- explainx: https://explainx.ai/blog/anthropic-model-hardware-standard-mhs-research-preview-august-2026
- Packet Nebula: https://packetnebula.com/articles/model-hardware-standard-mhs-research-preview/
- ANI: https://www.aninews.in/news/business/anthropic-announces-new-model-hardware-standard-for-ai-agents-plans-open-source-release-with-safety-guidance20260828112959/
- Third-party GitHub notes: https://github.com/ImChong/Robotics_Notebooks/blob/main/sources/sites/anthropic-model-hardware-standard.md
- LAP paper: https://arxiv.org/abs/2606.03755
- arduino-mcp-server: https://github.com/hardware-mcp/arduino-mcp-server
- BufrAI arduino-mcp: https://github.com/BufrAI/arduino-mcp
- mcp-serial: https://glama.ai/mcp/servers/HumbertoBernal/mcp-serial
- serial-mcp: https://github.com/bmdragos/serial-mcp
- esp32-mcp: https://github.com/StefanYasin/esp32-mcp
- ROS MCP Server: https://discourse.openrobotics.org/t/ros-mcp-server-release/50024
- Kiln: https://pypi.org/project/kiln3d/
- OctoEverywhere MCP: https://blog.octoeverywhere.com/mcp-server-for-3d-printing/
- labmcp-scpi: https://socket.dev/pypi/package/labmcp-scpi
- LabMCP: https://pypi.org/project/labmcp/
- plr-mcp: https://glama.ai/mcp/servers/mcvs54hua1
- Home Assistant MCP guide: https://dev.to/raspberry_tips/connect-home-assistant-to-ai-set-up-an-mcp-server-for-claude-chatgpt-gemini-3io5
- SiLA 2 and OPC UA LADS: https://www.zeiss.com/digital-innovation/insights/a/r-and-d-lab-automation-interoperability-standards-ai.html
