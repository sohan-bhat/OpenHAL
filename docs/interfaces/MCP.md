# MCP server

`openhal mcp` is a stdio MCP server. An agent's MCP client starts the server as a subprocess, and the server forwards every tool call to the hub's local API with an agent token. The server runs no safety checks, because the hub's kernel checks every write and action, and the tool returns the kernel's result unchanged.

## Before you start

1. Run `openhal init` once to create `~/.openhal`, the human token and a simulated sample device.
2. Start OpenHAL with `openhal start` and check the hub with `openhal status`.
3. Create an agent token for the client.

```sh
openhal token create --agent --scope control_low --name claude
```

The token is printed once. Scopes are `read` (reads only), `control_low` (low hazard devices) and `control_medium` (low and medium hazard devices). The hub holds every write and action on a high hazard device until a person approves the request, whatever the agent token's scope.

Give each client its own token, so the audit log shows which client did what and you can revoke one client's token without the others.

## Token

The server reads its token from the `OPENHAL_TOKEN` environment variable, or from a file given with `--token-file`. Because the hub treats a human's command as already confirmed, the server never reads `~/.openhal/human.token` and exits with an error at start when given a human token, so an agent always needs its own agent token.

A token file keeps the token out of client config files that may be synced or shared.

```sh
openhal token create --agent --scope control_low --name claude | tail -1 > ~/.openhal/claude.token
chmod 600 ~/.openhal/claude.token
```

## Claude Desktop

