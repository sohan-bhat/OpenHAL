# Install

OpenHAL needs Python 3.12 or newer. [uv](https://docs.astral.sh/uv/) is the quickest way to get both.

## From a clone

This is the README's route, which runs the CLI from the checkout and installs nothing else.

```text
git clone https://github.com/sohan-bhat/OpenHAL
cd OpenHAL
uv run openhal demo
```

## As a tool

`uv tool install` and `pipx install` put `openhal` on your PATH in its own environment. OpenHAL isn't on PyPI yet, so install OpenHAL from GitHub.

```text
uv tool install --compile-bytecode git+https://github.com/sohan-bhat/OpenHAL
pipx install git+https://github.com/sohan-bhat/OpenHAL
```

You can also build a wheel in a clone and install that file.

```text
uv build --wheel
uv tool install --compile-bytecode dist/openhal_hub-0.1.0.dev0-py3-none-any.whl
pipx install dist/openhal_hub-0.1.0.dev0-py3-none-any.whl
```

- `--compile-bytecode` makes the first run about twice as fast.
- Driver extras go in brackets, as in `"openhal-hub[esphome,openhal-firmware] @ git+https://github.com/sohan-bhat/OpenHAL"`. Installing again with other extras replaces the ones you had, so list every extra you use. `openhal doctor` lists the drivers whose extras are missing.
- A few dependencies have no Intel Mac wheels in their newest versions, and building those dependencies needs Rust, so on an Intel Mac add `--no-build` to uv, or `--pip-args=--only-binary=:all:` to pipx.

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

`openhal init --yes` takes the safe defaults without prompting. With `--yes`, init scans for devices, adds every device read-only, makes a read token and adds OpenHAL to every MCP client init finds, naming each backup. The service installs only with `--service`.

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
