# 0012 Humans and agents are different principals with different tokens

## Context

Agents must never approve confirmations, unlock after a stop or loosen limits. The hub has to tell a human from an agent.

## Decision

- Every API call carries a bearer token. Tokens have a kind (`agent` or `human`) and a scope.
- Agent scopes are `read`, `control_low` and `control_medium`. High hazard never has an agent scope. It always needs a human confirmation.
- Human tokens can confirm, reject, unlock after a stop, enable routines, finish a limits interview and sign high hazard routine approvals.
- `openhal init` creates one human token stored in `~/.openhal/human.token` with mode 0600, used by the CLI. The dashboard gets a human session by pairing: the CLI prints a one-time code, and the browser exchanges it for a session cookie bound to localhost.
- `openhal token create --agent --scope control_low` creates agent tokens for MCP clients. `openhal mcp` reads its token from the environment or a file the user points to.
- Optional `confirm.require_tty` (default true) makes `openhal confirm` and `openhal unlock` require an interactive terminal and a typed confirmation phrase, so an agent that can run shell commands as the user can't approve silently through the CLI.

## Consequences

An agent with full shell access as the same user can still read the human token file. The threat model states this. The mitigations are file permissions, the TTY requirement and the dashboard pairing flow.
