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

The installer needs nothing installed first, no sudo and no compiler. When uv is missing, the installer adds [uv](https://docs.astral.sh/uv/) 0.13.5 to `~/.local/bin`, then installs OpenHAL with Python 3.12. If `~/.local/bin` isn't on your PATH, the installer prints the line to add.

- Running the installer again upgrades OpenHAL in place.
- Until the first PyPI release, the installer uses the main branch.
- To pin a version, put `OPENHAL_VERSION=0.1.0` right before `sh` in the macOS and Linux command, or run `$env:OPENHAL_VERSION = '0.1.0'` in PowerShell first. The version comes from PyPI, or from the tag `v0.1.0` when PyPI lacks the version.

Then run `openhal init` and `openhal start`, as [Set up](#set-up) describes.

## With uv or pipx

`uv tool install` and `pipx install` put `openhal` on your PATH. OpenHAL runs on Python 3.12, 3.13, 3.14 and 3.15.

<!-- tools:start -->
OpenHAL isn't on PyPI yet, so uv and pipx install OpenHAL from GitHub, which needs git.

```text
uv tool install git+https://github.com/sohan-bhat/OpenHAL
pipx install git+https://github.com/sohan-bhat/OpenHAL
```
<!-- tools:end -->

Or build a wheel in a clone and install the wheel.

```text
uv build --wheel
uv tool install --compile-bytecode dist/halkit-*.whl
pipx install dist/halkit-*.whl
```

- `--compile-bytecode` makes the first run about twice as fast.
- Driver extras go in brackets, as in `"halkit[esphome,openhal-firmware] @ git+https://github.com/sohan-bhat/OpenHAL"`. Installing again replaces the old extras, so list every extra. `openhal doctor` lists missing extras.
- On an Intel Mac, add `--no-build` to uv or `--pip-args=--only-binary=:all:` to pipx, because a few dependencies would need Rust. The one-line installers already do this.

## From a clone

A clone needs uv and git.

```text
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```


## Set up

```text
openhal init
```

`openhal init` prompts for each step in a terminal.

1. Search for devices with read-only identify commands.
2. Add each device found, from the device's own description or the device library.
3. Answer each limit, where Enter keeps the suggestion, then type `confirm`. Say no to keep the file read-only for a later `openhal file confirm`.
4. Make a token for your AI client, read-only by default.
5. Add OpenHAL to Claude Code at user scope, Claude Desktop and Cursor when found. Each changed file is backed up first, and the setup for every client is printed.
6. Run the hub in the background at login.

`openhal init --yes` takes the safe defaults, with every device read-only, a read token and every MCP client found. `--no-clients` leaves MCP clients unchanged, and the service installs only with `--service`.

Add a device that discovery misses, such as a board on a known port, with `--device`.

```text
openhal init --device openhal-firmware=/dev/ttyACM0
```

## Background service

```text
openhal service install
```

macOS gets a launchd agent in `~/Library/LaunchAgents` and Linux a systemd user unit in `~/.config/systemd/user`, which start the hub now and at every login. The command also takes `status`, `restart`, `uninstall` and `print`, and `--dry-run` changes nothing.

On Linux the hub stops when you log out, unless lingering is on with `sudo loginctl enable-linger $USER`.

## Raspberry Pi

```text
git clone https://github.com/sohan-bhat/OpenHAL
OpenHAL/scripts/install-pi.sh
```

The script installs uv, the Pi system packages and the hub with the rpi-gpio, rpi-camera, pi-i2c-spi, serial and openhal-firmware extras. The script also adds you to the gpio, i2c, spi and dialout groups, turns on lingering and installs the service. `--dry-run` shows every command first.

The camera needs Raspberry Pi OS with Python 3.12 or newer, for the system's picamera2.

## Next

- [Quickstart](quickstart.md) runs the demo and a hub you control.
- [Connect Claude](tutorials/connect-claude.md) gives an AI client its own token.
