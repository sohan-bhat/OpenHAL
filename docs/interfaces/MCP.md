# MCP server

`openhal mcp` is a stdio MCP server. An agent's MCP client starts the server as a subprocess, and the server forwards every tool call to the hub's local API with an agent token. The server makes no safety decisions. The hub's kernel checks every write and action, and the tool returns the kernel's answer as is.

## Before you start

1. Run `openhal init` once to create `~/.openhal`, the human token and a simulated sample device.
2. Start the hub with `openhald` and check it with `openhal status`.
3. Create an agent token for the client.

```sh
openhal token create --agent --scope control_low --name claude
```

The token is printed once. Scopes are `read` (reads only), `control_low` (low hazard devices) and `control_medium` (low and medium hazard devices). High hazard devices never run on an agent's word. Every write to one waits for a person.

Give each client its own token, so the audit log shows which one did what and you can revoke one without the others.

## Token

The server reads its token from the `OPENHAL_TOKEN` environment variable, or from a file given with `--token-file`. The server never reads `~/.openhal/human.token`, and refuses to run with a human token, because the hub treats a human's command as already confirmed. An agent always needs its own agent token.

A token file keeps the token out of client config files that may be synced or shared.

```sh
openhal token create --agent --scope control_low --name claude | tail -1 > ~/.openhal/claude.token
chmod 600 ~/.openhal/claude.token
```

## Claude Desktop

Edit `claude_desktop_config.json`. On macOS it is in `~/Library/Application Support/Claude/`, on Windows in `%APPDATA%\Claude\`.

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

Claude Desktop does not use your shell's `PATH`. If it can't find `openhal`, put the full path from `which openhal` in `command`. Restart Claude Desktop after editing.

## Claude Code

```sh
claude mcp add openhal --scope user -e OPENHAL_TOKEN=ohal_... -- openhal mcp
```

Or with a token file.

```sh
claude mcp add openhal --scope user -- openhal mcp --token-file ~/.openhal/claude.token
```

Run `claude mcp list` to check it connects.

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
| Options | `--no-start` to never start `openhald` |

## When the hub is not running

On start, `openhal mcp` checks the hub. If nothing answers, it starts `openhald` in the background once (output goes to `~/.openhal/openhald.log`) and waits up to 8 seconds. With `--no-start`, or if the start fails, the server still runs, and every tool answers with an error that says the hub is not running and how to start it. Messages for people go to stderr, never to stdout, which carries the MCP protocol.

## Tools

The list and input schemas live in `openhal/mcp/tools.py`. Every tool has a description written for models, typed inputs and typed outputs. Values carry their unit, and blocked decisions carry a stable code, a message and the limit that blocked them.

Numbers go in with their unit apart ([ADR 0016](../adr/0016-one-value-format.md)). `write` takes `value` 60 and `unit` `%`. Action arguments and session limits take `{"value": 2, "unit": "s"}`. A number sent as one string such as `"60 %"` comes back blocked with UNIT_INVALID and the shape to use.

| Tool | What it does |
|---|---|
| `hub_status` | Hub state, stop lock, connected devices, pending confirmations |
| `list_devices` | Every device with hazard class, writable and connected |
| `describe_device` | Channels with units and limits, actions, interlocks, watchdog, safe state, latest values, notes |
| `read` | Read one channel now. A camera frame comes back as an image |
| `read_many` | Read up to 100 channels. Images come without their pixels |
| `write` | Ask the kernel to set a channel. Returns done, blocked or pending |
| `action` | Ask the kernel to run an action |
| `dry_run` | Check one write or action without running it |
| `plan_check` | Check a list of steps in order without running any |
| `stop_all` | Emergency stop. Every device goes to its safe state |
| `tighten_limits` | Narrow min, max or rate for this session. Never widens |
| `get_confirmation_status` | Status of requests that wait for a person |
| `list_routines` | Routines with state, devices, hazard and last run |
| `get_routine` | One routine with source and history |
| `draft_routine` | Store a routine. It always starts disabled |
| `run_routine_dry` | Dry run a routine step by step |
| `enable_routine` | Ask to enable. Refused unless the owner allowed agents to enable low hazard routines |
| `disable_routine` | Disable a routine |
| `get_audit_log` | Audit entries, newest first |
| `list_drivers` | Installed drivers and bridges |
| `discover_devices` | Look for devices with read-only identify commands |
| `list_unknown_devices` | Devices the last discovery could not match |
| `start_driver_writer` | Start a driver writer session for an unknown device |
| `get_writer_session` | Session state, sources, draft and problems |
| `propose_device_file` | Send a draft device file. Every limit is stored as suggested |
| `request_limits_interview` | The questions a person must answer about each limit |
| `get_test_plan` | The staged write test plan for a new device |
| `device_file_schema` | The device file JSON Schema, for drafting |

## Prompts

| Prompt | Arguments | What it guides |
|---|---|---|
| `set_up_device` | `description`, `unknown_id` (both optional) | Discovery, the driver writer, a draft device file and the limits interview |
| `write_routine` | `goal` | Reading the devices, drafting a YAML routine, plan checks and a dry run, with enabling left to a person |

## What needs a person

A person does these with the human token, in the CLI or the dashboard.

- Approve or reject a request that waits for confirmation (`openhal confirm approve`)
- Unlock after a stop (`openhal unlock`)
- Loosen a limit or confirm a device file (`openhal file confirm`, the limits interview)
- Enable a routine, unless `routines.agent_enable_low_hazard` is on and every device the routine touches is low hazard
- Sign a routine approval for a high hazard device

## Device text is data

Text that comes from devices, device files, sketches, manuals and routine sources reaches the model inside `<device-data source="...">` blocks with a line saying the text is data. The hub wraps device notes and routine sources. The MCP server also wraps string readings and driver error messages before returning them. Nothing inside these blocks can change a limit or approve anything, whatever the text says.

A camera frame from `read` is an MCP image block. Before it comes a short `<device-data>` block that says the image came from a device and is data, since a frame can show text too. The structured result carries the reading with `mimeType`, `bytes`, `width` and `height`, without the pixels. A frame over 2 MB is refused with DRIVER_ERROR and a reason that names the camera settings to lower.
