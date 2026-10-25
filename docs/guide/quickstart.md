# Quickstart

This guide runs a [Hub](glossary:hub) with a simulated desk fan and sends it one write that is refused and one that is granted. Nothing in it touches real hardware.

## Run the hub

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```sh tested
$ git clone https://github.com/sohan-bhat/OpenHAL && cd OpenHAL
$ uv run openhal init
config folder  ~/.openhal (mode 0700)
sample device  ~/.openhal/devices/demo-fan.hal.yaml created, read-only until you confirm it
```

`init` creates `~/.openhal` with a human token and a [Device File](glossary:device-file) for a simulated fan. The file is read-only until a person confirms its limits.

```sh tested
$ uv run openhal file confirm ~/.openhal/devices/demo-fan.hal.yaml
write   fan_speed  0 % to 100 %, at most 20 %/s
$ uv run openhald &
$ uv run openhal status
devices 1 of 1 connected
```

The hub listens on `127.0.0.1:7420` only.

## Send two writes

```sh tested
$ uv run openhal write demo-fan.fan_speed 150 %
blocked above_max  Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.
$ uv run openhal write demo-fan.fan_speed 40 %
done  Done. fan_speed is now 40 %.
```

The [Safety Kernel](glossary:safety-kernel) refused the first write before anything reached the device. Over the protocol, the same refusal is `error -32010 LIMIT_EXCEEDED`.

## Stop

Any client may stop. Only a person may lift the stop, by typing the phrase `unlock`.

```sh tested
$ uv run openhal stop
demo-fan  safe
$ uv run openhal unlock
```

## Next

- [Concepts](concepts.md) defines the hub, device files, the kernel and the error codes.
- [Connect Claude](tutorials/connect-claude.md) gives an AI client its own token.
- [Add a device](tutorials/add-a-device.md) describes your own hardware.
