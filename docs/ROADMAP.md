# Roadmap

What comes after v0.1, in the order the work should happen. Items carry no dates. OpenHAL is not affiliated with Anthropic or MHS.

Today 34 drivers pass the conformance suite on simulators.

## 1. Hardware verification

- Run the plans in [docs/hardware-tests/README.md](hardware-tests/README.md) in their order, starting with the plant waterer.
- Each passing report marks its device file `verified-on-hardware`, and a maintainer sets the driver's catalog status to `verified`.
- Fix what the reports find before adding drivers.

## 2. Next drivers

Every driver in `drivers/planned.json` and the coverage plan ([COVERAGE.md](drivers/COVERAGE.md)) is built. What remains for those drivers is hardware verification.

The drivers below are proposed next. Each speaks a protocol no current driver covers, and each serves makers, teaching labs or small labs.

| Driver | Protocol | Covers | Hazard default |
|---|---|---|---|
| `prusalink` | PrusaLink HTTP API | Prusa MK4, XL, MINI and Core One printers on their own network interface | medium |
| `reprapfirmware` | RepRapFirmware HTTP API | Duet boards in printers, CNC machines and lasers | medium |
| `micromanager` | Micro-Manager MMCore through pymmcore | microscope cameras, stages, shutters and filter wheels | medium |
| `epics` | EPICS Channel Access and pvAccess | beamline and lab instruments behind an EPICS IOC | medium |
| `labjack` | LabJack LJM | LabJack T4 and T7 data acquisition devices | low |
| `dynamixel` | Dynamixel Protocol 2.0 | Robotis servos outside a LeRobot arm | medium |
| `mavlink` | MAVLink 2 through pymavlink | ArduPilot and PX4 rovers, boats and drones | high |
| `ur-dashboard` | Universal Robots Dashboard Server and RTDE | UR collaborative arms | high |

Many devices need only a device file on an existing driver. WLED and Shelly devices fit the `http` driver, and Philips Hue fits `matter` or `homeassistant`. Those devices go to the device library, not into new drivers.

## 3. Windows support

The hub runs on macOS and Linux, and CI runs on Ubuntu. The parts below stop the hub on Windows.

- `openhal/hub/locks.py` locks device ports with `fcntl`, which Windows lacks.
- `openhal/cli/_tty.py` reads typed phrases from `/dev/tty`. Windows needs the console device `CONIN$`.
- `openhal/hub/daemon.py` installs signal handlers through `loop.add_signal_handler`, which the Windows event loop doesn't support.
- The human token and config folder rely on file modes 0600 and 0700. Windows needs access control lists instead.
- The background service uses launchd or systemd. Windows needs a service or a scheduled task.
- The serial, firmata, marlin and grbl tests open real pseudo-terminals, which Windows lacks.

The work is a Windows lock, a Windows phrase reader, a portable shutdown path, ACLs on the token file, a Windows service, `windows-latest` in the CI matrix, and a check in `openhal doctor` that names the Linux-only drivers (`rpi-gpio`, `rpi-camera`, `pi-i2c-spi` and SocketCAN in `can`).

## 4. MHS import and export

[spec/MHS-MAPPING.md](../spec/MHS-MAPPING.md) holds the plan. When Anthropic publishes an MHS specification, OpenHAL adds, in order,

1. an import that turns an MHS reference file into a `.hal.yaml` file with every limit suggested, so a person confirms them before anything is writable,
2. an export that writes an MHS reference file and reports what it couldn't carry over,
3. an `mhs` bridge driver, with the OpenHAL kernel still enforcing the OpenHAL device file,
4. round-trip tests on every file in `spec/examples/` and `library/`.

OpenMHP device packages and Device Context Protocol manifests are public today, so their import and export come first, in v0.2. Nothing in OpenHAL depends on guesses about the MHS format.

## 5. A hosted device library

The starter library ships in the repository under `library/` and inside the wheel, and discovery matches devices against it. A hosted library adds an index that any hub can search by the identifiers discovery reports, such as USB ids, `*IDN?` strings and mDNS types.

- Lookups are off until the person turns them on, because the hub makes no outbound connection by default. A lookup sends only the identifier.
- Files are signed by the library and checked by the hub.
- A downloaded file always loads read-only with suggested limits. The person confirms it on their own hub.
- Submissions stay pull requests, and files stay CC0.
- The `verified-on-hardware` badge links to its public report.

## 6. Vendor app protocol learning

Some devices have an interface but no description, and only the vendor's app knows the commands. The idea from the research is to record the app's traffic to a device the person owns and draft a device file from it. The idea needs a legal review before any code is written. The Bambu Lab terms note in docs/drivers/bambu.md shows why.

- Passive capture only, on the person's own device and network.
- Never break encryption, get around authentication or impersonate vendor software or a vendor cloud.
- The result is a draft with every limit suggested, which goes through the same limits interview.
- Learned commands are tested at their smallest value, one at a time, with a person approving each.
- Captured text is data. The hub never treats it as instructions.

## 7. Promised elsewhere in the docs

- Out-of-process drivers, so a third-party driver can't reach the kernel (SAFETY.md, threat T17, ADR 0004).
- Exporting the audit chain head outside the hub, so a deleted database is detectable (ADR 0010).
- Notification filters in the hub protocol (ADR 0015).
- The driver proposals in PROGRESS.md, including a reconnect hook, a push path for drivers that receive values and per-driver install hints.
- A PyPI name and a domain before the first release (NEEDS_HUMAN.md, items 1 and 2).

## 8. Business model sketch

The protocol, the specification, the hub, the safety kernel, the drivers, the firmware library and the device library stay open source under Apache-2.0 and CC0. Safety features are never paid features. Paid work is hosting and people's time.

- **Hosted remote access.** A relay that lets a person reach their own hub from outside their network. The hub dials out, traffic is end-to-end encrypted, and every command still passes the hub's own kernel and lands in its own audit log. Human-only steps still need the human.
- **Classroom and lab plans.** Many hubs managed together. An instructor distributes device files, each hub's owner confirms the limits, teaching assistants work the confirmation queues, and audit logs export for review.
- **A verified library.** A test lab runs the hardware test plans on a vendor's device and publishes the report. Vendors pay for the lab time, not for the badge. A device that fails is reported as failing, and every report is public.
- **Hardware partnerships.** Kits such as the plant waterer, boards that ship with the OpenHAL firmware library and a device file, and vendors who publish device files for their own products.
