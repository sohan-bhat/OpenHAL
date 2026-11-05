# MCP server

`openhal mcp` is a stdio MCP server that an MCP client starts as a subprocess. Each tool call goes to the hub's local API with an agent token, and the tool returns the kernel's result unchanged.

## Before you start

1. Run `openhal init` once for `~/.openhal`, the human token and a simulated sample device.
2. Run `openhal start`, then `openhal status` to check the hub.
3. Create an agent token for each client, so the audit log names the client and one token can be revoked alone.

```sh
openhal token create --agent --scope control_low --name claude
```

The token prints once. `read` allows reads only, `control_low` low hazard devices and `control_medium` low and medium hazard devices. Commands to a high hazard device are always held for a person.

## Token

The server reads `OPENHAL_TOKEN` or the `--token-file` file. The hub treats a human's command as confirmed, so the server never reads `~/.openhal/human.token` and exits at start when given a human token. With no token, the server still starts and lists its tools, and every call returns an error naming `openhal init` and `openhal start`. With no hub, every call returns an error naming `openhal start`.

A token file keeps the token out of client configs that may be shared.

```sh
openhal token create --agent --scope control_low --name claude | tail -1 > ~/.openhal/claude.token
chmod 600 ~/.openhal/claude.token
```

## Claude Desktop

