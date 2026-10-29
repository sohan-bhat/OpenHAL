# Command line reference

`openhal` talks to the hub's local API, so every command except `init`, `file` and `doctor`'s local checks needs a running hub (`openhald`). The CLI makes no safety decisions, because the hub's kernel checks every command.

## Global options

| Option | Meaning |
|---|---|
| `--url URL` | Hub address. Also `OPENHAL_URL`. Default from `api.host` and `api.port` in `config.yaml`, then `http://127.0.0.1:7420` |
| `--token-file PATH` | Read the token from this file |
| `--version` | Print the version |

The CLI looks for the token in `--token-file`, then `OPENHAL_TOKEN`, then `$OPENHAL_HOME/human.token` (default `~/.openhal/human.token`), and `OPENHAL_HOME` moves the whole config folder.

Most commands take `--json` and then print JSON on stdout instead of tables.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Blocked, refused or failed. The message says which rule and what to do |
| 2 | Usage error, for example a target that is not `device.channel` |
| 3 | The hub is not running |
| 4 | Token problem, missing or not accepted |

## Commands that need a person

`unlock`, `confirm approve`, `routine enable`, `routine run`, `routine approve`, `writer interview`, `writer finish` and `file confirm` need the human token. With `confirm.require_tty: true` (the default) these commands also need an interactive terminal and a typed phrase. Because the CLI reads the phrase from the terminal itself rather than standard input, a script or an agent that runs shell commands as you can't pipe the phrase in. `--phrase` passes the phrase on the command line and is accepted only when `confirm.require_tty` is false.

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

`openhal init` creates the config folder (mode 0700), `config.yaml` with the defaults, the human token in `human.token` (mode 0600) and `devices/plant-waterer.hal.yaml`, the simulated plant waterer from `examples/plant-waterer/mock/`. Because confirming limits takes a person, the sample loads read-only until you confirm its limits with `openhal file confirm`. Running `init` again keeps a working token, and `--new-token` creates a new token.

### openhal doctor

```
openhal doctor
```

`openhal doctor` checks the config folder and file permissions, `config.yaml`, whether the hub responds, whether the token is accepted and what kind of token it is, devices that failed to load, the stop lock, the Python packages the hub and MCP server need, and every driver and its optional dependencies. Each problem comes with the fix, and the command exits 1 if any check failed.

### openhal mcp

```
openhal mcp [--token-file PATH] [--no-start]
```

`openhal mcp` runs the stdio MCP server for AI clients, which docs/interfaces/MCP.md describes.

### openhal pair

```
openhal pair
```

`openhal pair` needs the human token and prints a six digit code that pairs a browser with the dashboard as you. The code works once and expires after 5 minutes.

### openhal token

```
openhal token create --name NAME [--agent | --human] [--scope read|control_low|control_medium]
openhal token list [--all]
openhal token revoke TOKEN_ID
```

`create` prints the token once, on the last line, so `| tail -1` captures the token, and the hub keeps only a hash of the token. Agent tokens default to the `read` scope, but human tokens always have full scope. `list` shows ids, names, kinds and scopes and never the tokens, and `revoke` takes effect on the next request.

These commands use the hub's token routes, and when the hub is not running or has no token routes yet, the commands work on `hub.db` in the config folder directly, which only the folder's owner can open.

## The hub and devices

### openhal status

```
openhal status [--json]
```

`openhal status` shows the hub's version and address, the specification version it speaks, such as v0.1, who you are, connected devices, pending confirmations, the stop lock and device files that failed to load.

### openhal devices

```
openhal devices [DEVICE] [--json]
```

`openhal devices` lists devices with driver, hazard class, mode (`writable` or `read-only`) and connection state. With a device id, the command shows every read channel, every write channel with its limits, max change per second and confirmation tier, every action, the interlocks and the notes.

### openhal discover

```
openhal discover [--driver NAME ...] [--json]
```

`openhal discover` looks for devices with probes that send only read-only identify commands, and prints matches against the device library, unknown devices with the command to start the driver writer, and per-driver errors.

### openhal read

```
openhal read DEVICE.CHANNEL [DEVICE.CHANNEL ...] [--json]
```

`openhal read` reads the channels now and exits 1 if any read failed.

