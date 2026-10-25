# Security policy

OpenHAL lets AI agents control hardware, so a security bug can be a physical safety bug. This page says which versions get fixes, how to report a problem privately, what counts as a safety issue and what happens after a report.

If something is moving, heating or switching right now and should not be, run `uv run openhal stop` or cut its power first. Report after.

## Supported versions

OpenHAL has no release yet. Fixes land on `main`.

| Version | Supported |
|---|---|
| `main` (0.1.0.dev0) | yes |
| anything older | no |

Once releases start, the newest release and `main` get security fixes.

## Report a problem privately

Use GitHub private vulnerability reporting. Never open a public issue, discussion or pull request for a security or safety problem.

1. Open https://github.com/sohan-bhat/OpenHAL/security/advisories/new, or choose **Security**, then **Report a vulnerability** on the repository page.
2. Describe the problem and the exact steps, or attach a test that shows it.
3. Give the version from `uv run openhal --version`, the commit from `git rev-parse --short HEAD`, the operating system, and the driver and device file involved.
4. Say whether real hardware was involved and whether anything moved, heated or switched.

Only the maintainers can read the report. If the form is missing, open an issue titled "Security contact request" with no details, and a maintainer will open a private advisory and invite you to it.

A failing test is the best report. Tests in the style of `tests/redteam/` and `tests/review_safety/` run the real kernel against simulators. Test only on simulators, mocks or hardware you own.

## What counts as a safety issue

Anything that lets a command past the safety kernel is a safety issue. These are examples, and each gets the highest priority.

- A command reaches a driver's `_write`, `_action` or protocol code without a grant the kernel issued for that exact command.
- A command the kernel should block reaches a device through any path, including MCP, the hub protocol, REST, the CLI, the Python client, routines, the Inspector and the driver writer.
- A limit gets wider without a person editing the device file, or a file loads writable while a limit is unconfirmed or suggested.
- An agent token approves a confirmation, lifts a stop, enables a routine or drives a high hazard device.
- A stop leaves a device out of its safe state without reporting it, or a command lands after a stop.
- Text from a device, a manual, a sketch or a bridge changes a limit, approves a request or starts a command.
- An entry in the audit log changes and `openhal log --verify` doesn't report it.
- The kernel fails open, stalls, or decides differently for the same state and command.

Other security problems are in scope too. Examples are reaching the hub from another machine while `api.allow_lan` is false, stealing or reusing a token, opening a path named in a device file, and a crash or hang that a client or a device can trigger.

## Out of scope

[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) lists these as residual risks. A report that makes one of them easier to exploit is still welcome.

- Limits a person confirmed that are unsafe.
- A device that ignores commands, or a sensor that reports wrong values.
- A deliberately malicious in-process driver (T17).
- An agent with shell access that runs the CLI as the owner (T18).
- Someone with full control of the owner's account.

Bugs in a device's own firmware or a vendor's service belong with that vendor. OpenHAL is not a substitute for e-stops, enclosures, hardware interlocks or certified safety systems ([docs/SAFETY.md](docs/SAFETY.md)).

## After a report

These are target times.

1. **Acknowledge** within 3 working days.
2. **Assess** within 10 working days. The maintainers reproduce the problem on a simulator or mock and rate it. A safety issue is rated high or critical.
3. **Fix** in the advisory's private fork, with a regression test in `tests/redteam/` or `tests/review_safety/`. A new kind of threat gets a row in docs/THREAT_MODEL.md.
4. **Release** the fix on `main`, and in a release once there are releases. Publish the advisory with a CVE through GitHub and credit the reporter, unless they ask not to be named.
5. **Disclose** when the fix is out, or 90 days after the report, whichever comes first, unless the reporter and the maintainers agree on another date.

While a fix is pending, the advisory says how to stay safe, for example by keeping a device file read-only or running `uv run openhal stop`.
