# Brief: drivers batch 3 (lab, robotics, CNC and astronomy)

Read docs/agents/COMMON.md first. Then read docs/drivers/WRITING-A-DRIVER.md (the driver contract), openhal/drivers/base.py, openhal/drivers/mock/ (the reference driver and conformance case), openhal/conformance/suite.py, spec/2026-10-24/drivers.md and safety.md, and one finished Tier 1 driver end to end, such as openhal/drivers/moonraker/ or openhal/drivers/serial/.

## Goal

Implement these eight drivers to the same standard as the Tier 1 drivers. Each needs a real protocol implementation, a simulator or fake that speaks the real protocol, tests, docs and a hardware test plan, and must pass the conformance suite at its declared level.

1. `grbl`. GRBL 1.1 CNC routers and laser cutters over serial.
   - Status reports (`?`) and `$` settings are read-only.
   - Jog and motion as actions.
   - Spindle and laser power as write channels.
   - Native safe state is feed hold (`!`) then soft reset (Ctrl-X).
   - High hazard by default, so every motion and spindle or laser command needs confirm-each-time.
   - The simulator models the GRBL line protocol with `ok`/`error:N` and alarms.
2. `ros2`. ROS 2 through rosbridge (roslibpy).
   - Topics as read channels, publishing to topics as write channels, services and actions as actions.
   - describe() proposes channels from the topic and service list.
   - High hazard by default.
   - The simulator is a small rosbridge v2 WebSocket server.
3. `opcua`. OPC UA through asyncua.
   - describe() browses nodes into channels with engineering units.
   - Method calls become actions.
   - Test against asyncua's own server.
4. `sila2`. SiLA 2 through the official sila2 Python package.
   - Properties as reads, observable properties as streams, commands as actions.
   - Test against a sila2 server generated in the test.
   - If the package can't install on this machine, record why and build against a faithful fake.
5. `indi`. INDI XML protocol over TCP, your own client.
   - Telescope mounts, cameras and focusers.
   - Number, switch and text vectors become channels.
   - Abort is the native safe state for mounts.
   - The simulator is an INDI server that speaks the XML protocol.
6. `alpaca`. ASCOM Alpaca REST and its discovery UDP broadcast.
   - Telescope, focuser, camera, switch and dome device types.
   - Abort slew and park as actions.
   - The simulator is an httpx mock transport that follows the Alpaca API reference.
7. `pylabrobot`. Liquid handlers and lab robots through PyLabRobot.
   - Use its simulator or chatterbox backends for tests.
   - Every motion is an action with confirm-each-time.
   - High hazard by default.
8. `lerobot`. Hugging Face LeRobot arms.
   - Joint positions as reads, goal positions as writes with per-joint limits and rates.
   - Torque off as the native safe state.
   - High hazard by default.
   - LeRobot pulls in heavy dependencies, so import it lazily and test against a faithful fake of its robot interface. Record what the fake assumes, and add a hardware test plan step that checks each assumption.

## Definition of done, per driver

- The package layout and rules in WRITING-A-DRIVER.md.
- `DriverInfo` includes `conformance`. Read-only drivers are "core", drivers that write are "control", and drivers with actions and confirmations are "full" if the suite supports it, otherwise "control".
- discover() and identify() use only read-only or documented-safe commands.
- Tests for normal operation, disconnects, timeouts, malformed responses and every error path, in tests/drivers/<name>/.
- `conformance.py` with a case that passes `tests/conformance/test_conformance.py`.
- An example device file in the package's examples/. It validates with `uv run openhal file validate`, and ships without `confirmed`, so it loads read-only.
- `catalog.json` with `name`, `tier` (2), `status` ("implemented"), `protocols`, `families`, `hazard_default`, `tests`, and `estimate` with its reasoning and sources. The catalog generator adds `conformance` from DriverInfo.
- docs/drivers/<name>.md and docs/hardware-tests/<name>.md. The test plan goes read-only first, then the smallest safe writes, each step with exact commands, expected output and a report template.
- Optional dependencies go in a pyproject extra named after the driver. Record each dependency's version, license and maintenance status in your report. Prefer permissive licenses, and never copy code from copyleft projects.

## Files you own

openhal/drivers/{grbl,ros2,opcua,sila2,indi,alpaca,pylabrobot,lerobot}/, tests/drivers/<those>/, docs/drivers/<name>.md and docs/hardware-tests/<name>.md for those drivers, and pyproject.toml only to add their extras and test dependencies. The orchestrator resolves lockfile conflicts.

## Not yours

Everything else, including drivers/catalog.json and planned.json (the orchestrator regenerates them), the README and openhal/spec/. Another agent builds the other eight planned drivers in parallel.