### openhal write

```
openhal write DEVICE.CHANNEL VALUE... [--json]
```

`openhal write` sends a request to set a channel, and the kernel checks the request. The value words are joined, so `60 %` and `"60 %"` are the same. The CLI splits the number from its unit before sending, so the hub receives `"value": 60, "unit": "%"` ([ADR 0016](../adr/0016-one-value-format.md)), and `--json` prints values the same way. Numbers need a unit, and the hub converts compatible units (`85 degF` against a degC channel). Bool channels take true, false, on, off, yes, no, 1 or 0. The command prints the decision, and a blocked command prints its code and message and exits 1. Because the plant waterer's pump runs only through `water`, the plant waterer has no write channels.

```
$ openhal write plant-waterer.pump on
blocked unknown_target  Blocked. plant-waterer has no write channel 'pump'. Write channels are none.
```

### openhal action

```
openhal action DEVICE.ACTION [KEY=VALUE ...] [--json]
```

`openhal action` runs an action, and arguments with units are typed as `duration=20s` or `"duration=20 s"`.

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

`openhal dry-run` checks commands against the current state without running the commands. A plan file is a YAML or JSON list of commands, evaluated in order as if the earlier ones had run.

```yaml file=plan.yaml
- { device: plant-waterer, action: water, args: { duration: 120 s } }
- { device: plant-waterer, action: water, args: { duration: 20 s } }
```

```
$ openhal dry-run --file plan.yaml
1. blocked above_max  Blocked. The duration limit is 30 s (max). Asked for 120 s.
2. allowed  Allowed.
```

`openhal dry-run` exits 1 if any command would be blocked.

### openhal stop

```
openhal stop [--reason TEXT] [--json]
```

`openhal stop` sets the stop lock, cancels pending confirmations, pauses routines and puts every device in its safe state, then prints the result per device (safe, partial, failed, pending or no_safe_state). Any principal may stop, and the command exits 1 if a device did not reach its safe state.

### openhal unlock

```
openhal unlock [--phrase unlock]
```

`openhal unlock` lifts the stop lock after a stop and needs the human token and the typed phrase.

## Confirmations

```
openhal confirm list [--all] [--json]
openhal confirm show REQUEST_ID [--json]
openhal confirm approve REQUEST_ID [--phrase approve]
openhal confirm reject REQUEST_ID [--reason TEXT]
```

Commands that need a person wait in the confirmation queue. `show` and `approve` print the command, who asked and the dry run at the time of asking. Approval makes the kernel check the command again against the current state, so a request that the current state would block is blocked instead of run. Rejecting needs the human token and no phrase.

## Audit log

```
openhal log [--device ID] [--status STATUS] [--event EVENT] [--since SEQ] [--limit N] [--json]
openhal log --verify
```

`openhal log` shows entries newest first, and `--verify` checks the hash chain and exits 1 if the chain is broken.

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

`new` stores a routine, always disabled, and the kind comes from the file suffix unless `--kind` sets the kind. `enable` prints the routine and its dry run first, and refuses if the dry run does not pass. `run` runs the routine once now. `approve` signs an approval that lets this exact routine content drive a high hazard device, so any change to the routine voids the approval.

A YAML routine looks like the one below, which checks the soil every hour and waters for 20 s when the soil is dry.

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

`start` begins a session for an unknown device, and a draft comes from your MCP client (`propose_device_file`) or from `propose`, with every limit in the draft stored as suggested. `interview` shows each limit question with the suggested value and the reason, reads your answer, and gives a bare number the question's unit. `finish` saves the device file into the devices folder, and `plan` shows the staged test plan, smallest safe values first.

## Drivers

```
openhal driver list [--json]
openhal driver test NAME
openhal driver new NAME [--title TEXT] [--root PATH]
```

`list` shows every driver with its protocols, hazard default, conformance level and status. `test` runs the conformance suite at the driver's declared level and exits 1 on any failure. `new` scaffolds an experimental `x-NAME` driver with a simulator, conformance case, tests and docs in an OpenHAL checkout, and never overwrites a file. [The driver guide](../drivers/WRITING-A-DRIVER.md) has the tutorial.

## Device files

