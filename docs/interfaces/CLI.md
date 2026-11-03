# Command line reference

`openhal` connects to the hub's local API, so every command except `init`, `file` and `doctor`'s local checks needs OpenHAL running, which `openhal start` does. The CLI runs no safety checks, because the hub's kernel checks every command.

## Global options

| Option | Meaning |
|---|---|
| `--url URL` | Hub address. Also `OPENHAL_URL`. Default from `api.host` and `api.port` in `config.yaml`, then `http://127.0.0.1:7420` |
| `--token-file PATH` | Read the token from this file |
| `--version` | Print the version |

The CLI reads the token from `--token-file`, then `OPENHAL_TOKEN`, then `$OPENHAL_HOME/human.token` (default `~/.openhal/human.token`), and `OPENHAL_HOME` moves the whole config folder.

Most commands take `--json` and then print JSON on stdout instead of tables.

## The next step

A bare `openhal` shows whether the config folder is set up, whether OpenHAL runs, which devices are connected and how many requests are held for a person, and then the next steps for that state. `openhal --help` lists every command. A bare group shows its most useful view and ends with one command to copy, built from your own devices and ids ([ADR 0020](../adr/0020-command-line-interaction-rules.md)).

| Command | Shows |
|---|---|
| `openhal limits` | Every device's limits and one change to copy |
| `openhal confirm` | The pending requests |
| `openhal routine` | The routines |
| `openhal runs` | The runs this token can see |
| `openhal token` | The active tokens |
| `openhal driver` | The drivers |
| `openhal library` | The library's device files |
| `openhal file` | Every device file in the devices folder and the next step |
| `openhal writer` | The unknown devices that discovery found |
| `openhal service` | The state of the background service, with exit code 0 |

In an interactive terminal, a command that leaves out a device, a channel, a request id, a routine, a run, a token, a library name, a driver or a device file shows a picker of the real values. The arrow keys move, typing filters the list, Enter picks and Control and C cancels. A left-out value for `write` or `dry-run` and each argument of an action are typed with the limits in view, and an answer that doesn't fit is typed again. `openhal limits set` alone walks through the device, the channel and the new value. A person-only step shows a picker only with the human token and still takes its typed phrase.

Without a terminal, or with `--json`, no command prompts. The error names what is missing, lists up to 10 valid values and shows one command to copy, and the command exits 2.

```
$ openhal limits show
error  openhal limits show needs a device.
  devices  plant-waterer
  run      openhal limits show plant-waterer
```

A mistyped command gets the closest command, and a mistyped device, routine, request, run or token id gets the closest real ids.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Blocked or failed. The message names the rule and what to do |
| 2 | Usage error, for example a missing argument without a terminal, or a target that is not `device.channel` |
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
| `limits set`, to widen a limit | `confirm` |
| `risk set`, to lower a level | `confirm` |
| `runs caps`, to raise a cap | `confirm` |

`file confirm` on a file with suggested limits and `writer interview` read every answer from the terminal, where Enter keeps a suggestion. Where no phrase can be typed, `limits set` and `risk set` don't fail. A wider limit or a lower level becomes a pending change that `confirm approve` takes with the phrase `approve`.


## Setup

### openhal init

```
openhal init [--new-token] [--no-sample]
```

