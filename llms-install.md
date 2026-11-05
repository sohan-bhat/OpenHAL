# Install OpenHAL for an MCP client

Run each command in a terminal on the person's computer. OpenHAL controls real hardware, so ask the person before any device search.

## 1. Install OpenHAL

On macOS and Linux, run this command.

```sh
curl -LsSf https://sohan-bhat.github.io/OpenHAL/install.sh | sh
```

On Windows, run this command in PowerShell.

```powershell
irm https://sohan-bhat.github.io/OpenHAL/install.ps1 | iex
```

The installer puts `openhal` in `~/.local/bin`, and `openhal --version` checks the install. If `openhal` isn't on PATH, run the PATH line the installer printed and open a new terminal.

## 2. Set up the hub

```sh
openhal init --yes --no-discover
```

This creates `~/.openhal`, the person's token and a simulated plant waterer, and adds OpenHAL to Claude Code, Claude Desktop and Cursor when those clients are installed. To search for devices too, ask the person, then run `openhal init --yes`, which sends only read-only identify commands.

## 3. Start the hub

```sh
openhal start
```

The hub runs until Control and C. On macOS and Linux, `openhal service install` runs the hub at every login instead. `openhal mcp` also starts the hub when the hub isn't running.

## 4. Make a token for the MCP client

```sh
openhal token create --name cline
```

The last output line is the read-only token, shown once. Add `--scope control_low` only when the person wants changes to low risk channels and actions.

## 5. Add the server to the MCP client

Add this server to the client's MCP settings, `cline_mcp_settings.json` for Cline, with the token from step 4 in place of `TOKEN`.

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

If `openhal` isn't on the client's PATH, put the full path in `command`. `command -v openhal` prints the path on macOS and Linux, and `(Get-Command openhal).Source` on Windows.

## 6. Check the setup

Call `hub_status` for the hub's version and device count, then `list_devices`, which lists the simulated plant waterer.

If a result says OpenHAL isn't set up for this AI client, check the token from step 5. If a result says the hub is not running, run `openhal start`.

## Without installing

Once OpenHAL 0.1.0 is on PyPI, a client with [uv](https://docs.astral.sh/uv/) can use `uvx` as the command and `--from halkit openhal mcp` as the arguments, and run steps 2 to 4 with `uvx --from halkit openhal`. The PyPI package is `halkit`, because `openhal` on PyPI is a different project.
