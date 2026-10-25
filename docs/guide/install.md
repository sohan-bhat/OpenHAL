# Install

OpenHAL needs Python 3.12 or newer. [uv](https://docs.astral.sh/uv/) is the quickest way to get both.

## From a clone

This is the README's route. It runs the CLI from the checkout and installs nothing else.

```text
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```

## As a tool

`uv tool install` and `pipx install` put `openhal` and `openhald` on your PATH, each in its own environment. OpenHAL isn't on PyPI yet, so install it from GitHub.

```text
uv tool install --compile-bytecode git+https://github.com/sohan-bhat/OpenHAL
pipx install git+https://github.com/sohan-bhat/OpenHAL
```

Or build a wheel in a clone and install that file.

```text
uv build --wheel
uv tool install --compile-bytecode dist/openhal_hub-0.1.0.dev0-py3-none-any.whl
pipx install dist/openhal_hub-0.1.0.dev0-py3-none-any.whl
```

- `--compile-bytecode` makes the first run about twice as fast.
- Driver extras go in brackets, as in `"openhal-hub[esphome,openhal-firmware] @ git+https://github.com/sohan-bhat/OpenHAL"`. Installing again with other extras replaces the ones you had, so list every extra you use. `openhal doctor` lists the drivers whose extras are missing.
- On an Intel Mac, add `--no-build` to uv, or `--pip-args=--only-binary=:all:` to pipx. A few dependencies have no Intel Mac wheels in their newest versions, and building them needs Rust.

## Set up

```text
openhal init
```

In a terminal it asks a few short questions.

1. Look for devices. Discovery sends only read-only identify commands.
2. Add each device it found as a read-only device file. OpenHAL firmware boards and ESPHome nodes describe themselves, and library matches come from the device library. No limit is confirmed for you.
3. Make a token for your AI client. It is read-only unless you pick another scope.
4. Write a client's config for you. The setup for Claude Desktop, Claude Code and Cursor is printed either way, and a file is backed up before it changes.
5. Run the hub in the background, starting at login.

`openhal init --yes` takes the safe defaults without asking. It looks for devices, adds them read-only and makes a read token. It writes a client config only with `--client NAME` and installs the service only with `--service`.

A device that discovery can't see, such as a board on a known port, goes in with `--device`.

```text
openhal init --device openhal-firmware=/dev/ttyACM0
```

## Background service

```text
openhal service install
```

macOS gets a launchd agent in `~/Library/LaunchAgents`, and Linux gets a systemd user unit in `~/.config/systemd/user`. The hub starts now and at every login. `status`, `restart` and `uninstall` do what they say, `print` shows the file, and `--dry-run` prints every step and changes nothing.

On Linux the hub stops when you log out, unless lingering is on with `sudo loginctl enable-linger $USER`.

## Raspberry Pi

```text
git clone https://github.com/sohan-bhat/OpenHAL
OpenHAL/scripts/install-pi.sh
```

The script installs uv if it's missing, the system packages the Pi drivers need, and the hub with the rpi-gpio, rpi-camera, pi-i2c-spi, serial and openhal-firmware extras. It adds you to the gpio, i2c, spi and dialout groups, turns on lingering, installs the service and prints the next command. Add `--dry-run` to see every command first.

The camera needs Raspberry Pi OS with Python 3.12 or newer, so the hub can see the system's picamera2.

## Next

- [Quickstart](quickstart.md) runs the demo and a hub you control.
- [Connect Claude](tutorials/connect-claude.md) gives an AI client its own token.