`openhal init` creates the config folder (mode 0700), `config.yaml` with the defaults, the human token in `human.token` (mode 0600) and `devices/plant-waterer.hal.yaml`, the simulated plant waterer from `examples/plant-waterer/mock/`. Every channel and action gets a risk level ([Risk](#risk)). The sample's channels are medium, so the sample takes commands at once within its own range. Running `init` again keeps a working token, and `--new-token` creates a new token. In a terminal, init also walks the limits interview for each device it adds that has high risk channels or actions.

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
openhal token revoke [TOKEN_ID]
```

`create` prints the token once, on the last line, so `| tail -1` captures the token, and the hub keeps only a hash of the token. Agent tokens default to the `read` scope, but human tokens always have full scope. `list` shows ids, names, kinds and scopes and never the tokens, and `revoke` takes effect on the next request.

These commands use the hub's token routes, and when the hub is not running or has no token routes yet, the commands work on `hub.db` in the config folder directly, which only the folder's owner can open.

## The hub and devices

### openhal start

```
openhal start [--host HOST] [--port PORT] [--verbose]
```

`openhal start` runs OpenHAL in the foreground on `api.host` and `api.port` from `config.yaml`, `127.0.0.1:7420` by default, until you press Control and C. `openhal service install` runs the same command in the background at every login. A second `openhal start` on the same config folder exits with an error, so two hubs never open the same devices.

### openhal status

```
openhal status [--json]
```

`openhal status` shows the hub's version and address, the specification version the hub implements, such as v0.1, who you are, connected devices, pending confirmations, the stop lock and device files that failed to load.

### openhal devices

```
openhal devices [DEVICE] [--json]
```

`openhal devices` lists devices with driver, hazard class, mode (`writable` or `read-only`) and connection state. With a device id, the command shows every read channel, every write channel with its limits, max change per second and confirmation tier, every action, the interlocks and the notes.

### openhal discover

```
openhal discover [--driver NAME ...] [--json]
```

`openhal discover` scans for devices with probes that send only read-only identify commands, and prints matches against the device library, unknown devices with the command to start the driver writer, and per-driver errors.

### openhal read

```
openhal read [DEVICE.CHANNEL ...] [--json]
```

`openhal read` reads the channels now and exits 1 if any read failed. At a terminal, a device id with no channel shows a picker of the device's channels.

### openhal write

```
openhal write [DEVICE.CHANNEL] [VALUE...] [--json]
```

`openhal write` sends a request to set a channel, and the kernel checks the request. The value words are joined, so `60 %` and `"60 %"` are the same. The CLI splits the number from its unit before sending, so the hub receives `"value": 60, "unit": "%"` ([ADR 0016](../adr/0016-one-value-format.md)), and `--json` prints values the same way. Numbers need a unit, and the hub converts compatible units (`85 degF` against a degC channel). Bool channels take true, false, on, off, yes, no, 1 or 0. The command prints the result, and a blocked command prints its code and message and exits 1. Because the plant waterer's pump runs only through `water`, the plant waterer has no write channels.

```
$ openhal write plant-waterer.pump on
blocked unknown_target  Blocked. plant-waterer has no write channel 'pump'. Write channels are none.
```

### openhal action

```
openhal action [DEVICE.ACTION] [KEY=VALUE ...] [--json]
```

`openhal action` runs an action, and arguments with units are typed as `duration=20s` or `"duration=20 s"`.

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

`openhal dry-run` checks commands against the current state without running the commands. A plan file is a YAML or JSON list of commands, evaluated in order as if the earlier ones had run.

```yaml file=plan.yaml
- { device: plant-waterer, action: water, args: { duration: 120 s } }
- { device: plant-waterer, action: water, args: { duration: 20 s } }
```

```
$ openhal dry-run --file plan.yaml
1. blocked above_max  Blocked. The duration limit is 30 s (max). Requested 120 s.
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
openhal confirm [--json]
openhal confirm show [REQUEST_ID] [--json]
openhal confirm approve [REQUEST_ID] [--phrase approve]
openhal confirm reject [REQUEST_ID] [--reason TEXT]
```

The hub holds commands that need a person in the confirmation queue, and a pending limit change from `openhal limits set` shows in the same list. `show` and `approve` print the command, who sent the request and the dry run at the time of the request. Approval makes the kernel check the command again against the current state, so a request that the current state would block is blocked instead of run. Rejecting needs the human token and no phrase.

## Audit log

```
openhal log [--device ID] [--status STATUS] [--event EVENT] [--since SEQ] [--limit N] [--json]
openhal log --verify
```

`openhal log` shows entries newest first, and `--verify` checks the hash chain and exits 1 if the chain is broken.

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

`new` stores a routine, always disabled, and the kind comes from the file suffix unless `--kind` sets the kind. `enable` prints the routine and its dry run first, and exits 1 without enabling the routine if the dry run does not pass. `run` runs the routine once now. `approve` signs an approval for this exact routine content to drive a high hazard device, so any change to the routine voids the approval.

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
openhal driver test [NAME]
openhal driver new NAME [--title TEXT] [--root PATH]
```

`list` shows every driver with its protocols, hazard default, conformance level and status. `test` runs the conformance suite at the driver's declared level and exits 1 on any failure. `new` scaffolds an experimental `x-NAME` driver with a simulator, conformance case, tests and docs in an OpenHAL checkout, and never overwrites a file. [The driver guide](../drivers/WRITING-A-DRIVER.md) has the tutorial.

## Device files

```
openhal file validate [PATH ...] [--json]
openhal file schema
openhal file confirm [PATH] [--by NAME] [--phrase confirm]
```

`validate` checks files against the spec, the devices folder when no path is given, and `schema` prints the JSON Schema. At a terminal, `confirm` without a path shows a picker of the files in the devices folder, read-only files first. `confirm` on a file with suggested limits walks the limits interview for its high risk channels and actions, one plain question per limit with the suggestion as the default, and a value past what the device reports is asked again. `confirm` then prints every limit and adds a top-level `confirmed` with your name, the date and the hash of the limits, so any later change to a limit makes its high risk entries read-only again. A file with no high risk entry has nothing to confirm. A running OpenHAL that serves this config folder loads the file at once, and the command says the device is now writable.

## Limits

```
openhal limits [--json]
openhal limits show [DEVICE[.CHANNEL]] [--json]
openhal limits set [DEVICE[.CHANNEL]] [--min VALUE] [--max VALUE] [--rate VALUE|none] [--phrase confirm]
```

A bare `openhal limits` prints every device's limits in one table and one narrower limit to copy. `show` prints each number channel's min, max and max change with the range the device itself reports. At a terminal, `set` with nothing else walks through the device, the channel with its limits and the range the device reports, and then the new value, and prints the same change as one command at the end. `set` takes values with units, such as `--max "80 %"` or `--rate "5 %/s"`, and never goes past the device's own range. A narrower limit applies at once and is written into the device file, with the confirmation bound again to the hash of the limits. In a terminal, a wider limit shows the change before and after and takes the typed phrase `confirm`. From a script, an agent's shell or an agent token, a wider limit waits as a pending limit change in `openhal confirm list` and in the Inspector until a person approves the change. An agent's narrower limit applies to that agent's session, as `tighten_limits` does.

A file that an earlier version's interview confirmed keeps its limits, such as a 60 % maximum on an LED. To give the LED its full range and no rate cap, run `openhal limits set DEVICE.CHANNEL --max "100 %" --rate none` and type `confirm`.

## Risk

```
openhal risk [--json]
openhal risk show [DEVICE[.NAME]] [--why] [--json]
openhal risk set [DEVICE.NAME] [low|medium|high] [--phrase confirm]
```

Every channel and action has a risk level, set from what it is ([Safety](../SAFETY.md#risk-levels)). Reading is always low. A low or medium channel takes commands at once within the device's own range, and a high one stays read-only until a person answers its limits with `openhal file confirm`.

A bare `openhal risk` shows how many channels and actions of each device sit at each level and one change to copy. `show` lists each channel and action with its level, who set the level and whether it takes commands, and `--why` adds the reasons. At a terminal, a left-out device, name or level opens a picker, and without one the error lists the valid values and one command to copy. `set` raises a level at once. Lowering a level gives an agent more, so in a terminal it takes the typed phrase `confirm`, and from a script or an agent's shell it waits as a pending change in `openhal confirm list` until a person approves it. Agent tokens change no level. Each change is saved in the device file with your name and the date and recorded in the audit log.

## Runs

```
openhal runs list [--json]
openhal runs show [RUN_ID] [--json]
openhal runs cancel [RUN_ID]
openhal runs caps [--max-steps N] [--max-seconds SECONDS] [--per-agent N] [--phrase confirm] [--json]
```

A run is a list of steps an agent or a script sends with `run_steps`, which the hub checks as a plan and then runs one command at a time through the kernel. `list` shows the runs this token can see, newest first, and the human token sees every run. `show` prints every step a run ran, and `cancel` ends a run before its next step.

`caps` shows the caps on runs, and with a new value changes them through the hub, which saves them in `config.yaml`. `--max-steps` bounds the steps in one run, counting every repeat, `--max-seconds` bounds a run, a wait or a sample, and `--per-agent` bounds how many of them one token has going at once. Changing a cap takes the human token. A lower cap applies at once, and a higher cap takes the typed phrase `confirm`, so no script or agent's shell can raise one.

## Device library

```
openhal library list [--driver NAME] [--json]
openhal library show [NAME] [--json]
openhal library add [NAME]
```

`list` shows every starter device file in the library with its driver, hazard class and what it can change. `show` prints what a file matches, every suggested limit in the file and the file itself, and `--json` gives the limits in the shape `hal/devices/describe` uses. `add` copies a file into the devices folder unchanged, never adds a confirmation, and never overwrites a file or adds a second file for a device id the folder already has. A name is the file name without `.hal.yaml`, such as `rigol-dp832`. When `discover` matches a library file, `discover` prints the `add` command to run. docs/guide/library.md explains how matching and confirmation work.

## Install and background service

### openhal init, the wizard

```
openhal init [--yes] [--discover | --no-discover] [--driver NAME ...] [--device DRIVER=ADDRESS ...]
             [--agent-scope read|control_low|control_medium] [--client NAME ...] [--service | --no-service]
             [--new-token] [--no-sample]
```

In an interactive terminal, `init` sets up the config folder, the human token and the sample as above, then prompts you to choose whether to look for devices, which found devices to add, whether to answer each device's limits now, the scope of a token for your AI client, which MCP clients to add OpenHAL to and whether to install the background service. With `--yes`, `init` takes the safe defaults without prompting. A run that can't prompt and has no `--yes`, such as a script, stops after the sample.

| Step | In a terminal | With `--yes` |
|---|---|---|
| Search for devices | yes, default yes | yes, unless `--no-discover` |
| Add each device found | yes, default yes | yes |
| Agent token in `agent.token` | scope, default `read` | `read`, or `--agent-scope` |
| Print the MCP client setup | always, once there is an agent token | always |
| Answer the high risk limits of a device it adds | yes or no, default yes, only when it has some | never |
| Add OpenHAL to each MCP client found | yes or no for each, default yes | every client found |
| Install the background service | yes or no, default no | only `--service` |

Found devices are saved as device files, where a library match is copied with the address discovery found and an `openhal-firmware` board or an ESPHome node returns its own description in reply to read-only commands. Every limit is marked `suggested: true` and every confirmation is dropped. Low and medium risk channels and actions take commands at once within the device's own range, and init prints how many entries sit at each level. High risk ones stay read-only until a person answers the limits interview, in init or later with `openhal file confirm`. A device that already has a file is left out, `--driver` limits discovery to some drivers, and `--device` adds a self-describing device at a known address, such as `openhal-firmware=/dev/ttyACM0`.

`init` keeps the agent token while the token works and has the requested scope. The client setup for Claude Desktop, Claude Code and Cursor starts `openhal mcp --token-file ~/.openhal/agent.token` with the full path to `openhal`. Init finds Claude Code by the `claude` program on your PATH and Claude Desktop and Cursor by their app or config folder. Claude Code gets `claude mcp add openhal --scope user`, so every session has the server, after a backup of `~/.claude.json`. `--client claude-desktop`, `claude-code` or `cursor` adds that client even when init doesn't find the client. An existing file is copied to `NAME.openhal-backup-DATE` first and keeps every other entry and its mode. A file that isn't valid JSON is left as it is, and `init` exits 1 if a step you asked for failed.

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
| File | `~/Library/LaunchAgents/org.openhal.hub.plist` | `~/.config/systemd/user/openhal.service` |
| Install | `launchctl bootstrap gui/UID` | `systemctl --user enable` and `restart` |
| Restart | `launchctl kickstart -k` | `systemctl --user restart` |
| Uninstall | `launchctl bootout` | `systemctl --user disable --now` |
| Logs | `~/.openhal/openhal.log` | `journalctl --user -u openhal` |

The service restarts the hub after a crash but not after a clean stop. Because a user unit stops at logout when lingering is off, `install` on Linux reports when lingering is off. `status` exits 1 when the service isn't running, and `--dry-run` prints every file and command and changes nothing. `print` shows the plist or unit, for this machine or the one `--platform` names.