```
openhal file validate PATH ... [--json]
openhal file schema
openhal file confirm PATH [--by NAME] [--phrase confirm]
```

`validate` checks files against the spec, and `schema` prints the JSON Schema. `confirm` prints every limit in a file, then adds a top-level `confirmed` with your name, the date and the hash of the limits, so any later change to a limit makes the file read-only again. `confirm` refuses while any entry is still marked `suggested: true`, and `openhald` loads the change after a restart.

## Device library

```
openhal library list [--driver NAME] [--json]
openhal library show NAME [--json]
openhal library add NAME
```

`list` shows every starter device file in the library with its driver, hazard class and what it can change. `show` prints what a file matches, every suggested limit in the file and the file itself, and `--json` gives the limits in the shape `hal/devices/describe` uses. `add` copies a file into the devices folder unchanged, never adds a confirmation, and refuses to overwrite a file or to add a second file for a device id the folder already has. A name is the file name without `.hal.yaml`, such as `rigol-dp832`. When `discover` matches a library file, it prints the `add` command to run. docs/guide/library.md explains how matching and confirmation work.

## Install and background service

### openhal init, the wizard

```
openhal init [--yes] [--discover | --no-discover] [--driver NAME ...] [--device DRIVER=ADDRESS ...]
             [--agent-scope read|control_low|control_medium] [--client NAME ...] [--service | --no-service]
             [--new-token] [--no-sample]
```

In an interactive terminal, `init` sets up the config folder, the human token and the sample as above, then prompts you to choose whether to look for devices, which found devices to add, the scope of a token for your AI client, which client config to save and whether to install the background service. With `--yes`, `init` takes the safe defaults without prompting. A run that can't prompt and has no `--yes`, such as a script, stops after the sample.

| Step | Asked in a terminal | With `--yes` |
|---|---|---|
| Look for devices | yes, default yes | yes, unless `--no-discover` |
| Add each device found | yes, default yes | yes |
| Agent token in `agent.token` | scope, default `read` | `read`, or `--agent-scope` |
| Print the MCP client setup | always, once there is an agent token | always |
| Save a client config | which one, default none | only `--client` |
| Install the background service | yes or no, default no | only `--service` |

Found devices are saved as read-only device files, where a library match is copied with the address discovery found and an `openhal-firmware` board or an ESPHome node describes itself with read-only commands. Every limit is marked `suggested: true` and every confirmation is dropped, so a person confirms the file before anything can change. A device that already has a file is left out, `--driver` limits discovery to some drivers, and `--device` adds a self-describing device at a known address, such as `openhal-firmware=/dev/ttyACM0`.

`init` keeps the agent token while the token works and has the requested scope. The client setup for Claude Desktop, Claude Code and Cursor starts `openhal mcp --token-file ~/.openhal/agent.token` with the full path to `openhal`. `--client claude-desktop`, `claude-code` or `cursor` saves that client's config file. An existing file is copied to `NAME.openhal-backup-DATE` first and keeps every other entry and its mode. A file that isn't valid JSON is left as it is, and `init` exits 1 if a step you asked for failed.

### openhal service

```
openhal service install [--dry-run]
openhal service uninstall [--dry-run]
openhal service restart [--dry-run]
openhal service status
openhal service print [--platform macos|linux]
```

`openhal service` runs the hub in the background as you, never as root, with the Python and config folder of this install, and the hub still listens on loopback only.

| | macOS | Linux |
|---|---|---|
| File | `~/Library/LaunchAgents/org.openhal.hub.plist` | `~/.config/systemd/user/openhald.service` |
| Install | `launchctl bootstrap gui/UID` | `systemctl --user enable` and `restart` |
| Restart | `launchctl kickstart -k` | `systemctl --user restart` |
| Uninstall | `launchctl bootout` | `systemctl --user disable --now` |
| Logs | `~/.openhal/openhald.log` | `journalctl --user -u openhald` |

The service restarts the hub after a crash but not after a clean stop. Because a user unit stops at logout when lingering is off, `install` on Linux reports when lingering is off. `status` exits 1 when the service isn't running, and `--dry-run` prints every file and command and changes nothing. `print` shows the plist or unit, for this machine or the one `--platform` names.
