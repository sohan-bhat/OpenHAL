# Command line reference

`openhal` talks to the hub's local API, so every command except `init`, `file` and `doctor`'s local checks needs a running hub (`openhald`). It makes no safety decisions. The hub's kernel decides every command.

## Global options

| Option | Meaning |
|---|---|
| `--url URL` | Hub address. Also `OPENHAL_URL`. Default from `api.host` and `api.port` in `config.yaml`, then `http://127.0.0.1:7420` |
| `--token-file PATH` | Read the token from this file |
| `--version` | Print the version |

The token is looked up in this order. `--token-file`, then `OPENHAL_TOKEN`, then `$OPENHAL_HOME/human.token` (default `~/.openhal/human.token`). `OPENHAL_HOME` moves the whole config folder.

Most commands take `--json` and then print JSON on stdout instead of tables.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Blocked, refused or failed. The message says which rule and what to do |
| 2 | Usage error, for example a target that is not `device.channel` |
| 3 | The hub is not running |
| 4 | Token problem, missing or not accepted |

## Commands only a person may run

`unlock`, `confirm approve`, `routine enable`, `routine run`, `routine approve`, `writer interview`, `writer finish` and `file confirm` need the human token. With `confirm.require_tty: true` (the default) they also need an interactive terminal and a typed phrase, read from the terminal itself rather than standard input. A script or an agent that runs shell commands as you can't pipe the phrase in. `--phrase` passes the phrase on the command line, and is accepted only when `confirm.require_tty` is false.

| Command | Phrase |
|---|---|
| `unlock` | `unlock` |
| `confirm approve` | `approve` |
| `routine enable` | `enable` |
| `routine run` | `run` |
| `routine approve` | `approve` |
| `writer finish` | `save` |
| `file confirm` | `confirm` |

`writer interview` reads every answer from the terminal.

## Setup

### openhal init

```
openhal init [--new-token] [--no-sample]
```

Creates the config folder (mode 0700), `config.yaml` with the defaults, the human token in `human.token` (mode 0600) and `devices/plant-waterer.hal.yaml`, the simulated plant waterer from `examples/plant-waterer/mock/`. The sample loads read-only until you confirm its limits with `openhal file confirm`, because only a person may confirm limits. Running `init` again keeps a working token. `--new-token` creates a new one.

### openhal doctor

```
openhal doctor
```

Checks the config folder and file permissions, `config.yaml`, whether the hub answers, whether the token is accepted and what kind it is, devices that failed to load, the stop lock, the Python packages the hub and MCP server need, and every driver and its optional dependencies. Each problem comes with the fix. Exits 1 if anything failed.

### openhal mcp

```
openhal mcp [--token-file PATH] [--no-start]
```

Runs the stdio MCP server for AI clients. See docs/interfaces/MCP.md.

### openhal pair

```
openhal pair
```

Prints a six digit code that pairs a browser with the dashboard as you. It works once and expires after 5 minutes. Needs the human token.

### openhal token

```
openhal token create --name NAME [--agent | --human] [--scope read|control_low|control_medium]
openhal token list [--all]
openhal token revoke TOKEN_ID
```

`create` prints the token once, on the last line, so `| tail -1` captures it. The hub keeps only a hash. Agent tokens default to the `read` scope. Human tokens always have full scope. `list` shows ids, names, kinds and scopes, never the tokens. `revoke` takes effect on the next request.

These commands use the hub's token routes. When the hub is not running, or has no token routes yet, they work on `hub.db` in the config folder directly, which only the folder's owner can open.

## The hub and devices

### openhal status

```
openhal status [--json]
```

Hub version and address, who you are, connected devices, pending confirmations, the stop lock and device files that failed to load.

### openhal devices

```
openhal devices [DEVICE] [--json]
```

Lists devices with driver, hazard class, mode (`writable` or `read-only`) and connection state. With a device id, shows every read channel, every write channel with its limits, max change per second and confirmation tier, every action, the interlocks and the notes.

### openhal discover

```
openhal discover [--driver NAME ...] [--json]
```

Looks for devices. Probing sends only read-only identify commands. Prints matches against the device library, unknown devices with the command to start the driver writer, and per-driver errors.

### openhal read

```
openhal read DEVICE.CHANNEL [DEVICE.CHANNEL ...] [--json]
```

Reads channels now. Exits 1 if any read failed.

### openhal write

```
openhal write DEVICE.CHANNEL VALUE... [--json]
```

Asks the kernel to set a channel. The value words are joined, so `60 %` and `"60 %"` are the same. The CLI splits the number from its unit before sending, so the hub receives `"value": 60, "unit": "%"` ([ADR 0016](../adr/0016-one-value-format.md)), and `--json` prints values the same way. Numbers need a unit, and the hub converts compatible units (`85 degF` against a degC channel). Bool channels take true, false, on, off, yes, no, 1 or 0. Prints the decision. A blocked command prints its code and message and exits 1. The plant waterer has no write channels, because its pump runs only through `water`.

```
$ openhal write plant-waterer.pump on
blocked unknown_target  Blocked. plant-waterer has no write channel 'pump'. Write channels are none.
```

