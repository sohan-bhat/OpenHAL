# 0018 One command, and OpenHAL runs with openhal start

## Context

ADR 0002 named the daemon `openhald`, so a person typed `openhal` for every command and a second name, `openhald`, to run the hub. On 2026-11-01 the owner read "Restart openhald to load the file" in the first-device flow and then "Restart the hub", took the daemon name for a typo and asked for one name, `openhal`, or a new name for the whole project.

## Options considered

1. Keep `openhald`. The owner read the second name as a mistake, so a newcomer would too.
2. Rename the whole project. The name OpenHAL is fine, and only the second command is the problem.
3. One command. `openhal start` runs the hub in the foreground, and `openhald` stays as an alias that no message names.

## Decision

Option 3. This decision replaces the daemon name in ADR 0002 and keeps the rest of ADR 0002.

- `openhal start` runs the hub exactly as `openhald` did, with the same `--host`, `--port` and `--verbose` options, in the foreground until Control and C or SIGTERM.
- `pyproject.toml` keeps the `openhald` entry point, so installed background services and scripts that run `openhald` keep working. No message, page, doc or diagram names `openhald`.
- A message that tells a person to start the hub says "Start OpenHAL with openhal start". Prose that explains how OpenHAL works keeps "the hub" as the name of the process, as in "the hub blocks the request".
- The background service runs `openhal start` with the Python that installed it. A new systemd unit is `openhal.service` and logs go to `openhal.log`. A unit or launchd agent from an earlier install runs `python -m openhal.hub.daemon`, which still runs the hub, and `openhal service install` replaces an old unit with the new one.
- `openhal/_brand.py` holds `START_COMMAND`, `openhal start`, and `DAEMON_ALIAS`, `openhald`, in place of `DAEMON_NAME`.

## Consequences

- The quickstart, the guides, the CLI and MCP references, the architecture diagram and the Inspector's offline message name `openhal start`.
- A hub that runs as `openhal start` and one that runs as `openhald` hold the same lock on the config folder, so the two can never run at once on one folder.
- The alias stays until a major version removes it, and ADR 0002's history stays as written.
