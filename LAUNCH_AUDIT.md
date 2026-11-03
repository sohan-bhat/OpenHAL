# Launch audit for 0.1.0

This audit followed the README and the install guide the way a stranger would, ran every gate, and checked each claim the README, the docs and the website make. It was done on 2026-11-03 on branch `worktree-agent-ac9cf948b036e340d`, rebased onto main at d0134d8, which includes the risk-level merge.

The machine was rendering the launch film the whole time, with load averages from 5 to 25 on 12 cores, so every time below is an upper bound.

## How the audit ran

- **Local clean state.** This environment can't change HOME, so the local runs pointed uv's cache, uv's Python folder, uv's tool folders and `OPENHAL_HOME` at empty folders instead. That gives uv and OpenHAL the same clean start a new machine has. Only uv, git and the system tools were on PATH.
- **Clean runners.** .github/workflows/clean-machine.yml does the same on fresh ubuntu-latest, macos-latest and windows-latest runners with no cache, and writes each step's time to the job summary. The workflow runs on demand and when its own file changes. The workflow hasn't run yet, so start the workflow from Actions after the merge.
- **Not run locally.** `openhal init`, `uv tool install` and the one-line installers write to the real home, and init searches for devices and registers MCP clients. A real ESP8266 and a demo hub on port 7420 are attached to this machine, so those steps ran only in the Clean machine workflow and in CI's installers job.

## README route

| Step | Result | Notes |
|---|---|---|
| `git clone https://github.com/sohan-bhat/OpenHAL` | passed in 8 s | 1,463 files |
| `cd OpenHAL` then `uv run openhal demo` | passed | The demo printed the trace, the audit log and "6 requests, 1 blocked, 1 confirmed by a person." |

What a stranger needs that the README doesn't give, and what is slow:

- **uv picks the newest Python.** The repository pins no Python, so `uv run` downloaded CPython 3.15.1. On 3.15, zeroconf and PyYAML have no wheels yet, so uv built both from source. That works here because this Mac has a compiler. A machine without one may be slower or fail. A `.python-version` file with `3.12` would match CI and the installers. That change was left out, because the file also moves every contributor's venv to 3.12.
- **`uv run` installs the dev tools.** The demo run installed 74 packages, including mypy, ruff, pytest and hypothesis, because `uv run` syncs the dev group. `uv run --no-dev openhal demo` would skip the dev tools.
- **A cold first run takes minutes.** The README run wasn't timed exactly. Similar cold installs here took 4 to 6 minutes, mostly downloads. The Clean machine workflow records exact times on clean runners.
- **The README says to install uv but not how.** The link goes to the uv docs, which have the one-line installer.

## Install guide

- The live site serves install.sh and install.ps1, and CI's installers job runs both from each commit on three systems.
- `uv tool install`, `pipx install`, `openhal init`, `openhal start` and `openhal status` run in the Clean machine workflow on all three systems.
- `uvx halkit demo` and `pipx run halkit demo` need halkit on PyPI. Until then the workflow skips those two steps with a notice.

## Packaging

- **Fixed. The sdist build took more than six minutes.** Hatchling walked the whole repository, the website and the film included. The sdist now takes only the package and what the wheel bundles. The build takes about 9 s, the sdist is 1.0 MB and the wheel 1.3 MB.
- **Added. `halkit` is a second command for the same CLI.** `uvx` and `pipx run` run the command named like the package, so `uvx halkit demo` had no command to run before. `openhal` stays the name every page uses.
- **Proved.** From the built wheel with an empty cache, `uvx --from dist/halkit-0.1.0-py3-none-any.whl halkit demo` passed in 347 s, Python download included. pipx isn't installed here, so pipx ran through uvx with its own home and caches in empty folders, and `pipx run --spec dist/halkit-0.1.0-py3-none-any.whl halkit demo` passed in 306 s.
- **Install matrix.** The wheel and the sdist of 0.1.0, each in a fresh venv with an empty uv cache on macOS (x86_64), ran `openhal --version`, `halkit --version`, `openhal demo` and `openhal driver list`.