Edit `claude_desktop_config.json` in `~/Library/Application Support/Claude/` on macOS or `%APPDATA%\Claude\` on Windows.

```json
{
  "mcpServers": {
    "openhal": {
      "command": "openhal",
      "args": ["mcp"],
      "env": { "OPENHAL_TOKEN": "ohal_..." }
    }
  }
}
```

Claude Desktop doesn't use your shell's `PATH`, so `command` may need the full path from `which openhal`. Restart Claude Desktop after editing.

## Claude Code

```sh
claude mcp add openhal --scope user -e OPENHAL_TOKEN=ohal_... -- openhal mcp
```

Or with a token file.

```sh
claude mcp add openhal --scope user -- openhal mcp --token-file ~/.openhal/claude.token
```

`claude mcp list` shows whether the server connects.

### The /openhal command

`openhal init` saves the `/openhal` command at `~/.claude/skills/openhal/SKILL.md` when adding OpenHAL to Claude Code, backing up a differing file first. The plugin in `plugins/openhal` ships the same command as `/openhal:openhal`.

| You type | Claude does |
|---|---|
| `/openhal` | Checks the server and hub, then shows each device's reads, settable channels with limits, actions and targets held for a person |
| `/openhal limits printer` | The same for one device |
| `/openhal setup` and a few words about the device | Runs the driver writer from discovery to the limits interview, sending nothing to the device |
| `/openhal routine` and a goal | Drafts and dry runs a routine, which stays disabled |
| `/openhal` and any other task | The task, through the OpenHAL tools |

The command makes every change through the MCP tools with the agent token and reports blocked or held commands as the hub returned each one. The server's two prompts appear as `/mcp__openhal__set_up_device` and `/mcp__openhal__write_routine`.

## Cursor

Use `~/.cursor/mcp.json` for every project, or `.cursor/mcp.json` for one.

```json
{
  "mcpServers": {
    "openhal": {
      "command": "openhal",
      "args": ["mcp", "--token-file", "/Users/you/.openhal/cursor.token"]
    }
  }
}
```

## Any other MCP client

| Setting | Value |
|---|---|
| Transport | stdio |
| Command | `openhal mcp`, or the full path to `openhal` |
| Token | `OPENHAL_TOKEN`, or `--token-file <path>` |
| Hub address | `OPENHAL_URL` or `--url`, default from `api.host` and `api.port` in `config.yaml` |
| Options | `--no-start` never starts OpenHAL |

## When the hub is not running

If no hub responds at start, `openhal mcp` runs `openhal start` in the background once, logging to `~/.openhal/openhal.log`, and allows the hub 8 seconds. With `--no-start` or a failed start, every tool returns an error with the command that starts the hub. Messages for people go to stderr, since stdout carries MCP.

## Tools

Schemas live in `openhal/mcp/tools.py`. A blocked result carries a stable code, a message and the limit. Numbers go in with the unit apart per [ADR 0016](../adr/0016-one-value-format.md), so `write` takes `value` 60 and `unit` `%`, and action arguments and session limits take `{"value": 2, "unit": "s"}`. One string such as `"60 %"` comes back blocked with UNIT_INVALID and the shape to use.

| Tool | Does |
|---|---|
| `hub_status` | Hub state, protocol version, stop lock, devices and pending confirmations |
| `list_devices` | Devices with hazard class, writable and connected |
| `find` | Search targets by text, unit, kind, hazard or connection |
| `describe_device` | One device's channels, units, limits, actions, interlocks, watchdog, safe state, latest values, notes and risk levels |
| `read` | One channel now. A camera frame comes back as an image |
| `read_many` | Up to 100 channels, images without pixels |
| `sample` | Readings at an interval over a duration, with min, max and mean |
| `wait_until` | Read until a condition holds or a timeout passes |
| `write` | Request a channel change. Returns done, blocked or pending |
| `action` | Request an action |
| `dry_run` | Check one write or action, running nothing |
| `plan_check` | Check a list of steps in order, running nothing |
| `run_steps` | Run read, write, action, wait and wait_until steps in order, with a repeat count |
| `get_run` | One of your runs with status, stop point, reason and step results |
| `list_runs` | Your runs, newest first |
| `cancel_run` | End one of your runs before its next step |
| `stop_all` | Emergency stop. Every device goes to its safe state and every run, wait and sample ends |
| `tighten_limits` | Narrow min, max or rate for this session, never wider |
| `request_limit_change` | Narrow a limit at once, or file a wider one for a person to approve |
| `get_confirmation_status` | Status of requests held for a person |
| `list_routines` | Routines with state, devices, hazard and last run |
| `get_routine` | One routine with source and history |
| `draft_routine` | Store a routine, always disabled |
| `run_routine_dry` | Dry run a routine step by step |
| `enable_routine` | Request enabling a routine. Blocked unless the owner lets agents enable low hazard routines |
| `disable_routine` | Disable a routine |
| `get_audit_log` | Audit entries, newest first |
| `list_drivers` | Installed drivers and bridges |
| `discover_devices` | Scan with read-only identify commands |
| `list_unknown_devices` | Devices the last scan could not match |
| `start_driver_writer` | Start a driver writer session for an unknown device |
| `get_writer_session` | Session state, sources, draft and problems |
| `propose_device_file` | Send a draft device file, with every limit stored as suggested |
| `request_limits_interview` | The limit questions a person must answer |
| `get_test_plan` | The staged test plan for a new device |
| `device_file_schema` | The device file JSON Schema |

## Runs and waits

`find` locates targets, so a task needs no device id in advance. Each `run_steps` step has a `kind`.

| Kind | Fields |
|---|---|
| `read` | `targets`, channels as `device.channel` |
| `write` | `device`, `channel`, `value`, `unit`, and `increment` to add on each repeat |
| `action` | `device`, `action`, `args` |
| `wait` | `seconds` |
| `wait_until` | `condition`, `timeout_s`, `interval_s` |

The hub checks the run as a plan first and runs nothing if a step would be blocked. Each command then goes through the kernel as a single `write` or `action` call does, and the run stops at the first step that isn't done, with the step, the code and the reason. A step that needs a person ends the run as `pending` with its `request_id`. [Runs of steps](../SAFETY.md#runs-of-steps) has every rule.

A run belongs to the token that started the run, so another agent's `get_run` and `cancel_run` find nothing. Conditions use the routine expression language, such as `<device>.<channel> > 30 degC`. `wait_until` and `sample` hold the call for their duration, so keep those calls under a minute and put longer waits in a run.

The caps in `config.yaml` are 200 steps per run, 600 seconds per run, wait or sample, and 2 runs, waits and samples going at once per token. Only a person changes the caps, with `openhal runs caps`. ADR 0019 has the run model.

## Prompts

| Prompt | Arguments | Guides |
|---|---|---|
| `set_up_device` | `description`, `unknown_id`, both optional | Discovery, the driver writer, a draft device file and the limits interview |
| `write_routine` | `goal` | Reading the devices, drafting a YAML routine, plan checks and a dry run, with enabling left to a person |

## What needs a person

Only a person with the human token, in the CLI or the dashboard, can do these.

- Approve or reject a held request with `openhal confirm approve`
- Unlock after a stop with `openhal unlock`
- Loosen a limit or confirm a device file with `openhal file confirm`
- Lower a risk level with `openhal risk set`. Agents see every level in `describe_device` and `find`
- Enable a routine, unless `routines.agent_enable_low_hazard` is on and every device the routine touches is low hazard
- Sign a routine approval for a high hazard device
- Change the run caps with `openhal runs caps`

## Device text is data

Text from devices, device files, sketches, manuals and routine sources reaches the model inside `<device-data source="...">` blocks marked as data. The hub wraps device notes and routine sources, and the MCP server also wraps string readings and driver errors. Nothing inside a block can change a limit or approve anything.

A camera frame from `read` is an MCP image block, after a short `<device-data>` block marking the image as device data. The structured result carries `mimeType`, `bytes`, `width` and `height` without the pixels. A frame over 2 MB returns DRIVER_ERROR with a reason naming the camera settings to lower.