Edit `claude_desktop_config.json`, which is in `~/Library/Application Support/Claude/` on macOS and in `%APPDATA%\Claude\` on Windows.

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

Because Claude Desktop does not use your shell's `PATH`, put the full path from `which openhal` in `command` when Claude Desktop can't find `openhal`, and restart Claude Desktop after editing the file.

## Claude Code

```sh
claude mcp add openhal --scope user -e OPENHAL_TOKEN=ohal_... -- openhal mcp
```

You can also pass a token file.

```sh
claude mcp add openhal --scope user -- openhal mcp --token-file ~/.openhal/claude.token
```

Run `claude mcp list` to check that the OpenHAL server connects.

## Cursor

Add the server to `~/.cursor/mcp.json` for every project, or `.cursor/mcp.json` for one.

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
| Command | `openhal mcp` (or the full path to `openhal`) |
| Token | `OPENHAL_TOKEN` environment variable, or `--token-file <path>` |
| Hub address | `OPENHAL_URL` or `--url`, default from `api.host` and `api.port` in `config.yaml` |
| Options | `--no-start` to never start OpenHAL |

## When the hub is not running

On start, `openhal mcp` checks the hub. If the hub doesn't respond, `openhal mcp` runs `openhal start` in the background once (output goes to `~/.openhal/openhal.log`) and waits up to 8 seconds. With `--no-start`, or if the start fails, the server still runs, and every tool returns an error stating that the hub is not running and how to start the hub. Because stdout carries the MCP protocol, messages for people go to stderr and never to stdout.

## Tools

The list and input schemas live in `openhal/mcp/tools.py`. Every tool has a description written for models, typed inputs and typed outputs. Values carry their unit, and blocked results carry a stable code, a message and the limit that blocked the request.

Numbers go in with their unit apart ([ADR 0016](../adr/0016-one-value-format.md)), so `write` takes `value` 60 and `unit` `%`, and action arguments and session limits take `{"value": 2, "unit": "s"}`. A number sent as one string such as `"60 %"` comes back blocked with UNIT_INVALID and the shape to use.

| Tool | What it does |
|---|---|
| `hub_status` | Hub state, protocol version, stop lock, connected devices, pending confirmations |
| `list_devices` | Every device with hazard class, writable and connected |
| `find` | Search every device's channels and actions by text, unit, kind, hazard and connection, as `device.channel` targets |
| `describe_device` | Channels with units and limits, actions, interlocks, watchdog, safe state, latest values, notes, and each channel's and action's risk level and whether it is read-only |
| `read` | Read one channel now. A camera frame comes back as an image |
| `read_many` | Read up to 100 channels. Images come without their pixels |
| `sample` | Read channels at an interval over a duration, with min, max and mean for numbers |
| `wait_until` | Wait until a condition over live readings holds, or a timeout passes, and return the readings |
| `write` | Request a channel change, which the kernel checks. Returns done, blocked or pending |
| `action` | Request an action, which the kernel checks |
| `dry_run` | Check one write or action without running it |
| `plan_check` | Check a list of steps in order without running any |
| `run_steps` | Run read, write, action, wait and wait_until steps in order, with a repeat count, through the kernel |
| `get_run` | One of your runs with its status, where it stopped and why, and its step results |
| `list_runs` | Your runs, newest first |
| `cancel_run` | End one of your runs before its next step |
| `stop_all` | Emergency stop. Every device goes to its safe state and every run, wait and sample ends |
| `tighten_limits` | Narrow min, max or rate for this session. Never widens |
| `request_limit_change` | Narrow a limit at once, or file a wider limit as a pending change that a person approves |
| `get_confirmation_status` | Status of requests held for a person's approval |
| `list_routines` | Routines with state, devices, hazard and last run |
| `get_routine` | One routine with source and history |
| `draft_routine` | Store a routine. Every new routine starts disabled |
| `run_routine_dry` | Dry run a routine step by step |
| `enable_routine` | Request to enable a routine. Blocked unless the owner allowed agents to enable low hazard routines |
| `disable_routine` | Disable a routine |
| `get_audit_log` | Audit entries, newest first |
| `list_drivers` | Installed drivers and bridges |
| `discover_devices` | Scan for devices with read-only identify commands |
| `list_unknown_devices` | Devices the last discovery could not match |
| `start_driver_writer` | Start a driver writer session for an unknown device |
| `get_writer_session` | Session state, sources, draft and problems |
| `propose_device_file` | Send a draft device file. Every limit is stored as suggested |
| `request_limits_interview` | The questions a person must answer about each limit |
| `get_test_plan` | The staged write test plan for a new device |
| `device_file_schema` | The device file JSON Schema, for drafting |

## Runs and waits

An agent finds what a hub has with `find`, so a task needs no device id in advance. `run_steps` takes a list of steps, each with a `kind`.

| Kind | Fields |
|---|---|
| `read` | `targets`, channels as `device.channel` |
| `write` | `device`, `channel`, `value`, `unit`, and `increment` to add that much on each repeat |
| `action` | `device`, `action`, `args` |
| `wait` | `seconds` |
| `wait_until` | `condition`, `timeout_s`, `interval_s` |

The hub checks the whole run as a plan first and runs nothing when a step would be blocked. After a `wait_until` step, a block that depends on live readings, such as an interlock, is left to the kernel's check when that step runs. Then every command goes through the kernel exactly as a `write` or `action` call does, and the run stops at the first step that isn't done, with the step, the code and the reason. A step that needs a person ends the run with status `pending` and its `request_id`, and the steps after it don't run. A run never approves, unlocks, widens a limit or enables a routine.

A run belongs to the token that started it, so another agent's `get_run` and `cancel_run` find no run by that id. `stop_all`, a person's stop and revoking the token end a run at once. A condition uses the routine expression language with every channel as `device.channel`, such as `<device>.<channel> > 30 degC`. `wait_until` and `sample` hold the call for their duration, so keep them under a minute and put longer waits in a run.

The caps in `config.yaml` bound the steps per run (200), the seconds per run, wait or sample (600) and the runs, waits and samples one token has going at once (2). Only a person changes them, with `openhal runs caps`. ADR 0019 has the whole run model.

## Prompts

| Prompt | Arguments | What it guides |
|---|---|---|
| `set_up_device` | `description`, `unknown_id` (both optional) | Discovery, the driver writer, a draft device file and the limits interview |
| `write_routine` | `goal` | Reading the devices, drafting a YAML routine, plan checks and a dry run, with enabling left to a person |

## What needs a person

Only a person with the human token can do the following, in the CLI or the dashboard.

- Approve or reject a request held for confirmation (`openhal confirm approve`)
- Unlock after a stop (`openhal unlock`)
- Loosen a limit or confirm a device file (`openhal file confirm`, the limits interview)
- Lower a risk level (`openhal risk set`). An agent sees every level in `describe_device` and `find`, and changes none
- Enable a routine, unless `routines.agent_enable_low_hazard` is on and every device the routine touches is low hazard
- Sign a routine approval for a high hazard device
- Change the run caps (`openhal runs caps`)

## Device text is data

Text that comes from devices, device files, sketches, manuals and routine sources reaches the model inside `<device-data source="...">` blocks with a line stating that the text is data. The hub wraps device notes and routine sources, and the MCP server also wraps string readings and driver error messages before returning them. Nothing inside these blocks can change a limit or approve anything, whatever the text contains.

A camera frame from `read` is an MCP image block. Because a frame can show text too, a short `<device-data>` block stating that the image came from a device and is data comes before the image. The structured result carries the reading with `mimeType`, `bytes`, `width` and `height`, without the pixels. A read of a frame over 2 MB returns DRIVER_ERROR with a reason that names the camera settings to lower.