| Python | Wheel | sdist |
|---|---|---|
| 3.12.15 | passed | passed |
| 3.13.2 | passed | passed |
| 3.14.9 | passed | passed |
| 3.15.1 | passed | passed |

  CI's new install job does the same on Linux, macOS and Windows for each version. The classifiers and the install guide name 3.12, 3.13, 3.14 and 3.15, and a test keeps the classifiers and the CI matrix the same.

## Tests and gates

- **Hardware guard.** tests/no_hardware.py hides every real device during tests. The guard covers serial listing, `openhal-firmware: auto`, HID, MIDI, Bluetooth, cameras, VISA, CAN, the Pi's GPIO and buses, and the network searches. Opening a real listed serial port fails the test. Tests run with `OPENHAL_HOME` in a temporary folder and `OPENHAL_URL` on a closed port, so no test and no child process reads the real `~/.openhal`, sends its token or reaches the running hub. tests/test_no_hardware.py proves each part.
- **Fixed. Two Playwright tests failed about one run in sixteen.** Radix moves focus for an arrow key in a timer, and a busy browser ran Enter before that timer, so Enter chose the item the list was leaving. A second race lost Tab right after Enter, because Radix keeps focus in a closed select during its 150 ms exit. The fix is in the select and menu components, and 60 repeats of both tests passed.
- **Fixed. A device with no file printed `openhal file confirm None`.**
- **Failing on main, from the risk-level merge.** Eighteen tests fail on pristine main at d0134d8 and on this branch. This branch fixes one, the generated Python API reference. The other 17 belong to the risk-level work, so the lead should send those tests there.
  - tests/library/test_library_files.py, 13 files. The test checks that every library file loads read-only, and files with only low and medium risk entries now load writable.
  - tests/library/test_library_cli.py::test_add_copies_the_file_read_only_and_never_overwrites, for the same reason.
  - tests/inspector/test_harness.py::test_devices_are_the_plant_waterer_and_the_mock_heater_and_lamp checks that the lamp is read-only.
  - tests/website/test_kernel_parity.py. The TypeScript kernel in website/src/lib/kernel has no risk levels yet.
  - tests/website/test_snippets.py for docs/guide/quickstart.md. `openhal init` no longer prints "read-only until you confirm it" for the sample, which is medium risk now.

## Reviews

- **Code review.** Ten findings on this branch. Eight are fixed. Escape and Tab are no longer held by the key queue, a closed list drops its held keys, a select that opens again during its exit drops the last redirect, the container stops on a failed token and keeps setup off the MCP stdin, the MCP server treats an unexpanded `${...}` token as no token, and the hardware guard clears `OPENHAL_FIRMWARE_PORTS` and resolves links. The container's read-only agent token stays on purpose, so the image can list and read the simulated plant waterer but not water the plant.
- **Security review.** No finding reached 8 out of 10. The one note, at 7, was that the listings ran an unpinned `halkit` from PyPI while the name is unclaimed. The listings now pin `halkit==0.1.0`, and the release item says to push the tag soon after merging.

## Claims checked

### Fixed

- docs/guide/faq.md said library files were "described and tested". Every one of the 33 library files is unverified, and the FAQ says so now.
- docs/guide/faq.md said devices with an interface need no firmware "once their drivers land". Those drivers are in.
- docs/drivers/can.md said the CAN driver "works with" SocketCAN and USB adapters. The page now says the driver can use SocketCAN and those adapters and is tested on a simulated bus, not on a real adapter.
- docs/SAFETY-REPORT.md gave the red team suite's size at review time as if current. The report now gives both counts, 100 then and 109 now.
- docs/ROADMAP.md, docs/LAUNCH.md and docs/DESIGN.md said 34 drivers. There are 35 with MuJoCo.

### Kept, and why

