# Brief: a new user's first device takes one guided step, with no file editing

Read docs/agents/COMMON.md first, then docs/SAFETY.md, docs/adr/0006 and 0012 (the driver writer and typed phrases), docs/DESIGN.md (The Inspector, Copy voice, Banned), openhal/cli/init_cmd.py, openhal/cli/file_confirm_cmd.py, openhal/cli/_tty.py, openhal/cli/writer_cmd.py, openhal/writer/ (engine.py and interview.py), openhal/service/devices.py, the hub's writer routes, dashboard/src/views/Device.svelte and Writer.svelte, and the tests for each.

## What the owner said

On 2026-11-01 the owner plugged a bare ESP8266 into a Mac and went through the first device by hand. `openhal init` found the board and wrote a read-only device file from the board's own description, and then confirming that file meant deleting `suggested: true` lines with sed and running `openhal file confirm` in a separate terminal, which also crashed on macOS (fixed in 414c0f4). The confirm message also said "Restart openhald to load the file", which the owner read as a typo. The owner wrote, word for word.

> my concern is if a new user comes up and uses this self hosted mcp i dont want them to go through this annoying process

## What must not change

A person answers every limit of a device once before an agent can change anything on the device. Every answer comes from the human principal, the typed phrase comes from a real terminal while `confirm.require_tty` is true or from the Inspector's signed-in human session, and the confirmation stays bound to the hash of the limits. An agent, a script or an agent token can never answer a limit, type the phrase or mark a limit checked. Never weaken a safety requirement (Part 7) to make a step shorter or a test pass.

## Goal

1. **One guided step in the terminal.** When `openhal init` finds a device described by the device or a library file with suggested limits, init asks whether to set the limits now, then walks the same limits interview the driver writer uses. Each question shows the channel, its unit and the suggested value as the default, Enter keeps the suggestion and a typed value replaces it, values outside what the device reports are refused with the reason, and the person types `confirm` once at the end. The file is saved confirmed and writable with no hand editing. Declining keeps today's behavior, a read-only file.
2. **The same for an existing file.** `openhal file confirm PATH` on a file that still has suggested limits runs the same interview inline instead of failing with "Answer the limits interview, or edit each one".
3. **The same in the Inspector.** A read-only device whose limits are suggested shows a "Review limits" action on its device page in the Inspector, which opens the existing limits interview from the Writer view for that file, answered in the human session, with the typed phrase at the end. One implementation of the interview serves the CLI, the hub and the Inspector.
4. **No restart.** After a confirm, from init, `openhal file confirm` or the Inspector, the running hub loads the confirmed file on its own, and the message says the device is now writable. Today the message tells the person to restart the hub. Keep the typed phrase prompt from openhal/cli/_tty.py, which says what to type, that anything else cancels, and waits after a mark on its own line.
5. **Plain words.** Each question is one short sentence a newcomer understands, such as "brightness, in percent. The most an agent may set. Suggested 100." Follow the copy rules in COMMON.md and run the humanizer skill over every new string.
6. **Docs.** Update docs/QUICKSTART.md, the website's quickstart and install pages and the docs for `openhal init` and `openhal file confirm` so the first device reads as one guided step. Propose DESIGN.md text in your report and don't edit DESIGN.md.

Load and use every installed skill that fits, at least humanizer, frontend-design:frontend-design, design-taste-frontend, web-design-guidelines, ui-ux-pro-max:ui-styling, playwright-cli and chrome-devtools-mcp:a11y-debugging. List in your report what you used and for what.

## Gates

Run Playwright and pytest one at a time, with at most 3 Playwright workers, and use ports 4441 to 4449 only. The machine is sometimes under heavy load, so rerun a failure alone before you treat it as real.

- The full gates in COMMON.md, `uv run pytest`, ruff, ruff format and mypy.
- Tests that drive the terminal interview through a real pseudo-terminal, as tests/interfaces/test_tty.py does, for init and for `openhal file confirm`, including Enter to keep a suggestion, a typed value, a value outside the device's range and a wrong phrase.
- Tests that an agent token, a script with no terminal and a `--phrase` while `require_tty` is true can't answer the interview or confirm, through the CLI, the hub routes and the Inspector.
- The Inspector's build, vitest and its end-to-end and axe tests in Chromium and Firefox for the new action, with axe at 0 violations in both themes.
- `pnpm build` and the affected Playwright specs on the website for the docs you change.
- Screenshots of the Inspector's Review limits flow at 1440 and 390 px in light and dark, saved by absolute path to /Users/sohanb/code/projects/openhal/qa/after/setup-1/. Look at every one before you report.

## Files you own

openhal/cli/, openhal/writer/, openhal/service/devices.py, the hub's writer and device file routes, dashboard/, openhal/hub/static/ (rebuild and commit the bundle last), docs/QUICKSTART.md, the website's quickstart, install and CLI pages, and their tests.

## Not yours

openhal/kernel/, openhal/drivers/ (the orchestrator is changing the openhal-firmware driver at the same time), firmware/, spec/, design/tokens.css, docs/DESIGN.md (propose) and every other website page.
