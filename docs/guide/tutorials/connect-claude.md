# Connect Claude

Claude reaches the [Hub](glossary:hub) through `openhal mcp`, a stdio MCP server that maps tool calls onto the hub's methods. The MCP server runs as an agent [Principal](glossary:principal) with its own token. This tutorial starts from the [quickstart](../quickstart.md), in the `OpenHAL` folder.

## Create a token

```sh tested
$ uv run openhal init
$ uv run openhal token create --agent --scope control_low --name claude | tail -1 > ~/.openhal/claude.token
$ chmod 600 ~/.openhal/claude.token
```

The token is shown only once, and the token's scope limits what the token may do.

| Scope | Allows |
|---|---|
| `read` | Reads only |
| `control_low` | Changes to low hazard devices |
| `control_medium` | Changes to low and medium hazard devices |

A change from an agent token to a high hazard device always waits for a person's approval, and `openhal mcp` refuses the human token.

## Claude Code

```sh tested
$ claude mcp add openhal --scope user -- uv run --directory "$PWD" openhal mcp --token-file ~/.openhal/claude.token
```

Run `claude mcp list` to check that the OpenHAL server connects.

## Claude Desktop

Add the server to `claude_desktop_config.json`, which on macOS is in `~/Library/Application Support/Claude/`. Because Claude Desktop does not read your shell's `PATH`, use absolute paths.

```json tested
{
  "mcpServers": {
    "openhal": {
      "command": "/Users/you/.local/bin/uv",
      "args": ["run", "--directory", "/Users/you/OpenHAL", "openhal", "mcp", "--token-file", "/Users/you/.openhal/claude.token"]
    }
  }
}
```

Restart Claude Desktop after you edit the file.

## Try it

Ask Claude to water the plant for 120 seconds. Because 120 seconds is above the duration limit, the [Safety Kernel](glossary:safety-kernel) blocks the command before the command reaches the board, and Claude reports the reason. When you ask for 20 seconds, the command runs.

`uv run openhal log` lists both requests under the token's name.