- "tested on simulator" for every driver is true. All 35 drivers pass the conformance suite against a simulator, and no hardware report exists in docs/hardware-tests.
- docs/drivers/COVERAGE.md and the catalog give device estimates such as "Thousands of models". The page frames each one as a rough order of magnitude with its reasoning, not as tested support.
- docs/guide/install.md says every dependency comes as a prebuilt wheel. That holds for the one-line installers, which use Python 3.12 and install with `--no-build`.

### For the README rewrite

README.md belongs to the agent rewriting the README, so nothing there changed. Each item below is wrong or missing today.

- The devices table has 34 rows. MuJoCo, the 35th driver, is missing.
- The table's "Hazard default" column and the safety model section describe the access model before risk levels.
- "v0.1, in development" should match the 0.1.0 release.
- "Devices covered" names models such as Voron, Sovol SV08, Hamilton STAR and Bambu X1. Under "Supported devices" these read as tested support, and no driver is tested on hardware.
- "`openhal init` ... prints the setup for Claude Desktop, Claude Code or Cursor". Init also writes those clients' config files after a backup.
- The supported Pythons, 3.12 to 3.15, aren't stated.
- After PyPI, `uvx halkit demo` gives the demo with no clone.
- `claude plugin validate` advises an install line, `/plugin install openhal --marketplace sohan-bhat/OpenHAL`.
- If the MCP Registry is used later, the README needs `<!-- mcp-name: io.github.sohan-bhat/openhal -->`, because PyPI shows the README and the registry checks that line.

### Safety-model wording the risk levels change

The lead rewrites this wording after the risk merge. The merge already changed docs/SAFETY.md, so check each place below against main first.

- **README.md.** The Hazard default column, "A device file stays read-only until a person confirms its limits", "the limits a person confirmed" and "single-use grant".
- **docs/guide.** quickstart.md, the sample is read-only until confirmed. concepts.md, read-only until confirm, scopes, grants, principals and hazard classes. install.md, the init steps and `--yes` read token. faq.md line 21. tutorials/connect-claude.md, the scope table. tutorials/add-a-device.md, create-a-routine.md and build-a-driver.md. conformance.md.
- **docs/interfaces.** MCP.md, CLI.md and PYTHON.md, wherever those pages describe scopes, hazard classes and `agent_enable_low_hazard`.
- **Other docs.** docs/QUICKSTART.md, docs/ARCHITECTURE.md, docs/THREAT_MODEL.md, docs/drivers/WRITING-A-DRIVER.md, the hazard columns in docs/drivers/COVERAGE.md, and docs/hardware-tests/README.md, which is ordered by hazard.
- **spec/GLOSSARY.md.** Grant, Principal with scope, and Confirmation Request.
- **The website.** library/index.astro, library/[slug].astro, drivers/index.astro, drivers/[name].astro ("Hazard default"), inspector.astro, docs/examples/3d-print-watch.astro, blog/why-we-built-openhal.md, index.astro, and the Playground's Playground.tsx, SimulatedDevice.tsx and parts.tsx.
- **Text this branch added or touched.** The MCP server's instructions in openhal/mcp/server.py, which mention "your token's scope and the device hazard class". HUMAN_PRINCIPAL_REFUSED in openhal/mcp/tools.py, which suggests `--scope control_low`. The token scopes in llms-install.md. NEEDS_HUMAN.md item 1, "lowest hazard first".
- **spec/v0.1.** schema.md and schema.json list `verified-on-simulator`, and device-files.md and the code use `tested-reads`. The spec belongs to the risk-level work.

## Still open

- docs/demo/first-steps.txt and first-steps.cast are a recording that shows `OpenHAL 0.1.0.dev0`. No script records the session again.
- The Docker image wasn't built, because Docker isn't installed here. The entrypoint wasn't run outside Docker either, because that run leaves a hub in the background. The Container workflow builds the image and checks that `openhal mcp` in the image lists its tools and answers `list_devices` before any push.
- The Clean machine and TestPyPI workflows haven't run.
