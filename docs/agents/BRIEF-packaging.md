# Brief: packaging (M13)

Read docs/agents/COMMON.md first. Then read README.md, docs/QUICKSTART.md, docs/guide/quickstart.md, openhal/cli/init_cmd.py, openhal/cli/doctor_cmd.py, openhal/hub/daemon.py, openhal/_brand.py, pyproject.toml and the writer flow for self-describing boards (openhal/writer/engine.py, `openhal writer`).

## Goal

Installing OpenHAL and reaching the first agent read takes under 60 seconds for a self-describing device.

1. **Install.** `uv tool install` and `pipx install` both work from a locally built wheel (`uv build`). Never publish anything. Document both in docs/guide/install.md, next to the git clone route in the README.
2. **`openhal init` wizard.** On a terminal it asks a few short questions, and with `--yes` it takes the safe defaults without asking.
   - Create the config folder and the human token, as today.
   - Run discovery and offer to add each self-describing device (openhal-firmware boards, ESPHome) and each library match as a read-only device file. Never confirm limits for the person.
   - Print the MCP client setup for Claude Desktop, Claude Code and Cursor. Write a client's config file only when the person asks, back it up first, and never touch a real config in tests.
   - Offer to install the background service.
3. **Services.** `openhal service install|uninstall|status|print`.
   - macOS writes a launchd agent in ~/Library/LaunchAgents and loads it with launchctl.
   - Linux writes a systemd user unit in ~/.config/systemd/user and enables it.
   - Run every command through one small runner, so tests and `--dry-run` print what would run. Never load, start or enable a real service on this Mac during the run. Tests use a temp HOME and a fake runner.
4. **Raspberry Pi.** scripts/install-pi.sh installs uv if missing, installs the hub with the Pi extras (rpi-gpio, rpi-camera, pi-i2c-spi, serial, openhal-firmware), adds the user to the gpio, i2c, spi and dialout groups, enables the service with lingering, and ends by printing the next command to run. `--dry-run` prints every command and runs none. Check it with `bash -n` and shellcheck if installed. A test runs the dry run. Never run it for real here.
5. **Timing.** scripts/time-first-read builds the wheel, installs it into a fresh temporary environment, runs `openhal init --yes`, starts the hub on loopback with a simulated self-describing board, and does a read through the MCP server as an agent. It prints each step's time. Record two runs in docs/verification/install.md. If a step is slow, fix it.
6. **Fresh install from the README.** Follow only the README's quickstart in a fresh temp folder (clone this repo from its local path instead of GitHub), time it and record it in the same file, along with anything the README got wrong.

## Files you own

openhal/cli/init_cmd.py, openhal/cli/service_cmd.py, openhal/service/, the registration lines in openhal/cli/main.py, scripts/install-pi.sh, scripts/time-first-read, tests/packaging/, tests/cli/ tests for init and service, docs/guide/install.md, docs/verification/install.md, a new section at the end of docs/interfaces/CLI.md, and pyproject.toml only for a new extra if you need one.

## Not yours

README.md and docs/QUICKSTART.md (report needed changes), the hub, kernel, drivers, library/ and everything else. Another agent builds the device library and `openhal library` in parallel, so call the discovery API, not library code that doesn't exist yet.
