---
title: Quickstart
---

OpenHAL isn't on PyPI yet. Install it from a checkout of the repository. You need Python 3.12 or newer and uv.

```sh tested
$ uv tool install ".[hub]"
```

Set up the config folder and a simulated desk fan, confirm its limits as a person, then start the hub.

```sh tested
$ openhal init
$ openhal file confirm ~/.openhal/devices/demo-fan.hal.yaml
$ openhald &
```

Ask for more than the fan allows. The hub refuses before anything moves.

```sh tested
$ openhal write demo-fan.fan_speed 150 %
blocked above_max  Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.
```

Give your AI client its own token and add the MCP server. This is Claude Code. The [MCP guide](../../../../docs/interfaces/MCP.md) covers Claude Desktop, Cursor and others.

```sh tested
$ openhal token create --agent --scope control_low --name claude | tail -1 > ~/.openhal/claude.token
$ chmod 600 ~/.openhal/claude.token
$ claude mcp add openhal --scope user -- openhal mcp --token-file ~/.openhal/claude.token
```
