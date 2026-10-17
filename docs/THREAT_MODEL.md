# Threat model

## Assets

1. People and property near connected hardware.
2. The hardware itself.
3. The limits, approvals and audit history that describe what is allowed and what happened.
4. The user's machine and network.

## Actors

| Actor | Trusted? | Reaches OpenHAL through |
|---|---|---|
| The human owner | yes | CLI with human token, dashboard with human session |
| An AI agent the owner connected | no, assumed fallible and possibly manipulated | MCP or API with an agent token |
| Text the agent reads (manuals, sketches, device output, web pages) | no, assumed adversarial | indirectly, through the agent and through device data |
| A device or bridged system | partly, its reports are believed but its text is data | drivers |
| Other software on the LAN | no | network, blocked by default |
| A third-party driver or routine | partly, reviewed code only | runs in the hub process |
| Someone with full access to the owner's account | out of scope | everything |

## Threats and controls

| # | Threat | Control | Test |
|---|---|---|---|
| T1 | Agent writes outside limits | Kernel checks 6 to 12, grants | kernel unit tests, property tests |
| T2 | Agent uses another unit to slip past a limit (degF against degC, rpm against percent) | Convert to channel unit before comparing, reject unconvertible units | redteam/test_units.py |
| T3 | Agent beats a rate limit with many small fast writes or parallel clients | Rate limit measured from last accepted value on a monotonic clock, per-device serialization | redteam/test_rate.py, property tests |
| T4 | Agent approves its own confirmation | Approval needs a human principal, agent tokens can't approve, confirmations re-evaluate | redteam/test_confirm_spoof.py |
| T5 | Agent unlocks after a stop | Unlock needs a human token and a typed phrase in a TTY | redteam/test_stop.py |
| T6 | Agent loosens limits | No API widens limits, session tightening only narrows, file edits record provenance | redteam/test_loosen.py |
| T7 | Prompt injection in device notes, sketch comments, manual PDFs, G-code comments, bridge entity names, device serial output | Delimited data blocks, the hub never interprets text as commands | redteam/test_injection.py |
| T8 | Code path that skips the kernel | Grants, final base methods, AST test for `_write` callers, conformance check | tests/kernel/test_single_path.py |
| T9 | Forged or reused grant | Private constructor guard, single use, binding to device, channel, value, expiry | tests/kernel/test_grants.py |
| T10 | Routine loops that hammer hardware or never stop | Same kernel checks, per-routine rate of runs, max run time, stop pauses routines | redteam/test_routines.py |
| T11 | High hazard device driven by automation | No agent scope covers high hazard, routines need a signed approval bound to their hash | redteam/test_high_hazard.py |
| T12 | Kernel crash leaves a command half-checked | Fail closed on any exception, logged | tests/kernel/test_fail_closed.py |
| T13 | Remote attacker on the LAN | Localhost bind by default, pairing tokens for LAN | tests/hub/test_bind.py |
| T14 | Token theft from disk | Tokens stored hashed in the DB, human token file mode 0600 | tests/hub/test_tokens.py |
| T15 | Audit history edited to hide an event | Append-only triggers, hash chain, `openhal log verify` | tests/audit/test_chain.py |
| T16 | Malformed or malicious device file (huge numbers, NaN limits, recursive expressions, path traversal in fields) | Strict schema, finite checks, expression depth limit, no file paths from device files are opened | tests/spec/test_malicious_files.py |
| T17 | Malicious in-process driver | Conformance suite and review for bundled drivers. Residual risk documented. Out-of-process drivers on the roadmap | redteam/test_malicious_driver.py (proves it can't use the kernel path to reach other devices) |
| T18 | Agent with shell access runs the CLI as the human | `confirm.require_tty`, typed phrases, dashboard pairing. Residual risk documented | manual, documented |
| T19 | Discovery sends a harmful command to an unknown serial device | Only documented read-only identify commands per protocol, short timeouts, skip ports held by other processes | tests/hub/test_discovery_safety.py |
| T20 | Driver writer turns manual text into a dangerous limit | Extracted commands marked unconfirmed, limits only from the human interview | tests/writer/test_interview.py |

## Residual risks we accept for v0.1

- An agent running arbitrary shell commands as the owner can read the human token file and act as the owner. Recommend running agents that have shell access under a different OS user, documented in the security guide.
- A deliberately malicious in-process driver can bypass the kernel for its own transport.
- Physical failure modes (stuck relays, lying sensors, firmware that ignores commands).
- Limits that a human confirmed but that are unsafe.
