# Brief: safety red team (Part 7.2)

Read docs/agents/COMMON.md first, then docs/SAFETY.md, docs/THREAT_MODEL.md, docs/adr/0004 (grants), docs/adr/0015 and spec/2026-10-24/safety.md. Then read the code you attack: openhal/kernel/, openhal/drivers/base.py, openhal/hub/, openhal/protocol/, openhal/mcp/, openhal/routines/ and openhal/writer/.

## Goal

Try to make OpenHAL execute a write or action it must refuse, through every interface. Every attempt becomes a test in `tests/redteam/` that asserts the attempt is blocked. Write up the results in `docs/SAFETY-REPORT.md`.

## Attacks to cover, at minimum

1. **Bypass through every interface.** That means the JSON-RPC protocol (WebSocket and stdio), REST, MCP tools, the CLI, the Python client, routines (YAML and Python), the driver writer (propose, answers, finish) and the Inspector's REST routes. Use each one as an agent to try a write above a limit, an approve, an unlock and a limit loosening.
2. **Units.** Malformed units, unit conversion tricks (degF to exceed a degC limit, mA versus A, percent versus fraction, kelvin offsets, prefixes like `1e3 m%`), NaN, infinity, huge exponents, negative zero, unicode digits and lookalike characters.
3. **Rate limits.** Rapid sequences, alternating values, many small steps, and concurrent clients racing the same channel.
4. **Concurrency.** Writes racing a stop, a stop racing an unlock, two clients approving the same request, and a request approved after it expires.
5. **Prompt injection as data.** Instructions hidden in device notes, sketch comments, a manual's text, G-code comments, Home Assistant entity names, a device's own serial output, MQTT payloads, BLE names and MCP tool results. Nothing read from any of them may change limits, approve requests or trigger actions, and the text must reach agents only inside data blocks.
6. **Malicious drivers.** A driver that calls `_write` directly, reuses or forges a Grant, keeps a Grant for later, or writes to another device. The single-path guarantee from ADR 0004 must hold.
7. **Routines.** Loops, a routine that rewrites itself to dodge approval, a routine touching a high hazard device without approval, and a routine running after a stop.
8. **Confirmation spoofing.** An agent posing as a person, a forged session cookie, a CSRF attempt on the Inspector's REST routes, a confirmation phrase arriving through stdin or a pipe, and a principal reading or approving another principal's requests.
9. **Protocol edge cases.** Messages before initialize, batch requests, huge payloads, deeply nested JSON, duplicate ids, a method above the declared conformance level, and tokens leaking into the message log.
10. **Fail-safe behavior.** Make the kernel raise inside a check. The command must be blocked and logged, never allowed through.

## Rules

- Never change openhal/ code. When an attack gets through, write the test so it fails (mark it `xfail(strict=True)` with the finding id), describe it in the report, and keep going. The orchestrator fixes the kernel, so you don't need to.
- Mocks and simulators only.
- No comments in code, docstrings only.

## Deliverables

- `tests/redteam/`. One module per attack family. Every test must pass, except strict xfails for real findings.
- `docs/SAFETY-REPORT.md`. Every attempt with its interface, its expected result and its actual result, plus findings ranked by severity, each with a proposed fix.

## Files you own

tests/redteam/ and docs/SAFETY-REPORT.md.
