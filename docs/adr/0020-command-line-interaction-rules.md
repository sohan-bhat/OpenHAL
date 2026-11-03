# 0020 Every command shows the next step

## Context

On 2026-11-02 the owner ran `openhal`, `openhal limits` and `openhal limits show` and got the full help, "Missing command." and "Missing argument 'target'." in a red box. The owner wrote "great ui, poor interaction design choices the user doesnt know what to do. adding more text in the --help doesnt fix anything".

A person who doesn't know a device id or a command can't use an error that names only the missing word, so the CLI needs rules that every command follows, and every step that only a person may take keeps its safety rules.

## Options considered

1. Longer help text. The owner ruled the option out.
2. A full screen terminal app for every task. A script or an agent can't drive one, and the plain commands would still end in errors.
3. A few rules for every command, a picker of the real choices at a terminal and an exact error everywhere else.

## Decision

Option 3. Every command follows these rules.

- A bare command does the common thing. A group shows the most useful view for its state, such as every limit for `openhal limits` and the pending requests for `openhal confirm`, and ends with one real command to copy, built from the person's own devices and ids.
- A bare `openhal` shows whether the config folder is set up, whether OpenHAL runs, which devices are connected and how many requests are held for a person, then the next steps for that state. `openhal init` comes first when nothing is set up, `openhal start` when OpenHAL is off, and the commands for a running hub after that. `openhal --help` keeps the full list.
- At an interactive terminal, a left-out device, channel, request id, routine, run, token, library name, driver or device file opens a picker of the real values. Arrow keys move, typing filters the list and Enter picks. A left-out value is a typed answer with the limits in view, and an answer that can't stand is typed again. `openhal limits set` alone walks through the device, the channel and the new value.
- Without a terminal, or with `--json`, no command prompts. The error names what is missing, lists up to 10 valid values from the hub and shows one exact command to copy. The exit codes stay as they were, so a missing argument still exits 2.
- A mistyped command gets the closest command, and a mistyped device, routine, request, run or token id gets the closest real ids.
- Person-only steps keep every rule from ADR 0012 and spec Part 7. A picker may choose which pending request, routine or token a step works on, but the typed phrase is still required, `confirm.require_tty` still applies, and the picker for a person-only step shows only with the human token.
- Pickers come from questionary on prompt_toolkit (docs/DEPENDENCIES.md) in plain bold with no colors. A picker reads the keys from the terminal device behind standard input, because kqueue on macOS returns an error for /dev/tty. The typed phrases still come from /dev/tty.

## Consequences

- openhal/cli/_pick.py holds the picker and the typed answer, and openhal/cli/_choices.py holds the missing-argument error and the nearest ids. A new command with an id argument passes its list of real values to `_choices.need` and gets both behaviors.
- Arguments that a picker can fill are optional in the help, shown as `[TARGET]`.
- Tests drive the pickers through a real pseudo-terminal (tests/terminal.py), and each terminal-free error is tested with its values and its command.
