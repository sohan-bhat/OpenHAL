## Drivers batch 1: report

All eight drivers (serial, firmata, scpi, moonraker, octoprint, marlin, homeassistant, esphome) are built, tested against simulators and pass conformance. Nothing was sent to real hardware.

The brief asked for this report at `docs/agents/REPORT-drivers-1.md`, but the harness blocked writing that file. The full report is below, ready to save there.

**Branch:** `worktree-agent-a477415b4ee0ceb96`. 39 commits on top of `ef189a6`, 88 files, about 13.6k lines added. The tree is clean. Nothing was pushed. Commits use the global identity with no trailers.

**Checks:** `uv run pytest` passes (510 tests). `ruff check`, `ruff format` and `mypy openhal` are clean. I ran the driver tests and conformance three times in a row with no flakes. Driver coverage is 93% overall.

### Conformance and tests per driver

Every driver passed 12 of 12 conformance checks with none skipped. Each case breaks the connection and makes the device slow, and the slow hook forces the next read to the transport, so the timeout check really tests something.

| Driver | Tests | Coverage | Simulator |
|---|---|---|---|
| serial | 42 | 96% | simulated pyserial port, plus a real pty opened by pyserial |
| firmata | 36 | 94% | StandardFirmata board model on the simulated port and a pty |
| scpi | 39 | 95% | TCP SCPI bench supply through real PyVISA/pyvisa-py, plus a pyvisa-sim multimeter |
| moonraker | 31 | 93% | Klipper model behind an httpx mock transport and a real local WebSocket server |
| octoprint | 27 | 95% | REST model behind an httpx mock transport |
| marlin | 31 | 97% | Marlin host protocol model on the simulated port and a pty |
| homeassistant | 26 | 91% | REST mock transport and a real local WebSocket server |
| esphome | 15 | 89% | native API server on a local socket, driven by the real aioesphomeapi client |

### What was delivered

- **Packages:** each of the eight has `__init__.py` (NAME and ENTRY only), `driver.py`, `simulator.py`, `conformance.py`, `catalog.json` and `examples/`.
- **Extra modules:**
  - `serial/link.py`: async serial link shared by serial, marlin and firmata.
  - `serial/mapping.py`: templates, regex parsing and unit mapping, plus the device unit table shared with homeassistant and esphome.
  - `firmata/protocol.py`: my own Firmata client.
  - `scpi/families.py`: channel proposals built from the `*IDN?` reply.
- **Tests:** `tests/drivers/__init__.py`, one test file per driver, and `tests/drivers/serial/kit.py`, a small helper that sends every write through a real kernel.
- **Docs:** `docs/drivers/<name>.md` and `docs/hardware-tests/<name>.md` for all eight. The test plans go from read-only steps to small safe writes, with exact commands, expected output and a report template.
- **pyproject.toml:** one extra per driver, plus `types-pyserial` and `pyvisa-sim` in the dev group.
- **Examples:** every example validates with `openhal file validate` and loads in its driver. They ship without `confirmed`, so they load read-only until a human confirms the limits. The conformance files use a top-level `confirmed`. The spec examples `rigol-dp832`, `klipper-printer`, `ha-desk-lamp` and `esphome-plant` also load in the new drivers.

### New dependencies (for docs/DEPENDENCIES.md)

| Package | Version | License | Used by |
|---|---|---|---|
| pyserial | 3.5 | BSD-3-Clause | serial, firmata, marlin and scpi extras |
| pyvisa | 1.16.2 | MIT | scpi |
| pyvisa-py | 0.8.1 | MIT | scpi |
| pyusb | 1.3.1 | BSD-3-Clause | scpi (USB-TMC) |
| aioesphomeapi | 46.22.0 | MIT | esphome |
| protobuf | 7.36.2 | BSD-3-Clause | via aioesphomeapi |
| noiseprotocol | 0.3.1 | MIT | via aioesphomeapi |
| chacha20poly1305-reuseable | 0.13.2 | Apache-2.0 OR BSD-3-Clause | via aioesphomeapi |
| cryptography | 48.0.1 | Apache-2.0 OR BSD-3-Clause | via aioesphomeapi |
| aiohappyeyeballs | 2.7.1 | PSF-2.0 | via aioesphomeapi |
| async-interrupt | 1.2.2 | Apache-2.0 | via aioesphomeapi |
| tzlocal | 5.4.5 | MIT | via aioesphomeapi |
| tzdata | 2026.5 | Apache-2.0 | via aioesphomeapi |
| backports-zstd | 1.8.0 | PSF-2.0 | via aioesphomeapi |
| pyvisa-sim | 0.7.1 | MIT | dev only |
| stringparser | 0.7 | BSD-3-Clause | dev only, via pyvisa-sim |
| types-pyserial | 3.5.0.20260712 | Apache-2.0 | dev only |

