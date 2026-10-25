# Brief: drivers batch 4 (home, building, buses and cameras)

Read docs/agents/COMMON.md first. Then read docs/drivers/WRITING-A-DRIVER.md (the driver contract), openhal/drivers/base.py, openhal/drivers/mock/ (the reference driver and conformance case), openhal/conformance/suite.py, spec/2026-10-24/drivers.md and safety.md, and one finished Tier 1 driver end to end, such as openhal/drivers/mqtt/ or openhal/drivers/homeassistant/.

## Goal

Implement these eight drivers to the same standard as the Tier 1 drivers. Each needs a real protocol implementation, a simulator or fake that speaks the real protocol, tests, docs and a hardware test plan, and must pass the conformance suite at its declared level.

1. `onvif`. ONVIF cameras.
   - Device information and stream URIs as read-only data.
   - PTZ moves as actions with pan, tilt and zoom limits.
   - Stop as the native safe state.
   - Use a maintained ONVIF client if one is permissively licensed, otherwise write your own small SOAP client.
   - The simulator answers the ONVIF SOAP calls you use.
2. `bambu`. Bambu Lab printers over the local LAN MQTT interface.
   - First research and record the current terms and firmware authorization status, since Bambu Lab changed local access in 2025. Cite sources in the docs page, and add a NEEDS_HUMAN note if anything needs the owner's legal review.
   - Implement only what is permitted in LAN or developer mode.
   - Temperatures and print state as reads. Pause, resume and stop as actions.
   - Medium hazard by default.
   - The simulator is a local MQTT broker publishing reports in the documented format. The mqtt driver's test broker shows how.
3. `can`. CAN bus through python-can.
   - Signals decoded from frames (id, byte offset, length, scale, offset and unit in the device file map) as reads.
   - Sending frames as writes and actions.
   - Test on python-can's virtual bus.
   - Medium hazard by default.
4. `knx`. KNX building automation through xknx, over KNXnet/IP tunneling or routing.
   - Group addresses with datapoint types as channels.
   - The simulator is a fake KNXnet/IP gateway or xknx's own test facilities.
5. `matter`. Matter devices through python-matter-server's WebSocket API.
   - Nodes, endpoints and clusters become channels and actions.
   - The simulator is a WebSocket server that speaks the matter-server message format.
   - The Home Assistant bridge stays the other route, so say so in the docs.
6. `pi-i2c-spi`. I2C and SPI sensors and DACs on Raspberry Pi through smbus2 and spidev.
   - Register maps in the device file (address, register, length, endianness, scale and unit).
   - Writes only to registers the file lists.
   - Test with fake bus objects.
7. `upnp`. UPnP devices through async-upnp-client.
   - SSDP discovery (read-only), service actions and state variables as channels and actions.
   - Test with a fake device description and SOAP responses.
8. `zigbee-zwave`. Zigbee and Z-Wave through their bridges.
   - Zigbee2MQTT over MQTT (`mqtt://` URL) and zwave-js-server over WebSocket (`ws://` URL).
   - Exposed features and command classes become channels.
   - Simulators for both.
   - The Home Assistant bridge stays the other route, so say so in the docs.

## Definition of done, per driver

- The package layout and rules in WRITING-A-DRIVER.md.
- `DriverInfo` includes `conformance`. Read-only drivers are "core", drivers that write are "control", and drivers with actions and confirmations are "full" if the suite supports it, otherwise "control".
- discover() and identify() use only read-only or documented-safe commands.
- Tests for normal operation, disconnects, timeouts, malformed responses and every error path, in tests/drivers/<package>/.
- `conformance.py` with a case that passes `tests/conformance/test_conformance.py`.
- An example device file in the package's examples/. It validates with `uv run openhal file validate`, and ships without `confirmed`, so it loads read-only.
- `catalog.json` with `name`, `tier` (2 for onvif, 3 for the rest), `status` ("implemented"), `protocols`, `families`, `hazard_default`, `tests`, and `estimate` with its reasoning and sources.
- docs/drivers/<name>.md and docs/hardware-tests/<name>.md. The test plan goes read-only first, then the smallest safe writes, each step with exact commands, expected output and a report template.
- Optional dependencies go in a pyproject extra named after the driver. Record each dependency's version, license and maintenance status in your report. Prefer permissive licenses, and never copy code from copyleft projects.

Driver names are already registered in openhal/spec/models.py:
- `pi-i2c-spi` (package `pi_i2c_spi`), with primary parameter `bus`
- `zigbee-zwave` (package `zigbee_zwave`), with `url`
- `matter`, with `url`
- `upnp`, with `location`
- `knx`, with `gateway`
- `can`, with `channel`
- `bambu`, with `host`

## Files you own

openhal/drivers/{onvif,bambu,can,knx,matter,pi_i2c_spi,upnp,zigbee_zwave}/, tests/drivers/<those>/, docs/drivers/<name>.md and docs/hardware-tests/<name>.md for those drivers, and pyproject.toml only to add their extras and test dependencies. The orchestrator resolves lockfile conflicts.

## Not yours

Everything else, including drivers/catalog.json and planned.json, the README and openhal/spec/. Another agent builds the other eight planned drivers in parallel.
