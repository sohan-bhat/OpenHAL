# Command line reference

Every command except `init`, `file` and the local checks of `doctor` needs a running hub. Safety checks run in the hub's kernel.

## Global options

| Option | Meaning |
|---|---|
| `--url URL` | Hub address. Also `OPENHAL_URL`. Default from `api.host` and `api.port` in `config.yaml`, then `http://127.0.0.1:7420` |
| `--token-file PATH` | Token file. Without the option, `OPENHAL_TOKEN`, then `$OPENHAL_HOME/human.token` |
| `OPENHAL_HOME` | The config folder, `~/.openhal` by default |
| `--json` | JSON on stdout, on most commands |
| `--version` | Print the version |

## The next step

A bare `openhal` shows the setup state, connected devices, requests held for a person and the next steps. `openhal --help` lists every command. A bare group shows its main view and one command to copy, built from your own devices and ids, per [ADR 0020](../adr/0020-command-line-interaction-rules.md). `openhal file` shows every device file and the next step, `openhal writer` the unknown devices discovery found, `openhal runs` the runs this token can see, and `openhal service` the service state with exit code 0.

At a terminal, a left-out argument opens a picker of real values. Values for `write`, `dry-run` and action arguments are typed with the limits in view, and an answer out of range is typed again. Person-only pickers need the human token and still take the typed phrase.

Without a terminal, or with `--json`, nothing prompts. The command exits 2 with the missing value, up to 10 valid values and one command to copy.

```
$ openhal limits show
error  openhal limits show needs a device.
  devices  plant-waterer
  run      openhal limits show plant-waterer
```

A mistyped command or id gets the closest real matches.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Blocked or failed. The message names the rule and the next step |
| 2 | Usage error, such as a missing argument without a terminal or a target that is not `device.channel` |
| 3 | The hub is not running |
| 4 | The token is missing or not accepted |

## Commands that need a person

These commands need the human token. With the default `confirm.require_tty: true`, these commands also need a terminal and a typed phrase, read from the terminal itself so no script or agent's shell can pipe the phrase in. `--phrase` works only when `confirm.require_tty` is false.

| Command | Phrase |
|---|---|
| `unlock` | `unlock` |
| `confirm approve` | `approve` |
| `routine enable` | `enable` |
| `routine run` | `run` |
| `routine approve` | `approve` |
| `writer interview` | every answer typed at the terminal, Enter keeps a suggestion |
| `writer finish` | `save` |
| `file confirm` | `confirm` |
| `limits set`, to widen a limit | `confirm` |
| `risk set`, to lower a level | `confirm` |
| `runs caps`, to raise a cap | `confirm` |

Where no phrase can be typed, a wider limit or a lower level becomes a pending change for `confirm approve`.

## Setup

### openhal init

```
openhal init [--new-token] [--no-sample]
```

