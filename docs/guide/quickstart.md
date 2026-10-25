# Quickstart

This guide goes from a checkout of the repository to an AI client that can read a simulated desk fan and gets blocked when it asks for too much. Nothing in it touches real hardware. It takes about ten minutes.

## Install

OpenHAL needs Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). The package isn't on PyPI yet, so install it from the repository folder.

```sh tested
$ uv tool install ".[hub]"
```

That puts two commands on your path. `openhal` is the command line and `openhald` is the hub.

## Set up the config folder

```sh tested
$ openhal init
config folder  ~/.openhal (mode 0700)
sample device  ~/.openhal/devices/demo-fan.hal.yaml created, read-only until you confirm it
```

`init` creates `~/.openhal` with your settings, a human token that only you can read, and a device file for a simulated fan. The fan runs on the mock driver, so writes change a value in memory and nothing else. Set `OPENHAL_HOME` to keep the folder somewhere else.

## Confirm the limits

A device file loads read-only until a person confirms its limits. Agents can never do this step. The command prints every limit and asks you to type `confirm`.

```sh tested
$ openhal file confirm ~/.openhal/devices/demo-fan.hal.yaml
write   fan_speed  0 % to 100 %, at most 20 %/s
```

The confirmation records your name, the date and a hash of the limits. If anyone changes a limit later, the file is read-only again until a person confirms it.

## Start the hub

```sh tested
$ openhald &
$ openhal status
devices 1 of 1 connected
```

The hub listens on 127.0.0.1 only. Other machines can't reach it unless you turn on `api.allow_lan` and pair them.

## Read and write

```sh tested
$ openhal read demo-fan.temperature
$ openhal dry-run demo-fan.fan_speed 40 %
allowed  Allowed.
$ openhal write demo-fan.fan_speed 30 %
done  Done. fan_speed is now 30 %.
```

A dry run checks a command against the current state without sending it. Now ask for more than the fan allows.

```sh tested
$ openhal write demo-fan.fan_speed 150 %
blocked above_max  Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.
$ openhal write demo-fan.fan_speed 85 degF
blocked bad_unit  fan_speed: 85.0 °F can't be converted to percent.
```

Every block has a stable code and a message that names the rule. Numbers always need a unit. The hub converts units it can, such as `0.5 dimensionless` to 50 %, and refuses the rest.

## Connect an AI client

Each client gets its own agent token. The scope `control_low` lets it drive low hazard devices like this fan. The token is printed once, so save it straight to a file.

```sh tested
$ openhal token create --agent --scope control_low --name claude | tail -1 > ~/.openhal/claude.token
$ chmod 600 ~/.openhal/claude.token
$ claude mcp add openhal --scope user -- openhal mcp --token-file ~/.openhal/claude.token
```

That adds the MCP server to Claude Code. The [MCP guide](../interfaces/MCP.md) has the setup for Claude Desktop, Cursor and other clients. Ask your client to read the fan's temperature, then to set the fan to 150 %. It gets the same block you saw above.

An agent can't approve its own requests, loosen a limit, confirm a device file or lift a stop. Those need you, with the human token, at a terminal or in the dashboard.

## Stop everything

Any client may stop, including an agent. Only a person may lift the stop, by typing the phrase `unlock`.

```sh tested
$ openhal stop
demo-fan  safe
$ openhal write demo-fan.fan_speed 10 %
blocked stopped  Blocked. The hub is stopped. A human must unlock it before anything can move.
$ openhal unlock
```

## Script it in Python

The Python library talks to the same hub with the same checks. A blocked command comes back as a decision, not an exception.

```python tested
from openhal.client import connect

with connect() as hub:
    reading = hub.read("demo-fan", "temperature")
    print(reading.value, reading.unit)
    decision = hub.write("demo-fan", "fan_speed", "150 %")
    print(decision.status, decision.code, decision.message)
```

## Next

- [Concepts](concepts.md) explains device files, the kernel, tokens and hazard classes.
- [Contributing a device file](contributing-a-device-file.md) shows how to describe your own device.
- The [safety model](../SAFETY.md) lists every check in the order the kernel runs them.
