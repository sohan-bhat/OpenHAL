# Drivers batch 2 report

All nine drivers are done and every check passes. I could not write `docs/agents/REPORT-drivers-2.md`: the Write tool blocks subagents from writing report files. The full report is below so you can save it as that file.

Branch `worktree-agent-af4d0f34b4befd5d1`, 42 commits on top of `24dbe73`, nothing pushed, working tree clean. The checks were `uv run pytest` (545 passed, 276 before this work), `ruff check`, `ruff format --check` and `mypy openhal`. Every example file validates with `uv run openhal file validate`. Nothing has been tried on real hardware. Every driver was tested only against its simulator or fake.

---

# Report, drivers batch 2

## Drivers and conformance

| Driver | Library | Simulator or fake | Tests | Conformance |
|---|---|---|---|---|
| http | httpx | simulated smart plug on `httpx.MockTransport` | 37 | 12 passed |
| modbus | pymodbus | pymodbus's own server running a simulated fan controller, TCP, and RTU framing over `socket://` | 42 | 12 passed. The suite runs TCP. The RTU case runs in the driver tests and passes |
| mqtt | paho-mqtt | an MQTT 3.1.1 broker I wrote from the OASIS standard, running in-process with a simulated fan. A real paho client talks to it | 32 | 12 passed |
| ble | bleak | fake BleakClient and BleakScanner, simulated Environmental Sensing peripheral | 43 | 12 passed |
| midi | mido, python-rtmidi | fake mido backend, simulated pad controller, real mido messages | 20 | 11 passed, 1 skipped (timeout, MIDI is local) |
| hid | hidapi | fake hidapi module, simulated macropad with a real report descriptor | 24 | 11 passed, 1 skipped (timeout, HID is local) |
| uvc | opencv-python-headless | fake VideoCapture, real cv2 JPEG encoding | 17 | 8 passed, 4 skipped (read-only, so the write checks don't apply) |
| rpi-camera | picamera2 (apt) | fake Picamera2 built from the Picamera2 manual | 16 | 8 passed, 4 skipped (read-only) |
| rpi-gpio | gpiozero | gpiozero's mock pin factory with PWM pins | 29 | 11 passed, 1 skipped (timeout, GPIO is local) |

## Files

Each driver has the standard package under `openhal/drivers/<package>/`, plus `tests/drivers/<package>/`, `docs/drivers/<name>.md` and `docs/hardware-tests/<name>.md`. A few drivers have extra modules:
- `http/values.py` (JSON paths, templates, payload coercion), which mqtt also imports
- `http/openapi.py`
- `ble/codec.py`, which handles the GATT formats including IEEE 11073 SFLOAT and FLOAT
- `hid/descriptor.py`, a parser for HID report descriptors
- `rpi_gpio/stop_button.py`, which holds `watch_stop_button` and is exported from the package

Outside the driver directories:
- `pyproject.toml` has new extras `rpi-gpio`, `mqtt`, `modbus`, `ble`, `midi`, `hid`, `uvc` and `http`, and `uv.lock` is updated.
- I added `tests/drivers/__init__.py`, an empty file. The other driver agent needs the same one, so that merge is trivial.

## New dependencies (versions from uv.lock)

| Package | Version | License | Notes |
|---|---|---|---|
| gpiozero | 2.0.1.post3 | BSD-3-Clause | Brings colorzero 2.0 (BSD-3) and setuptools 84.2.1 (MIT) |
| paho-mqtt | 2.1.0 | EPL-2.0 OR BSD-3-Clause | Used under the BSD option. Last release 2024-04, project still active |
| pymodbus | 3.16.1 | BSD-3-Clause | Installed with the `[serial]` extra |
| pyserial | 3.5 | BSD-3-Clause | Comes in through pymodbus |
| bleak | 3.0.2 | MIT | On macOS it brings pyobjc-core and three pyobjc frameworks, 12.2.2, MIT |
| mido | 1.3.3 | MIT | |
| python-rtmidi | 1.5.8 | MIT | Last release 2023-11, no wheels for Python 3.13 or newer, so it builds from source (it built here) |
| hidapi | 0.15.0 | GPL-3.0, BSD or original HIDAPI, user's choice | Used unmodified under the BSD option |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | 33 MB download, plus numpy 2.5.4 (BSD-3) |
| httpx | 0.28.1 | BSD-3-Clause | Already in the hub extra |

Not added:
- **picamera2 0.3.38 (BSD-2):** `uv lock` fails on macOS, because python-prctl only builds on Linux. On a Pi it comes from apt as `python3-picamera2`. The driver imports it lazily and explains the apt install when it is missing. There is no `rpi-camera` extra.
- **amqtt (MIT):** it pins `websockets==15.0.1`, which conflicts with the hub's websockets 17.3, and pulls in heavy dependencies. I wrote the small broker instead.
- **lgpio:** it ships with Raspberry Pi OS.

No copyleft code was copied. Each docs page lists the specs and manuals it is based on.

## Decisions

- **Injecting fakes:** each driver takes its fake through a keyword-only constructor argument (`transport=`, `client_factory=`, `backend=`, `hid_module=`, `capture_factory=`, `picamera2_class=`, `pin_factory=`). The hub still builds drivers with `cls(file)`.
- **Push protocols (MQTT, BLE notify, MIDI, HID input):** the driver keeps the newest value per source. A read returns it with its arrival time, or `Reading(value=None)` before anything has arrived. The kernel treats `None` as unknown.
- **Write channels with no read-back:** a read returns the last value the driver sent, or `None` before the first write. Every write channel can be read, as your update requires.
- **Rounding:** values are rounded to the protocol's resolution, and the returned reading shows the value actually sent. A value the protocol can't carry raises `DriverError` and nothing is sent. Nothing is clamped.
- **Suspect readings:** each driver marks readings outside `range` as suspect, because nothing upstream does it yet.
- **MQTT:** commands are never queued or replayed. paho's auto-reconnect is off, and a missing PUBACK drops the client so the command can't arrive late. Client ids are `oh-` plus the first 13 characters of the device id plus a 6-character hash, so two devices never share an id. Without the hash, ids sharing a prefix collided and a broker drops the older session.
- **Modbus health:** health reads the first mapped channel, because a socket or serial port stays open after the device behind it dies.
- **rpi-gpio connect state:** outputs start inactive on connect by default (`on_connect: off`), because an active-low relay left on a low pin is on. `on_connect: keep` is available for files that need it.
- **uvc and rpi-camera:** both are read-only, with `safe_state_support: none`.
- **describe():** implemented for all nine drivers. Every proposed write channel or action is marked `suggested: true`.

## Open issues

- **Hardware plans not run:** a person still has to run every plan in `docs/hardware-tests/`. rpi-camera is the least certain. Its plan lists each assumption the fake makes and the step that checks it.
- **python-rtmidi maintenance:** it is slowing down. mido's other backends work through the `backend` parameter.
- **GPIO pins on exit:** when the hub exits, gpiozero releases the pins and they usually become inputs. An active-low relay without a pull-up can then switch on. No driver can fix this. The docs and the example's `safe_state_note` say to fit a pull resistor.
- **HID output reports:** they are sent whole from a buffer that starts at zero (or the map's `fill`), so fields no channel has written yet go out as zero.
- **rpi-camera example units:** the example reads exposure in `ms` while libcamera reports `us`. This relies on the kernel unit conversion from your update, which isn't on this branch yet. The conformance case uses matching units.
- **Timeout check:** the suite's timeout check passes either way. The driver tests cover timeouts directly.

## Contract change proposals

1. **Allow `*_env` keys in `Connect._no_secrets`.** It rejects `password_env` because the name contains `password`, even though the value is only a variable name. mqtt uses `token_env` for the broker password as a workaround.
2. **Add a push path for stream channels.** For example, an optional `Driver.set_listener(callback)` that the hub calls when it registers a device. Today pushed values only reach clients when someone reads.
3. **Mark suspect readings in one place.** `Kernel.note_reading` or `Hub._record` could do it, and drivers could drop their copies.
4. **Accept convertible units in the conformance read check.** `read_every_channel` requires the channel's exact unit or `None`. Now that the kernel converts units, a driver that reports the device's own unit fails conformance.
5. **Add a `restore_connection` hook to `ConformanceCase`.** It would run after the health check, so cases can test a real outage instead of breaking and repairing the link in one step.
6. **Add a shared `openhal/drivers/common.py`.** It would hold the duration parameter type, the range check, map-error formatting, and the JSON path and template helpers mqtt currently imports from `http.values`.
7. **Per-driver install hints.** The registry's error message tells users to install `openhal-hub[<name>]`, which is wrong for rpi-camera (apt only). An optional install field in `catalog.json` or `DriverInfo` would fix that.
8. **Reject duplicate YAML keys in device files.** The loader currently keeps the last value, so a repeated `max` would silently change a limit. I found this while writing tests.

## Orchestrator note

Saved by the orchestrator from the agent's hand-back, because the harness blocks subagents from writing report files. Merged into main. The full suite passed with 964 tests after both driver batches merged.