- httpx 0.28.1, websockets 17.3 and zeroconf 0.151.5 (LGPL-2.1, used unmodified) were already in the hub extra.
- cryptography moved from 50.0.2 to 48.0.1 in the lock because aioesphomeapi holds it back.
- pyserial's last release is from 2020, but it is stable and every alternative wraps it.
- aioesphomeapi is actively maintained.
- I skipped the AGPL Firmata clients (pymata4, pymata-express, telemetrix). pyfirmata2 (MIT) uses its own threads and callbacks, so firmata has its own small client written from the protocol docs.
- No code was copied from any project. Every docs page cites its sources.

### Decisions

- **Safety of commands:**
  - Command templates accept only named placeholders.
  - Any command containing a control character is refused, so a string value can't sneak in a second command.
  - Bool text uses `on`/`off` map keys, because YAML 1.2 turns `true:`/`false:` keys into booleans.
- **Checking writes that devices don't acknowledge:**
  - Firmata: a pin state query after each write.
  - ESPHome: waits for the state update.
  - SCPI: reads `SYST:ERR?`.
  - serial: matches `expect`/`error` patterns.
  - A device that ignores a command fails the write.
- **Values that can't be read back** (Marlin and OctoPrint part fan, serial without `get`): read returns the last value sent, or `None` (unknown) before the first write and after a failed one. This follows your contract update 3.
- **Built-in safe states:**
  - marlin: `M104/M140/M141 S0`.
  - moonraker: `TURN_OFF_HEATERS`.
  - octoprint: all heater targets to 0.
  - M112 and Klipper's emergency stop are sent only when explicitly enabled, because both need a firmware restart.
  - The other five drivers use the device file's safe state.
- **Firmata outputs:** output pins are never configured on connect, because setting a pin to OUTPUT already drives it. The first allowed write configures them.
- **Bridges:**
  - Home Assistant exposes only the entities listed in `entity`/`entities`.
  - ESPHome checks every channel against the device's entity list on connect.
  - `match.scpi_idn`, `match.moonraker`, `match.esphome` and `match.homeassistant` are all checked on connect, so a file can't drive the wrong device.
- **Secrets:** secrets come only from environment variables. OctoPrint uses `token_env`, because the spec rejects parameter names containing `api_key`.
- **describe():** firmata, scpi, moonraker, octoprint, homeassistant and esphome all describe themselves. Every proposed write and action is `suggested: true`, and the tests confirm each proposal loads read-only.

### Contract updates from your mid-task message

- **1 and 2:** conformance files use a top-level `confirmed`, and interlock words resolve to enum values.
- **3:** cached write values are dropped when a write fails, so the kernel's follow-up read never repeats a stale value.
- **4:** drivers raise DriverError with clear messages.
- **5:** drivers convert to the channel unit themselves and report it. The suite in this branch still rejects a unit that differs from the channel's.

### Open issues

- The first `ResourceManager('@py')` in a fresh process can take several seconds. On a cold machine the first SCPI connect could come close to the kernel's 10 s connect timeout.
- The ESPHome simulator is plaintext only, so Noise encryption is tested only as a failure case.
- aioesphomeapi logs a harmless "Timezone resolution failed" warning when a connect is cancelled.
- `stream: true` channels are served from caches, but the hub still has to poll them.
- Moonraker and OctoPrint HTTP are tested against mock transports, not real HTTP servers.
- The hardware test plans use the CLI from BRIEF-interfaces, which is being built in parallel. The read-only steps use a small probe script that works today.

### Contract change proposals

1. **Long actions:** the kernel's 10 s action timeout is shorter than printer homing. Allow an action-level `timeout` in the device file, or a `started` result status.
2. **Unknown readings:** document in WRITING-A-DRIVER.md that `Reading.value=None` means unknown.
3. **Pushed values:** add an optional `Driver.subscribe(callback)` so drivers can push readings into `Kernel.note_reading` and live events.
4. **Async conformance setup:** add an async setup hook to `ConformanceCase`. The esphome case currently runs its simulator on its own event loop in a thread.
5. **Shared helpers:** move `serial/link.py` and `serial/mapping.py`, which six other drivers import, to `openhal/drivers/_common/` and document them.
6. **Identify after connect:** have the suite call `identify()` again after `connect()`, so it covers the real identification command (`*IDN?`, M115, device info).
7. **Timeout check:** document that `make_slow` must make the next read reach the transport. A driver answering from a cache passes the check without touching it.

## Orchestrator note

Saved by the orchestrator from the agent's hand-back, because the harness blocks subagents from writing report files. Merged into main. The full suite passed with 964 tests after both driver batches merged.