### openhal action

```
openhal action DEVICE.ACTION [KEY=VALUE ...] [--json]
```

Runs an action. Arguments with units are typed as `duration=20s` or `"duration=20 s"`.

```
$ openhal action plant-waterer.water duration=120s
blocked above_max  Blocked. The duration limit is 30 s (max). Asked for 120 s.
$ openhal action plant-waterer.water duration=20s
done  Done. water ran.
```

### openhal dry-run

```
openhal dry-run DEVICE.CHANNEL VALUE...
openhal dry-run DEVICE.ACTION [KEY=VALUE ...]
openhal dry-run --file plan.yaml
```

Checks commands against the current state without running them. A plan file is a YAML or JSON list of commands, evaluated in order as if the earlier ones had run.

```yaml file=plan.yaml
- { device: plant-waterer, action: water, args: { duration: 120 s } }
- { device: plant-waterer, action: water, args: { duration: 20 s } }
```

```
$ openhal dry-run --file plan.yaml
1. blocked above_max  Blocked. The duration limit is 30 s (max). Asked for 120 s.
2. allowed  Allowed.
```

Exits 1 if any command would be blocked.

### openhal stop

```
openhal stop [--reason TEXT] [--json]
```

Sets the stop lock, cancels pending confirmations, pauses routines and puts every device in its safe state. Prints the result per device (safe, partial, failed, pending or no_safe_state). Any principal may stop. Exits 1 if a device did not reach its safe state.

### openhal unlock

```
openhal unlock [--phrase unlock]
```

Lifts the stop lock after a stop. Needs the human token and the typed phrase.

## Confirmations

```
openhal confirm list [--all] [--json]
openhal confirm show REQUEST_ID [--json]
openhal confirm approve REQUEST_ID [--phrase approve]
openhal confirm reject REQUEST_ID [--reason TEXT]
```

Commands that need a person wait in the confirmation queue. `show` and `approve` print the command, who asked and the dry run at the time of asking. Approval makes the kernel check the command again against the current state, so a request that would now be blocked is blocked, not run. Rejecting needs the human token and no phrase.

## Audit log

```
openhal log [--device ID] [--status STATUS] [--event EVENT] [--since SEQ] [--limit N] [--json]
openhal log --verify
```

Shows entries newest first. `--verify` checks the hash chain and exits 1 if it is broken.

## Routines

```
openhal routine list [--json]
openhal routine show ID [--json]
openhal routine new ID --file PATH [--kind yaml|python]
openhal routine dry-run ID [--json]
openhal routine enable ID [--phrase enable]
openhal routine disable ID
openhal routine run ID [--phrase run]
openhal routine delete ID [--yes]
openhal routine approve ID --device DEVICE [--phrase approve]
```

`new` stores a routine, always disabled. The kind comes from the file suffix unless given. `enable` prints the routine and its dry run first, and refuses if the dry run does not pass. `run` runs it once now. `approve` signs an approval that lets this exact routine content drive a high hazard device. Any change to the routine voids it.

A YAML routine looks like this. It checks the soil every hour and waters for 20 s when it is dry.

```yaml
id: morning-water
triggers:
  - every: 1 h
steps:
  - if: "plant-waterer.soil_moisture < 35 %"
    then:
      - action: { device: plant-waterer, action: water, args: { duration: 20 s } }
```

## Driver writer

```
openhal writer start [--unknown ID] [--driver NAME] [--param KEY=VALUE ...] [--sketch PATH] [--manual PATH]
openhal writer show SESSION_ID [--json]
openhal writer propose SESSION_ID --file draft.hal.yaml
openhal writer interview SESSION_ID
openhal writer finish SESSION_ID [--save-as NAME] [--phrase save]
openhal writer plan SESSION_ID [--json]
```

`start` begins a session for a device OpenHAL doesn't know. A draft comes from your MCP client (`propose_device_file`) or from `propose`. Every limit in a draft is stored as suggested. `interview` asks you each limit question with the suggested value and the reason, and a bare number gets the question's unit. `finish` saves the device file into the devices folder. `plan` shows the staged test plan, smallest safe values first.

## Drivers

```
openhal driver list [--json]
openhal driver test NAME
openhal driver new NAME [--title TEXT] [--root PATH]
```

`list` shows every driver with its protocols, hazard default, conformance level and status. `test` runs the conformance suite at the driver's declared level and exits 1 on any failure. `new` scaffolds an experimental `x-NAME` driver with a simulator, conformance case, tests and docs in an OpenHAL checkout, and never overwrites a file. The tutorial is in docs/drivers/WRITING-A-DRIVER.md.

## Device files

```
openhal file validate PATH ... [--json]
openhal file schema
openhal file confirm PATH [--by NAME] [--phrase confirm]
```

`validate` checks files against the spec. `schema` prints the JSON Schema. `confirm` prints every limit in a file, then adds a top-level `confirmed` with your name, the date and the hash of the limits. Any later change to a limit makes the file read-only again. It refuses while any entry is still marked `suggested: true`. Restart `openhald` to load the change.
