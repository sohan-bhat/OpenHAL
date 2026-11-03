# Install OpenHAL for an MCP client

These steps install OpenHAL, start the OpenHAL hub and add the OpenHAL MCP server to an MCP client such as Cline. Every command runs in a terminal on the person's computer. OpenHAL controls real hardware, so ask the person before step 2, which searches the computer for devices.

## 1. Install OpenHAL

On macOS and Linux, run this command.

```sh
curl -LsSf https://sohan-bhat.github.io/OpenHAL/install.sh | sh
```

On Windows, run this command in PowerShell.

```powershell
irm https://sohan-bhat.github.io/OpenHAL/install.ps1 | iex
```

The installer needs nothing installed first and puts the `openhal` command in `~/.local/bin`. Check the install with `openhal --version`, which prints `openhal` and the version. If the terminal doesn't find `openhal`, the installer printed the line that adds `~/.local/bin` to PATH. Run that line and open a new terminal.

## 2. Set up the hub

```sh
openhal init --yes --no-discover
```

This creates the config folder `~/.openhal`, the person's own token and a simulated plant waterer to try commands on, and adds OpenHAL to Claude Code, Claude Desktop and Cursor when those clients are installed. `--no-discover` skips the device search. To search for devices too, ask the person and then run `openhal init --yes`, which sends only read-only identify commands.

## 3. Start the hub

```sh
openhal start
```

The hub runs until Control and C. On macOS and Linux, `openhal service install` runs the hub in the background at every login instead. `openhal mcp` also starts the hub on its own when the hub isn't running.

## 4. Make a token for the MCP client

```sh
openhal token create --name cline
```

The last line of the output is the token, shown once. The token is read-only. For a token that may also change low risk channels and actions, add `--scope control_low`, and only when the person asks for that.

## 5. Add the server to the MCP client

Add this server to the client's MCP settings. For Cline, the file is `cline_mcp_settings.json`. Put the token from step 4 in place of `TOKEN`.

```json
{
  "mcpServers": {
    "openhal": {
      "command": "openhal",
      "args": ["mcp"],
      "env": {
        "OPENHAL_TOKEN": "TOKEN"
      }
    }
  }
}
```

If the client doesn't find `openhal`, give the full path in `command`. On macOS and Linux, `command -v openhal` prints the path. On Windows, `(Get-Command openhal).Source` prints the path.

## 6. Check the setup

Call the `hub_status` tool. The answer shows the hub's version and how many devices are connected. Then call `list_devices`, which shows the simulated plant waterer.

A tool result that says OpenHAL isn't set up for this AI client means the server has no token, so check step 5. A tool result that says the hub is not running means the hub needs `openhal start`.

## Without installing

Once OpenHAL 0.1.0 is on PyPI, a client with [uv](https://docs.astral.sh/uv/) can start the server with no install step. Use `uvx` as the command and `--from halkit openhal mcp` as the arguments, and run steps 2 to 4 with `uvx --from halkit openhal` in place of `openhal`. The PyPI package is `halkit`, and the `openhal` package on PyPI is a different project.