Creates the config folder with mode 0700, `config.yaml`, `human.token` with mode 0600 and `devices/plant-waterer.hal.yaml`, a simulated sample whose channels are medium [risk](#risk). A rerun keeps a working token unless `--new-token` is given. At a terminal, init runs the limits interview for each added device with high risk channels or actions.

### openhal doctor

```
openhal doctor
```

Checks the config folder and permissions, `config.yaml`, the hub, the token and its kind, device files that failed to load, the stop lock, Python packages and driver dependencies. Prints a fix for each problem and exits 1 on any failure.

### openhal mcp

```
openhal mcp [--token-file PATH] [--no-start]
```

Runs the stdio MCP server, as [MCP server](MCP.md) describes.

### openhal pair

```
openhal pair
```

Needs the human token. Prints a six digit code that pairs a browser with the dashboard as you, once, within 5 minutes.

### openhal token

```
openhal token create --name NAME [--agent | --human] [--scope read|control_low|control_medium]
openhal token list [--all]
openhal token revoke [TOKEN_ID]
```

`create` prints the token once, on the last line, so `| tail -1` captures the token. The hub stores only a hash. Agent tokens default to `read`, and human tokens have full scope. `list` never shows tokens, and `revoke` applies from the next request. Without a running hub, these commands use the owner-only `hub.db` in the config folder.

## The hub and devices

### openhal start

```
openhal start [--host HOST] [--port PORT] [--verbose]
```

Runs the hub in the foreground on `api.host` and `api.port`, `127.0.0.1:7420` by default. A second `openhal start` on the same config folder exits with an error.

### openhal status

```
openhal status [--json]
```

Shows the hub's version, address and spec version, who you are, devices, pending confirmations, the stop lock and device files that failed to load.

### openhal devices

```
openhal devices [DEVICE] [--json]
```

Lists devices with driver, hazard class, mode and connection state. With a device id, shows channels with limits, max change and confirmation tier, actions, interlocks and notes.

### openhal discover

```
openhal discover [--driver NAME ...] [--json]
```

Scans with read-only identify commands and prints library matches, unknown devices with the driver writer command, and per-driver errors.

### openhal read

```
openhal read [DEVICE.CHANNEL ...] [--json]
```

Exits 1 if any read failed. A device id with no channel opens a picker of the device's channels.

### openhal write

```
openhal write [DEVICE.CHANNEL] [VALUE...] [--json]
```

Requests a channel change. Value words are joined, so `60 %` equals `"60 %"`, and the hub receives the number and unit apart per [ADR 0016](../adr/0016-one-value-format.md). Numbers need a unit, and compatible units such as `85 degF` on a degC channel convert. Bool channels take true, false, on, off, yes, no, 1 or 0. A blocked command exits 1. The plant waterer has no write channels, since the pump runs only through `water`.

```
$ openhal write plant-waterer.pump on
blocked unknown_target  Blocked. plant-waterer has no write channel 'pump'. Write channels are none.
```

### openhal action

```
openhal action [DEVICE.ACTION] [KEY=VALUE ...] [--json]
```

Arguments with units are typed as `duration=20s` or `"duration=20 s"`.

```
$ openhal action plant-waterer.water duration=120s
blocked above_max  Blocked. The duration limit is 30 s (max). Requested 120 s.
$ openhal action plant-waterer.water duration=20s
done  Done. water ran.
```

### openhal dry-run

```
openhal dry-run DEVICE.CHANNEL VALUE...
openhal dry-run DEVICE.ACTION [KEY=VALUE ...]
openhal dry-run --file plan.yaml
```

Checks commands without running the commands. A plan file is a YAML or JSON list of commands, checked in order as if each earlier one ran. Exits 1 if any command would be blocked.

```yaml file=plan.yaml
- { device: plant-waterer, action: water, args: { duration: 120 s } }
- { device: plant-waterer, action: water, args: { duration: 20 s } }
```

```
$ openhal dry-run --file plan.yaml
1. blocked above_max  Blocked. The duration limit is 30 s (max). Requested 120 s.
2. allowed  Allowed.
```

### openhal stop

```
openhal stop [--reason TEXT] [--json]
```

Sets the stop lock, cancels confirmations, pauses routines, applies every safe state and prints each device's result, safe, partial, failed, pending or no_safe_state. Any principal may stop. Exits 1 if a device missed its safe state.

### openhal unlock

```
openhal unlock [--phrase unlock]
```

Lifts the stop lock. Needs the human token and the typed phrase.

## Confirmations

```
openhal confirm list [--all] [--json]
openhal confirm [--json]
openhal confirm show [REQUEST_ID] [--json]
openhal confirm approve [REQUEST_ID] [--phrase approve]
openhal confirm reject [REQUEST_ID] [--reason TEXT]
```

Commands that need a person and pending limit changes are held here. `show` and `approve` print the command, the sender and the dry run at request time. Approval checks the command again against the current state. Rejecting needs the human token and no phrase.

## Audit log

```
openhal log [--device ID] [--status STATUS] [--event EVENT] [--since SEQ] [--limit N] [--json]
openhal log --verify
```

Newest first. `--verify` checks the hash chain and exits 1 if the chain is broken.

## Routines

```
openhal routine list [--json]
openhal routine show [ID] [--json]
openhal routine new ID --file PATH [--kind yaml|python]
openhal routine dry-run [ID] [--json]
openhal routine enable [ID] [--phrase enable]
openhal routine disable [ID]
openhal routine run [ID] [--phrase run]
openhal routine delete [ID] [--yes]
openhal routine approve [ID] [--device DEVICE] [--phrase approve]
```

`new` stores a routine disabled, with the kind from the file suffix or `--kind`. `enable` shows the routine and its dry run, and exits 1 without enabling if the dry run fails. `approve` signs this exact routine content for a high hazard device, so any change voids the approval.

This routine waters for 20 s when the soil is dry, checking every hour.

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

`start` opens a session for an unknown device. A draft comes from your MCP client's `propose_device_file` or from `propose`, with every limit stored as suggested. `interview` shows each limit question with a suggested value and the reason, and a bare number takes the question's unit. `finish` saves the device file. `plan` shows the staged test plan, smallest safe values first.

## Drivers

```
openhal driver list [--json]
openhal driver test [NAME]
openhal driver new NAME [--title TEXT] [--root PATH]
```

`test` runs the conformance suite at the driver's declared level and exits 1 on any failure. `new` scaffolds an experimental `x-NAME` driver with a simulator, conformance case, tests and docs in an OpenHAL checkout, and never overwrites a file. [The driver guide](../drivers/WRITING-A-DRIVER.md) has the tutorial.

## Device files

```
openhal file validate [PATH ...] [--json]
openhal file schema
openhal file confirm [PATH] [--by NAME] [--phrase confirm]
```

`validate` checks the given files, or the devices folder. `confirm` with no path opens a picker, read-only files first. On a file with suggested limits, `confirm` runs the limits interview for high risk channels and actions, with each suggestion as the default and values past the device's range typed again. `confirm` then adds a top-level `confirmed` with your name, the date and the hash of the limits, so any later limit change makes high risk entries read-only again. A running hub loads the confirmed file at once.

## Limits

```
openhal limits [--json]
openhal limits show [DEVICE[.CHANNEL]] [--json]
openhal limits set [DEVICE[.CHANNEL]] [--min VALUE] [--max VALUE] [--rate VALUE|none] [--phrase confirm]
```

A bare `openhal limits` prints every device's limits. `show` adds the range the device reports. `set` takes values with units, such as `--max "80 %"` or `--rate "5 %/s"`, and never goes past the device's own range.

- A narrower limit applies at once and is saved in the device file, with the confirmation bound again to the hash of the limits.
- A wider limit takes the typed phrase `confirm` at a terminal. From a script, an agent's shell or an agent token, a wider limit becomes a pending change in `openhal confirm list` and the Inspector.
- An agent's narrower limit applies to that agent's session only, as `tighten_limits` does.

A file an earlier interview confirmed keeps its limits, such as a 60 % maximum on an LED. For the full range and no rate cap, run `openhal limits set DEVICE.CHANNEL --max "100 %" --rate none` and type `confirm`.

## Risk

```
openhal risk [--json]
openhal risk show [DEVICE[.NAME]] [--why] [--json]
openhal risk set [DEVICE.NAME] [low|medium|high] [--phrase confirm]
```

Every channel and action has a [risk level](../SAFETY.md#risk-levels). Low and medium targets take commands at once within the device's own range. High ones stay read-only until a person answers their limits with `openhal file confirm`.

A bare `openhal risk` counts each device's targets per level. `show` lists each level, who set the level and whether the target takes commands, and `--why` adds the reasons. `set` raises a level at once. Lowering takes the typed phrase `confirm`, or becomes a pending change from a script or an agent's shell. Agent tokens change no level. Each change goes into the device file with your name and the date, and into the audit log.

## Runs

```
openhal runs list [--json]
openhal runs show [RUN_ID] [--json]
openhal runs cancel [RUN_ID]
openhal runs caps [--max-steps N] [--max-seconds SECONDS] [--per-agent N] [--phrase confirm] [--json]
```

A run is a list of steps sent with `run_steps`, checked as a plan and then run through the kernel one command at a time. The human token sees every run, and other tokens see their own. `cancel` ends a run before its next step.

`caps` shows the run caps and saves new values to `config.yaml` through the hub. `--max-steps` bounds the steps in one run, repeats included. `--max-seconds` bounds a run, a wait or a sample. `--per-agent` bounds how many of those one token has going at once. Changing a cap takes the human token, and raising one takes the typed phrase `confirm`.

## Device library

```
openhal library list [--driver NAME] [--json]
openhal library show [NAME] [--json]
openhal library add [NAME]
```

`show` prints what a file matches, every suggested limit and the file itself, and `--json` gives the limits in the shape `hal/devices/describe` uses. `add` copies a file into the devices folder unchanged and unconfirmed, and never overwrites a file or adds a second file for a device id. A name is the file name without `.hal.yaml`, such as `rigol-dp832`. `discover` prints the `add` command for each library match. [The library guide](../guide/library.md) covers matching and confirmation.

## Install and background service

### openhal init, the wizard

```
openhal init [--yes] [--discover | --no-discover] [--driver NAME ...] [--device DRIVER=ADDRESS ...]
             [--agent-scope read|control_low|control_medium] [--client NAME ...] [--no-clients]
             [--service | --no-service]
             [--new-token] [--no-sample]
```

At a terminal, `init` sets up the config folder, token and sample, then prompts for each step below. `--yes` takes the defaults. Without a terminal or `--yes`, as in a script, init stops after the sample.

| Step | In a terminal | With `--yes` |
|---|---|---|
| Search for devices | yes, default yes | yes, unless `--no-discover` |
| Add each device found | yes, default yes | yes |
| Agent token in `agent.token` | scope, default `read` | `read`, or `--agent-scope` |
| Print the MCP client setup | always, once there is an agent token | always |
| Answer the high risk limits of an added device | yes or no, default yes, only when the device has some | never |
| Add OpenHAL to each MCP client found | yes or no for each, default yes, none with `--no-clients` | every client found, none with `--no-clients` |
| Install the background service | yes or no, default no | only `--service` |

Found devices become device files with every limit marked `suggested: true` and every confirmation dropped. A library match gets the address discovery found, and an `openhal-firmware` board or an ESPHome node supplies its own description over read-only commands. Init prints how many targets sit at each risk level. A device that already has a file is skipped. `--driver` limits discovery to some drivers, and `--device` adds a self-describing device at a known address, such as `openhal-firmware=/dev/ttyACM0`.

Init keeps an agent token that works and has the requested scope. Client setup runs `openhal mcp --token-file ~/.openhal/agent.token` with the full path to `openhal`. Claude Code is found by the `claude` program on PATH and gets `claude mcp add openhal --scope user` after a backup of `~/.claude.json`. Claude Desktop and Cursor are found by their app or config folder. `--client claude-desktop`, `claude-code` or `cursor` adds a client init didn't find. `--no-clients` changes no client and still prints the setup. Each edited config file is first copied to `NAME.openhal-backup-DATE` and keeps its other entries and mode. A file that isn't valid JSON is left alone, and init exits 1 if a requested step failed.

### openhal service

```
openhal service install [--dry-run]
openhal service uninstall [--dry-run]
openhal service restart [--dry-run]
openhal service status
openhal service print [--platform macos|linux]
```

Runs the hub at every login as you, never as root, on loopback only.

| | macOS | Linux |
|---|---|---|
| File | `~/Library/LaunchAgents/org.openhal.hub.plist` | `~/.config/systemd/user/openhal.service` |
| Install | `launchctl bootstrap gui/UID` | `systemctl --user enable` and `restart` |
| Restart | `launchctl kickstart -k` | `systemctl --user restart` |
| Uninstall | `launchctl bootout` | `systemctl --user disable --now` |
| Logs | `~/.openhal/openhal.log` | `journalctl --user -u openhal` |

The service restarts the hub only after a crash. On Linux, `install` reports when lingering is off, since a user unit then stops at logout. `status` exits 1 when the service isn't running. `--dry-run` changes nothing and prints every file and command. `print` shows the plist or unit for this machine or for `--platform`.
