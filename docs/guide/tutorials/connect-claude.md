# Connect Claude

Claude reaches the [Hub](glossary:hub) through `openhal mcp`, a stdio MCP server that maps tool calls onto the hub's methods. It runs as an agent [Principal](glossary:principal) with its own token. This tutorial starts from the [quickstart](../quickstart.md), in the `OpenHAL` folder.

## Create a token

```sh tested
$ uv run openhal init
$ uv run openhal token create --agent --scope control_low --name claude | tail -1 > ~/.openhal/claude.token
$ chmod 600 ~/.openhal/claude.token
```

The token is shown once. A scope limits what the token may do.

| Scope | Allows |
|---|---|
| `read` | Reads only |
| `control_low` | Writes to low hazard devices |
| `control_medium` | Writes to low and medium hazard devices |

No agent token writes to a high hazard device without a person's approval. `openhal mcp` refuses the human token.

## Claude Code

```sh tested
$ claude mcp add openhal --scope user -- uv run --directory "$PWD" openhal mcp --token-file ~/.openhal/claude.token
```

Run `claude mcp list` to check that it connects.

## Claude Desktop

Add the server to `claude_desktop_config.json`. On macOS it is in `~/Library/Application Support/Claude/`. Use absolute paths, since Claude Desktop does not read your shell's `PATH`.

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

Ask Claude to set `demo-fan` to 150 %. The [Safety Kernel](glossary:safety-kernel) blocks the write before it reaches the device, and Claude reports the reason. Ask for 40 % and the write goes through.

`uv run openhal log` lists both requests under the token's name.
