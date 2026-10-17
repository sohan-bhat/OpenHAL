# 0006 The driver writer runs through the user's own AI over MCP

## Context

The driver writer reads sketches and manuals and drafts device files. That reading benefits from a language model, but OpenHAL should not require an API key or send a user's documents to a service they did not choose.

## Options considered

1. OpenHAL calls a model API with its own key. Needs a key, adds cost, and sends files to a third party by default.
2. The hub exposes the driver writer as MCP tools and prompts. The user's model (Claude, ChatGPT, Cursor or any MCP client) does the reading and drafting, and the hub does every deterministic step (detection, parsing, probing with read-only commands, validation, the limits interview, the test plan).
3. Option 2, plus an optional direct API key as a fallback for people who use the CLI without an MCP client.

## Decision

Option 3. Static parsing (sketch command extraction, SCPI identification, protocol describe calls) works with no model at all, and the CLI can finish a device file from those results plus the interview. MCP tools (`start_driver_writer`, `propose_device_file`, `request_limits_interview`) let the user's model add what static parsing can't. An `OPENHAL_WRITER_MODEL` setting with a user-provided key is supported but off by default.

## Consequences

- Nothing proposed by a model can set a limit. `propose_device_file` stores a draft with every limit marked `suggested`. Only the human side of the interview (CLI prompt or dashboard form with a human session) confirms limits.
- Document text the model reads is returned as delimited data. The hub never follows instructions found in it.
