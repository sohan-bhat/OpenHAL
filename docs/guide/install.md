# Install

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

The installer needs nothing installed first. When uv is missing, the installer puts [uv](https://docs.astral.sh/uv/) 0.13.5 in `~/.local/bin` with Astral's own installer, and uv then installs OpenHAL in an environment of its own with Python 3.12. Every dependency comes as a prebuilt wheel, so nothing needs a compiler. The installer needs no sudo and changes nothing outside uv's own folders, so when `~/.local/bin` isn't on your PATH, the installer prints the line that adds the folder.

- Running the installer again upgrades OpenHAL in place.
- Until the first release on PyPI, the installer installs OpenHAL from the repository's main branch.
- To install one version, set `OPENHAL_VERSION`. Put `OPENHAL_VERSION=0.1.0` right before `sh` in the macOS and Linux command, or run `$env:OPENHAL_VERSION = '0.1.0'` in PowerShell first. The installer takes that version from PyPI, or from the tag `v0.1.0` while PyPI lacks the version.

Then set up your first device and your AI clients with `openhal init`, and start OpenHAL with `openhal start`. [Set up](#set-up) describes each step.

## With uv or pipx

`uv tool install` and `pipx install` put `openhal` on your PATH in an environment of its own. OpenHAL runs on Python 3.12, 3.13, 3.14 and 3.15.

<!-- tools:start -->
OpenHAL isn't on PyPI yet, so uv and pipx install OpenHAL from GitHub, which needs git.

```text
uv tool install git+https://github.com/sohan-bhat/OpenHAL
pipx install git+https://github.com/sohan-bhat/OpenHAL
```
<!-- tools:end -->

You can also build a wheel in a clone and install that file.

```text
uv build --wheel
uv tool install --compile-bytecode dist/halkit-*.whl
pipx install dist/halkit-*.whl
```

- `--compile-bytecode` after `uv tool install` makes the first run about twice as fast.
- Driver extras go in brackets, as in `"halkit[esphome,openhal-firmware] @ git+https://github.com/sohan-bhat/OpenHAL"`. Installing again with other extras replaces the ones you had, so list every extra you use. `openhal doctor` lists the drivers whose extras are missing.
- A few dependencies have no Intel Mac wheels in their newest versions, and building those dependencies needs Rust, so on an Intel Mac add `--no-build` to uv, or `--pip-args=--only-binary=:all:` to pipx. The one-line installers do this for you.

## From a clone

This is the README's route, which needs uv and git and runs the CLI from the checkout.

```text
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```


## Set up

```text
openhal init
```

In a terminal, `openhal init` prompts with a few short questions.

1. Search for devices, using only read-only identify commands.
2. Add each device discovery found. OpenHAL firmware boards and ESPHome nodes send their own descriptions, and library matches come from the device library.
3. Answer each limit of each device now. Enter keeps a suggestion, a typed value replaces the suggestion, and you type `confirm` once at the end, so the device file is saved writable. Say no to keep the file read-only and answer later with `openhal file confirm`.
4. Make a token for your AI client, read-only unless you pick another scope.
5. Add OpenHAL to each MCP client init finds, Claude Code at user scope, Claude Desktop and Cursor, with yes as the default. The setup for every client is printed either way, and a file is backed up before the file changes.
6. Run the hub in the background, starting at login.

`openhal init --yes` takes the safe defaults without prompting. With `--yes`, init scans for devices, adds every device read-only, makes a read token and adds OpenHAL to every MCP client init finds, naming each backup. Add `--no-clients` to set up a home, such as a test home, that leaves your MCP clients as they are. The service installs only with `--service`.

A device that discovery can't find, such as a board on a known port, goes in with `--device`.

```text
openhal init --device openhal-firmware=/dev/ttyACM0
```

## Background service

```text
openhal service install
```

macOS gets a launchd agent in `~/Library/LaunchAgents`, and Linux gets a systemd user unit in `~/.config/systemd/user`. The hub starts now and at every login. `status`, `restart` and `uninstall` act as their names describe, `print` shows the file, and `--dry-run` prints every step and changes nothing.

On Linux the hub stops when you log out, unless lingering is on with `sudo loginctl enable-linger $USER`.

## Raspberry Pi

```text
git clone https://github.com/sohan-bhat/OpenHAL
OpenHAL/scripts/install-pi.sh
```

The script installs uv if it's missing, the system packages the Pi drivers need, and the hub with the rpi-gpio, rpi-camera, pi-i2c-spi, serial and openhal-firmware extras. The script then adds you to the gpio, i2c, spi and dialout groups, turns on lingering, installs the service and prints the next command. Add `--dry-run` to see every command first.

The camera needs Raspberry Pi OS with Python 3.12 or newer, so the hub can import the system's picamera2.

## Next

- [Quickstart](quickstart.md) runs the demo and a hub you control.
- [Connect Claude](tutorials/connect-claude.md) gives an AI client its own token.
